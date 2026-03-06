#!/usr/bin/env python3
"""
Memory Leak Chaos Scenario
===========================
Gradually increases memory usage inside the user-service container to simulate
a memory leak, then waits for the SRE agent swarm to detect and remediate it.
"""

from __future__ import annotations

import logging
import time

from scripts.chaos.injector import stress_memory, kill_container, restart_container

logger = logging.getLogger(__name__)

# The service container to target (matches docker-compose service name)
TARGET_CONTAINER = "sre-agent-user-service-1"

SCENARIO_ID = "memory_leak"
DESCRIPTION = "Simulates a gradual memory leak in the user-service container"


def run(duration_seconds: int = 120, mb: int = 600) -> dict:
    """
    Inject a memory leak and return metadata that the runner can log.

    Args:
        duration_seconds: How long to hold the memory pressure.
        mb:               Megabytes to allocate inside the container.
    """
    logger.warning(
        "[CHAOS:memory_leak] Starting — allocating %d MiB in '%s' for %ds",
        mb, TARGET_CONTAINER, duration_seconds,
    )
    start = time.time()
    stress_memory(TARGET_CONTAINER, mb=mb, duration_seconds=duration_seconds)
    return {
        "scenario_id": SCENARIO_ID,
        "target": TARGET_CONTAINER,
        "injected_at": start,
        "parameters": {"mb": mb, "duration_seconds": duration_seconds},
    }


def cleanup() -> None:
    """Ensure the container is running again after the test."""
    try:
        restart_container(TARGET_CONTAINER)
        logger.info("[CHAOS:memory_leak] Cleanup — restarted '%s'", TARGET_CONTAINER)
    except Exception as e:
        logger.error("[CHAOS:memory_leak] Cleanup failed: %s", e)
