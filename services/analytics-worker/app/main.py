"""
Analytics Worker — NATS event consumer + Redis aggregation.

Subscribes to:
  orders.created       → increment order counter, accumulate revenue
  payments.completed   → track successful payment metrics
  payments.failed      → track failure rate

Publishes every 60s:
  analytics.summary    → JSON with rolling metrics

Exposes:
  GET /health   → liveness probe
  GET /metrics  → Prometheus metrics
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from datetime import datetime

import nats
import redis.asyncio as aioredis
from fastapi import FastAPI, Response
from prometheus_client import Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST
import uvicorn

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
NATS_URL = os.getenv("NATS_URL", "nats://localhost:4222")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/2")
PUBLISH_INTERVAL = int(os.getenv("ANALYTICS_PUBLISH_INTERVAL", "60"))
PORT = int(os.getenv("PORT", "8009"))

# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------
ORDERS_TOTAL = Counter("analytics_orders_total", "Total orders seen by analytics worker")
REVENUE_TOTAL = Counter("analytics_revenue_total", "Total revenue accumulated (USD cents)")
PAYMENTS_COMPLETED = Counter("analytics_payments_completed_total", "Successful payments")
PAYMENTS_FAILED = Counter("analytics_payments_failed_total", "Failed payments")
NATS_EVENTS = Counter("analytics_nats_events_total", "Events consumed from NATS", ["subject"])

# ---------------------------------------------------------------------------
# Redis client
# ---------------------------------------------------------------------------
_redis: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    return _redis


# ---------------------------------------------------------------------------
# Event handlers (write to Redis counters)
# ---------------------------------------------------------------------------

async def handle_order_created(data: dict) -> None:
    """Increment order count and accumulate revenue for the current minute."""
    r = await get_redis()
    minute_key = datetime.utcnow().strftime("analytics:orders:%Y%m%d%H%M")
    await r.incr(minute_key)
    await r.expire(minute_key, 86400)  # keep 24h of per-minute counters
    ORDERS_TOTAL.inc()

    total = data.get("total", 0)
    if total:
        rev_key = datetime.utcnow().strftime("analytics:revenue:%Y%m%d%H")
        await r.incrbyfloat(rev_key, float(total))
        await r.expire(rev_key, 86400 * 7)  # keep 7 days of hourly revenue
        REVENUE_TOTAL.inc(float(total) * 100)  # store as cents in Prometheus


async def handle_payment_completed(data: dict) -> None:
    r = await get_redis()
    await r.incr(f"analytics:payments:completed:{datetime.utcnow().strftime('%Y%m%d%H')}")
    PAYMENTS_COMPLETED.inc()


async def handle_payment_failed(data: dict) -> None:
    r = await get_redis()
    await r.incr(f"analytics:payments:failed:{datetime.utcnow().strftime('%Y%m%d%H')}")
    PAYMENTS_FAILED.inc()


HANDLERS = {
    "orders.created": handle_order_created,
    "payments.completed": handle_payment_completed,
    "payments.failed": handle_payment_failed,
}

# ---------------------------------------------------------------------------
# Summary publisher — runs every PUBLISH_INTERVAL seconds
# ---------------------------------------------------------------------------


async def publish_summary(nc: nats.NATS) -> None:
    """Aggregate Redis counters and publish a summary to analytics.summary."""
    r = await get_redis()
    now = datetime.utcnow()
    hour_key = now.strftime("%Y%m%d%H")
    minute_key = now.strftime("%Y%m%d%H%M")

    orders_this_minute = int(await r.get(f"analytics:orders:{minute_key}") or 0)
    orders_this_hour = sum(
        int(v or 0)
        for v in await r.mget(*[
            f"analytics:orders:{now.strftime('%Y%m%d%H')}{m:02d}"
            for m in range(60)
        ])
    )
    revenue_this_hour = float(await r.get(f"analytics:revenue:{hour_key}") or 0)
    payments_completed = int(await r.get(f"analytics:payments:completed:{hour_key}") or 0)
    payments_failed = int(await r.get(f"analytics:payments:failed:{hour_key}") or 0)

    summary = {
        "timestamp": now.isoformat(),
        "window": "last_hour",
        "orders": {"this_minute": orders_this_minute, "this_hour": orders_this_hour},
        "revenue_usd": revenue_this_hour,
        "payments": {
            "completed": payments_completed,
            "failed": payments_failed,
            "success_rate": (
                payments_completed / (payments_completed + payments_failed)
                if (payments_completed + payments_failed) > 0
                else 1.0
            ),
        },
    }

    try:
        js = nc.jetstream()
        await js.publish("analytics.summary", json.dumps(summary).encode())
        print(f"Published analytics summary: orders/hr={orders_this_hour} revenue=${revenue_this_hour:.2f}")
    except Exception as exc:
        print(f"WARN: Failed to publish analytics.summary: {exc}")


# ---------------------------------------------------------------------------
# NATS consumer loop
# ---------------------------------------------------------------------------

async def nats_consumer() -> None:
    print(f"Analytics worker connecting to NATS at {NATS_URL}...")
    nc = await nats.connect(NATS_URL, max_reconnect_attempts=-1)
    js = nc.jetstream()

    for subject, handler in HANDLERS.items():
        async def message_cb(msg, _handler=handler, _subject=subject):
            NATS_EVENTS.labels(subject=_subject).inc()
            try:
                data = json.loads(msg.data.decode())
                await _handler(data)
                if hasattr(msg, "ack"):
                    await msg.ack()
            except Exception as exc:
                print(f"WARN: analytics handler error for {_subject}: {exc}")

        try:
            await js.subscribe(
                subject,
                durable=f"analytics-{subject.replace('.', '-')}",
                cb=message_cb,
                manual_ack=True,
            )
        except Exception:
            await nc.subscribe(subject, cb=message_cb)

    print(f"Analytics worker listening on: {list(HANDLERS.keys())}")

    # Periodic summary publisher
    while True:
        await asyncio.sleep(PUBLISH_INTERVAL)
        await publish_summary(nc)


# ---------------------------------------------------------------------------
# Health HTTP sidecar
# ---------------------------------------------------------------------------

api = FastAPI(title="Analytics Worker", version="0.2.0")


@api.get("/health")
async def health():
    redis_ok = False
    try:
        r = await get_redis()
        await r.ping()
        redis_ok = True
    except Exception:
        pass
    return {
        "status": "healthy" if redis_ok else "degraded",
        "service": "analytics-worker",
        "version": "0.2.0",
        "dependencies": {"redis": "ok" if redis_ok else "down"},
    }


@api.get("/metrics")
async def metrics_endpoint():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def run_http_server() -> None:
    uvicorn.run(api, host="0.0.0.0", port=PORT, log_level="warning")


def main() -> None:
    threading.Thread(target=run_http_server, daemon=True).start()
    print(f"Analytics health server on :{PORT}")
    asyncio.run(nats_consumer())


if __name__ == "__main__":
    main()
