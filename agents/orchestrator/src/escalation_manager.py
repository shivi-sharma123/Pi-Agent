"""
EscalationManager — handles timeouts, retries, and escalation to humans.

Scans active FSMs for timeout conditions and either retries the current
state or escalates to a human operator.
"""

from __future__ import annotations

import logging
from typing import Any

from shared.messaging.nats_client import NATSClient, build_message
from shared.messaging.subjects import HUMAN_APPROVALS, INCIDENTS_LIFECYCLE

from incident_fsm import IncidentFSM

logger = logging.getLogger(__name__)


class EscalationManager:
    """Checks timeouts on active FSMs and triggers retries or escalation."""

    def __init__(self, nats: NATSClient) -> None:
        self.nats = nats

    async def check_timeouts(self, active_fsms: dict[str, IncidentFSM]) -> list[str]:
        """
        Scan all active FSMs for timeouts.
        Returns list of incident IDs that were escalated.
        """
        escalated: list[str] = []
        for incident_id, fsm in list(active_fsms.items()):
            if fsm.is_terminal:
                continue
            if not fsm.is_timed_out():
                continue

            if fsm.should_retry():
                await self._retry_current_state(fsm)
            else:
                await self._escalate_to_human(incident_id, fsm)
                escalated.append(incident_id)

        return escalated

    async def _retry_current_state(self, fsm: IncidentFSM) -> None:
        """Re-publish command for the current state and increment retry counter."""
        count = fsm.increment_retry()
        logger.warning(
            "Retrying state %s for incident %s (attempt %d)",
            fsm.state, fsm.incident_id, count,
        )

        msg = build_message(
            source_agent="orchestrator",
            target_agent="*",
            message_type="state_retry",
            payload={
                "incident_id": fsm.incident_id,
                "state": fsm.state,
                "retry_count": count,
            },
            correlation_id=fsm.incident_id,
            priority=1,
        )
        await self.nats.publish(INCIDENTS_LIFECYCLE, msg)

    async def _escalate_to_human(self, incident_id: str, fsm: IncidentFSM) -> None:
        """Escalate to human operator when retries are exhausted."""
        logger.error(
            "Escalating incident %s to human — state %s timed out after max retries",
            incident_id, fsm.state,
        )

        msg = build_message(
            source_agent="orchestrator",
            target_agent="human",
            message_type="escalation",
            payload={
                "incident_id": incident_id,
                "current_state": fsm.state,
                "retry_count": fsm.retry_count,
                "reason": f"State '{fsm.state}' timed out after {fsm.retry_count} retries",
            },
            correlation_id=incident_id,
            priority=0,  # critical
        )
        await self.nats.publish(HUMAN_APPROVALS, msg)

    async def handle_dead_agent(
        self,
        agent_id: str,
        agent_type: str,
        active_fsms: dict[str, IncidentFSM],
    ) -> None:
        """
        When an agent dies, check if any incidents are waiting on that agent type
        and escalate them.
        """
        # Map agent types to states that depend on them
        agent_state_map: dict[str, set[str]] = {
            "agents.diagnoser": {"diagnosing"},
            "agents.remediator": {"executing"},
            "agents.safety": {"safety_review"},
            "agents.observer": {"detecting"},
        }

        affected_states = agent_state_map.get(agent_type, set())
        for incident_id, fsm in active_fsms.items():
            if fsm.state in affected_states:
                logger.warning(
                    "Agent %s died while incident %s is in %s — escalating",
                    agent_id, incident_id, fsm.state,
                )
                await self._escalate_to_human(incident_id, fsm)
