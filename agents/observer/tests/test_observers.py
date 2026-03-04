import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

from agents.observer.src.metrics_observer import MetricsObserver
from agents.observer.src.log_observer import LogObserver
from agents.observer.src.health_observer import HealthObserver
from agents.observer.src.synthetic_prober import SyntheticProber

# Mock NATS connectivity
@pytest.fixture
def mock_nats():
    with patch("shared.messaging.nats_client.NATSClient.connect", new_callable=AsyncMock) as mock:
        yield mock

@pytest.fixture
def mock_publish():
    with patch("shared.messaging.nats_client.NATSClient.publish", new_callable=AsyncMock) as mock:
        yield mock

@pytest.mark.asyncio
async def test_metrics_observer_success(mock_nats, mock_publish):
    observer = MetricsObserver(nats_url="nats://localhost:4222")
    
    # Mock HTTP response from Prometheus
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "status": "success",
        "data": {
            "result": [
                {
                    "metric": {"job": "payment-svc"},
                    "value": [1234567890, "0.15"]  # E.g., 15% error rate, triggering anomaly
                }
            ]
        }
    }
    
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
        await observer.poll_metrics()
        
    # It should have triggered an error_rate anomaly (since 0.15 > 0.05 default threshold)
    assert mock_publish.call_count >= 1
    call_args = mock_publish.call_args[0]
    subject, payload = call_args[0], call_args[1]
    
    assert subject == "agents.observer.anomalies"
    assert payload["message_type"] == "anomaly_detected"
    assert payload["payload"]["metric"] in ["cpu_usage", "error_rate", "latency_p99"]


@pytest.mark.asyncio
async def test_log_observer_success(mock_nats, mock_publish):
    observer = LogObserver(nats_url="nats://localhost:4222")
    
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "status": "success",
        "data": {
            "result": [
                {
                    "stream": {"container": "auth-svc"},
                    "values": [
                        ["1234567890", "ERROR Exception handling request"]
                    ]
                }
            ]
        }
    }
    
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
        await observer.poll_logs(1234567800)
        
    assert mock_publish.call_count >= 1
    call_args = mock_publish.call_args[0]
    assert call_args[0] == "agents.observer.anomalies"
    assert call_args[1]["payload"]["service"] == "auth-svc"


@pytest.mark.asyncio
async def test_health_observer_failure(mock_nats, mock_publish):
    observer = HealthObserver(nats_url="nats://localhost:4222")
    observer.targets = [{"service": "test-svc", "url": "http://test-svc/health"}]
    
    mock_resp = MagicMock()
    mock_resp.status_code = 500  # Return 500
    mock_resp.json.return_value = {"status": "error"}
    
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
        await observer.probe_endpoints()
        
    assert mock_publish.call_count == 1
    call_args = mock_publish.call_args[0]
    assert call_args[1]["payload"]["service"] == "test-svc"
    assert call_args[1]["payload"]["value"] == 0


@pytest.mark.asyncio
async def test_synthetic_prober_failure(mock_nats, mock_publish):
    observer = SyntheticProber(nats_url="nats://localhost:4222")
    
    # Simulate a timeout during checkout flow
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=httpx.RequestError("Timeout", request=MagicMock())):
        await observer.simulate_checkout_flow()
        
    assert mock_publish.call_count == 1
    call_args = mock_publish.call_args[0]
    assert call_args[1]["payload"]["metric"] == "e2e_checkout"
    assert call_args[1]["payload"]["service"] == "api-gateway"
