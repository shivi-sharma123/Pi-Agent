#!/usr/bin/env python3
"""
CPU Spike Chaos Scenario
=========================
Saturates CPU cores inside the order-service container to simulate CPU-bound
runaway query or computation spike.
"""

from __future__ import annotations

import logging
import time

from scripts.chaos.injector import stress_cpu, restart_container

logger = logging.getLogger(__name__)

TARGET_CONTAINER = "sre-agent-order-service-1"
SCENARIO_ID = "cpu_spike"
DESCRIPTION = "Saturates CPU in the order-service container"


def run(duration_seconds: int = 90, cores: int = 4) -> dict:
    logger.warning(
        "[CHAOS:cpu_spike] Starting — %d cores on '%s' for %ds",
        cores, TARGET_CONTAINER, duration_seconds,
    )
    start = time.time()
    stress_cpu(TARGET_CONTAINER, cores=cores, duration_seconds=duration_seconds)
    return {
        "scenario_id": SCENARIO_ID,
        "target": TARGET_CONTAINER,
        "injected_at": start,
        "parameters": {"cores": cores, "duration_seconds": duration_seconds},
    }


def cleanup() -> None:
    try:
        restart_container(TARGET_CONTAINER)
    except Exception as e:
        logger.error("[CHAOS:cpu_spike] Cleanup failed: %s", e)
