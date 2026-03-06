# Getting Started

This guide brings up the full local stack and verifies the control plane.

## Prerequisites

- Docker Engine + Docker Compose v2 (`docker compose`)
- Python 3.11+
- `make`
- Optional: API key for diagnoser LLM backend (`GEMINI_API_KEY` or `OPENAI_API_KEY`)

## 1. Configure Environment

```bash
cp .env.example .env
```

Set at least:

- `NATS_URL`
- DB credentials if you are not using defaults
- `GEMINI_API_KEY` or `OPENAI_API_KEY` for LLM-based diagnosis

## 2. Start Infrastructure and Application Stack

### Fast path

```bash
make up
```

### Step-by-step path

```bash
make infra-up
make init-nats
make obs-up
make dashboard-up
```

## 3. Verify Health

```bash
make ps
make health
```

Primary endpoints:

- API gateway: `http://localhost:8000`
- Dashboard API: `http://localhost:8010`
- Dashboard UI: `http://localhost:3001`
- NATS monitoring: `http://localhost:8222`
- Grafana: `http://localhost:3000`
- Prometheus: `http://localhost:9090`

## 4. Run Tests Locally

```bash
make test
```

For integration-only suites:

```bash
make test-integration
```

## 5. Run Chaos Scenarios

Use the scenario runner (recommended entrypoint):

```bash
python scripts/chaos/runner.py --dry-run
python scripts/chaos/runner.py --scenario memory_leak
```

Reports are written under `scripts/chaos/report_*.md`.

## 6. Shutdown

```bash
make down
make infra-down
```

Or full cleanup:

```bash
make clean
```

## Troubleshooting

- If JetStream streams are missing, rerun `make init-nats`.
- If dashboard has no live updates, verify NATS and WebSocket endpoint `/ws` on `:8010`.
- If diagnosis is always heuristic, verify LLM key env vars in the running diagnoser environment.
