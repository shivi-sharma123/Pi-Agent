import pytest
import os
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from runbook_engine import RunbookEngine
from action_executor import ActionExecutor
from verification_engine import VerificationEngine
from rollback_manager import RollbackManager

TEST_RUNBOOK_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "runbooks"))

@pytest.fixture
def runbook_engine():
    return RunbookEngine(runbook_dir=TEST_RUNBOOK_DIR)

@pytest.fixture
def executor():
    ex = ActionExecutor()
    # Mock the Docker API away completely
    ex.client = None
    return ex

@pytest.fixture
def verify_engine():
    return VerificationEngine()

def test_runbook_loader(runbook_engine):
    assert len(runbook_engine.runbooks) >= 2
    assert "runbook_memory_leak" in runbook_engine.runbooks

def test_runbook_matcher_success(runbook_engine):
    diagnosis = {
        "root_cause": {
            "category": "database_overload",
            "service": "postgres-orders",
            "confidence": 85
        }
    }
    match = runbook_engine.find_match(diagnosis)
    assert match is not None
    assert match["id"] == "runbook_database_overload"

def test_runbook_matcher_fail_confidence(runbook_engine):
    diagnosis = {
        "root_cause": {
            "category": "network_partition",
            "service": "api-gateway",
            "confidence": 30 # Less than 70 threshold
        }
    }
    match = runbook_engine.find_match(diagnosis)
    assert match is None

def test_action_rendering(runbook_engine):
    raw_action = {
        "type": "container_restart",
        "params": {"target": "{{diagnosis.root_cause.service}}"}
    }
    diagnosis = {"root_cause": {"service": "redis-session"}}
    
    rendered = runbook_engine.render_action(raw_action, diagnosis)
    assert rendered["params"]["target"] == "redis-session"

def test_dummy_action_executor(executor):
    action = {"type": "container_restart", "params": {"target": "user-svc"}}
    ok, msg = executor.execute(action)
    assert ok
    assert "dummy mode" in msg.lower()

    bad_action = {"type": "invalid_type", "params": {}}
    ok, msg = executor.execute(bad_action)
    assert not ok
    assert "unknown action type" in msg.lower()

@pytest.mark.asyncio
async def test_verification_engine_no_checks(verify_engine):
    runbook = {"id": "fake", "verification": {"checks": []}}
    ok, msg = await verify_engine.verify(runbook, {})
    assert ok
    assert "passed" in msg.lower()

def test_rollback_manager(executor):
    rm = RollbackManager(executor)
    # Action without rollback definition
    action_no_rb = {"id": "act-1"}
    assert rm.rollback(action_no_rb) == False
    
    # Action with rollback definition
    action_with_rb = {
        "id": "scale_up", 
        "rollback": {
            "type": "container_restart", 
            "params": {"target": "foo"}
        }
    }
    assert rm.rollback(action_with_rb) == True

# ---------------------------------------------------------------------------
# Task 4.1.7 — Per-runbook YAML action tests
# ---------------------------------------------------------------------------

class TestMemoryLeakRunbook:
    """Verify the memory_leak.yml runbook matches and exposes correct actions."""

    def test_matches_with_sufficient_confidence(self, runbook_engine):
        diagnosis = {
            "root_cause": {
                "category": "memory_leak",
                "service": "user-svc",
                "confidence": 75,
            }
        }
        match = runbook_engine.find_match(diagnosis)
        assert match is not None
        assert match["id"] == "runbook_memory_leak"

    def test_matches_at_minimum_confidence(self, runbook_engine):
        """memory_leak runbook has confidence_minimum: 50 — should match at exactly 50."""
        diagnosis = {
            "root_cause": {
                "category": "memory_leak",
                "service": "payment-svc",
                "confidence": 50,
            }
        }
        match = runbook_engine.find_match(diagnosis)
        assert match is not None, "Should match at exactly the minimum confidence threshold"

    def test_action_is_container_restart(self, runbook_engine):
        """First action must be a container_restart targeting the diagnosed service."""
        diagnosis = {
            "root_cause": {
                "category": "memory_leak",
                "service": "order-svc",
                "confidence": 80,
            }
        }
        match = runbook_engine.find_match(diagnosis)
        assert match is not None
        actions = match.get("actions", [])
        assert len(actions) >= 1, "Runbook must have at least one action"
        first_action = actions[0]
        assert first_action["type"] == "container_restart"

    def test_action_template_renders_service(self, runbook_engine):
        """The target param should resolve to the diagnosed service name after rendering."""
        raw_action = {
            "type": "container_restart",
            "params": {"target": "{{diagnosis.root_cause.service}}"},
        }
        diagnosis = {"root_cause": {"service": "payment-svc"}}
        rendered = runbook_engine.render_action(raw_action, diagnosis)
        assert rendered["params"]["target"] == "payment-svc"


class TestNetworkPartitionRunbook:
    """Verify the network_partition.yml runbook matches and exposes correct actions."""

    def test_matches_with_sufficient_confidence(self, runbook_engine):
        diagnosis = {
            "root_cause": {
                "category": "network_partition",
                "service": "auth-svc",
                "confidence": 80,
            }
        }
        match = runbook_engine.find_match(diagnosis)
        assert match is not None
        assert match["id"] == "runbook_network_partition"

    def test_does_not_match_below_threshold(self, runbook_engine):
        """network_partition has confidence_minimum: 70 — 69 should not match."""
        diagnosis = {
            "root_cause": {
                "category": "network_partition",
                "service": "auth-svc",
                "confidence": 69,
            }
        }
        match = runbook_engine.find_match(diagnosis)
        assert match is None

    def test_action_is_circuit_breaker(self, runbook_engine):
        diagnosis = {
            "root_cause": {
                "category": "network_partition",
                "service": "auth-svc",
                "confidence": 90,
            }
        }
        match = runbook_engine.find_match(diagnosis)
        assert match is not None
        actions = match.get("actions", [])
        assert len(actions) >= 1
        first_action = actions[0]
        assert first_action["type"] == "circuit_breaker"

    def test_action_requires_approval(self, runbook_engine):
        """circuit_breaker on network_partition is high-risk and must require approval."""
        diagnosis = {
            "root_cause": {
                "category": "network_partition",
                "service": "api-gateway",
                "confidence": 85,
            }
        }
        match = runbook_engine.find_match(diagnosis)
        assert match is not None
        first_action = match["actions"][0]
        assert first_action.get("approval_required") is True


class TestDatabaseOverloadRunbook:
    """Verify the database_overload.yml runbook matches and exposes correct actions."""

    def test_has_at_least_one_action(self, runbook_engine):
        diagnosis = {
            "root_cause": {
                "category": "database_overload",
                "service": "postgres-payments",
                "confidence": 75,
            }
        }
        match = runbook_engine.find_match(diagnosis)
        assert match is not None
        assert len(match.get("actions", [])) >= 1

    def test_action_targets_pgbouncer(self, runbook_engine):
        """database_overload runbook must restart pgbouncer (static target, not templated)."""
        diagnosis = {
            "root_cause": {
                "category": "database_overload",
                "service": "postgres-orders",
                "confidence": 85,
            }
        }
        match = runbook_engine.find_match(diagnosis)
        assert match is not None
        first_action = match["actions"][0]
        assert first_action["type"] == "container_restart"
        assert first_action["params"].get("target") == "pgbouncer"

    def test_action_requires_approval(self, runbook_engine):
        """database_overload action is medium risk and must require human approval."""
        diagnosis = {
            "root_cause": {
                "category": "database_overload",
                "service": "postgres-agents",
                "confidence": 80,
            }
        }
        match = runbook_engine.find_match(diagnosis)
        assert match is not None
        first_action = match["actions"][0]
        assert first_action.get("approval_required") is True

    def test_verification_has_wait_time(self, runbook_engine):
        """database_overload verification should wait longer (30s) for DB stabilization."""
        diagnosis = {
            "root_cause": {
                "category": "database_overload",
                "service": "postgres-payments",
                "confidence": 70,
            }
        }
        match = runbook_engine.find_match(diagnosis)
        assert match is not None
        verification = match.get("verification", {})
        assert verification.get("wait_seconds", 0) >= 30
