"""
Unit tests for shared.db.models — SQLAlchemy ORM model definitions.

These tests verify tables, columns, relationships, and model
instantiation without requiring a real database connection.

Note: status/severity fields use plain String columns (not Python enums),
so tests assert on the column type and valid string values.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy import inspect, String
from sqlalchemy.orm import RelationshipProperty

from shared.db.models import (
    AgentHeartbeat,
    Anomaly,
    Base,
    Incident,
)


class TestIncidentModel:
    def test_table_name(self):
        assert Incident.__tablename__ == "incidents"

    def test_required_columns_present(self):
        mapper = inspect(Incident)
        col_names = {c.key for c in mapper.columns}
        required = {
            "id", "status", "severity",
            "created_at", "updated_at", "state_entered_at",
            "resolved_at", "closed_at",
            "diagnosis", "diagnosis_confidence",
            "root_cause_category", "root_cause_service",
            "runbook_id", "remediation_actions",
            "auto_resolved", "escalation_reason",
            "resolution_summary", "postmortem", "timeline",
        }
        missing = required - col_names
        assert not missing, f"Columns missing from Incident: {missing}"

    def test_status_column_is_string_type(self):
        mapper = inspect(Incident)
        col = mapper.columns["status"]
        assert isinstance(col.type, String)

    def test_severity_column_is_string_type(self):
        mapper = inspect(Incident)
        col = mapper.columns["severity"]
        assert isinstance(col.type, String)

    def test_has_anomalies_relationship(self):
        mapper = inspect(Incident)
        rel_names = {r.key for r in mapper.relationships}
        assert "anomalies" in rel_names

    def test_incident_instantiation(self):
        inc = Incident(
            status="detected",
            severity="high",
        )
        assert inc.status == "detected"
        assert inc.severity == "high"
        # auto_resolved defaults to False at DB level (server_default);
        # Python ORM default may be None until flushed — check falsy is sufficient
        assert not inc.auto_resolved

    def test_duration_seconds_without_resolved_at(self):
        inc = Incident(status="diagnosing", severity="medium")
        inc.created_at = datetime(2026, 3, 3, 10, 0, 0)
        # Should not raise; returns a float based on (now - created_at)
        duration = inc.duration_seconds
        assert duration is not None
        assert isinstance(duration, float)


class TestAnomalyModel:
    def test_table_name(self):
        assert Anomaly.__tablename__ == "anomalies"

    def test_required_columns_present(self):
        mapper = inspect(Anomaly)
        col_names = {c.key for c in mapper.columns}
        required = {
            "id", "incident_id", "metric", "service", "severity",
            "category", "description", "value", "threshold",
            "z_score", "raw_payload", "labels",
            "detected_at", "fingerprint",
        }
        missing = required - col_names
        assert not missing, f"Columns missing from Anomaly: {missing}"

    def test_has_incident_relationship(self):
        mapper = inspect(Anomaly)
        rel_names = {r.key for r in mapper.relationships}
        assert "incident" in rel_names

    def test_anomaly_instantiation(self):
        anomaly = Anomaly(
            metric="container_cpu_usage_seconds_total",
            service="order-svc",
            severity="high",
            value=0.95,
            threshold=0.8,
        )
        assert anomaly.metric == "container_cpu_usage_seconds_total"
        assert anomaly.value == 0.95


class TestAgentHeartbeatModel:
    def test_table_name(self):
        assert AgentHeartbeat.__tablename__ == "agent_heartbeats"

    def test_required_columns_present(self):
        mapper = inspect(AgentHeartbeat)
        col_names = {c.key for c in mapper.columns}
        required = {
            "agent_id", "agent_type", "hostname", "version",
            "status", "last_seen_at", "metrics",
        }
        missing = required - col_names
        assert not missing, f"Columns missing from AgentHeartbeat: {missing}"

    def test_heartbeat_instantiation(self):
        hb = AgentHeartbeat(
            agent_id="observer.metrics.host1.abc12345",
            agent_type="observer.metrics",
            status="healthy",
        )
        assert hb.agent_id == "observer.metrics.host1.abc12345"
        assert hb.status == "healthy"

    def test_status_string_values_accepted(self):
        """Verify that common status strings don't raise during model init."""
        for status in ("healthy", "degraded", "dead"):
            hb = AgentHeartbeat(
                agent_id=f"agent.test.{status}",
                agent_type="test",
                status=status,
            )
            assert hb.status == status


class TestBaseMetadata:
    def test_all_three_tables_registered(self):
        table_names = set(Base.metadata.tables.keys())
        assert {"incidents", "anomalies", "agent_heartbeats"}.issubset(table_names)
