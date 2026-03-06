# Development Guide

This guide focuses on extending and validating the swarm.

## Local Workflow

```bash
make install-dev
make lint
make test
```

Useful runtime commands:

```bash
make up
make logs
make ps
make down
```

## Code Areas

- `agents/`: control-plane agent implementations
- `shared/`: cross-agent runtime package (messaging, db, config, logging)
- `dashboard/`: FastAPI API + React frontend
- `services/`: target infrastructure microservices and workers
- `scripts/`: operational scripts (NATS bootstrap, chaos tooling)

## Adding a New Agent

1. Create `agents/<name>/src/` with a class inheriting `BaseAgent`.
2. Define `agent_type` and implement `setup()`, `run_loop()`, `teardown()`.
3. Use subject constants from `shared/messaging/subjects.py`.
4. Add requirements and Dockerfile for the new agent.
5. Wire the service into `docker-compose.yml`.
6. Add unit tests under `agents/<name>/tests/`.
7. Document inputs/outputs in `docs/agents/`.

## Adding a New Runbook

1. Add YAML under `agents/remediator/runbooks/`.
2. Define match conditions (`root_cause_category`, `confidence_minimum`).
3. Define action type and params.
4. Set `risk` and `approval_required` correctly.
5. Add verification checks and wait interval.
6. Add or update tests in `agents/remediator/tests/`.

## Dashboard Development

- API entrypoint: `dashboard/api/main.py`
- Frontend entrypoint: `dashboard/frontend/src/main.tsx`
- WebSocket endpoint: `/ws` on dashboard API

## Related Docs

- [Agent Reference](../agents/README.md)
- [Incident Lifecycle](../workflows/incident_lifecycle.md)
- [Chaos Engineering](./chaos.md)
