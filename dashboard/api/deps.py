"""Dependency injection for Dashboard API — DB session + NATS client."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from shared.config.settings import settings
from shared.messaging.nats_client import NATSClient

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
_engine = create_async_engine(
    settings.agents_db_url,
    echo=False,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
)

_SessionFactory = async_sessionmaker(
    bind=_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for database sessions."""
    async with _SessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ---------------------------------------------------------------------------
# NATS
# ---------------------------------------------------------------------------
_nats_client: NATSClient | None = None


async def get_nats() -> NATSClient:
    """Return the shared NATS client singleton."""
    global _nats_client
    if _nats_client is None or not _nats_client.is_connected:
        _nats_client = NATSClient(url=settings.nats_url)
        await _nats_client.connect()
    return _nats_client


async def close_nats() -> None:
    """Close NATS connection on shutdown."""
    global _nats_client
    if _nats_client and _nats_client.is_connected:
        await _nats_client.close()
        _nats_client = None


async def dispose_db() -> None:
    """Dispose DB engine on shutdown."""
    await _engine.dispose()
