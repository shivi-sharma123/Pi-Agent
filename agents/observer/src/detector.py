import logging
import statistics
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


@dataclass
class AnomalyResult:
    """Represents a detected anomaly signal returned by the AnomalyDetector."""
    metric: str
    service: str
    severity: str
    value: float
    threshold_type: str
    threshold_used: float = 0.0
    z_score: float = 0.0
    baseline_mean: float = 0.0
    baseline_stdev: float = 0.0
    labels: dict = None
    category: str = None
    description: str = None
    raw_payload: dict = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric": self.metric,
            "service": self.service,
            "severity": self.severity,
            "value": self.value,
            "threshold_type": self.threshold_type,
            "threshold_used": self.threshold_used,
            "z_score": self.z_score,
            "baseline_mean": self.baseline_mean,
            "baseline_stdev": self.baseline_stdev,
            "labels": self.labels or {},
            "category": self.category,
            "description": self.description,
            "raw_payload": self.raw_payload,
        }


class AnomalyDetector:
    """
    Maintains a sliding window of historical metric values.
    Calculates z-scores for dynamic thresholds, and evaluates static limits.
    """

    def __init__(self, window_size: int = 60, min_data_points: int = 5):
        self.window_size = window_size
        self.min_data_points = min_data_points
        # metric_key -> deque([values])
        self.windows: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=self.window_size)
        )

    def _get_key(self, metric_name: str, service: str) -> str:
        return f"{metric_name}:{service}"

    def record_value(self, metric_name: str, service: str, value: float) -> None:
        """Stores a new reading in the sliding window."""
        key = self._get_key(metric_name, service)
        self.windows[key].append(value)

    def evaluate(
        self,
        metric_name: str,
        service: str,
        value: float,
        config: Dict[str, Any],
        labels: Dict[str, str] = None,
    ) -> List[AnomalyResult]:
        """
        Evaluates a single value against configured thresholds.
        Returns a list of AnomalyResult (empty if healthy).
        """
        self.record_value(metric_name, service, value)
        threshold_type = config.get("threshold_type", "static")
        severity_map = config.get("severity_map", {})

        anomalies = []
        key = self._get_key(metric_name, service)
        history = self.windows[key]

        # For dynamic calculation, we want to evaluate the *new* value against the *previous baseline*.
        # So we look at history up to the previous element (excluding the one we just added).
        baseline = list(history)[:-1]

        if threshold_type == "dynamic":
            if len(baseline) < self.min_data_points:
                # Not enough data to establish a baseline
                return anomalies

            mean = statistics.mean(baseline)
            stdev = statistics.stdev(baseline) if len(baseline) > 1 else 0.0

            if stdev == 0:
                # Standard deviation is 0, so any deviation is technically an anomaly if values differ,
                # but mathematically z-score is undefined. Let's ignore zero variance for now unless value != mean.
                if value != mean and mean != 0:
                    stdev = 0.01

            z_score = (value - mean) / stdev if stdev > 0 else 0.0

            # Evaluate severity map highest to lowest
            # e.g., {"critical": 3.0, "warning": 2.0} -> requires z_score > 3.0 for critical
            for severity, threshold in sorted(
                severity_map.items(), key=lambda item: item[1], reverse=True
            ):
                if abs(z_score) >= threshold:
                    anomalies.append(
                        AnomalyResult(
                            metric=metric_name,
                            service=service,
                            severity=severity,
                            value=value,
                            threshold_type="dynamic",
                            threshold_used=threshold,
                            z_score=z_score,
                            baseline_mean=mean,
                            baseline_stdev=stdev,
                            labels=labels,
                        )
                    )
                    break  # Only emit the highest severity anomaly

        elif threshold_type == "static":
            for severity, threshold in sorted(
                severity_map.items(), key=lambda item: item[1], reverse=True
            ):
                # Static default: value greater than threshold implies anomaly
                # Example {"critical": 95, "warning": 80} -> alert on > 95
                if value >= threshold:
                    anomalies.append(
                        AnomalyResult(
                            metric=metric_name,
                            service=service,
                            severity=severity,
                            value=value,
                            threshold_type="static",
                            threshold_used=threshold,
                            labels=labels,
                        )
                    )
                    break

        return anomalies
