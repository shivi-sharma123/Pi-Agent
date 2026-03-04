import pytest
import asyncio
import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from policy_engine import PolicyEngine
from blast_radius import BlastRadiusCalculator
from rate_limiter import RateLimiter
from approval_gateway import HumanApprovalGateway

@pytest.fixture
def policy_engine():
    return PolicyEngine()

@pytest.fixture
def blast_calc():
    return BlastRadiusCalculator()

@pytest.fixture
def rate_limiter():
    return RateLimiter()

def test_policy_banned_actions(policy_engine):
    banned_action = {
        "type": "container_restart",
        "params": {"target": "postgres-agents"},
        "risk": "low"
    }
    allowed_action = {
        "type": "container_restart",
        "params": {"target": "order-svc"},
        "risk": "low",
        "approval_required": False
    }

    ok, _ = policy_engine.evaluate(banned_action)
    assert not ok

    ok, _ = policy_engine.evaluate(allowed_action)
    assert ok

def test_policy_high_risk(policy_engine):
    high_risk_action = {
        "type": "container_restart",
        "params": {"target": "order-svc"},
        "risk": "high"
    }

    ok, reason = policy_engine.evaluate(high_risk_action)
    assert not ok
    assert "human approval" in reason.lower()

def test_blast_radius_calculator(blast_calc):
    # Testing a core dependency
    res = blast_calc.calculate({
        "params": {"target": "redis"}
    })
    
    assert res["risk_level"] == "critical"
    assert "user-svc" in res["affected_services"]
    assert "auth-svc" in res["affected_services"]

    # Testing an edge/leaf node
    leaf_res = blast_calc.calculate({
        "params": {"target": "api-gateway"}
    })
    
    assert leaf_res["risk_level"] == "low"
    assert len(leaf_res["affected_services"]) == 0

def test_rate_limiter(rate_limiter):
    action = {"type": "restart", "params": {"target": "order-svc"}}
    
    # 1st attempt should pass
    ok, _ = rate_limiter.check(action)
    assert ok
    rate_limiter.record(action)
    
    # Immediately retrying the EXACT action should hit the cooldown
    ok, reason = rate_limiter.check(action)
    assert not ok
    assert "cooldown" in reason.lower()

    # Fast forward time to test limit per hour
    # We'll artificially inject events past the cooldown
    now = datetime.utcnow()
    past_10_min = now - timedelta(minutes=20)
    past_30_min = now - timedelta(minutes=40)
    
    rate_limiter.action_history = [
        {"fingerprint": rate_limiter._fingerprint(action), "timestamp": past_10_min, "action": action},
        {"fingerprint": rate_limiter._fingerprint(action), "timestamp": past_30_min, "action": action},
        # (the initial one at `now` is gone)
    ]
    
    # Now try a 3rd time (Limit is 3)
    ok, _ = rate_limiter.check(action)
    assert ok # this is #3, passes
    rate_limiter.record(action) # records #3
    
    # Now try a 4th time (Limit exceeded)
    ok, reason = rate_limiter.check(action)
    assert not ok
    assert "rate limit exceeded" in reason.lower()

def test_human_approval_formatting():
    gateway = HumanApprovalGateway()
    
    res = gateway.format_approval_request(
        incident_id="incident-123",
        diagnosis={"root_cause": {"service": "redis", "category": "memory_leak"}},
        action={"type": "restart", "params": {"target": "redis"}},
        policy_reason="High risk target",
        blast_info={"risk_level": "critical", "affected_services": ["user-svc"]}
    )

    assert res["status"] == "pending_human_approval"
    assert res["incident_id"] == "incident-123"
    assert res["proposed_action"]["type"] == "restart"
    assert res["context"]["root_cause_service"] == "redis"
