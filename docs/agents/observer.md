# Observer Agent

Observer agents detect anomalous behavior and publish events for orchestration.

## Subtypes

Implemented in `agents/observer/src/main.py` via `--type`:

- `metrics`: `metrics_observer.py`
- `logs`: `log_observer.py`
- `health`: `health_observer.py`
- `synthetic`: `synthetic_prober.py`

## Core Components

- `detector.py`: threshold and z-score anomaly evaluation
- `deduplicator.py`: fingerprint-based alert storm suppression
- `predictor.py`: trend-based early warning (`trend_breach_predicted`)

## Inputs

- Prometheus query API (metrics observer)
- Loki query API (log observer)
- service health endpoints (health observer)
- synthetic transaction endpoints (synthetic prober)

## Outputs

- Subject: `agents.observer.anomalies`
- Message types: `anomaly_detected`, `trend_breach_predicted`

## Notes

- Deduplication uses a sliding time window.
- Metrics observer combines static and dynamic thresholding.
- Predictive alerts are emitted as warning-severity anomaly messages.
