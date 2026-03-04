"""Tests for IncidentFSM — all transitions, invalid transitions, timeouts, retries."""

import sys
import os
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from incident_fsm import (
    STATES,
    TRANSITIONS,
    STATE_TIMEOUTS,
    MAX_RETRIES_PER_STATE,
    IncidentFSM,
)


class TestIncidentFSMInit:
    def test_default_state(self):
        fsm = IncidentFSM("inc-1")
        assert fsm.state == "detecting"
        assert fsm.incident_id == "inc-1"
        assert fsm.retry_count == 0

    def test_custom_initial_state(self):
        fsm = IncidentFSM("inc-2", initial_state="diagnosing")
        assert fsm.state == "diagnosing"

    def test_invalid_initial_state(self):
        with pytest.raises(ValueError, match="Invalid initial state"):
            IncidentFSM("inc-3", initial_state="nonexistent")


class TestTransitions:
    def test_happy_path(self):
        """Full happy path: detecting -> ... -> closed."""
        fsm = IncidentFSM("inc-1")
        fsm.transition("diagnosing")
        assert fsm.state == "diagnosing"
        fsm.transition("proposing_remediation")
        assert fsm.state == "proposing_remediation"
        fsm.transition("safety_review")
        assert fsm.state == "safety_review"
        fsm.transition("executing")
        assert fsm.state == "executing"
        fsm.transition("verifying")
        assert fsm.state == "verifying"
        fsm.transition("resolved")
        assert fsm.state == "resolved"
        fsm.transition("closed")
        assert fsm.state == "closed"

    def test_safety_rejection_loop(self):
        """safety_review -> proposing_remediation (on rejection)."""
        fsm = IncidentFSM("inc-1", initial_state="safety_review")
        assert fsm.can_transition("proposing_remediation")
        fsm.transition("proposing_remediation")
        assert fsm.state == "proposing_remediation"

    def test_execution_failure_loop(self):
        """executing -> proposing_remediation (on failure)."""
        fsm = IncidentFSM("inc-1", initial_state="executing")
        assert fsm.can_transition("proposing_remediation")
        fsm.transition("proposing_remediation")
        assert fsm.state == "proposing_remediation"

    def test_verification_failure_loop(self):
        """verifying -> executing (on verification failure)."""
        fsm = IncidentFSM("inc-1", initial_state="verifying")
        assert fsm.can_transition("executing")
        fsm.transition("executing")
        assert fsm.state == "executing"

    def test_invalid_transition_raises(self):
        fsm = IncidentFSM("inc-1")
        with pytest.raises(ValueError, match="Invalid transition"):
            fsm.transition("resolved")

    def test_cannot_transition_from_closed(self):
        fsm = IncidentFSM("inc-1", initial_state="closed")
        assert not fsm.can_transition("detecting")
        assert not fsm.can_transition("resolved")

    def test_all_valid_transitions_allowed(self):
        for source, targets in TRANSITIONS.items():
            for target in targets:
                fsm = IncidentFSM("test", initial_state=source)
                assert fsm.can_transition(target)

    def test_transition_records_history(self):
        fsm = IncidentFSM("inc-1")
        fsm.transition("diagnosing")
        assert len(fsm.history) == 1
        assert fsm.history[0]["from"] == "detecting"
        assert fsm.history[0]["to"] == "diagnosing"

    def test_transition_resets_retry_count(self):
        fsm = IncidentFSM("inc-1")
        fsm.retry_count = 2
        fsm.transition("diagnosing")
        assert fsm.retry_count == 0


class TestTimeouts:
    def test_not_timed_out_initially(self):
        fsm = IncidentFSM("inc-1")
        assert not fsm.is_timed_out()

    def test_timed_out_after_threshold(self):
        fsm = IncidentFSM("inc-1")
        fsm.state_entered_at = datetime.utcnow() - timedelta(seconds=200)
        assert fsm.is_timed_out()  # detecting timeout is 120s

    def test_no_timeout_for_resolved(self):
        fsm = IncidentFSM("inc-1", initial_state="resolved")
        fsm.state_entered_at = datetime.utcnow() - timedelta(hours=24)
        assert not fsm.is_timed_out()

    def test_no_timeout_for_closed(self):
        fsm = IncidentFSM("inc-1", initial_state="closed")
        fsm.state_entered_at = datetime.utcnow() - timedelta(hours=24)
        assert not fsm.is_timed_out()


class TestRetries:
    def test_should_retry_initially(self):
        fsm = IncidentFSM("inc-1")
        assert fsm.should_retry()

    def test_should_retry_after_one(self):
        fsm = IncidentFSM("inc-1")
        fsm.increment_retry()
        assert fsm.should_retry()

    def test_should_not_retry_at_max(self):
        fsm = IncidentFSM("inc-1")
        for _ in range(MAX_RETRIES_PER_STATE):
            fsm.increment_retry()
        assert not fsm.should_retry()

    def test_increment_retry_resets_timeout_clock(self):
        fsm = IncidentFSM("inc-1")
        fsm.state_entered_at = datetime.utcnow() - timedelta(seconds=300)
        assert fsm.is_timed_out()
        fsm.increment_retry()
        assert not fsm.is_timed_out()


class TestTerminal:
    def test_resolved_is_terminal(self):
        fsm = IncidentFSM("inc-1", initial_state="resolved")
        assert fsm.is_terminal

    def test_closed_is_terminal(self):
        fsm = IncidentFSM("inc-1", initial_state="closed")
        assert fsm.is_terminal

    def test_detecting_is_not_terminal(self):
        fsm = IncidentFSM("inc-1")
        assert not fsm.is_terminal
