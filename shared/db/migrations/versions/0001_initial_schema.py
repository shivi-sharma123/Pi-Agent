"""Initial migration — creates incidents, anomalies, agent_heartbeats tables.

Revision ID: 0001
Revises: (none)
Create Date: 2026-03-03
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# ---------------------------------------------------------------------------
# Alembic revision identifiers
# ---------------------------------------------------------------------------

revision: str = "0001"
down_revision: str | None = None
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------


def upgrade() -> None:
    # ------------------------------------------------------------------
    # incidents
    # ------------------------------------------------------------------
    op.create_table(
        "incidents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "detected", "diagnosing", "remediating", "verifying",
                "resolved", "closed", "escalated",
                name="incidentstatus",
            ),
            nullable=False,
            server_default="detected",
        ),
        sa.Column(
            "severity",
            sa.Enum("critical", "high", "medium", "low", name="incidentseverity"),
            nullable=False,
            server_default="medium",
        ),
        sa.Column("affected_service", sa.String(length=200), nullable=True),
        sa.Column("correlation_id", sa.String(length=100), nullable=True),
        sa.Column("anomaly_ids", postgresql.JSONB(), nullable=True),
        sa.Column("diagnosis", postgresql.JSONB(), nullable=True),
        sa.Column("remediation_actions", postgresql.JSONB(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_incidents_status", "incidents", ["status"])
    op.create_index("ix_incidents_severity", "incidents", ["severity"])
    op.create_index(
        "ix_incidents_affected_service", "incidents", ["affected_service"]
    )

    # ------------------------------------------------------------------
    # anomalies
    # ------------------------------------------------------------------
    op.create_table(
        "anomalies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source", sa.String(length=200), nullable=False),
        sa.Column(
            "anomaly_type",
            sa.Enum(
                "metric_spike", "log_pattern", "health_check_failure", "synthetic_failure",
                name="anomalytype",
            ),
            nullable=False,
        ),
        sa.Column("metric_name", sa.String(length=300), nullable=True),
        sa.Column("metric_value", sa.Float(), nullable=True),
        sa.Column("threshold", sa.Float(), nullable=True),
        sa.Column("raw_data", postgresql.JSONB(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_anomalies_incident_id", "anomalies", ["incident_id"])
    op.create_index("ix_anomalies_source", "anomalies", ["source"])

    # ------------------------------------------------------------------
    # agent_heartbeats
    # ------------------------------------------------------------------
    op.create_table(
        "agent_heartbeats",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", sa.String(length=200), nullable=False),
        sa.Column("agent_type", sa.String(length=100), nullable=False),
        sa.Column("hostname", sa.String(length=200), nullable=True),
        sa.Column(
            "status",
            sa.Enum("healthy", "degraded", "offline", name="agentstatus"),
            nullable=False,
            server_default="healthy",
        ),
        sa.Column("uptime_seconds", sa.Float(), nullable=True),
        sa.Column("messages_processed", sa.Integer(), nullable=True),
        sa.Column("errors", sa.Integer(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agent_heartbeats_agent_id", "agent_heartbeats", ["agent_id"]
    )
    op.create_index(
        "ix_agent_heartbeats_created_at",
        "agent_heartbeats",
        ["created_at"],
        postgresql_using="brin",  # BRIN index — efficient for time-series inserts
    )


def downgrade() -> None:
    op.drop_table("agent_heartbeats")
    op.drop_table("anomalies")
    op.drop_table("incidents")
    # Drop enums created above
    for enum_name in (
        "incidentstatus", "incidentseverity", "anomalytype", "agentstatus"
    ):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
