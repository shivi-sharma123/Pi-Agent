"""
Tests for Analytics Worker handlers.
"""
import pytest
from unittest.mock import AsyncMock, patch
from app.main import handle_order_created, api
from fastapi.testclient import TestClient

client = TestClient(api)

@patch("app.main.get_redis")
def test_health_endpoint(mock_get_redis):
    mock_redis = AsyncMock()
    mock_get_redis.return_value = mock_redis
    
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"

@pytest.mark.asyncio
@patch("app.main.get_redis")
async def test_handle_order_created(mock_get_redis):
    mock_redis = AsyncMock()
    mock_get_redis.return_value = mock_redis
    
    await handle_order_created({
        "id": "ord-1",
        "total": "100.0"
    })
    
    # Should incr order count
    assert mock_redis.incr.call_count == 1
    # Should incr revenue
    mock_redis.incrbyfloat.assert_called_once()
    assert float(mock_redis.incrbyfloat.call_args[0][1]) == 100.0
