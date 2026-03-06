import hashlib
from collections import defaultdict
from datetime import datetime
from typing import Dict, List

from .detector import AnomalyResult


class AlertDeduplicator:
    """
    Prevents alert storms by grouping similar anomalies over a sliding time window.
    Uses a fingerprint based on metric + service + severity.
    """

    def __init__(self, window_seconds: int = 300, max_per_window: int = 1):
        """
        :param window_seconds: How long to remember an alert (default 5 mins).
        :param max_per_window: The max number of allowed alerts matching the fingerprint
                               in the window before silencing they are silenced.
        """
        self.window_seconds = window_seconds
        self.max_per_window = max_per_window
        # Mapping from fingerprint -> list of seen timestamps
        self.seen: Dict[str, List[datetime]] = defaultdict(list)

    def fingerprint(self, anomaly: AnomalyResult) -> str:
        """
        Creates a deterministic hash identifying this exact type of anomaly
        so we don't alert multiple times for the same active condition.
        """
        raw = f"{anomaly.metric}:{anomaly.service}:{anomaly.severity}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def is_duplicate(self, anomaly: AnomalyResult) -> bool:
        """
        Returns True if this exact anomaly has already occurred `max_per_window`
        times within `window_seconds`. False if it's new/allowed to fire.
        """
        fp = self.fingerprint(anomaly)
        now = datetime.now(timezone.utc)

        # Clean old entries outside the time window
        self.seen[fp] = [
            t for t in self.seen[fp] if (now - t).total_seconds() < self.window_seconds
        ]

        if len(self.seen[fp]) >= self.max_per_window:
            return True

        self.seen[fp].append(now)
        return False
