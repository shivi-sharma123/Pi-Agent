"""Tests for incidents API endpoints."""

import sys
import os
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestIncidentSchemas:
    """Test Pydantic schema validation."""

    def test_incident_summary_schema(self):
        from api.schemas import IncidentSummary
        summary = IncidentSummary(
            id="inc-1",
            status="detecting",
            severity="high",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        assert summary.id == "inc-1"
        assert summary.auto_resolved is False

    def test_incident_detail_schema(self):
        from api.schemas import IncidentDetail
        detail = IncidentDetail(
            id="inc-1",
            status="resolved",
            severity="critical",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            state_entered_at=datetime.utcnow(),
            resolved_at=datetime.utcnow(),
            auto_resolved=True,
            resolution_summary="Container restarted",
        )
        assert detail.auto_resolved is True

    def test_incident_stats_schema(self):
        from api.schemas import IncidentStats
        stats = IncidentStats(
            total=10,
            by_status={"detecting": 2, "resolved": 8},
            resolved_today=3,
        )
        assert stats.total == 10

    def test_timeline_event_schema(self):
        from api.schemas import TimelineEvent
        event = TimelineEvent(
            event_type="anomaly_detected",
            agent="observer.metrics",
            summary="High CPU detected",
            timestamp=datetime.utcnow().isoformat(),
        )
        assert event.event_type == "anomaly_detected"
