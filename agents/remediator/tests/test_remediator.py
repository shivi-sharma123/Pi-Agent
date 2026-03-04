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
