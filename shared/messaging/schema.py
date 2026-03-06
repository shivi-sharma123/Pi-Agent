"""
AgentMessage — the canonical message envelope for all inter-agent communication.

Every message in the system (anomalies, diagnosis requests, remediation proposals,
safety decisions, human approvals) uses this schema.  The correlation_id ties all
messages that belong to the same incident together so the orchestrator can track
incident lifecycle end-to-end.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class AgentMessage:
    """
    Canonical message envelope shared by all agents in the swarm.

    Fields follow the LLD §2.2 specification.
    """

    # --- Identity ---
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    """Unique identifier for this specific message (UUID v4)."""

    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    """Links all messages that belong to the same incident / request chain."""

    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    """Distributed tracing identifier (propagated across service boundaries)."""

    # --- Routing ---
    source_agent: str = ""
    """Sender identifier, e.g. 'observer.metrics', 'diagnoser.rca'."""

    target_agent: str = ""
    """Recipient identifier, e.g. 'orchestrator', 'safety', '*' for broadcast."""

    message_type: str = ""
    """Semantic type, e.g. 'anomaly_detected', 'diagnosis_complete'."""

    # --- Priority & TTL ---
    priority: int = 2
    """0=critical, 1=high, 2=medium, 3=low."""

    ttl_seconds: int = 300
    """Message expiry in seconds; consumers should discard stale messages."""

    # --- Lifecycle ---
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    """UTC timestamp when the message was created."""

    retry_count: int = 0
    """Number of times this message has been re-attempted (for idempotency)."""

    # --- Payload ---
    payload: dict[str, Any] = field(default_factory=dict)
    """Type-specific data (anomaly details, diagnosis result, proposed actions, etc.)."""

    context: dict[str, Any] = field(default_factory=dict)
    """Accumulated investigation context that grows as the incident progresses."""

    # ------------------------------------------------------------------ #
    # Serialisation helpers                                                #
    # ------------------------------------------------------------------ #

    def to_dict(self) -> dict[str, Any]:
        """Convert to a plain dict suitable for JSON serialisation."""
        return {
            "message_id": self.message_id,
            "correlation_id": self.correlation_id,
            "trace_id": self.trace_id,
            "source_agent": self.source_agent,
            "target_agent": self.target_agent,
            "message_type": self.message_type,
            "priority": self.priority,
            "ttl_seconds": self.ttl_seconds,
            "timestamp": self.timestamp.isoformat(),
            "retry_count": self.retry_count,
            "payload": self.payload,
            "context": self.context,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentMessage":
        """Reconstruct an AgentMessage from a deserialised dict."""
        ts = data.get("timestamp")
        return cls(
            message_id=data.get("message_id", str(uuid.uuid4())),
            correlation_id=data.get("correlation_id", str(uuid.uuid4())),
            trace_id=data.get("trace_id", str(uuid.uuid4())),
            source_agent=data.get("source_agent", ""),
            target_agent=data.get("target_agent", ""),
            message_type=data.get("message_type", ""),
            priority=data.get("priority", 2),
            ttl_seconds=data.get("ttl_seconds", 300),
            timestamp=datetime.fromisoformat(ts) if isinstance(ts, str) else datetime.now(timezone.utc),
            retry_count=data.get("retry_count", 0),
            payload=data.get("payload", {}),
            context=data.get("context", {}),
        )

    def is_expired(self) -> bool:
        """Return True if the message has exceeded its TTL."""
        age = (datetime.now(timezone.utc) - self.timestamp).total_seconds()
        return age > self.ttl_seconds
