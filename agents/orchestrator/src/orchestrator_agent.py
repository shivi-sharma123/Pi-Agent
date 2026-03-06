"""
OrchestratorAgent — central coordinator for the incident lifecycle.

Subscribes to NATS subjects from all other agents and manages incident
state through the IncidentFSM. Additive design — does not modify any
existing agent code.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy import select

from shared.agents.base import BaseAgent
from shared.db.models import Anomaly, Incident
from shared.db.session import get_session
from shared.messaging.nats_client import build_message
from shared.messaging.schema import AgentMessage
from shared.messaging.subjects import (
    AGENT_HEARTBEAT,
    DIAGNOSER_REQUESTS,
    DIAGNOSER_RESULTS,
    HUMAN_APPROVALS_RESPONSES,
    INCIDENTS_LIFECYCLE,
    OBSERVER_ANOMALIES,
    REMEDIATOR_EXECUTIONS,
    SAFETY_DECISIONS,
)

from agent_router import AgentRouter
from escalation_manager import EscalationManager
from incident_fsm import IncidentFSM
from timeline_builder import add_event, generate_postmortem

logger = logging.getLogger(__name__)


class OrchestratorAgent(BaseAgent):
    """Central coordinator that ties all agents together."""

    agent_type = "agents.orchestrator"

    def __init__(self, nats_url: str | None = None) -> None:
        super().__init__()
        self.router = AgentRouter(self.nats)
        self.escalation = EscalationManager(self.nats)
        self.active_fsms: Dict[str, IncidentFSM] = {}
        self._check_interval = 10  # seconds between timeout checks

    async def setup(self) -> None:
        # Subscribe to all relevant subjects
        await self.nats.subscribe(
            OBSERVER_ANOMALIES,
            handler=self._handle_anomaly,
            durable="orchestrator-anomalies",
        )
        await self.nats.subscribe(
            DIAGNOSER_RESULTS,
            handler=self._handle_diagnosis_result,
            durable="orchestrator-diagnosis",
        )
        await self.nats.subscribe(
            SAFETY_DECISIONS,
            handler=self._handle_safety_decision,
            durable="orchestrator-safety",
        )
        await self.nats.subscribe(
            REMEDIATOR_EXECUTIONS,
            handler=self._handle_execution_result,
            durable="orchestrator-executions",
        )
        await self.nats.subscribe(
            AGENT_HEARTBEAT,
            handler=self._handle_heartbeat,
            durable="orchestrator-heartbeat",
        )
        await self.nats.subscribe(
            HUMAN_APPROVALS_RESPONSES,
            handler=self._handle_human_approval,
            durable="orchestrator-approvals",
        )

        # Recover in-flight incidents from DB
        await self._recover_inflight()
        logger.info("Orchestrator setup complete — %d in-flight incidents", len(self.active_fsms))

    async def run_loop(self) -> None:
        """Periodic timeout check loop."""
        while self._running:
            try:
                # Check timeouts
                escalated = await self.escalation.check_timeouts(self.active_fsms)
                if escalated:
                    logger.warning("Escalated %d incidents", len(escalated))

                # Prune stale agents
                dead = self.router.prune_stale_agents()
                for agent_id in dead:
                    info = self.router.registry.get(agent_id)
                    if info:
                        await self.escalation.handle_dead_agent(
                            agent_id, info.agent_type, self.active_fsms
                        )
            except Exception as exc:
                logger.error("Error in run_loop: %s", exc, exc_info=True)

            await asyncio.sleep(self._check_interval)

    async def teardown(self) -> None:
        logger.info("Orchestrator shutting down")

    # ------------------------------------------------------------------ #
    # NATS Handlers                                                        #
    # ------------------------------------------------------------------ #

    async def _handle_anomaly(self, msg: AgentMessage) -> None:
        """Create a new incident when an anomaly is detected."""
        self._increment_processed()
        correlation_id = msg.correlation_id
        payload = msg.payload

        # Avoid duplicate incidents for same correlation
        if correlation_id in self.active_fsms:
            logger.info("Anomaly for existing incident %s — skipping", correlation_id)
            return

        # Create incident in DB
        incident_id = correlation_id
        now = datetime.now(timezone.utc)
        severity = payload.get("severity", "medium")

        timeline: list[dict] = []
        add_event(timeline, "anomaly_detected", msg.source_agent,
                  f"Anomaly detected: {payload.get('metric', 'unknown')} on {payload.get('service', 'unknown')}",
                  {"anomaly": payload})

        async with get_session() as session:
            incident = Incident(
                id=incident_id,
                status="detecting",
                severity=severity,
                created_at=now,
                updated_at=now,
                state_entered_at=now,
                timeline=timeline,
            )
            session.add(incident)

            # Link anomaly
            anomaly = Anomaly(
                id=str(uuid.uuid4()),
                incident_id=incident_id,
                metric=payload.get("metric", "unknown"),
                service=payload.get("service", "unknown"),
                severity=severity,
                description=payload.get("description"),
                value=payload.get("value"),
                threshold=payload.get("threshold"),
                detected_at=now,
                raw_payload=payload,
            )
            session.add(anomaly)

        # Create FSM and transition to diagnosing
        fsm = IncidentFSM(incident_id, initial_state="detecting")
        fsm.transition("diagnosing")
        self.active_fsms[incident_id] = fsm

        # Update DB status
        await self._update_incident_status(incident_id, "diagnosing", timeline={
            "action": "add_event",
            "event_type": "diagnosis_started",
            "agent": self.agent_id,
            "summary": "Orchestrator requesting diagnosis",
        })

        # Route to diagnoser
        await self.router.route_to_diagnoser(
            source_agent=self.agent_id,
            correlation_id=incident_id,
            payload=payload,
            context=msg.context,
        )

        await self._publish_lifecycle("incident.created", incident_id, severity=severity)
        logger.info("Incident %s created — transitioning to diagnosing", incident_id)

    async def _handle_diagnosis_result(self, msg: AgentMessage) -> None:
        """Process diagnosis and transition to proposing_remediation."""
        self._increment_processed()
        incident_id = msg.correlation_id
        fsm = self.active_fsms.get(incident_id)
        if not fsm:
            logger.warning("Diagnosis for unknown incident %s", incident_id)
            return

        diagnosis = msg.payload
        try:
            fsm.transition("proposing_remediation")
        except ValueError as e:
            logger.error("FSM transition error: %s", e)
            return

        # Update incident with diagnosis
        async with get_session() as session:
            result = await session.execute(select(Incident).where(Incident.id == incident_id))
            incident = result.scalar_one_or_none()
            if incident:
                incident.status = "proposing_remediation"
                incident.state_entered_at = datetime.now(timezone.utc)
                incident.updated_at = datetime.now(timezone.utc)
                incident.diagnosis = diagnosis
                incident.diagnosis_confidence = diagnosis.get("confidence", 0)
                incident.root_cause_category = diagnosis.get("root_cause", {}).get("category")
                incident.root_cause_service = diagnosis.get("root_cause", {}).get("service")
                timeline = incident.timeline or []
                add_event(timeline, "diagnosis_complete", msg.source_agent,
                          f"Diagnosis: {incident.root_cause_category} ({incident.diagnosis_confidence}% confidence)",
                          {"diagnosis": diagnosis})
                incident.timeline = timeline

        await self._publish_lifecycle("incident.updated", incident_id, state="proposing_remediation")
        logger.info("Incident %s diagnosed — proposing remediation", incident_id)

    async def _handle_safety_decision(self, msg: AgentMessage) -> None:
        """Process safety decision — approve or reject."""
        self._increment_processed()
        incident_id = msg.correlation_id
        fsm = self.active_fsms.get(incident_id)
        if not fsm:
            return

        status = msg.payload.get("status")

        if status == "approved":
            try:
                fsm.transition("executing")
            except ValueError:
                return
            await self._update_incident_timeline(incident_id, "safety_approved",
                                                  msg.source_agent, "Action approved by safety agent")
            await self._update_incident_status(incident_id, "executing")
            await self._publish_lifecycle("incident.updated", incident_id, state="executing")

        elif status == "rejected":
            reason = msg.payload.get("reason", "")
            if fsm.should_retry():
                fsm.increment_retry()
                await self._update_incident_timeline(incident_id, "safety_rejected",
                                                      msg.source_agent, f"Rejected: {reason}")
                try:
                    fsm.transition("proposing_remediation")
                except ValueError:
                    pass
            else:
                await self.escalation._escalate_to_human(incident_id, fsm)

        elif status == "pending_human_approval":
            try:
                fsm.transition("safety_review")
            except ValueError:
                pass
            await self._update_incident_timeline(incident_id, "safety_approved",
                                                  msg.source_agent, "Pending human approval")
            await self._update_incident_status(incident_id, "safety_review")

    async def _handle_execution_result(self, msg: AgentMessage) -> None:
        """Process remediation execution result."""
        self._increment_processed()
        incident_id = msg.correlation_id
        fsm = self.active_fsms.get(incident_id)
        if not fsm:
            return

        status = msg.payload.get("status")
        if status == "success":
            try:
                fsm.transition("verifying")
                fsm.transition("resolved")
            except ValueError as e:
                logger.error("FSM transition error: %s", e)
                return

            now = datetime.now(timezone.utc)
            async with get_session() as session:
                result = await session.execute(select(Incident).where(Incident.id == incident_id))
                incident = result.scalar_one_or_none()
                if incident:
                    incident.status = "resolved"
                    incident.state_entered_at = now
                    incident.updated_at = now
                    incident.resolved_at = now
                    incident.auto_resolved = True
                    incident.resolution_summary = msg.payload.get("details", "Auto-resolved")
                    incident.remediation_actions = [msg.payload]
                    timeline = incident.timeline or []
                    add_event(timeline, "action_executed", msg.source_agent,
                              f"Action executed: {msg.payload.get('action_type', 'unknown')}")
                    add_event(timeline, "verification_passed", msg.source_agent, "Verification passed")
                    add_event(timeline, "resolved", self.agent_id, "Incident resolved")
                    incident.timeline = timeline
                    incident.postmortem = generate_postmortem(incident.to_dict() | {
                        "timeline": timeline, "resolved_at": now.isoformat()
                    })

            await self._publish_lifecycle("incident.resolved", incident_id)
            logger.info("Incident %s resolved", incident_id)
        else:
            # Execution failed
            if fsm.should_retry():
                fsm.increment_retry()
                await self._update_incident_timeline(incident_id, "action_executed",
                                                      msg.source_agent,
                                                      f"Execution failed: {msg.payload.get('details', '')}")
                try:
                    fsm.transition("proposing_remediation")
                except ValueError:
                    pass
            else:
                await self.escalation._escalate_to_human(incident_id, fsm)

    async def _handle_heartbeat(self, msg: AgentMessage) -> None:
        """Update agent registry from heartbeat."""
        self.router.update_agent_status(msg.payload)

    async def _handle_human_approval(self, msg: AgentMessage) -> None:
        """Process human approve/reject from dashboard."""
        self._increment_processed()
        incident_id = msg.correlation_id
        fsm = self.active_fsms.get(incident_id)
        if not fsm:
            return

        decision = msg.payload.get("decision")
        if decision == "approve":
            try:
                fsm.transition("executing")
            except ValueError:
                return
            await self._update_incident_timeline(incident_id, "safety_approved",
                                                  "human", "Approved by human operator")
            await self._update_incident_status(incident_id, "executing")
            await self._publish_lifecycle("incident.updated", incident_id, state="executing")
        elif decision == "reject":
            reason = msg.payload.get("reason", "Rejected by operator")
            await self._update_incident_timeline(incident_id, "safety_rejected",
                                                  "human", f"Rejected: {reason}")
            await self.escalation._escalate_to_human(incident_id, fsm)

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    async def _recover_inflight(self) -> None:
        """Load in-flight incidents from DB on startup."""
        try:
            async with get_session() as session:
                result = await session.execute(
                    select(Incident).where(
                        Incident.status.notin_(["resolved", "closed"])
                    )
                )
                incidents = result.scalars().all()
                for inc in incidents:
                    self.active_fsms[inc.id] = IncidentFSM(
                        incident_id=inc.id,
                        initial_state=inc.status,
                        state_entered_at=inc.state_entered_at,
                    )
        except Exception as exc:
            logger.error("Failed to recover in-flight incidents: %s", exc)

    async def _update_incident_status(
        self, incident_id: str, status: str, **extra: Any
    ) -> None:
        """Update incident status in DB."""
        async with get_session() as session:
            result = await session.execute(select(Incident).where(Incident.id == incident_id))
            incident = result.scalar_one_or_none()
            if incident:
                incident.status = status
                incident.state_entered_at = datetime.now(timezone.utc)
                incident.updated_at = datetime.now(timezone.utc)

    async def _update_incident_timeline(
        self, incident_id: str, event_type: str, agent: str, summary: str
    ) -> None:
        """Append an event to the incident timeline in DB."""
        async with get_session() as session:
            result = await session.execute(select(Incident).where(Incident.id == incident_id))
            incident = result.scalar_one_or_none()
            if incident:
                timeline = incident.timeline or []
                add_event(timeline, event_type, agent, summary)
                incident.timeline = timeline
                incident.updated_at = datetime.now(timezone.utc)

    async def _publish_lifecycle(
        self, event_type: str, incident_id: str, **extra: Any
    ) -> None:
        """Publish an incident lifecycle event to NATS."""
        msg = build_message(
            source_agent=self.agent_id,
            target_agent="*",
            message_type=event_type,
            payload={"incident_id": incident_id, **extra},
            correlation_id=incident_id,
            priority=1,
        )
        await self.nats.publish(INCIDENTS_LIFECYCLE, msg)
