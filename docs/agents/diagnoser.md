# Diagnoser Agent

The diagnoser builds incident context and generates root-cause hypotheses.

## Main Module

- `agents/diagnoser/src/rca_engine.py`

## Pipeline

1. Consume anomaly from `agents.observer.anomalies`.
2. Correlate anomaly into an incident (`correlation_engine.py`).
3. Gather logs/metrics context (`context_collector.py`).
4. Generate RCA hypothesis (`hypothesis_generator.py`).
5. If confidence is low, run multi-hypothesis scoring (`debate_engine.py`).
6. Persist diagnosis and publish result.

## Outputs

- Subject: `agents.diagnoser.results`
- Payload includes diagnosis and confidence

## LLM Backends

`hypothesis_generator.py` supports:

- Gemini backend (preferred when configured)
- OpenAI backend (fallback)
- deterministic heuristic fallback when no key is set

## Key Responsibilities

- convert raw anomalies into causal hypotheses
- provide machine-readable diagnosis for runbook selection
- reduce false-confidence outcomes via debate scoring
