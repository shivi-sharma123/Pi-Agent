"""
SQLAlchemy ORM models for the agent incident store (postgres-agents DB).

Tables:
  - incidents:         Full lifecycle record of each detected incident.
  - anomalies:         Individual anomaly signals that triggered/joined an incident.
  - agent_heartbeats:  Latest heartbeat per agent — used for health monitoring.

All models use async-compatible types (asyncpg under the hood).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""
    pass


# ---------------------------------------------------------------------------
# Incidents
# ---------------------------------------------------------------------------

class Incident(Base):
    """
    Represents a single production incident from detection through resolution.

    The lifecycle goes:  detecting → diagnosing → proposing_remediation
                         → safety_review → executing → verifying → resolved/closed.
    """

    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        comment="UUID v4 — matches the correlation_id used in NATS messages",
    )

    # --- Status ---
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="detecting",
        comment="Current FSM state (detecting, diagnosing, resolved, …)",
    )
    severity: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="medium",
        comment="critical | high | medium | low",
    )

    # --- Timestamps ---
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    state_entered_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow,
        comment="When the current status was entered — used for timeout detection",
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # --- Diagnosis ---
    diagnosis: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, comment="Full LLM diagnosis payload"
    )
    diagnosis_confidence: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="0-100 confidence from RCA engine"
    )
    root_cause_category: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )
    root_cause_service: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )

    # --- Remediation ---
    runbook_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    remediation_actions: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True, comment="List of executed action records"
    )
    auto_resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    escalation_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # --- Post-mortem ---
    resolution_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    postmortem: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    timeline: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True, comment="Ordered list of timeline events for the dashboard"
    )

    # --- Relationships ---
    anomalies: Mapped[list["Anomaly"]] = relationship(
        "Anomaly", back_populates="incident", cascade="all, delete-orphan"
    )

    @property
    def duration_seconds(self) -> Optional[float]:
        """Seconds from creation to resolution (or now if still open)."""
        end = self.resolved_at or datetime.utcnow()
        return (end - self.created_at).total_seconds()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "severity": self.severity,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "state_entered_at": self.state_entered_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "diagnosis": self.diagnosis,
            "diagnosis_confidence": self.diagnosis_confidence,
            "root_cause_category": self.root_cause_category,
            "root_cause_service": self.root_cause_service,
            "runbook_id": self.runbook_id,
            "auto_resolved": self.auto_resolved,
            "escalation_reason": self.escalation_reason,
            "resolution_summary": self.resolution_summary,
            "duration_seconds": self.duration_seconds,
        }


# ---------------------------------------------------------------------------
# Anomalies
# ---------------------------------------------------------------------------

class Anomaly(Base):
    """
    Individual anomaly signal detected by an Observer agent.

    Multiple anomalies may be grouped under the same Incident when they
    come from related services within a short time window.
    """

    __tablename__ = "anomalies"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    incident_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), ForeignKey("incidents.id", ondelete="SET NULL"), nullable=True
    )

    # --- Detection metadata ---
    metric: Mapped[str] = mapped_column(String(200), nullable=False)
    service: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # --- Values ---
    value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    threshold: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    z_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # --- Raw payload ---
    raw_payload: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, comment="Full observer payload for forensic use"
    )
    labels: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # --- Timestamps ---
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    fingerprint: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True, comment="Deduplication fingerprint"
    )

    # --- Relationships ---
    incident: Mapped[Optional["Incident"]] = relationship("Incident", back_populates="anomalies")


# ---------------------------------------------------------------------------
# Agent Heartbeats
# ---------------------------------------------------------------------------

class AgentHeartbeat(Base):
    """
    Tracks the last heartbeat received from each agent.

    Used by the orchestrator to detect dead / unresponsive agents and
    trigger escalation if critical agents stop publishing.
    """

    __tablename__ = "agent_heartbeats"

    agent_id: Mapped[str] = mapped_column(
        String(200),
        primary_key=True,
        comment="Unique agent identifier, e.g. 'observer.metrics.instance-1'",
    )
    agent_type: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="observer | diagnoser | remediator | safety …"
    )
    hostname: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # --- Health ---
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="healthy",
        comment="healthy | degraded | dead"
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    # --- Metrics reported by agent ---
    metrics: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True,
        comment="Agent-specific metrics: messages_processed, errors, uptime_seconds, …",
    )
