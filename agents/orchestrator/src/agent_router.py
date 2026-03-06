"""
AgentRouter — tracks live agents via heartbeats and routes messages.

Maintains an in-memory registry of agents, prunes stale entries,
and provides helpers to route work to the correct agent type.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from shared.messaging.nats_client import NATSClient, build_message
from shared.messaging.subjects import DIAGNOSER_REQUESTS, SAFETY_REVIEWS


HEARTBEAT_TIMEOUT_SECONDS = 90


@dataclass
class AgentInfo:
    agent_id: str
    agent_type: str
    hostname: str = ""
    status: str = "healthy"
    last_seen_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metrics: dict[str, Any] = field(default_factory=dict)


class AgentRouter:
    """Tracks agent health and routes messages to available agents."""

    def __init__(self, nats: NATSClient) -> None:
        self.nats = nats
        self.registry: dict[str, AgentInfo] = {}

    def update_agent_status(self, heartbeat_payload: dict) -> AgentInfo:
        """Register or update an agent from a heartbeat message payload."""
        agent_id = heartbeat_payload.get("agent_id", "")
        info = AgentInfo(
            agent_id=agent_id,
            agent_type=heartbeat_payload.get("agent_type", ""),
            hostname=heartbeat_payload.get("hostname", ""),
            status=heartbeat_payload.get("status", "healthy"),
            last_seen_at=datetime.now(timezone.utc),
            metrics={
                "uptime_seconds": heartbeat_payload.get("uptime_seconds", 0),
                "messages_processed": heartbeat_payload.get("messages_processed", 0),
                "errors": heartbeat_payload.get("errors", 0),
            },
        )
        self.registry[agent_id] = info
        return info

    def get_available_agents(self, agent_type: str) -> list[AgentInfo]:
        """Return agents of given type with heartbeat within timeout."""
        now = datetime.now(timezone.utc)
        return [
            info for info in self.registry.values()
            if info.agent_type == agent_type
            and info.status != "dead"
            and (now - info.last_seen_at).total_seconds() <= HEARTBEAT_TIMEOUT_SECONDS
        ]

    def prune_stale_agents(self) -> list[str]:
        """Mark agents as dead if heartbeat is stale. Returns list of dead agent IDs."""
        now = datetime.now(timezone.utc)
        dead: list[str] = []
        for agent_id, info in self.registry.items():
            elapsed = (now - info.last_seen_at).total_seconds()
            if elapsed > HEARTBEAT_TIMEOUT_SECONDS and info.status != "dead":
                info.status = "dead"
                dead.append(agent_id)
        return dead

    async def route_to_diagnoser(
        self,
        source_agent: str,
        correlation_id: str,
        payload: dict,
        context: dict | None = None,
    ) -> None:
        """Publish a diagnosis request to the diagnoser subject."""
        msg = build_message(
            source_agent=source_agent,
            target_agent="agents.diagnoser",
            message_type="diagnosis_request",
            payload=payload,
            correlation_id=correlation_id,
            context=context,
            priority=1,
        )
        await self.nats.publish(DIAGNOSER_REQUESTS, msg)

    async def route_to_remediator(
        self,
        source_agent: str,
        correlation_id: str,
        payload: dict,
        context: dict | None = None,
    ) -> None:
        """Publish a safety review request (remediator listens on diagnoser results)."""
        msg = build_message(
            source_agent=source_agent,
            target_agent="agents.safety",
            message_type="safety_review_request",
            payload=payload,
            correlation_id=correlation_id,
            context=context,
            priority=1,
        )
        await self.nats.publish(SAFETY_REVIEWS, msg)

    def get_all_agents(self) -> list[dict]:
        """Return all agents as dicts for API consumption."""
        now = datetime.now(timezone.utc)
        result = []
        for info in self.registry.values():
            elapsed = (now - info.last_seen_at).total_seconds()
            result.append({
                "agent_id": info.agent_id,
                "agent_type": info.agent_type,
                "hostname": info.hostname,
                "status": info.status if elapsed <= HEARTBEAT_TIMEOUT_SECONDS else "dead",
                "last_seen_at": info.last_seen_at.isoformat(),
                "metrics": info.metrics,
            })
        return result
