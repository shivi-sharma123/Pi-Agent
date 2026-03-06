"""
TrendPredictor
==============
Analyses a sliding window of metric samples to detect monotonic trends that
will breach a threshold **before** the breach actually occurs.

Uses Ordinary Least Squares linear regression (no external ML deps required —
just the standard library and numpy).  Projects the current trend forward and
emits an early-warning anomaly if the projected value crosses the threshold
within the look-ahead window.

Used by: MetricsObserver  (agents/observer/src/metrics_observer.py)

Usage::

    predictor = TrendPredictor(
        metric_name="memory_usage_rss_bytes",
        threshold=0.90,               # 90 % of container limit
        look_ahead_seconds=1800,      # Warn 30 min out
        window_size=20,               # Analyse last 20 samples
    )
    predictor.push(timestamp=time.time(), value=0.72)
    alert = predictor.evaluate()
    if alert:
        await publish_anomaly(alert)
"""

from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Optional


@dataclass
class _Sample:
    timestamp: float  # Unix epoch seconds
    value: float


@dataclass
class TrendAlert:
    """Returned by TrendPredictor.evaluate() when a breach is predicted."""
    metric_name: str
    service: str
    current_value: float
    projected_value: float
    threshold: float
    predicted_breach_in_seconds: float
    slope: float            # units/second
    confidence: float       # R² of the regression fit (0.0 – 1.0)
    alert_type: str = "trend_breach_predicted"


class TrendPredictor:
    """
    Stateful per-metric trend detector using OLS linear regression.
    """

    def __init__(
        self,
        metric_name: str,
        service: str,
        threshold: float,
        look_ahead_seconds: float = 1800.0,
        window_size: int = 20,
        min_samples: int = 5,
        min_r2: float = 0.7,
    ) -> None:
        self.metric_name = metric_name
        self.service = service
        self.threshold = threshold
        self.look_ahead_seconds = look_ahead_seconds
        self.window_size = window_size
        self.min_samples = min_samples
        self.min_r2 = min_r2

        self._samples: Deque[_Sample] = deque(maxlen=window_size)

    # ─── Public API ───────────────────────────────────────────────────────────

    def push(self, value: float, timestamp: Optional[float] = None) -> None:
        """Add a new metric sample."""
        self._samples.append(_Sample(timestamp=timestamp or time.time(), value=value))

    def evaluate(self) -> Optional[TrendAlert]:
        """
        Run OLS regression over the current window.
        Returns a TrendAlert if a breach is predicted within look_ahead_seconds,
        otherwise returns None.
        """
        if len(self._samples) < self.min_samples:
            return None

        xs = [s.timestamp for s in self._samples]
        ys = [s.value for s in self._samples]

        slope, intercept, r2 = self._ols(xs, ys)

        # Reject weak trends
        if r2 < self.min_r2:
            return None

        # Only care about increasing trends (slope > 0) heading toward threshold
        if slope <= 0:
            return None

        current_value = ys[-1]
        now = xs[-1]

        # Time until projected value crosses threshold
        if slope == 0:
            return None
        time_to_breach = (self.threshold - current_value) / slope

        if time_to_breach < 0 or time_to_breach > self.look_ahead_seconds:
            return None

        projected = intercept + slope * (now + time_to_breach)

        return TrendAlert(
            metric_name=self.metric_name,
            service=self.service,
            current_value=round(current_value, 4),
            projected_value=round(projected, 4),
            threshold=self.threshold,
            predicted_breach_in_seconds=round(time_to_breach, 1),
            slope=round(slope, 6),
            confidence=round(r2, 4),
        )

    # ─── Private helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _ols(xs: list[float], ys: list[float]) -> tuple[float, float, float]:
        """
        Ordinary Least Squares regression.
        Returns (slope, intercept, R²).
        """
        n = len(xs)
        # Normalise timestamps to avoid floating-point precision issues
        x0 = xs[0]
        xs = [x - x0 for x in xs]

        mean_x = sum(xs) / n
        mean_y = sum(ys) / n

        ss_xy = sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(n))
        ss_xx = sum((xs[i] - mean_x) ** 2 for i in range(n))

        if ss_xx == 0:
            return 0.0, mean_y, 0.0

        slope = ss_xy / ss_xx
        intercept = mean_y - slope * mean_x

        # R² calculation
        ss_res = sum((ys[i] - (intercept + slope * xs[i])) ** 2 for i in range(n))
        ss_tot = sum((ys[i] - mean_y) ** 2 for i in range(n))
        r2 = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

        return slope, intercept + slope * x0, max(0.0, r2)
