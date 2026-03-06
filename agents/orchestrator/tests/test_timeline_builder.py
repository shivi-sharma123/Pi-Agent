"""Tests for TimelineBuilder — add_event, generate_postmortem."""

import sys
import os
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from timeline_builder import add_event, generate_postmortem, EVENT_TYPES


class TestAddEvent:
    def test_appends_event(self):
        timeline: list[dict] = []
        result = add_event(timeline, "anomaly_detected", "observer.metrics", "High CPU")
        assert len(result) == 1
        assert result[0]["event_type"] == "anomaly_detected"
        assert result[0]["agent"] == "observer.metrics"
        assert result[0]["summary"] == "High CPU"
        assert "timestamp" in result[0]

    def test_multiple_events(self):
        timeline: list[dict] = []
        add_event(timeline, "anomaly_detected", "observer", "Anomaly 1")
        add_event(timeline, "diagnosis_started", "diagnoser", "Starting RCA")
        assert len(timeline) == 2

    def test_with_details(self):
        timeline: list[dict] = []
        add_event(timeline, "diagnosis_complete", "diagnoser", "Found issue",
                  {"confidence": 85})
        assert timeline[0]["details"]["confidence"] == 85

    def test_returns_same_list(self):
        timeline: list[dict] = []
        result = add_event(timeline, "resolved", "orchestrator", "Done")
        assert result is timeline


class TestGeneratePostmortem:
    def test_basic_postmortem(self):
        now = datetime.now(timezone.utc)
        incident = {
            "id": "inc-1",
            "status": "resolved",
            "severity": "high",
            "created_at": (now - timedelta(minutes=10)).isoformat(),
            "resolved_at": now.isoformat(),
            "timeline": [
                {"event_type": "anomaly_detected", "timestamp": (now - timedelta(minutes=10)).isoformat()},
                {"event_type": "diagnosis_complete", "timestamp": (now - timedelta(minutes=8)).isoformat()},
                {"event_type": "safety_approved", "timestamp": (now - timedelta(minutes=5)).isoformat()},
                {"event_type": "resolved", "timestamp": now.isoformat()},
            ],
            "root_cause_category": "memory_leak",
            "root_cause_service": "user-svc",
            "resolution_summary": "Container restarted",
        }
        pm = generate_postmortem(incident)
        assert pm["incident_id"] == "inc-1"
        assert pm["severity"] == "high"
        assert pm["duration_seconds"] is not None
        assert abs(pm["duration_seconds"] - 600) < 5
        assert pm["total_events"] == 4
        assert pm["root_cause"] == "memory_leak"
        assert len(pm["key_decisions"]) == 1  # safety_approved

    def test_empty_timeline(self):
        pm = generate_postmortem({"id": "inc-2", "timeline": []})
        assert pm["total_events"] == 0
        assert pm["state_durations"] == {}

    def test_missing_fields(self):
        pm = generate_postmortem({})
        assert pm["incident_id"] is None
        assert pm["duration_seconds"] is None


class TestEventTypes:
    def test_all_event_types_valid(self):
        assert "anomaly_detected" in EVENT_TYPES
        assert "resolved" in EVENT_TYPES
        assert "closed" in EVENT_TYPES
        assert len(EVENT_TYPES) == 12
