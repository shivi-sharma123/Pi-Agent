#!/usr/bin/env python3
"""
Chaos Scoring Module
====================
Queries PostgreSQL for incident statistics and computes a letter-grade score
based on MTTD (Mean Time to Detect) and MTTR (Mean Time to Resolve).

Scoring rubric:
  A (≥ 90 pts) — MTTD < 60s AND MTTR < 120s
  B (≥ 70 pts) — MTTD < 120s AND MTTR < 300s
  C (≥ 50 pts) — MTTD < 300s AND MTTR < 600s
  F (< 50 pts) — Undetected or MTTR > 10 min
"""

from __future__ import annotations

import logging
import os
from typing import Any

import psycopg2

logger = logging.getLogger(__name__)

_DB_CONN_STR = os.environ.get(
    "POSTGRES_AGENTS_URL",
    "host=localhost port=5432 dbname=agents_db user=sre_user password=sre_pass",
)


def fetch_incident_stats(since_epoch: float) -> dict[str, Any] | None:
    """
    Query the most recent incident created after *since_epoch* and return
    timing stats.

    Returns a dict with:
      ``created_at_epoch``, ``detected_at``, ``resolved_at``
    or None if no incident was found.
    """
    try:
        conn = psycopg2.connect(_DB_CONN_STR)
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        EXTRACT(EPOCH FROM created_at)        AS created_epoch,
                        EXTRACT(EPOCH FROM state_entered_at)  AS detected_epoch,
                        EXTRACT(EPOCH FROM resolved_at)       AS resolved_epoch
                    FROM incidents
                    WHERE EXTRACT(EPOCH FROM created_at) >= %s
                    ORDER BY created_at DESC
                    LIMIT 1;
                    """,
                    (since_epoch,),
                )
                row = cur.fetchone()
        conn.close()
        if not row:
            return None
        return {
            "created_at": row[0],
            "detected_at": row[1],
            "resolved_at": row[2],
        }
    except Exception as e:
        logger.error("Failed to fetch incident stats: %s", e)
        return None


def score_scenario(mttd: float | None, mttr: float | None) -> str:
    """
    Return a letter grade + numeric score string based on MTTD and MTTR.

    Args:
        mttd: Seconds from chaos injection to first detection.
        mttr: Seconds from chaos injection to full remediation.
    """
    if mttd is None:
        return "F (0) — undetected"

    # Compute component scores (0-50 each)
    mttd_score = _range_score(mttd, best=30, acceptable=120, worst=300)
    mttr_score = _range_score(mttr or 9999, best=90, acceptable=300, worst=600)
    total = mttd_score + mttr_score

    if total >= 90:
        grade = "💚 A"
    elif total >= 70:
        grade = "🟡 B"
    elif total >= 50:
        grade = "🟠 C"
    else:
        grade = "🔴 F"

    return f"{grade} ({int(total)})"


def _range_score(value: float, best: float, acceptable: float, worst: float) -> float:
    """Map a value onto a 0-50 scale where lower is better."""
    if value <= best:
        return 50.0
    if value >= worst:
        return 0.0
    # Linear interpolation between best→acceptable (50→25) and acceptable→worst (25→0)
    if value <= acceptable:
        return 50 - 25 * (value - best) / (acceptable - best)
    return 25 - 25 * (value - acceptable) / (worst - acceptable)
