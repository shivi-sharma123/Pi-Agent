# Agent Reference

This section documents each agent role, its inputs/outputs, and key modules.

## Pages

- [Observer](./observer.md)
- [Diagnoser](./diagnoser.md)
- [Remediator](./remediator.md)
- [Safety](./safety.md)
- [Orchestrator](./orchestrator.md)
- [Learner](./learner.md)

## Shared Runtime Contract

All agents inherit from `shared/agents/base.py` and share:

- NATS connection lifecycle
- heartbeat publishing to `agents.heartbeat`
- structured logging context
- graceful shutdown behavior

Common message format is `AgentMessage` from `shared/messaging/schema.py`.
