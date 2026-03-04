import asyncio
import logging
from typing import List, Dict

import httpx

from agents.observer.src.deduplicator import AlertDeduplicator
from agents.observer.src.detector import AnomalyResult
from shared.agents.base import BaseAgent
from shared.messaging.schema import AgentMessage

logger = logging.getLogger(__name__)


class HealthObserver(BaseAgent):
    """
    Observer Agent that actively probes HTTP endpoints (/health) 
    and publishes anomalies if they fail or time out.
    """

    agent_type = "observer.health"

    def __init__(self, nats_url: str):
        super().__init__(nats_url=nats_url)
        self.deduplicator = AlertDeduplicator(window_seconds=120, max_per_window=1)
        self.http_client = httpx.AsyncClient(timeout=3.0) # 3 second aggressive timeout
        
        self.poll_interval = 10 # 10 seconds probe
        
        self.targets: List[Dict[str, str]] = [
            {"service": "user-svc", "url": "http://user-svc:8001/health"},
            {"service": "auth-svc", "url": "http://auth-svc:8004/health"},
            {"service": "order-svc", "url": "http://order-svc:8002/health"},
            {"service": "payment-svc", "url": "http://payment-svc:8005/health"},
            {"service": "product-svc", "url": "http://product-svc:8003/health"},
            {"service": "search-svc", "url": "http://search-svc:8006/health"},
            {"service": "notification-worker", "url": "http://notification-worker:8007/health"},
            {"service": "inventory-worker", "url": "http://inventory-worker:8008/health"},
            {"service": "analytics-worker", "url": "http://analytics-worker:8009/health"},
        ]

    async def setup(self):
        logger.info("HealthObserver setup complete", targets=len(self.targets))

    async def run_loop(self):
        await self.probe_endpoints()
        await asyncio.sleep(self.poll_interval)

    async def teardown(self):
        await self.http_client.aclose()
        logger.info("HealthObserver shutting down")

    async def probe_endpoints(self):
        tasks = [self._probe(t) for t in self.targets]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for t, success in zip(self.targets, results):
            if isinstance(success, Exception):
                logger.error(f"Probe task crashed for {t['service']} - Error: {success}")
                continue
                
            if not success:
               anomaly = AnomalyResult(
                   metric="http_health",
                   service=t["service"],
                   severity="critical",
                   value=0, # 0 means down
                   threshold_type="active_probe",
                   description=f"Active health probe failed for {t['url']}"
               )
               
               if not self.deduplicator.is_duplicate(anomaly):
                   await self.publish_anomaly(anomaly)

    async def _probe(self, target: Dict[str, str]) -> bool:
        """Returns True if the endpoint returns 200, False otherwise."""
        try:
            response = await self.http_client.get(target["url"])
            if response.status_code == 200:
                # Expecting {"status": "ok", ...}
                data = response.json()
                if data.get("status") in ["ok", "healthy"]:
                   return True
            logger.warning(f"Target returned unhealthy HTTP status. Service: {target['service']}, Status: {response.status_code}")
            return False
            
        except httpx.RequestError as e:
            logger.warning(f"Target health probe timeout/connection generic error. Service: {target['service']}, Error: {str(e)}")
            return False
        except Exception as e:
            logger.exception(f"Unexpected error probing target: {target['service']}")
            return False

    async def publish_anomaly(self, anomaly: AnomalyResult):
        payload = anomaly.to_dict()
        msg = AgentMessage(
            source_agent=self.agent_id,
            message_type="anomaly_detected",
            payload=payload
        )
        
        logger.error(
            f"Emitting Health Anomaly - Service: {anomaly.service}, URL: {anomaly.description}"
        )
        
        await self.nats.publish("agents.observer.anomalies", msg.to_dict())
        self._increment_processed(1)
