import httpx
import logging
import urllib.parse
from datetime import datetime, timedelta
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class ContextCollector:
    """
    Gathers surrounding context (logs, metrics) for a given anomaly 
    to feed into the Correlation and RCA engines.
    """

    def __init__(
        self, 
        prometheus_url: str = "http://prometheus:9090",
        loki_url: str = "http://loki:3100"
    ):
        self.prometheus_url = prometheus_url
        self.loki_url = loki_url
        self.http_client = httpx.AsyncClient(timeout=10.0)

    async def close(self):
        await self.http_client.aclose()

    async def collect_context(self, anomaly: Dict[str, Any]) -> Dict[str, Any]:
        """
        Given a raw anomaly payload, gathers logs and metrics for the affected service.
        """
        service = anomaly.get("service")
        # Ensure fallback to current time
        raw_ts = anomaly.get("timestamp")
        if raw_ts:
            try:
                anomaly_time = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
            except ValueError:
                anomaly_time = datetime.now(timezone.utc)
        else:
            anomaly_time = datetime.now(timezone.utc)

        # Gather context window: 5 mins before, 1 min after
        start_time = anomaly_time - timedelta(minutes=5)
        end_time = anomaly_time + timedelta(minutes=1)

        start_ts_sec = int(start_time.timestamp())
        end_ts_sec = int(end_time.timestamp())
        
        start_ts_ns = start_ts_sec * 1_000_000_000
        end_ts_ns = end_ts_sec * 1_000_000_000

        logs = await self.get_recent_logs(service, start_ts_ns, end_ts_ns)
        metrics = await self.get_recent_metrics(service, start_ts_sec, end_ts_sec)

        return {
            "anomaly": anomaly,
            "context": {
                "logs": logs,
                "metrics_summary": metrics,
                "window": {
                    "start": start_time.isoformat(),
                    "end": end_time.isoformat()
                }
            }
        }

    async def get_recent_logs(self, service: str, start_ts_ns: int, end_ts_ns: int) -> List[str]:
        if not service:
            return []

        # We query loki for the last 50 error/warn/critical lines for this service
        query = f'{{container="{service}"}} |= "ERROR" or |= "WARN" or |= "EXCEPTION" or |= "exception" or |= "error" or |= "warn"'
        encoded_query = urllib.parse.quote(query)
        
        url = f"{self.loki_url}/loki/api/v1/query_range?query={encoded_query}&start={start_ts_ns}&end={end_ts_ns}&limit=50"
        
        try:
            resp = await self.http_client.get(url)
            resp.raise_for_status()
            data = resp.json()
            
            log_lines = []
            for result in data.get("data", {}).get("result", []):
                for value in result.get("values", []):
                    # value is [timestamp_str, log_line_str]
                    if len(value) == 2:
                        log_lines.append(value[1].strip())
            return log_lines[-50:] # ensure we only return 50 max
        except Exception as e:
            logger.warning(f"Failed to fetch logs for {service}: {e}")
            return [f"<Failed to fetch logs: {str(e)}>"]

    async def get_recent_metrics(self, service: str, start_ts_sec: int, end_ts_sec: int) -> str:
        """
        Gets a summary of key metrics for the service (CPU, Memory anomalies) during the window.
        """
        if not service:
            return "No service specified."

        cpu_query = f'rate(container_cpu_usage_seconds_total{{container="{service}"}}[1m])'
        mem_query = f'container_memory_usage_bytes{{container="{service}"}}'
        
        cpu_avg = await self._query_prom_avg(cpu_query, start_ts_sec, end_ts_sec)
        mem_avg = await self._query_prom_avg(mem_query, start_ts_sec, end_ts_sec)
        
        return f"CPU Usage Avg (1m rate): {cpu_avg}, Memory Usage Avg: {mem_avg} bytes"

    async def _query_prom_avg(self, query: str, start_ts: int, end_ts: int) -> str:
        encoded_query = urllib.parse.quote(query)
        # Using simply query_range to get the points and compute avg, or using PromQL avg_over_time
        # Better yet, let's just ask prometheus to do the math:
        avg_query = f'avg_over_time({query}[{(end_ts - start_ts)}s])'
        encoded_avg_query = urllib.parse.quote(avg_query)
        
        # We query at the end of the window to get the avg over the whole window
        url = f"{self.prometheus_url}/api/v1/query?query={encoded_avg_query}&time={end_ts}"
        
        try:
            resp = await self.http_client.get(url)
            resp.raise_for_status()
            data = resp.json()
            
            results = data.get("data", {}).get("result", [])
            if results and len(results) > 0:
                # result format: [timestamp, value_string]
                val = results[0].get("value", [0, "0"])[1]
                try:
                    return f"{float(val):.4f}"
                except ValueError:
                    return val
            return "No data"
        except Exception as e:
            logger.warning(f"Failed to fetch metric avg for query {query}: {e}")
            return "Error fetching"
