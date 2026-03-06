"""
Incident Finite State Machine — manages incident lifecycle transitions.

States: detecting -> diagnosing -> proposing_remediation -> safety_review
        -> executing -> verifying -> resolved -> closed

Pure state machine with no external dependencies. Fully unit-testable.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


# Valid states in lifecycle order
STATES = (
    "detecting",
    "diagnosing",
    "proposing_remediation",
    "safety_review",
    "executing",
    "verifying",
    "resolved",
    "closed",
)

# Valid transitions: source -> set of allowed destinations
TRANSITIONS: dict[str, set[str]] = {
    "detecting": {"diagnosing"},
    "diagnosing": {"proposing_remediation"},
    "proposing_remediation": {"safety_review"},
    "safety_review": {"executing", "proposing_remediation"},  # rejection loops back
    "executing": {"verifying", "proposing_remediation"},      # failure retries
    "verifying": {"resolved", "executing"},                   # verification failure retries
    "resolved": {"closed"},
    "closed": set(),
}

# Per-state timeout in seconds
STATE_TIMEOUTS: dict[str, int] = {
    "detecting": 120,
    "diagnosing": 180,
    "proposing_remediation": 120,
    "safety_review": 300,
    "executing": 180,
    "verifying": 120,
}

MAX_RETRIES_PER_STATE = 2


class IncidentFSM:
    """Tracks the lifecycle state of a single incident."""

    def __init__(
        self,
        incident_id: str,
        initial_state: str = "detecting",
        state_entered_at: Optional[datetime] = None,
        retry_count: int = 0,
    ) -> None:
        if initial_state not in STATES:
            raise ValueError(f"Invalid initial state: {initial_state}")
        self.incident_id = incident_id
        self.state = initial_state
        self.state_entered_at = state_entered_at or datetime.now(timezone.utc)
        self.retry_count = retry_count
        self.history: list[dict] = []

    def can_transition(self, target: str) -> bool:
        """Check if a transition to target state is valid."""
        return target in TRANSITIONS.get(self.state, set())

    def transition(self, target: str) -> str:
        """
        Transition to a new state. Returns the new state.
        Raises ValueError if the transition is invalid.
        """
        if not self.can_transition(target):
            raise ValueError(
                f"Invalid transition: {self.state} -> {target} "
                f"(allowed: {TRANSITIONS.get(self.state, set())})"
            )
        now = datetime.now(timezone.utc)
        self.history.append({
            "from": self.state,
            "to": target,
            "at": now.isoformat(),
        })
        self.state = target
        self.state_entered_at = now
        self.retry_count = 0  # reset retries on state change
        return self.state

    def is_timed_out(self) -> bool:
        """Check if the current state has exceeded its timeout."""
        timeout = STATE_TIMEOUTS.get(self.state)
        if timeout is None:
            return False  # resolved/closed don't time out
        elapsed = (datetime.now(timezone.utc) - self.state_entered_at).total_seconds()
        return elapsed > timeout

    def should_retry(self) -> bool:
        """Check if we can retry the current state (under max retries)."""
        return self.retry_count < MAX_RETRIES_PER_STATE

    def increment_retry(self) -> int:
        """Increment retry counter and reset the timeout clock. Returns new count."""
        self.retry_count += 1
        self.state_entered_at = datetime.now(timezone.utc)
        return self.retry_count

    @property
    def is_terminal(self) -> bool:
        """Whether the FSM is in a terminal state."""
        return self.state in ("resolved", "closed")
