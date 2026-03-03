"""
Payment Service — FastAPI application.

Handles payment processing for orders and publishes domain events to NATS.

Endpoints:
  GET  /health             → liveness + DB + NATS check
  POST /payments           → initiate a payment for an order
  GET  /payments/{id}      → get payment by ID
  POST /payments/{id}/refund → request a full refund

NATS events:
  payments.completed       → on successful payment
  payments.failed          → on payment failure
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import Optional

import asyncpg
import nats
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class PaymentCreate(BaseModel):
    order_id: str
    amount: float = Field(..., gt=0)
    currency: str = Field(default="USD", max_length=3)
    method: str = Field(default="card")  # card | bank_transfer | wallet


class PaymentResponse(BaseModel):
    id: str
    order_id: str
    status: str
    amount: float
    currency: str
    method: str
    created_at: str
    updated_at: str
    failure_reason: Optional[str] = None

# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency",
    ["method", "endpoint"],
)
PAYMENTS_TOTAL = Counter("payments_total", "Total payments processed", ["status"])

# ---------------------------------------------------------------------------
# Global clients
# ---------------------------------------------------------------------------

_pg_pool: asyncpg.Pool | None = None
_nc: nats.NATS | None = None

# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise DB pool and NATS connection on startup."""
    global _pg_pool, _nc

    db_url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5434/payments")
    nats_url = os.getenv("NATS_URL", "nats://localhost:4222")

    # PostgreSQL connection pool
    _pg_pool = await asyncpg.create_pool(
        dsn=db_url,
        min_size=2,
        max_size=10,
        command_timeout=10,
    )
    # Bootstrap schema
    await _bootstrap_schema(_pg_pool)

    # NATS (best-effort — non-fatal on failure)
    try:
        _nc = await nats.connect(nats_url, max_reconnect_attempts=5)
    except Exception as exc:
        print(f"WARN: NATS not available — {exc}")

    yield

    if _pg_pool:
        await _pg_pool.close()
    if _nc and not _nc.is_closed:
        await _nc.drain()


async def _bootstrap_schema(pool: asyncpg.Pool) -> None:
    """Create the payments table if it doesn't exist."""
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id             TEXT PRIMARY KEY,
                order_id       TEXT NOT NULL,
                status         TEXT NOT NULL DEFAULT 'pending',
                amount         NUMERIC(12, 2) NOT NULL,
                currency       TEXT NOT NULL DEFAULT 'USD',
                method         TEXT NOT NULL DEFAULT 'card',
                failure_reason TEXT,
                created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_payments_order_id ON payments(order_id);
        """)


# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Payment Service",
    description="Payment processing for the SRE Agent Swarm demo",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def metrics_middleware(request, call_next):
    start = time.monotonic()
    response = await call_next(request)
    elapsed = time.monotonic() - start
    path = request.url.path
    REQUEST_COUNT.labels(method=request.method, endpoint=path, status_code=response.status_code).inc()
    REQUEST_LATENCY.labels(method=request.method, endpoint=path).observe(elapsed)
    return response


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    db_ok = False
    nats_ok = _nc is not None and not _nc.is_closed
    try:
        async with _pg_pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        db_ok = True
    except Exception:
        pass

    status = "healthy" if db_ok else "degraded"
    return {
        "status": status,
        "service": "payment-svc",
        "version": "0.1.0",
        "dependencies": {
            "postgres": "ok" if db_ok else "down",
            "nats": "ok" if nats_ok else "down",
        },
    }


@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/payments", status_code=201, response_model=PaymentResponse)
async def create_payment(payload: PaymentCreate):
    """
    Initiate payment for an order.

    For Phase 1, payment always succeeds.
    In Phase 3+, this will integrate with an actual payment gateway.
    """
    payment_id = str(uuid.uuid4())
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # Simulate brief processing
    await asyncio.sleep(0.1)

    # Mark as completed (Phase 1 always succeeds)
    status = "completed"
    failure_reason = None

    async with _pg_pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO payments (id, order_id, status, amount, currency, method, created_at, updated_at)
               VALUES ($1, $2, $3, $4, $5, $6, NOW(), NOW())""",
            payment_id, payload.order_id, status, payload.amount, payload.currency, payload.method,
        )

    PAYMENTS_TOTAL.labels(status=status).inc()

    # Publish NATS event
    subject = "payments.completed" if status == "completed" else "payments.failed"
    await _publish_event(subject, {
        "payment_id": payment_id,
        "order_id": payload.order_id,
        "amount": payload.amount,
        "currency": payload.currency,
        "status": status,
    })

    return PaymentResponse(
        id=payment_id,
        order_id=payload.order_id,
        status=status,
        amount=payload.amount,
        currency=payload.currency,
        method=payload.method,
        created_at=now,
        updated_at=now,
        failure_reason=failure_reason,
    )


@app.get("/payments/{payment_id}", response_model=PaymentResponse)
async def get_payment(payment_id: str):
    async with _pg_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, order_id, status, amount, currency, method, failure_reason, created_at, updated_at "
            "FROM payments WHERE id=$1",
            payment_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Payment not found")
    return PaymentResponse(
        id=row["id"],
        order_id=row["order_id"],
        status=row["status"],
        amount=float(row["amount"]),
        currency=row["currency"],
        method=row["method"],
        created_at=row["created_at"].isoformat(),
        updated_at=row["updated_at"].isoformat(),
        failure_reason=row["failure_reason"],
    )


@app.post("/payments/{payment_id}/refund", response_model=PaymentResponse)
async def refund_payment(payment_id: str):
    async with _pg_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM payments WHERE id=$1", payment_id)
        if not row:
            raise HTTPException(status_code=404, detail="Payment not found")
        if row["status"] != "completed":
            raise HTTPException(status_code=409, detail="Only completed payments can be refunded")

        await conn.execute(
            "UPDATE payments SET status='refunded', updated_at=NOW() WHERE id=$1",
            payment_id,
        )

    await _publish_event("payments.failed", {
        "payment_id": payment_id,
        "order_id": row["order_id"],
        "reason": "refunded",
    })

    return PaymentResponse(
        id=row["id"], order_id=row["order_id"], status="refunded",
        amount=float(row["amount"]), currency=row["currency"], method=row["method"],
        created_at=row["created_at"].isoformat(), updated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )


async def _publish_event(subject: str, data: dict) -> None:
    """Publish a JSON event to NATS. Silently fails if NATS unavailable."""
    if _nc is None or _nc.is_closed:
        return
    try:
        js = _nc.jetstream()
        await js.publish(subject, json.dumps(data).encode())
    except Exception as exc:
        print(f"WARN: Failed to publish to {subject}: {exc}")
