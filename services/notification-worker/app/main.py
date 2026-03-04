"""
Notification Worker — NATS event consumer.

Subscribes to:
  orders.created         → order confirmation email/push
  payments.completed     → payment receipt
  payments.failed        → payment failure alert
  inventory.low          → low stock alert (internal)

Exposes:
  GET /health            → liveness probe
  GET /metrics           → Prometheus metrics
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from typing import Any

import nats
from fastapi import FastAPI, Response
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST
import uvicorn


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

NATS_URL = os.getenv("NATS_URL", "nats://localhost:4222")
PORT = int(os.getenv("PORT", "8007"))


# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------

NOTIFICATIONS_SENT = Counter(
    "notifications_sent_total",
    "Total notifications sent",
    ["event_type", "channel"],
)
NATS_MESSAGES_RECEIVED = Counter(
    "nats_messages_received_total",
    "Total NATS messages received",
    ["subject"],
)

# ---------------------------------------------------------------------------
# Notification dispatch (stubs for Phase 2 — real providers in Phase 3)
# ---------------------------------------------------------------------------


def send_email(to: str, subject: str, body: str) -> None:
    """Stub email sender. Phase 3 will wire to SendGrid/SES."""
    print(f"[EMAIL] to={to!r} subject={subject!r} body_len={len(body)}")
    NOTIFICATIONS_SENT.labels(event_type="email", channel="email").inc()


def send_push(user_id: str, title: str, message: str) -> None:
    """Stub push notification. Phase 3 will wire to FCM/APNs."""
    print(f"[PUSH] user_id={user_id!r} title={title!r} message={message!r}")
    NOTIFICATIONS_SENT.labels(event_type="push", channel="push").inc()


def send_slack(channel: str, text: str) -> None:
    """Stub Slack notifier for internal alerts."""
    print(f"[SLACK] channel={channel!r} text={text!r}")
    NOTIFICATIONS_SENT.labels(event_type="slack", channel="slack").inc()


# ---------------------------------------------------------------------------
# Event handlers
# ---------------------------------------------------------------------------


def handle_order_created(data: dict[str, Any]) -> None:
    """Notify customer that their order was placed."""
    order_id = data.get("id", "?")
    user_id = data.get("user_id", "?")
    total = data.get("total", 0)
    send_email(
        to=f"user_{user_id}@example.com",
        subject=f"Order #{order_id} Confirmed",
        body=f"Your order for ${total:.2f} has been placed successfully.",
    )
    send_push(
        user_id=user_id,
        title="Order Confirmed",
        message=f"Order #{order_id} is being processed.",
    )


def handle_payment_completed(data: dict[str, Any]) -> None:
    """Notify customer that their payment was accepted."""
    order_id = data.get("order_id", "?")
    amount = data.get("amount", 0)
    currency = data.get("currency", "USD")
    send_email(
        to="customer@example.com",
        subject=f"Payment Receipt — {currency} {amount:.2f}",
        body=f"Your payment of {currency} {amount:.2f} for order #{order_id} was successful.",
    )


def handle_payment_failed(data: dict[str, Any]) -> None:
    """Notify customer that their payment failed."""
    order_id = data.get("order_id", "?")
    reason = data.get("reason", "unknown")
    send_email(
        to="customer@example.com",
        subject="Payment Failed",
        body=f"Payment for order #{order_id} failed: {reason}. Please try again.",
    )
    send_push(
        user_id="unknown",  # TODO: wire user_id through payment event
        title="Payment Failed",
        message=f"Your payment for order #{order_id} could not be processed.",
    )


def handle_inventory_low(data: dict[str, Any]) -> None:
    """Alert ops team about low stock."""
    product_id = data.get("product_id", "?")
    stock = data.get("stock", 0)
    send_slack(
        channel="#ops-alerts",
        text=f":warning: Low stock alert: product {product_id} has {stock} units remaining.",
    )


HANDLERS = {
    "orders.created": handle_order_created,
    "payments.completed": handle_payment_completed,
    "payments.failed": handle_payment_failed,
    "inventory.low": handle_inventory_low,
}


# ---------------------------------------------------------------------------
# NATS consumer loop
# ---------------------------------------------------------------------------


async def nats_consumer() -> None:
    """Connect to NATS and consume all subscribed subjects."""
    print(f"Connecting to NATS at {NATS_URL}...")
    nc = await nats.connect(NATS_URL, max_reconnect_attempts=-1)
    js = nc.jetstream()

    for subject, handler in HANDLERS.items():
        # Durable push consumer — survives worker restarts
        consumer_name = f"notification-{subject.replace('.', '-')}"
        try:
            sub = await js.subscribe(
                subject,
                durable=consumer_name,
                manual_ack=True,
            )
        except Exception:
            # Subject may not have a JetStream stream — fall back to core NATS
            sub = await nc.subscribe(subject)

        async def message_handler(msg, _handler=handler, _subject=subject):
            NATS_MESSAGES_RECEIVED.labels(subject=_subject).inc()
            try:
                data = json.loads(msg.data.decode())
                _handler(data)
                if hasattr(msg, "ack"):
                    await msg.ack()
            except Exception as exc:
                print(f"WARN: Error handling {_subject}: {exc}")
                if hasattr(msg, "nak"):
                    await msg.nak()

        await sub.unsubscribe(0)  # unlimited messages
        # Re-subscribe with message_handler
        try:
            await js.subscribe(subject, durable=consumer_name, cb=message_handler, manual_ack=True)
        except Exception:
            await nc.subscribe(subject, cb=message_handler)

    print(f"Notification worker listening on: {list(HANDLERS.keys())}")

    # Keep running
    while True:
        await asyncio.sleep(10)


# ---------------------------------------------------------------------------
# Health / metrics HTTP sidecar (FastAPI, same process)
# ---------------------------------------------------------------------------

api = FastAPI(title="Notification Worker", version="0.2.0")


@api.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "notification-worker",
        "version": "0.2.0",
        "subscriptions": list(HANDLERS.keys()),
    }


@api.get("/metrics")
async def metrics_endpoint():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def run_http_server() -> None:
    """Run FastAPI health server in a background thread."""
    uvicorn.run(api, host="0.0.0.0", port=PORT, log_level="warning")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main() -> None:
    # Start HTTP sidecar in background thread
    thread = threading.Thread(target=run_http_server, daemon=True)
    thread.start()
    print(f"Health server running on :{PORT}")

    # Run NATS consumer in main event loop
    asyncio.run(nats_consumer())


if __name__ == "__main__":
    main()
