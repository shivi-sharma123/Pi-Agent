"""Tests for WebSocket connection manager."""

import sys
import os
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.websocket.manager import ConnectionManager


@pytest.fixture
def manager():
    return ConnectionManager()


@pytest.fixture
def mock_ws():
    ws = AsyncMock()
    ws.accept = AsyncMock()
    ws.send_text = AsyncMock()
    return ws


class TestConnectionManager:
    @pytest.mark.asyncio
    async def test_connect(self, manager, mock_ws):
        await manager.connect(mock_ws)
        assert manager.connection_count == 1
        mock_ws.accept.assert_called_once()

    def test_disconnect(self, manager, mock_ws):
        manager.active_connections.append(mock_ws)
        manager.disconnect(mock_ws)
        assert manager.connection_count == 0

    def test_disconnect_not_connected(self, manager, mock_ws):
        manager.disconnect(mock_ws)  # should not raise
        assert manager.connection_count == 0

    @pytest.mark.asyncio
    async def test_broadcast(self, manager, mock_ws):
        await manager.connect(mock_ws)
        await manager.broadcast("incident.created", {"id": "inc-1"})
        mock_ws.send_text.assert_called_once()
        sent = mock_ws.send_text.call_args[0][0]
        assert "incident.created" in sent
        assert "inc-1" in sent

    @pytest.mark.asyncio
    async def test_broadcast_removes_dead_connections(self, manager):
        good_ws = AsyncMock()
        good_ws.accept = AsyncMock()
        good_ws.send_text = AsyncMock()

        bad_ws = AsyncMock()
        bad_ws.accept = AsyncMock()
        bad_ws.send_text = AsyncMock(side_effect=Exception("connection closed"))

        await manager.connect(good_ws)
        await manager.connect(bad_ws)
        assert manager.connection_count == 2

        await manager.broadcast("test", {"data": 1})
        assert manager.connection_count == 1

    @pytest.mark.asyncio
    async def test_multiple_clients(self, manager):
        ws1 = AsyncMock()
        ws1.accept = AsyncMock()
        ws1.send_text = AsyncMock()
        ws2 = AsyncMock()
        ws2.accept = AsyncMock()
        ws2.send_text = AsyncMock()

        await manager.connect(ws1)
        await manager.connect(ws2)
        await manager.broadcast("test", {})
        ws1.send_text.assert_called_once()
        ws2.send_text.assert_called_once()
