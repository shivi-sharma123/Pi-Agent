#!/usr/bin/env python3
"""
Database Overload Chaos Scenario
===================================
Runs heavy SQL queries inside the postgres-agents container to saturate the
connection pool and simulate a DB overload event.
"""

from __future__ import annotations

import logging
import time

import docker

logger = logging.getLogger(__name__)

TARGET_CONTAINER = "sre-agent-postgres-agents-1"
SCENARIO_ID = "database_overload"
DESCRIPTION = "Runs expensive SQL queries to saturate the PostgreSQL connection pool"

# Heavy query that causes a table scan and sort — adjust to match your schema
_HEAVY_QUERY = (
    "SELECT a.id, b.id FROM incidents a CROSS JOIN incidents b "
    "ORDER BY random() LIMIT 100000;"
)
_STRESS_WORKERS = 20  # Parallel psql sessions


def run(duration_seconds: int = 60) -> dict:
    logger.warning(
        "[CHAOS:database_overload] Starting %d parallel heavy queries for %ds",
        _STRESS_WORKERS, duration_seconds,
    )
    start = time.time()
    client = docker.from_env()
    c = client.containers.get(TARGET_CONTAINER)

    # Spawn workers in background
    for _ in range(_STRESS_WORKERS):
        cmd = (
            f"psql -U sre_user -d agents_db -c \"{_HEAVY_QUERY}\""
        )
        c.exec_run(cmd=cmd, detach=True, environment={"PGPASSWORD": "sre_pass"})

    return {
        "scenario_id": SCENARIO_ID,
        "target": TARGET_CONTAINER,
        "injected_at": start,
        "parameters": {"workers": _STRESS_WORKERS, "duration_seconds": duration_seconds},
    }


def cleanup() -> None:
    """Nothing to restore — queries will finish naturally."""
    logger.info("[CHAOS:database_overload] No cleanup required (queries are self-terminating).")
