"""
Unit tests for the AgentMessage schema.

Tests cover:
  - Default field generation (UUID, timestamp)
  - Serialisation to dict
  - Round-trip deserialisation from dict
  - TTL / expiry logic
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta

import pytest

from shared.messaging.schema import AgentMessage


class TestAgentMessage:
    def test_default_ids_are_uuids(self):
        msg = AgentMessage()
        assert len(msg.message_id) == 36
        assert len(msg.correlation_id) == 36
        assert len(msg.trace_id) == 36

    def test_two_messages_have_different_ids(self):
        a = AgentMessage()
        b = AgentMessage()
        assert a.message_id != b.message_id
        assert a.correlation_id != b.correlation_id

    def test_to_dict_contains_all_fields(self):
        msg = AgentMessage(
            source_agent="observer.metrics",
            target_agent="orchestrator",
            message_type="anomaly_detected",
            payload={"metric": "cpu_usage", "value": 95.0},
            priority=1,
        )
        d = msg.to_dict()
        assert d["source_agent"] == "observer.metrics"
        assert d["target_agent"] == "orchestrator"
        assert d["message_type"] == "anomaly_detected"
        assert d["payload"]["metric"] == "cpu_usage"
        assert d["priority"] == 1
        assert "timestamp" in d

    def test_round_trip_serialisation(self):
        original = AgentMessage(
            source_agent="diagnoser",
            target_agent="orchestrator",
            message_type="diagnosis_complete",
            payload={"root_cause": "memory_leak", "confidence": 85},
            context={"incident_id": "test-123"},
        )
        restored = AgentMessage.from_dict(original.to_dict())
        assert restored.message_id == original.message_id
        assert restored.correlation_id == original.correlation_id
        assert restored.source_agent == original.source_agent
        assert restored.message_type == original.message_type
        assert restored.payload["confidence"] == 85

    def test_is_expired_returns_false_for_fresh_message(self):
        msg = AgentMessage(ttl_seconds=300)
        assert not msg.is_expired()

    def test_is_expired_returns_true_for_old_message(self):
        msg = AgentMessage(ttl_seconds=1)
        # Backdate the timestamp to make it appear 2 seconds old
        msg.timestamp = datetime.utcnow() - timedelta(seconds=2)
        assert msg.is_expired()

    def test_from_dict_handles_missing_optional_fields(self):
        """from_dict should work with a minimal dict (defaults applied)."""
        msg = AgentMessage.from_dict({
            "message_id": "abc-123",
            "message_type": "test",
        })
        assert msg.message_id == "abc-123"
        assert msg.priority == 2  # default
        assert msg.payload == {}

    def test_payload_is_independent_between_instances(self):
        """Payload dicts should not be shared between instances."""
        a = AgentMessage()
        b = AgentMessage()
        a.payload["key"] = "value"
        assert "key" not in b.payload
