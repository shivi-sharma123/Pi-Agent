"""
Async SQLAlchemy engine and session factory.

Usage::

    from shared.db.session import get_session

    async with get_session() as session:
        result = await session.execute(select(Incident))
        incidents = result.scalars().all()
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from shared.config.settings import settings

# ---------------------------------------------------------------------------
# Engine — one per process, created lazily
# ---------------------------------------------------------------------------

_engine = create_async_engine(
    settings.agents_db_url,
    echo=settings.environment == "development",  # SQL logging in dev only
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,   # detect stale connections
)

# Session factory — creates new sessions from the shared engine
_SessionFactory = async_sessionmaker(
    bind=_engine,
    class_=AsyncSession,
    expire_on_commit=False,  # avoid lazy-loading issues after commit
)


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Async context manager that yields a database session.

    Automatically commits on clean exit and rolls back on exception.

    Example::

        async with get_session() as session:
            session.add(incident)
            # commit happens automatically on exit
    """
    async with _SessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    """
    Dispose of the engine connection pool.

    Call during application shutdown to cleanly close all DB connections.
    """
    await _engine.dispose()
