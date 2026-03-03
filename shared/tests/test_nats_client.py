"""
Unit tests for the NATSClient build_message helper.
"""

from __future__ import annotations

import pytest

from shared.messaging.nats_client import build_message
from shared.messaging.schema import AgentMessage


class TestBuildMessage:
    def test_required_fields_are_set(self):
        msg = build_message(
            source_agent="observer.metrics",
            target_agent="orchestrator",
            message_type="anomaly_detected",
            payload={"metric": "cpu"},
        )
        assert isinstance(msg, AgentMessage)
        assert msg.source_agent == "observer.metrics"
        assert msg.target_agent == "orchestrator"
        assert msg.message_type == "anomaly_detected"
        assert msg.payload == {"metric": "cpu"}

    def test_correlation_id_is_used_when_provided(self):
        msg = build_message(
            source_agent="a",
            target_agent="b",
            message_type="test",
            payload={},
            correlation_id="incident-xyz-123",
        )
        assert msg.correlation_id == "incident-xyz-123"

    def test_default_correlation_id_is_generated(self):
        msg = build_message(
            source_agent="a",
            target_agent="b",
            message_type="test",
            payload={},
        )
        # Auto-generated — just check it's a string of reasonable length
        assert len(msg.correlation_id) == 36

    def test_priority_and_ttl_defaults(self):
        msg = build_message(source_agent="a", target_agent="b", message_type="t", payload={})
        assert msg.priority == 2
        assert msg.ttl_seconds == 300

    def test_context_is_passed_through(self):
        ctx = {"incident_id": "abc", "phase": "detecting"}
        msg = build_message(
            source_agent="a", target_agent="b", message_type="t",
            payload={}, context=ctx,
        )
        assert msg.context["incident_id"] == "abc"
