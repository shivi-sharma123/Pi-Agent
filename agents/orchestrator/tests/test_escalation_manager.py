"""Tests for EscalationManager — timeouts, retries, escalation."""

import sys
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

from incident_fsm import IncidentFSM, MAX_RETRIES_PER_STATE
from escalation_manager import EscalationManager


@pytest.fixture
def mock_nats():
    nats = MagicMock()
    nats.publish = AsyncMock()
    return nats


@pytest.fixture
def manager(mock_nats):
    return EscalationManager(mock_nats)


class TestCheckTimeouts:
    @pytest.mark.asyncio
    async def test_no_timeouts(self, manager):
        fsm = IncidentFSM("inc-1", initial_state="diagnosing")
        escalated = await manager.check_timeouts({"inc-1": fsm})
        assert len(escalated) == 0

    @pytest.mark.asyncio
    async def test_retry_on_timeout(self, manager, mock_nats):
        fsm = IncidentFSM("inc-1", initial_state="diagnosing")
        fsm.state_entered_at = datetime.now(timezone.utc) - timedelta(seconds=300)
        escalated = await manager.check_timeouts({"inc-1": fsm})
        assert len(escalated) == 0  # retried, not escalated
        assert fsm.retry_count == 1
        mock_nats.publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_escalate_after_max_retries(self, manager, mock_nats):
        fsm = IncidentFSM("inc-1", initial_state="diagnosing")
        fsm.state_entered_at = datetime.now(timezone.utc) - timedelta(seconds=300)
        fsm.retry_count = MAX_RETRIES_PER_STATE  # exhausted
        escalated = await manager.check_timeouts({"inc-1": fsm})
        assert "inc-1" in escalated
        mock_nats.publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_terminal_states(self, manager):
        fsm = IncidentFSM("inc-1", initial_state="resolved")
        fsm.state_entered_at = datetime.now(timezone.utc) - timedelta(hours=1)
        escalated = await manager.check_timeouts({"inc-1": fsm})
        assert len(escalated) == 0


class TestHandleDeadAgent:
    @pytest.mark.asyncio
    async def test_escalates_affected_incidents(self, manager, mock_nats):
        fsm = IncidentFSM("inc-1", initial_state="diagnosing")
        await manager.handle_dead_agent(
            "diagnoser.host1.abc",
            "agents.diagnoser",
            {"inc-1": fsm},
        )
        mock_nats.publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_ignores_unaffected_incidents(self, manager, mock_nats):
        fsm = IncidentFSM("inc-1", initial_state="detecting")
        await manager.handle_dead_agent(
            "diagnoser.host1.abc",
            "agents.diagnoser",
            {"inc-1": fsm},
        )
        mock_nats.publish.assert_not_called()
