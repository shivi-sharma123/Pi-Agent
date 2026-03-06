# SRE Agent Swarm Documentation

This documentation covers the architecture, runtime behavior, and day-2 operations of the SRE Agent Swarm.

## Documentation Map

- [Architecture Overview](./architecture/overview.md)
- [Messaging Protocol](./architecture/messaging.md)
- [Microservices Map](./architecture/microservices.md)
- [Incident Lifecycle](./workflows/incident_lifecycle.md)
- [Getting Started](./operations/getting_started.md)
- [Agent Reference](./agents/README.md)
- [Development Guide](./development/README.md)
- [Chaos Engineering Guide](./development/chaos.md)
- [Low Level Design](./lld.md)
- [Project Plan and Status](./TODO.md)

## System Summary

The swarm coordinates six agent roles:

- `observer` detects anomalies from metrics, logs, health checks, and synthetic probes.
- `diagnoser` generates root-cause hypotheses from contextual evidence.
- `remediator` maps diagnosis output to runbooks and executes actions.
- `safety` enforces policy, rate limits, and human approval gates.
- `orchestrator` manages incident state transitions and escalation.
- `learner` stores historical outcomes and recommends runbooks for similar incidents.

## Core Stack

- Runtime: Docker Compose, Python, Go, Node.js, Django
- Messaging: NATS JetStream
- State: PostgreSQL, Redis, Elasticsearch, ChromaDB
- Observability: Prometheus, Grafana, Loki, Tempo, AlertManager
- Dashboard: FastAPI API + React frontend
- LLM Backends: Gemini (primary), OpenAI (fallback)
