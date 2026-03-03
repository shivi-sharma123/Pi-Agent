#!/usr/bin/env python3
"""
NATS JetStream Initialisation Script.

Creates all streams and durable consumers required by the SRE Agent Swarm.
Run this once after `docker compose up -d` to bootstrap the message bus.

Usage:
    python scripts/init_nats.py [--nats-url nats://localhost:4222]
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import nats
import nats.js.api

# Import stream definitions from shared package
# For standalone usage, define them inline here so the script works without
# a full pip install of the shared package.
STREAMS = {
    "AGENTS": {
        "subjects": [
            "agents.orchestrator.commands",
            "agents.observer.anomalies",
            "agents.diagnoser.requests",
            "agents.diagnoser.results",
            "agents.remediator.proposals",
            "agents.remediator.executions",
            "agents.safety.reviews",
            "agents.safety.decisions",
            "agents.learning.feedback",
            "agents.heartbeat",
        ],
        "max_age": 86_400,       # 24 hours retention
        "max_msgs": 1_000_000,
        "storage": "file",
    },
    "INCIDENTS": {
        "subjects": ["incidents.lifecycle"],
        "max_age": 7 * 86_400,   # 7 days
        "max_msgs": 100_000,
        "storage": "file",
    },
    "HUMAN": {
        "subjects": ["human.approvals", "human.approvals.responses"],
        "max_age": 3_600,         # 1 hour (approvals expire quickly)
        "max_msgs": 10_000,
        "storage": "memory",
    },
    "BUSINESS": {
        "subjects": ["orders.created", "payments.completed", "payments.failed", "inventory.low"],
        "max_age": 3 * 86_400,
        "max_msgs": 500_000,
        "storage": "file",
    },
}


async def create_streams(js: nats.js.JetStreamContext) -> None:
    """Create or update all JetStream streams defined in STREAMS."""
    for stream_name, config in STREAMS.items():
        storage = nats.js.api.StorageType.FILE if config["storage"] == "file" else nats.js.api.StorageType.MEMORY
        stream_config = nats.js.api.StreamConfig(
            name=stream_name,
            subjects=config["subjects"],
            max_age=config["max_age"],
            max_msgs=config["max_msgs"],
            storage=storage,
            num_replicas=1,
            discard=nats.js.api.DiscardPolicy.OLD,
            retention=nats.js.api.RetentionPolicy.LIMITS,
        )
        try:
            # Check if stream already exists by fetching its info
            await js.stream_info(stream_name)
            # If it exists, update it
            await js.update_stream(config=stream_config)
            print(f"  ✓ Updated stream: {stream_name} ({len(config['subjects'])} subjects)")
        except nats.js.errors.NotFoundError:
            # Stream doesn't exist — create it
            await js.add_stream(config=stream_config)
            print(f"  ✓ Created stream: {stream_name} ({len(config['subjects'])} subjects)")


async def main(nats_url: str) -> None:
    print(f"Connecting to NATS at {nats_url}...")
    nc = await nats.connect(nats_url, max_reconnect_attempts=5)
    js = nc.jetstream()

    print("\nCreating JetStream streams:")
    await create_streams(js)

    await nc.drain()
    print("\n✅ NATS JetStream initialisation complete!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Initialise NATS JetStream streams")
    parser.add_argument(
        "--nats-url",
        default="nats://localhost:4222",
        help="NATS connection URL (default: nats://localhost:4222)",
    )
    args = parser.parse_args()

    try:
        asyncio.run(main(args.nats_url))
    except Exception as exc:
        print(f"❌ Error: {exc}", file=sys.stderr)
        sys.exit(1)
