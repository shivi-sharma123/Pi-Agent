"""Health and metrics endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from api.deps import _engine, _nats_client
from api.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Check API health with dependency status."""
    db_ok = False
    nats_ok = False

    try:
        async with _engine.connect() as conn:
            await conn.execute(
                __import__("sqlalchemy").text("SELECT 1")
            )
            db_ok = True
    except Exception:
        pass

    if _nats_client and _nats_client.is_connected:
        nats_ok = True

    status = "healthy" if (db_ok and nats_ok) else "degraded"
    return HealthResponse(
        status=status,
        service="dashboard-api",
        nats_connected=nats_ok,
        db_connected=db_ok,
    )


@router.get("/metrics")
async def metrics():
    """Placeholder for Prometheus metrics endpoint."""
    return {"status": "ok"}
