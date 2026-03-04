"""Tests for AgentRouter — registration, pruning, routing."""

import sys
import os
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

from agent_router import AgentRouter, AgentInfo, HEARTBEAT_TIMEOUT_SECONDS


@pytest.fixture
def mock_nats():
    nats = MagicMock()
    nats.publish = AsyncMock()
    return nats


@pytest.fixture
def router(mock_nats):
    return AgentRouter(mock_nats)


class TestUpdateAgentStatus:
    def test_register_new_agent(self, router):
        info = router.update_agent_status({
            "agent_id": "observer.host1.abc",
            "agent_type": "agents.observer",
            "hostname": "host1",
            "status": "healthy",
            "uptime_seconds": 100,
        })
        assert info.agent_id == "observer.host1.abc"
        assert info.agent_type == "agents.observer"
        assert "observer.host1.abc" in router.registry

    def test_update_existing_agent(self, router):
        router.update_agent_status({
            "agent_id": "obs1",
            "agent_type": "agents.observer",
        })
        router.update_agent_status({
            "agent_id": "obs1",
            "agent_type": "agents.observer",
            "status": "degraded",
        })
        assert router.registry["obs1"].status == "degraded"


class TestGetAvailableAgents:
    def test_returns_healthy_agents(self, router):
        router.update_agent_status({
            "agent_id": "obs1", "agent_type": "agents.observer"
        })
        agents = router.get_available_agents("agents.observer")
        assert len(agents) == 1

    def test_excludes_dead_agents(self, router):
        router.update_agent_status({
            "agent_id": "obs1", "agent_type": "agents.observer"
        })
        router.registry["obs1"].status = "dead"
        agents = router.get_available_agents("agents.observer")
        assert len(agents) == 0

    def test_excludes_stale_agents(self, router):
        router.update_agent_status({
            "agent_id": "obs1", "agent_type": "agents.observer"
        })
        router.registry["obs1"].last_seen_at = datetime.utcnow() - timedelta(seconds=200)
        agents = router.get_available_agents("agents.observer")
        assert len(agents) == 0

    def test_filters_by_type(self, router):
        router.update_agent_status({"agent_id": "obs1", "agent_type": "agents.observer"})
        router.update_agent_status({"agent_id": "diag1", "agent_type": "agents.diagnoser"})
        assert len(router.get_available_agents("agents.observer")) == 1
        assert len(router.get_available_agents("agents.diagnoser")) == 1


class TestPruneStaleAgents:
    def test_marks_stale_as_dead(self, router):
        router.update_agent_status({"agent_id": "obs1", "agent_type": "agents.observer"})
        router.registry["obs1"].last_seen_at = datetime.utcnow() - timedelta(
            seconds=HEARTBEAT_TIMEOUT_SECONDS + 10
        )
        dead = router.prune_stale_agents()
        assert "obs1" in dead
        assert router.registry["obs1"].status == "dead"

    def test_does_not_re_mark_dead(self, router):
        router.update_agent_status({"agent_id": "obs1", "agent_type": "agents.observer"})
        router.registry["obs1"].status = "dead"
        router.registry["obs1"].last_seen_at = datetime.utcnow() - timedelta(seconds=200)
        dead = router.prune_stale_agents()
        assert len(dead) == 0

    def test_keeps_fresh_agents(self, router):
        router.update_agent_status({"agent_id": "obs1", "agent_type": "agents.observer"})
        dead = router.prune_stale_agents()
        assert len(dead) == 0


class TestRouting:
    @pytest.mark.asyncio
    async def test_route_to_diagnoser(self, router, mock_nats):
        await router.route_to_diagnoser("orch", "inc-1", {"test": True})
        mock_nats.publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_route_to_remediator(self, router, mock_nats):
        await router.route_to_remediator("orch", "inc-1", {"action": "restart"})
        mock_nats.publish.assert_called_once()


class TestGetAllAgents:
    def test_returns_all(self, router):
        router.update_agent_status({"agent_id": "obs1", "agent_type": "agents.observer"})
        router.update_agent_status({"agent_id": "diag1", "agent_type": "agents.diagnoser"})
        all_agents = router.get_all_agents()
        assert len(all_agents) == 2
