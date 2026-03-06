# Messaging Protocol

The swarm uses NATS JetStream for inter-agent communication. Message payloads use a shared envelope defined in `shared/messaging/schema.py`.

## AgentMessage Envelope

Core fields:

- `message_id`: unique message UUID.
- `correlation_id`: incident/request correlation key.
- `trace_id`: distributed tracing key.
- `source_agent`, `target_agent`, `message_type`.
- `priority`: `0` critical to `3` low.
- `ttl_seconds`: expiry budget for consumers.
- `timestamp`: message creation time.
- `payload`: event-specific content.
- `context`: accumulated investigation context.

## Subjects

Defined in `shared/messaging/subjects.py`:

- `agents.orchestrator.commands`
- `agents.observer.anomalies`
- `agents.diagnoser.requests`
- `agents.diagnoser.results`
- `agents.remediator.proposals`
- `agents.remediator.executions`
- `agents.safety.reviews`
- `agents.safety.decisions`
- `agents.learning.feedback`
- `agents.heartbeat`
- `incidents.lifecycle`
- `human.approvals`
- `human.approvals.responses`
- Domain events: `orders.created`, `payments.completed`, `payments.failed`, `inventory.low`

## Streams

Stream bootstrap is done by `scripts/init_nats.py`.

- `AGENTS`: agent traffic and heartbeat subjects.
- `INCIDENTS`: lifecycle events.
- `HUMAN`: approval requests and responses.
- `BUSINESS`: service domain events.

## Delivery Semantics

- Subscriptions use explicit ack and redelivery behavior.
- Durable consumers are used for core control-plane subjects.
- `ttl_seconds` allows stale message discard in consumers.

## Operational Notes

- For request-reply interactions, callers use `NATSClient.request()`.
- Correlation IDs should stay stable for the full incident lifetime.
- Subject constants should be imported from `shared/messaging/subjects.py`, not hard-coded.
