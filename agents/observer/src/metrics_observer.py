import asyncio
import logging
import time
from typing import Any, Dict

import httpx

from agents.observer.src.deduplicator import AlertDeduplicator
from agents.observer.src.detector import AnomalyDetector
from agents.observer.src.predictor import TrendPredictor
from shared.agents.base import BaseAgent
from shared.messaging.schema import AgentMessage

logger = logging.getLogger(__name__)


class MetricsObserver(BaseAgent):
    """
    Observer Agent that periodically queries Prometheus for key metrics.
     Evaluates the readings against dynamic/static thresholds.
     If an anomaly is detected and not deduplicated, publishes to NATS.
    """

    agent_type = "observer.metrics"

    def __init__(self, nats_url: str, prometheus_url: str = "http://prometheus:9090"):
        super().__init__(nats_url=nats_url)
        self.prometheus_url = prometheus_url
        self.detector = AnomalyDetector(min_data_points=3, window_size=12)
        self.deduplicator = AlertDeduplicator(window_seconds=300, max_per_window=1)
        self.http_client = httpx.AsyncClient(timeout=5.0)

        # Per-(metric_name, service) trend predictors — created lazily
        self._predictors: dict[tuple[str, str], TrendPredictor] = {}
        
        # Define what we monitor and how
        self.queries = [
            {
                "name": "cpu_usage",
                "promql": 'sum(rate(container_cpu_usage_seconds_total{container=~".+-svc|.*-worker"}[1m])) by (container)',
                "config": {
                    "threshold_type": "static",
                    "severity_map": {"critical": 1.5, "warning": 1.0} # 1 core
                }
            },
            {
                "name": "error_rate",
                "promql": 'sum(rate(http_requests_total{status=~"5.."}[1m])) by (job) / sum(rate(http_requests_total[1m])) by (job)',
                "config": {
                    "threshold_type": "static",
                    "severity_map": {"critical": 0.05, "warning": 0.01} # 5% error rate
                }
            },
            {
                "name": "latency_p99",
                "promql": 'histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[1m])) by (le, job))',
                "config": {
                    "threshold_type": "dynamic", # Dynamic baseline!
                    "severity_map": {"critical": 3.0, "warning": 2.0} # Z-score deviations
                }
            }
        ]

    async def setup(self):
        """Called once before the main loop starts."""
        logger.info("MetricsObserver setup complete", prometheus_url=self.prometheus_url)

    async def run_loop(self):
        """Called repeatedly in a loop by BaseAgent. We will sleep between polls."""
        await self.poll_metrics()
        await asyncio.sleep(15) # Poll every 15 seconds

    async def teardown(self):
        """Called on shutdown."""
        await self.http_client.aclose()
        logger.info("MetricsObserver shutting down")

    async def poll_metrics(self):
        for q in self.queries:
            try:
                # Query Prometheus API
                response = await self.http_client.get(
                    f"{self.prometheus_url}/api/v1/query",
                    params={"query": q["promql"]}
                )
                response.raise_for_status()
                data = response.json()
                
                if data.get("status") != "success":
                    logger.error("Prometheus query failed", query=q["name"], error=data)
                    continue

                results = data.get("data", {}).get("result", [])
                
                for r in results:
                    # Extract the service/container name from labels
                    labels = r.get("metric", {})
                    service = labels.get("job") or labels.get("container") or "unknown"
                    
                    # Some metrics return "NaN" string from PromQL if there's no data
                    val_str = r.get("value", [0, "0"])[1]
                    if val_str == "NaN":
                        continue
                        
                    value = float(val_str)
                    
                    # Evaluate value using the shared detector logic
                    anomalies = self.detector.evaluate(
                        metric_name=q["name"],
                        service=service,
                        value=value,
                        config=q["config"],
                        labels=labels,
                    )
                    
                    for anomaly in anomalies:
                        if not self.deduplicator.is_duplicate(anomaly):
                            await self.publish_anomaly(anomaly)

                    # Also feed into TrendPredictor for early-warning predictions
                    key = (q["name"], service)
                    if key not in self._predictors:
                        # Pick a sensible threshold from the query's severity_map
                        threshold = q["config"]["severity_map"].get("warning", 1.0)
                        self._predictors[key] = TrendPredictor(
                            metric_name=q["name"],
                            service=service,
                            threshold=threshold,
                            look_ahead_seconds=1800,
                            window_size=20,
                        )
                    predictor = self._predictors[key]
                    predictor.push(value=value, timestamp=time.time())
                    trend_alert = predictor.evaluate()
                    if trend_alert:
                        await self._publish_trend_alert(trend_alert)
                            
            except httpx.RequestError as e:
                logger.error("Failed to connect to Prometheus", error=str(e))
            except Exception as e:
                logger.exception("Unexpected error in poll_metrics")

    async def publish_anomaly(self, anomaly):
        """Packs the AnomalyResult into an AgentMessage and publishes to NATS."""
        payload = anomaly.to_dict()
        msg = AgentMessage(
            source_agent=self.agent_id,
            message_type="anomaly_detected",
            payload=payload
        )
        logger.warning(
            f"Emitting Anomaly - Metric: {anomaly.metric}, Service: {anomaly.service}, "
            f"Severity: {anomaly.severity}, Value: {anomaly.value}"
        )
        await self.nats.publish("agents.observer.anomalies", msg)
        self._increment_processed(1)

    async def _publish_trend_alert(self, alert) -> None:
        """Publish a predictive trend-breach alert as a low-severity anomaly."""
        payload = {
            "metric": alert.metric_name,
            "service": alert.service,
            "value": alert.current_value,
            "projected_value": alert.projected_value,
            "threshold": alert.threshold,
            "predicted_breach_in_seconds": alert.predicted_breach_in_seconds,
            "slope": alert.slope,
            "confidence": alert.confidence,
            "alert_type": alert.alert_type,
            "severity": "warning",
        }
        msg = AgentMessage(
            source_agent=self.agent_id,
            message_type="trend_breach_predicted",
            payload=payload,
        )
        logger.warning(
            "[PREDICTOR] Trend alert: %s/%s will breach %.2f in ~%.0fs (R²=%.2f)",
            alert.service, alert.metric_name, alert.threshold,
            alert.predicted_breach_in_seconds, alert.confidence,
        )
        await self.nats.publish("agents.observer.anomalies", msg)
        self._increment_processed(1)
