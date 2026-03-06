"""
RunbookOptimizer
================
Maintains per-runbook performance counters in PostgreSQL and exposes a
summary view. This enables the system to surface which runbooks are working
well and which might need human review.

Database table: ``runbook_stats``  (created automatically on first use)

| Column          | Type    | Notes                                         |
|-----------------|---------|-----------------------------------------------|
| runbook_id      | TEXT PK | e.g. "runbook_memory_leak"                    |
| total_attempts  | INT     | Total times the runbook was executed          |
| successes       | INT     | Executions that passed VerificationEngine     |
| total_mttr_sec  | BIGINT  | Cumulative MTTR for computing average         |
| last_updated_at | TEXT    | ISO-8601 timestamp                            |
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS runbook_stats (
    runbook_id       TEXT PRIMARY KEY,
    total_attempts   INTEGER NOT NULL DEFAULT 0,
    successes        INTEGER NOT NULL DEFAULT 0,
    total_mttr_sec   BIGINT  NOT NULL DEFAULT 0,
    last_updated_at  TEXT    NOT NULL DEFAULT ''
);
"""


class RunbookOptimizer:
    """
    Async PostgreSQL-backed runbook performance tracker.

    Usage::

        optimizer = RunbookOptimizer(db_url="postgresql+asyncpg://...")
        await optimizer.initialise()
        await optimizer.record(runbook_id="runbook_memory_leak", outcome="success", mttr_seconds=90)
        stats = await optimizer.get_all_stats()
    """

    def __init__(self, db_url: str) -> None:
        self._engine = create_async_engine(db_url, echo=False, pool_size=3)
        self._session_factory = sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False
        )

    async def initialise(self) -> None:
        """Create the runbook_stats table if it doesn't exist."""
        async with self._engine.begin() as conn:
            await conn.execute(text(CREATE_TABLE_SQL))
        logger.info("RunbookOptimizer initialised — runbook_stats table ready.")

    async def record(
        self,
        runbook_id: str,
        outcome: str,
        mttr_seconds: int = 0,
    ) -> None:
        """
        Upsert a remediation result into the stats table.

        Args:
            runbook_id:    Identifier matching runbook YAML filename stem.
            outcome:       ``"success"`` | ``"failed_verification"`` | ``"failed_execution"``
            mttr_seconds:  Time from incident detected to remediation verified.
        """
        success_delta = 1 if outcome == "success" else 0
        now = datetime.now(timezone.utc).isoformat()

        upsert_sql = text("""
            INSERT INTO runbook_stats
                (runbook_id, total_attempts, successes, total_mttr_sec, last_updated_at)
            VALUES
                (:runbook_id, 1, :success_delta, :mttr, :now)
            ON CONFLICT (runbook_id) DO UPDATE SET
                total_attempts  = runbook_stats.total_attempts + 1,
                successes       = runbook_stats.successes + :success_delta,
                total_mttr_sec  = runbook_stats.total_mttr_sec + :mttr,
                last_updated_at = :now;
        """)

        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(
                    upsert_sql,
                    {
                        "runbook_id": runbook_id,
                        "success_delta": success_delta,
                        "mttr": mttr_seconds,
                        "now": now,
                    },
                )
        logger.info(
            "Recorded runbook '%s' outcome='%s' mttr=%ds",
            runbook_id, outcome, mttr_seconds,
        )

    async def get_stats(self, runbook_id: str) -> dict[str, Any] | None:
        """Return performance stats for a single runbook or None if not tracked."""
        async with self._session_factory() as session:
            result = await session.execute(
                text("SELECT * FROM runbook_stats WHERE runbook_id = :rid"),
                {"rid": runbook_id},
            )
            row = result.mappings().first()
            if row is None:
                return None
            return self._row_to_dict(dict(row))

    async def get_all_stats(self) -> list[dict[str, Any]]:
        """Return a sorted list of all runbooks by success rate (descending)."""
        async with self._session_factory() as session:
            result = await session.execute(
                text("SELECT * FROM runbook_stats ORDER BY successes::float / GREATEST(total_attempts,1) DESC"),
            )
            return [self._row_to_dict(dict(row)) for row in result.mappings()]

    # ───────────────────────────────────────────────────────────────────────────
    # Helpers
    # ───────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _row_to_dict(row: dict) -> dict[str, Any]:
        total = row["total_attempts"] or 0
        success = row["successes"] or 0
        mttr_total = row["total_mttr_sec"] or 0
        return {
            "runbook_id": row["runbook_id"],
            "total_attempts": total,
            "successes": success,
            "success_rate": round(success / total, 3) if total > 0 else 0.0,
            "avg_mttr_seconds": int(mttr_total / total) if total > 0 else 0,
            "last_updated_at": row["last_updated_at"],
        }
