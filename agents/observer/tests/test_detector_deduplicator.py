from collections import deque
from typing import Dict

import pytest

from agents.observer.src.deduplicator import AlertDeduplicator
from agents.observer.src.detector import AnomalyDetector, AnomalyResult


def test_anomaly_result_to_dict():
    anomaly = AnomalyResult(
        metric="cpu_usage",
        service="user-svc",
        severity="critical",
        value=95.5,
        threshold_type="static",
        threshold_used=90.0
    )
    result = anomaly.to_dict()
    assert result["metric"] == "cpu_usage"
    assert result["service"] == "user-svc"
    assert result["value"] == 95.5
    assert result["threshold_used"] == 90.0
    assert result["labels"] == {}


def test_deduplicator_fingerprint():
    dedup = AlertDeduplicator()
    a1 = AnomalyResult(metric="cpu", service="svc-a", severity="warning", value=80, threshold_type="static")
    a2 = AnomalyResult(metric="cpu", service="svc-a", severity="warning", value=85, threshold_type="static")
    a3 = AnomalyResult(metric="mem", service="svc-a", severity="warning", value=80, threshold_type="static")

    # a1 and a2 should match because metric, service, and severity are the same
    assert dedup.fingerprint(a1) == dedup.fingerprint(a2)
    # a3 has different metric
    assert dedup.fingerprint(a1) != dedup.fingerprint(a3)


def test_deduplicator_blocks_duplicates():
    # Allow max 2 per 10s
    dedup = AlertDeduplicator(window_seconds=10, max_per_window=2)
    a = AnomalyResult(metric="cpu", service="svc-a", severity="warning", value=80, threshold_type="static")

    # First event allowed
    assert not dedup.is_duplicate(a)
    # Second event allowed
    assert not dedup.is_duplicate(a)
    # Third event blocked (>= max_per_window)
    assert dedup.is_duplicate(a)


def test_detector_static_threshold():
    detector = AnomalyDetector()
    config = {
        "threshold_type": "static",
        "severity_map": {"warning": 80, "critical": 90}
    }
    
    # Below warning
    res = detector.evaluate("cpu", "svc-a", 70.0, config)
    assert len(res) == 0

    # Above warning, below critical
    res = detector.evaluate("cpu", "svc-a", 85.0, config)
    assert len(res) == 1
    assert res[0].severity == "warning"
    assert res[0].threshold_used == 80

    # Above critical
    res = detector.evaluate("cpu", "svc-a", 95.0, config)
    assert len(res) == 1
    assert res[0].severity == "critical"
    assert res[0].threshold_used == 90


def test_detector_dynamic_threshold_returns_empty_if_insufficient_data():
    # Require 5 data points
    detector = AnomalyDetector(min_data_points=5)
    config = {
        "threshold_type": "dynamic",
        "severity_map": {"warning": 2.0}
    }
    
    # Under minimum
    for val in [50, 50, 50, 50]:
        res = detector.evaluate("lat", "svc-a", val, config)
        assert len(res) == 0


def test_detector_dynamic_threshold():
    detector = AnomalyDetector(min_data_points=3, window_size=5)
    config = {
        "threshold_type": "dynamic",
        "severity_map": {"warning": 2.0, "critical": 3.0}
    }
    
    # Establish baseline [10, 10, 10]
    # Mean = 10, Stdev = 0
    detector.evaluate("lat", "svc-a", 10, config)
    detector.evaluate("lat", "svc-a", 10, config)
    
    # The third point evaluates the history [10, 10] beforehand
    res = detector.evaluate("lat", "svc-a", 10, config)
    assert len(res) == 0
    
    # Mean after three 10s is 10, Stdev is 0. 
    # Anomaly detector will treat stdev=0 as 0.01 if mean != 0 and value != mean
    # Evaluate a spike: 30
    # Mean of history [10, 10, 10] is 10, Stdev is 0. 
    # value=30 != mean=10 -> stdev=0.01 -> z_score = (30-10)/0.01 = 2000. It's critical!
    res = detector.evaluate("lat", "svc-a", 30, config)
    assert len(res) == 1
    assert res[0].severity == "critical"

    # Now history is [10, 10, 10, 30] -> calculate realistic stdev
    # Let's add multiple values to get stdev
    # We want mean ≈ 10, stdev ≈ 1 so that value=14 gives z_score ≈ 4 (critical)
    for v in [10, 10, 10, 10, 10, 10]:
        detector.evaluate("lat", "svc-a", v, config)
        
    # Baseline is roughly mean=10, stdev is very small but not 0 due to the 30 in the window.
    # Actually wait - the window size is 5! Our history is 5 elements long.
    # If we add [10,10,10,10,10], history becomes exactly [10,10,10,10,10]. Stdev is 0!
    # Let's fill it with [9, 11, 10, 10, 10] -> Mean=10, Stdev=0.707
    for v in [9, 11, 10, 10, 10]:
        detector.evaluate("lat", "svc-a", v, config)

    # With mean=10, stdev=0.707, value=14 -> z_score = 4 / 0.707 = 5.6 -> critical
    res = detector.evaluate("lat", "svc-a", 14, config) # > 3 std devs
    assert len(res) == 1
    assert res[0].severity == "critical"
