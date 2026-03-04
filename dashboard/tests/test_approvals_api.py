"""Tests for approvals API schemas."""

import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.schemas import ApprovalAction, ApprovalRequest


class TestApprovalSchemas:
    def test_approval_request_schema(self):
        req = ApprovalRequest(
            id="inc-1",
            incident_id="inc-1",
            action_type="container_restart",
            risk_level="medium",
            reason="Needs human review",
            created_at=datetime.utcnow(),
        )
        assert req.status == "pending"
        assert req.action_type == "container_restart"

    def test_approval_action_schema(self):
        action = ApprovalAction(reason="Looks good")
        assert action.reason == "Looks good"

    def test_approval_action_empty_reason(self):
        action = ApprovalAction()
        assert action.reason == ""
