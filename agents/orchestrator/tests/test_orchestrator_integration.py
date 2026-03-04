"""
End-to-end integration tests for the Orchestrator Agent.

Simulates the full incident lifecycle by mocking NATS and DB,
verifying FSM transitions, timeline events, and escalation paths.
"""

import sys
import os
import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

from incident_fsm import IncidentFSM
from timeline_builder import add_event, generate_postmortem
from agent_router import AgentRouter
from escalation_manager import EscalationManager
from shared.messaging.schema import AgentMessage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_msg(
    msg_type: str,
    payload: dict = None,
    correlation_id: str = None,
    source: str = "test-agent",
) -> AgentMessage:
    return AgentMessage(
        message_id=str(uuid.uuid4()),
        correlation_id=correlation_id or str(uuid.uuid4()),
        source_agent=source,
        target_agent="orchestrator",
        message_type=msg_type,
        payload=payload or {},
    )


# ---------------------------------------------------------------------------
# Test: Full happy-path lifecycle
# ---------------------------------------------------------------------------

class TestHappyPathLifecycle:
    """Simulate: anomaly -> diagnosis -> safety approve -> execute -> resolve."""

    def test_full_fsm_lifecycle(self):
        incident_id = str(uuid.uuid4())
        fsm = IncidentFSM(incident_id)

        # Step 1: detecting -> diagnosing
        assert fsm.state == "detecting"
        fsm.transition("diagnosing")
        assert fsm.state == "diagnosing"

        # Step 2: diagnosing -> proposing_remediation
        fsm.transition("proposing_remediation")
        assert fsm.state == "proposing_remediation"

        # Step 3: proposing_remediation -> safety_review
        fsm.transition("safety_review")
        assert fsm.state == "safety_review"

        # Step 4: safety_review -> executing (approved)
        fsm.transition("executing")
        assert fsm.state == "executing"

        # Step 5: executing -> verifying
        fsm.transition("verifying")
        assert fsm.state == "verifying"

        # Step 6: verifying -> resolved
        fsm.transition("resolved")
        assert fsm.state == "resolved"
        assert fsm.is_terminal

        # Step 7: resolved -> closed
        fsm.transition("closed")
        assert fsm.state == "closed"
        assert fsm.is_terminal

    def test_timeline_records_all_events(self):
        timeline: list[dict] = []
        add_event(timeline, "anomaly_detected", "observer", "High CPU on user-svc")
        add_event(timeline, "diagnosis_started", "orchestrator", "Requesting diagnosis")
        add_event(timeline, "diagnosis_complete", "diagnoser", "Memory leak detected",
                  {"confidence": 85})
        add_event(timeline, "remediation_proposed", "remediator", "Restart container")
        add_event(timeline, "safety_approved", "safety", "Action approved")
        add_event(timeline, "action_executed", "remediator", "Container restarted")
        add_event(timeline, "verification_passed", "remediator", "Health check passed")
        add_event(timeline, "resolved", "orchestrator", "Incident resolved")

        assert len(timeline) == 8
        assert timeline[0]["event_type"] == "anomaly_detected"
        assert timeline[-1]["event_type"] == "resolved"

    def test_postmortem_generation(self):
        now = datetime.utcnow()
        incident = {
            "id": "inc-test-1",
            "status": "resolved",
            "severity": "critical",
            "created_at": (now - timedelta(minutes=5)).isoformat(),
            "resolved_at": now.isoformat(),
            "root_cause_category": "memory_leak",
            "root_cause_service": "user-svc",
            "resolution_summary": "Container restarted successfully",
            "timeline": [
                {"event_type": "anomaly_detected", "timestamp": (now - timedelta(minutes=5)).isoformat()},
                {"event_type": "diagnosis_complete", "timestamp": (now - timedelta(minutes=4)).isoformat()},
                {"event_type": "safety_approved", "timestamp": (now - timedelta(minutes=3)).isoformat()},
                {"event_type": "action_executed", "timestamp": (now - timedelta(minutes=1)).isoformat()},
                {"event_type": "resolved", "timestamp": now.isoformat()},
            ],
        }
        pm = generate_postmortem(incident)
        assert pm["incident_id"] == "inc-test-1"
        assert pm["severity"] == "critical"
        assert pm["root_cause"] == "memory_leak"
        assert pm["total_events"] == 5
        assert pm["duration_seconds"] is not None
        assert abs(pm["duration_seconds"] - 300) < 5


# ---------------------------------------------------------------------------
# Test: Safety rejection + retry path
# ---------------------------------------------------------------------------

class TestSafetyRejectionPath:
    def test_rejection_loops_back(self):
        fsm = IncidentFSM("inc-reject")
        fsm.transition("diagnosing")
        fsm.transition("proposing_remediation")
        fsm.transition("safety_review")

        # Safety rejects — loop back
        fsm.transition("proposing_remediation")
        assert fsm.state == "proposing_remediation"

        # Resubmit
        fsm.transition("safety_review")
        fsm.transition("executing")
        assert fsm.state == "executing"


# ---------------------------------------------------------------------------
# Test: Timeout + escalation path
# ---------------------------------------------------------------------------

class TestTimeoutEscalation:
    @pytest.mark.asyncio
    async def test_timeout_triggers_retry(self):
        mock_nats = MagicMock()
        mock_nats.publish = AsyncMock()
        mgr = EscalationManager(mock_nats)

        fsm = IncidentFSM("inc-timeout", initial_state="diagnosing")
        fsm.state_entered_at = datetime.utcnow() - timedelta(seconds=300)

        escalated = await mgr.check_timeouts({"inc-timeout": fsm})
        assert len(escalated) == 0  # first timeout = retry
        assert fsm.retry_count == 1

    @pytest.mark.asyncio
    async def test_max_retries_escalates(self):
        mock_nats = MagicMock()
        mock_nats.publish = AsyncMock()
        mgr = EscalationManager(mock_nats)

        fsm = IncidentFSM("inc-escalate", initial_state="diagnosing")
        fsm.state_entered_at = datetime.utcnow() - timedelta(seconds=300)
        fsm.retry_count = 2  # max retries exhausted

        escalated = await mgr.check_timeouts({"inc-escalate": fsm})
        assert "inc-escalate" in escalated
        mock_nats.publish.assert_called()

    @pytest.mark.asyncio
    async def test_dead_agent_escalates_affected(self):
        mock_nats = MagicMock()
        mock_nats.publish = AsyncMock()
        mgr = EscalationManager(mock_nats)

        fsm = IncidentFSM("inc-dead", initial_state="diagnosing")
        await mgr.handle_dead_agent("diag1", "agents.diagnoser", {"inc-dead": fsm})
        mock_nats.publish.assert_called()


# ---------------------------------------------------------------------------
# Test: Agent router registration & health
# ---------------------------------------------------------------------------

class TestAgentRouterIntegration:
    def test_heartbeat_registration_and_query(self):
        mock_nats = MagicMock()
        router = AgentRouter(mock_nats)

        # Register agents
        router.update_agent_status({
            "agent_id": "observer.host1.abc",
            "agent_type": "agents.observer",
            "hostname": "host1",
            "status": "healthy",
        })
        router.update_agent_status({
            "agent_id": "diagnoser.host1.xyz",
            "agent_type": "agents.diagnoser",
            "hostname": "host1",
            "status": "healthy",
        })

        observers = router.get_available_agents("agents.observer")
        assert len(observers) == 1
        diagnosers = router.get_available_agents("agents.diagnoser")
        assert len(diagnosers) == 1

    def test_stale_agent_pruning(self):
        mock_nats = MagicMock()
        router = AgentRouter(mock_nats)

        router.update_agent_status({
            "agent_id": "obs-stale",
            "agent_type": "agents.observer",
        })
        # Age the heartbeat
        router.registry["obs-stale"].last_seen_at = datetime.utcnow() - timedelta(seconds=200)

        dead = router.prune_stale_agents()
        assert "obs-stale" in dead
        assert router.registry["obs-stale"].status == "dead"
        assert len(router.get_available_agents("agents.observer")) == 0


# ---------------------------------------------------------------------------
# Test: Human approval flow
# ---------------------------------------------------------------------------

class TestHumanApprovalFlow:
    def test_fsm_safety_review_to_executing_on_approve(self):
        fsm = IncidentFSM("inc-approval", initial_state="safety_review")
        assert fsm.can_transition("executing")
        fsm.transition("executing")
        assert fsm.state == "executing"

    def test_fsm_safety_review_to_proposing_on_reject(self):
        fsm = IncidentFSM("inc-reject", initial_state="safety_review")
        assert fsm.can_transition("proposing_remediation")
        fsm.transition("proposing_remediation")
        assert fsm.state == "proposing_remediation"


# ---------------------------------------------------------------------------
# Test: Multiple concurrent incidents
# ---------------------------------------------------------------------------

class TestConcurrentIncidents:
    @pytest.mark.asyncio
    async def test_multiple_fsms_independent(self):
        mock_nats = MagicMock()
        mock_nats.publish = AsyncMock()
        mgr = EscalationManager(mock_nats)

        fsm1 = IncidentFSM("inc-1", initial_state="diagnosing")
        fsm2 = IncidentFSM("inc-2", initial_state="executing")
        fsm3 = IncidentFSM("inc-3", initial_state="resolved")

        active = {"inc-1": fsm1, "inc-2": fsm2, "inc-3": fsm3}

        # No timeouts initially
        escalated = await mgr.check_timeouts(active)
        assert len(escalated) == 0

        # Timeout inc-1 only
        fsm1.state_entered_at = datetime.utcnow() - timedelta(seconds=300)
        escalated = await mgr.check_timeouts(active)
        assert len(escalated) == 0  # retry first
        assert fsm1.retry_count == 1
        assert fsm2.retry_count == 0  # unaffected

    def test_fsm_history_independent(self):
        fsm1 = IncidentFSM("inc-1")
        fsm2 = IncidentFSM("inc-2")
        fsm1.transition("diagnosing")
        assert len(fsm1.history) == 1
        assert len(fsm2.history) == 0
