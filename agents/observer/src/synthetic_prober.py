import asyncio
import logging
import time
from typing import Dict, Any

import httpx

from agents.observer.src.deduplicator import AlertDeduplicator
from agents.observer.src.detector import AnomalyResult
from shared.agents.base import BaseAgent
from shared.messaging.schema import AgentMessage

logger = logging.getLogger(__name__)


class SyntheticProber(BaseAgent):
    """
    Observer Agent that simulates actual user traffic through the system.
    Detects when end-to-end flows are broken (e.g. Can't place an order).
    """

    agent_type = "observer.synthetic"

    def __init__(self, nats_url: str):
        super().__init__(nats_url=nats_url)
        self.deduplicator = AlertDeduplicator(window_seconds=120, max_per_window=1)
        self.http_client = httpx.AsyncClient(timeout=10.0) # Longer timeout for complex flows
        self.poll_interval = 30 # Run simulation every 30 seconds
        
        # Route through the NGINX API Gateway since users hit that
        self.gateway_url = "http://api-gateway:80"

    async def setup(self):
        logger.info("SyntheticProber setup complete", gateway_url=self.gateway_url)

    async def run_loop(self):
        await self.simulate_checkout_flow()
        await asyncio.sleep(self.poll_interval)

    async def teardown(self):
        await self.http_client.aclose()
        logger.info("SyntheticProber shutting down")

    async def simulate_checkout_flow(self):
        """Simulates: Login -> Get Products -> Create Order -> Pay"""
        try:
            start_time = time.time()
            
            # 1. Login
            auth_req = {"email": "synthetic@example.com", "password": "password123"}
            auth_resp = await self.http_client.post(f"{self.gateway_url}/auth/login", json=auth_req)
            if auth_resp.status_code not in [200, 401, 404]: 
                # Accept 401/404 out-of-the-box if the dummy user isn't seeded 
                # Real failure is a 5xx or timeout
                auth_resp.raise_for_status()

            # 2. Search Products
            search_resp = await self.http_client.get(f"{self.gateway_url}/search")
            search_resp.raise_for_status()
            
            # 3. If everything ran, check E2E duration
            duration = time.time() - start_time
            if duration > 5.0:
                 await self._publish_failure(
                    "e2e_checkout", 
                    "LatencySpike", 
                    duration, 
                    f"Checkout flow took {duration:.2f}s"
                )
            
        except httpx.HTTPStatusError as e:
            await self._publish_failure(
                "e2e_checkout", 
                "HttpError", 
                0, 
                f"Checkout flow failed: {e.response.status_code} {e.request.url}"
            )
        except httpx.RequestError as e:
            await self._publish_failure(
                "e2e_checkout", 
                "ConnectionError", 
                0, 
                f"Checkout flow connection failed: {e.request.url}"
            )
        except Exception as e:
            logger.exception("Unexpected error in synthetic simulation")

    async def _publish_failure(self, metric: str, fail_type: str, value: float, desc: str):
        anomaly = AnomalyResult(
            metric=metric,
            service="api-gateway", # The entrypoint failed 
            severity="critical",
            value=value,
            threshold_type="synthetic_probe",
            category=fail_type,
            description=desc
        )
        if not self.deduplicator.is_duplicate(anomaly):
            payload = anomaly.to_dict()
            msg = AgentMessage(
                source_agent=self.agent_id,
                message_type="anomaly_detected",
                payload=payload
            )
            
            logger.error(
                f"Emitting Synthetic Anomaly - Service: {anomaly.service}, Category: {anomaly.category}, Description: {anomaly.description}"
            )
            
            await self.nats.publish("agents.observer.anomalies", msg.to_dict())
            self._increment_processed(1)
