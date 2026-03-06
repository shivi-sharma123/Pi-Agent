#!/usr/bin/env python3
"""
Network Partition Chaos Scenario
==================================
Adds artificial latency and packet loss to the payment-service container to
simulate intermittent network degradation / partial partition.
"""

from __future__ import annotations

import logging
import time

from scripts.chaos.injector import add_network_latency, drop_network_packets, clear_network_latency

logger = logging.getLogger(__name__)

TARGET_CONTAINER = "sre-agent-payment-service-1"
SCENARIO_ID = "network_partition"
DESCRIPTION = "Injects network latency and packet loss into the payment-service"


def run(latency_ms: int = 300, jitter_ms: int = 100, loss_percent: int = 20) -> dict:
    logger.warning(
        "[CHAOS:network_partition] Starting — %dms±%dms latency + %d%% loss on '%s'",
        latency_ms, jitter_ms, loss_percent, TARGET_CONTAINER,
    )
    start = time.time()
    add_network_latency(TARGET_CONTAINER, latency_ms=latency_ms, jitter_ms=jitter_ms)
    drop_network_packets(TARGET_CONTAINER, loss_percent=loss_percent)
    return {
        "scenario_id": SCENARIO_ID,
        "target": TARGET_CONTAINER,
        "injected_at": start,
        "parameters": {
            "latency_ms": latency_ms,
            "jitter_ms": jitter_ms,
            "loss_percent": loss_percent,
        },
    }


def cleanup() -> None:
    try:
        clear_network_latency(TARGET_CONTAINER)
        logger.info("[CHAOS:network_partition] Network rules cleared on '%s'", TARGET_CONTAINER)
    except Exception as e:
        logger.error("[CHAOS:network_partition] Cleanup failed: %s", e)
