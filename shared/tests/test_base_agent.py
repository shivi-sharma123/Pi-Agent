"""
Unit tests for shared.agents.base — BaseAgent lifecycle and configuration.

Tests use a minimal ConcreteAgent subclass that doesn't require real
NATS/DB connections. NATS is fully mocked via unittest.mock.
"""
from __future__ import annotations

import asyncio
import signal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.agents.base import BaseAgent


# ---------------------------------------------------------------------------
# Test fixture: minimal concrete agent
# ---------------------------------------------------------------------------

class ConcreteAgent(BaseAgent):
    """Minimal BaseAgent subclass for unit testing."""

    agent_type = "test.agent"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setup_called = False
        self.teardown_called = False
        self.run_loop_count = 0

    async def setup(self) -> None:
        self.setup_called = True

    async def run_loop(self) -> None:
        self.run_loop_count += 1
        # Stop after first iteration so the test doesn't loop forever
        await self.stop()

    async def teardown(self) -> None:
        self.teardown_called = True


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBaseAgentInit:
    def test_agent_id_contains_type_and_hostname(self):
        agent = ConcreteAgent()
        assert "test.agent" in agent.agent_id

    def test_custom_heartbeat_interval(self):
        agent = ConcreteAgent(heartbeat_interval=60)
        assert agent.heartbeat_interval == 60

    def test_custom_nats_connect_timeout(self):
        agent = ConcreteAgent(nats_connect_timeout=30)
        assert agent.nats_connect_timeout == 30

    def test_default_nats_connect_timeout_is_set(self):
        agent = ConcreteAgent()
        # Must be a positive integer (default is 10 from settings fallback)
        assert isinstance(agent.nats_connect_timeout, int)
        assert agent.nats_connect_timeout > 0

    def test_two_agents_have_different_ids(self):
        a1 = ConcreteAgent()
        a2 = ConcreteAgent()
        assert a1.agent_id != a2.agent_id

    def test_running_is_false_before_start(self):
        agent = ConcreteAgent()
        assert agent._running is False


class TestBaseAgentLifecycle:
    """Test that start() calls the correct lifecycle hooks."""

    @pytest.mark.asyncio
    async def test_lifecycle_hooks_called(self):
        agent = ConcreteAgent()

        # Fully mock out NATS so no real connection is made
        mock_nats = AsyncMock()
        agent.nats = mock_nats

        with patch("asyncio.wait_for", new=AsyncMock(return_value=None)):
            await agent.start()

        assert agent.setup_called, "setup() must be called during start()"
        assert agent.teardown_called, "teardown() must be called on shutdown"
        assert agent.run_loop_count >= 1, "run_loop() must be called at least once"

    @pytest.mark.asyncio
    async def test_nats_connect_timeout_raises_on_timeout(self):
        agent = ConcreteAgent(nats_connect_timeout=1)
        mock_nats = AsyncMock()
        agent.nats = mock_nats

        # Simulate asyncio.wait_for raising TimeoutError
        with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
            with pytest.raises(RuntimeError, match="NATS connect timeout"):
                await agent.start()

    @pytest.mark.asyncio
    async def test_stop_sets_running_false(self):
        agent = ConcreteAgent()
        agent._running = True
        await agent.stop()
        assert agent._running is False


class TestBaseAgentCounters:
    def test_increment_processed(self):
        agent = ConcreteAgent()
        agent._increment_processed(5)
        assert agent._messages_processed == 5

    def test_increment_errors(self):
        agent = ConcreteAgent()
        agent._increment_errors(2)
        agent._increment_errors(1)
        assert agent._errors == 3
