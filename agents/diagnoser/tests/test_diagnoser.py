import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from agents.diagnoser.src.context_collector import ContextCollector
from agents.diagnoser.src.correlation_engine import CorrelationEngine
from agents.diagnoser.src.hypothesis_generator import HypothesisGenerator
from agents.diagnoser.src.rca_engine import RCAEngine
from shared.messaging.schema import AgentMessage
from shared.db.models import Incident

@pytest.fixture
def mock_httpx_get():
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock:
        yield mock

@pytest.mark.asyncio
async def test_context_collector(mock_httpx_get):
    collector = ContextCollector()
    mock_resp_loki = MagicMock()
    mock_resp_loki.status_code = 200
    mock_resp_loki.json.return_value = {
        "status": "success",
        "data": {
            "result": [
                {"values": [["12345", "ERROR: DB connection failed"]]}
            ]
        }
    }
    
    mock_resp_prom = MagicMock()
    mock_resp_prom.status_code = 200
    mock_resp_prom.json.return_value = {
        "status": "success",
        "data": {"result": [{"value": [12345, "0.15"]}]}
    }
    
    # We set side_effect to return Loki then Prom then Prom
    mock_httpx_get.side_effect = [mock_resp_loki, mock_resp_prom, mock_resp_prom]
    
    anomaly = {"service": "test-svc", "timestamp": "2023-01-01T12:00:00Z"}
    context = await collector.collect_context(anomaly)
    
    assert "ERROR: DB connection failed" in context["context"]["logs"]
    assert "0.1500" in context["context"]["metrics_summary"]

@pytest.mark.asyncio
async def test_hypothesis_generator():
    with patch.dict("os.environ", {"OPENAI_API_KEY": ""}):
        generator = HypothesisGenerator() # No API key should fall back to dummy
        context = {"anomaly": {"service": "test-svc", "metric": "error_rate"}}
        diagnosis, confidence = await generator.generate_hypothesis("inc-123", context)
        
        assert diagnosis["root_cause_service"] == "test-svc"
        assert "error_rate" in diagnosis.get("diagnosis_summary", "") or "Dummy inference" in diagnosis.get("diagnosis_summary", "")
        # Dummy generator sets confidence to 60
        assert confidence == 60

@pytest.fixture
def mock_session():
    with patch("agents.diagnoser.src.correlation_engine.get_session") as mock_maker:
        mock_session_inst = AsyncMock()
        context_manager = MagicMock()
        context_manager.__aenter__.return_value = mock_session_inst
        mock_maker.return_value = context_manager
        yield mock_session_inst

@pytest.mark.asyncio
async def test_correlation_engine_new_incident(mock_session):
    engine = CorrelationEngine()
    
    mock_result = MagicMock()
    mock_result.scalars().all.return_value = [] # No active incidents
    mock_session.execute.return_value = mock_result
    
    def side_effect_flush():
        pass
    mock_session.flush.side_effect = side_effect_flush
    
    incident, created = await engine.correlate({"service": "test-svc", "severity": "high", "metric": "cpu"})
    
    assert created is True
    assert incident.status == "detecting"
    
@pytest.mark.asyncio
async def test_rca_engine():
    with patch("shared.messaging.nats_client.NATSClient.connect", new_callable=AsyncMock):
        with patch("shared.messaging.nats_client.NATSClient.subscribe", new_callable=AsyncMock) as mock_sub:
            with patch("shared.messaging.nats_client.NATSClient.publish", new_callable=AsyncMock) as mock_pub:
                agent = RCAEngine(nats_url="nats://localhost:4222")
                await agent.setup()
                mock_sub.assert_called_once()
                
                # Mock components
                agent.correlator.correlate = AsyncMock(return_value=(Incident(id="inc-123", status="detecting"), True))
                agent.collector.collect_context = AsyncMock(return_value={})
                agent.hypothesis_gen.generate_hypothesis = AsyncMock(return_value=({"root_cause_service": "test"}, 80))
                
                with patch("agents.diagnoser.src.rca_engine.get_session") as mock_maker:
                    mock_session_inst = AsyncMock()
                    ctx = MagicMock()
                    ctx.__aenter__.return_value = mock_session_inst
                    mock_maker.return_value = ctx
                    
                    mock_session_inst.get.return_value = Incident(id="inc-123")
                    
                    msg = AgentMessage(source_agent="metrics_observer", message_type="anomaly_detected", payload={"service": "test-svc"})
                    await agent.handle_anomaly(msg)
                    
                assert mock_pub.call_count == 1
                assert agent._messages_processed == 1
