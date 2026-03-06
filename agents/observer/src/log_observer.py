import asyncio
import logging
import urllib.parse
from datetime import datetime, timedelta, timezone

import httpx

from agents.observer.src.deduplicator import AlertDeduplicator
from shared.agents.base import BaseAgent
from shared.messaging.schema import AgentMessage

logger = logging.getLogger(__name__)


class LogObserver(BaseAgent):
    """
    Observer Agent that periodically queries Loki for critical log patterns
    (e.g., Exceptions, OOMKilled, ECONNREFUSED) across all services.
    Publishes anomalies to NATS.
    """

    agent_type = "observer.logs"

    def __init__(self, nats_url: str, loki_url: str = "http://loki:3100"):
        super().__init__(nats_url=nats_url)
        self.loki_url = loki_url
        # Logs don't need a sliding window baseline, but they DO need deduplication
        self.deduplicator = AlertDeduplicator(window_seconds=300, max_per_window=1)
        
        self.http_client = httpx.AsyncClient(timeout=5.0)
        
        # We query the last N seconds
        self.poll_interval = 15
        
        # LogQL queries for bad patterns
        self.queries = [
            {
                "name": "unhandled_exception",
                "logql": '{container=~".+-svc|.*-worker"} |= "Exception" != "Failed to get message"',
                "severity": "high"
            },
            {
                "name": "connection_refused",
                "logql": '{container=~".+-svc|.*-worker"} |= "ECONNREFUSED"',
                "severity": "critical"
            },
            {
                "name": "oom_killed",
                "logql": '{container=~".+-svc|.*-worker"} |= "OOMKilled"',
                "severity": "critical"
            }
        ]

    async def setup(self):
        logger.info("LogObserver setup complete", loki_url=self.loki_url)

    async def run_loop(self):
        # Query window: now minus polling interval, minus a few seconds for ingestion buffer
        start_time = datetime.now(timezone.utc) - timedelta(seconds=self.poll_interval + 5)
        start_ts = int(start_time.timestamp() * 1e9)  # Loki wants nanoseconds
        
        await self.poll_logs(start_ts)
        await asyncio.sleep(self.poll_interval)

    async def teardown(self):
        await self.http_client.aclose()
        logger.info("LogObserver shutting down")

    async def poll_logs(self, start_ts: int):
        for q in self.queries:
            try:
                # Loki Query API
                params = {
                    "query": q["logql"],
                    "start": str(start_ts),
                    "limit": 100
                }
                url = f"{self.loki_url}/loki/api/v1/query_range"
                
                response = await self.http_client.get(url, params=params)
                response.raise_for_status()
                data = response.json()
                
                if data.get("status") != "success":
                    logger.error("Loki query failed", query=q["name"], error=data)
                    continue

                results = data.get("data", {}).get("result", [])
                
                for r in results:
                    stream = r.get("stream", {})
                    # Get service name from labels
                    service = stream.get("container") or stream.get("job") or "unknown"
                    
                    values = r.get("values", [])
                    if not values:
                        continue
                        
                    # We got bad logs! Pick the first one as representative for the anomaly
                    timestamp_ns, log_line = values[0]
                    
                    # Construct a raw faux-anomaly result for the deduplicator to use
                    from agents.observer.src.detector import AnomalyResult
                    anomaly = AnomalyResult(
                        metric=q["name"],
                        service=service,
                        severity=q["severity"],
                        value=len(values), # Number of bad log lines found
                        threshold_type="log_pattern",
                        description=f"Matched log pattern: {log_line[:200]}...",
                        labels=stream,
                        raw_payload=values
                    )
                    
                    if not self.deduplicator.is_duplicate(anomaly):
                        await self.publish_anomaly(anomaly)
                            
            except httpx.RequestError as e:
                logger.error("Failed to connect to Loki", error=str(e))
            except Exception as e:
                logger.exception("Unexpected error in poll_logs")

    async def publish_anomaly(self, anomaly):
        payload = anomaly.to_dict()
        msg = AgentMessage(
            source_agent=self.agent_id,
            message_type="anomaly_detected",
            payload=payload
        )
        
        logger.warning(
            f"Emitting Log Anomaly - Metric: {anomaly.metric}, Service: {anomaly.service}, Severity: {anomaly.severity}, Lines Matched: {anomaly.value}"
        )
        
        await self.nats.publish("agents.observer.anomalies", msg)
        self._increment_processed(1)
