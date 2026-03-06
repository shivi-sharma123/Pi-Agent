# System Architecture Overview

The SRE Agent Swarm is an event-driven control plane for automated incident detection, diagnosis, and remediation across a microservices environment.

## Design Principles

- Decoupled agents communicate asynchronously over NATS JetStream.
- The orchestrator owns lifecycle state and timeout handling.
- Safety gates protect high-impact actions with policy and human approval.
- Every state change is persisted for auditability and postmortems.

## Logical Components

- Target infrastructure: application services, workers, data stores, and observability stack.
- Agent control plane: observer, diagnoser, remediator, safety, orchestrator, learner.
- Dashboard plane: REST and WebSocket interfaces for incidents, agents, and approvals.

## End-to-End Flow

1. Observer publishes an anomaly (`agents.observer.anomalies`).
2. Orchestrator creates incident state and routes to diagnoser.
3. Diagnoser produces RCA hypothesis and confidence.
4. Remediator proposes an action from runbooks.
5. Safety approves, rejects, or requests human approval.
6. Remediator executes and verifies.
7. Orchestrator resolves or escalates based on outcome and retries.
8. Learner ingests post-incident feedback for future retrieval.

## Data Planes

- Messaging plane: NATS subjects and JetStream streams.
- State plane: incident/anomaly/heartbeat records in PostgreSQL.
- Context plane: Prometheus and Loki queries for diagnosis and verification.
- Learning plane: ChromaDB vectors plus runbook performance stats.

## Key Source Files

- `agents/orchestrator/src/orchestrator_agent.py`
- `agents/orchestrator/src/incident_fsm.py`
- `shared/messaging/subjects.py`
- `shared/db/models.py`
- `dashboard/api/main.py`

See [Microservices Map](./microservices.md) and [Messaging Protocol](./messaging.md) for details.
