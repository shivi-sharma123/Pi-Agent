# SRE Agent Swarm — Testing Guide

This document covers every testing workflow: unit tests, integration tests, Docker smoke tests, end-to-end incident lifecycle verification, chaos engineering, and manual API testing.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Unit Tests (No Infrastructure Required)](#2-unit-tests-no-infrastructure-required)
3. [Docker Build Verification](#3-docker-build-verification)
4. [Infrastructure Smoke Tests](#4-infrastructure-smoke-tests)
5. [Service Health Checks](#5-service-health-checks)
6. [Integration Tests](#6-integration-tests)
7. [End-to-End Incident Lifecycle](#7-end-to-end-incident-lifecycle)
8. [Dashboard API Manual Testing](#8-dashboard-api-manual-testing)
9. [WebSocket Live Events](#9-websocket-live-events)
10. [Chaos Engineering](#10-chaos-engineering)
11. [Linting](#11-linting)
12. [CI Pipeline](#12-ci-pipeline)
13. [Troubleshooting](#13-troubleshooting)

---

## 1. Prerequisites

### Local Environment

```bash
# Python 3.11+ required
python3 --version

# Go 1.22+ (for order-service and inventory-worker tests)
go version

# Node.js 18+ (for auth-service)
node --version

# Docker + Docker Compose
docker --version
docker compose version
```

### Install Python Dev Dependencies

```bash
# Install the shared package in editable mode (includes pytest, pytest-asyncio, ruff, etc.)
make install-dev
# — OR manually —
pip install -e "shared/[dev]"
```

### Environment Variables

```bash
cp .env.example .env
# Edit .env if needed (defaults work for local Docker setup)
```

Key variables:
| Variable | Default | Purpose |
|----------|---------|---------|
| `NATS_URL` | `nats://localhost:4222` | NATS message bus |
| `AGENTS_DB_HOST` | `localhost` | PostgreSQL for agent incident store |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis for sessions/cache |
| `GEMINI_API_KEY` | `your-key-here` | Required by diagnoser (LLM-based RCA) |

---

## 2. Unit Tests (No Infrastructure Required)

Unit tests mock all external dependencies (NATS, PostgreSQL, Redis, HTTP APIs). They can run anywhere with Python installed.

### Run All Unit Tests

```bash
make test
```

This is equivalent to:

```bash
make test-unit
```

### What It Does

1. Installs microservice + agent test dependencies
2. Runs pytest across all test directories
3. Runs Go tests for order-service and inventory-worker

### Run Tests by Component

#### Shared Library (11 tests)

```bash
python -m pytest shared/tests/ -v
```

**Tests cover:**
- `test_base_agent.py` — BaseAgent init, lifecycle hooks, signal handling, counters
- `test_models.py` — SQLAlchemy ORM models (Incident, Anomaly, AgentHeartbeat)
- `test_logger.py` — Structured logging (JSON + console formats), context binding
- `test_schema.py` — AgentMessage serialisation, round-trip, TTL/expiry logic
- `test_nats_client.py` — `build_message()` factory helper
- `test_settings.py` — Pydantic settings, environment overrides

**Expected output:**
```
shared/tests/test_base_agent.py    ...........   11 passed
shared/tests/test_logger.py        .........     9 passed
shared/tests/test_models.py        .............  13 passed
shared/tests/test_schema.py        .........     9 passed
shared/tests/test_nats_client.py   .....         5 passed
shared/tests/test_settings.py      .....         5 passed
```

#### Orchestrator Agent (62 tests)

```bash
python -m pytest agents/orchestrator/tests/ -v
```

**Tests cover:**
- `test_incident_fsm.py` (21 tests) — All state transitions, invalid transitions, timeouts, retries, terminal states
- `test_agent_router.py` (12 tests) — Agent registration, pruning stale agents, routing to diagnoser/remediator
- `test_escalation_manager.py` (6 tests) — Timeout detection, retry logic, max-retry escalation, dead agent handling
- `test_timeline_builder.py` (8 tests) — Event appending, postmortem generation, state duration calculation
- `test_orchestrator_integration.py` (16 tests) — Full FSM lifecycle, timeline recording, postmortem, safety rejection loop, timeout escalation, human approval flow, concurrent incidents

**Expected output:** `62 passed`

#### Dashboard API (13 tests)

```bash
python -m pytest dashboard/tests/ -v
```

**Tests cover:**
- `test_incidents_api.py` — Pydantic schema validation for IncidentSummary, IncidentDetail, IncidentStats, TimelineEvent
- `test_approvals_api.py` — ApprovalRequest and ApprovalAction schema validation
- `test_websocket.py` — WebSocket ConnectionManager: connect, disconnect, broadcast, dead connection cleanup

**Expected output:** `13 passed`

#### Observer Agent

```bash
python -m pytest agents/observer/tests/ -v
```

**Tests cover:**
- `test_detector_deduplicator.py` — AnomalyDetector thresholds, AlertDeduplicator windowing
- `test_predictor.py` — TrendPredictor linear regression, breach prediction
- `test_observers.py` — MetricsObserver + LogObserver publish behaviour

#### Diagnoser Agent

```bash
python -m pytest agents/diagnoser/tests/ -v
```

**Tests cover:**
- `test_diagnoser.py` — RCA pipeline mocking
- `test_hypothesis_generator.py` — LLM prompt construction, response parsing

#### Safety Agent

```bash
python -m pytest agents/safety/tests/ -v
```

**Tests cover:**
- `test_safety.py` — PolicyEngine rules, BlastRadiusCalculator, RateLimiter, HumanApprovalGateway formatting

#### Microservice Tests (Python)

```bash
# Search service
cd services/search-service && python -m pytest app/test_main.py -v

# Notification worker
cd services/notification-worker && python -m pytest app/test_main.py -v

# Analytics worker
cd services/analytics-worker && python -m pytest app/test_main.py -v

# Product service (Django)
cd services/product-service && PYTHONPATH=. django-admin test app.tests --settings=app.config
```

#### Go Service Tests

```bash
# Order service
cd services/order-service && go test ./... -v

# Inventory worker
cd services/inventory-worker && go test ./... -v
```

### Quick Smoke Test (All Unit Tests Combined)

```bash
python -m pytest shared/tests/ agents/orchestrator/tests/ dashboard/tests/ -v --tb=short
```

**Expected: 130 passed**

---

## 3. Docker Build Verification

Verify all 18 Docker images build successfully without starting services.

```bash
# Build all images (no cache for clean build)
docker compose build

# Build specific images
docker compose build user-svc order-svc payment-svc auth-svc
docker compose build product-svc search-svc notification-worker inventory-worker analytics-worker
docker compose build metrics-observer log-observer health-observer synthetic-prober
docker compose build diagnoser-agent safety-agent remediator-agent orchestrator-agent
docker compose build dashboard-api dashboard-frontend
```

**Expected:** All images build without errors. Watch for:
- Python dependency resolution failures
- Go compilation errors
- Node.js package install failures
- Frontend build (Vite/TypeScript) errors

---

## 4. Infrastructure Smoke Tests

### Start Infrastructure Only

```bash
make infra-up
```

This starts:
| Service | Port | Purpose |
|---------|------|---------|
| `postgres-agents` | 5432 | Agent incident store |
| `postgres-orders` | 5433 | Order database |
| `postgres-payments` | 5434 | Payment database |
| `postgres-inventory` | 5435 | Inventory database |
| `redis` | 6379 | Session/cache store |
| `nats` | 4222 (client), 8222 (monitoring) | Message bus |
| `elasticsearch` | 9200 | Product search index |

### Verify Infrastructure Health

```bash
# PostgreSQL instances
pg_isready -h localhost -p 5432    # agents DB
pg_isready -h localhost -p 5433    # orders DB
pg_isready -h localhost -p 5434    # payments DB
pg_isready -h localhost -p 5435    # inventory DB

# Redis
redis-cli ping
# Expected: PONG

# NATS
curl -sf http://localhost:8222/healthz
# Expected: ok

# NATS JetStream info
curl -sf http://localhost:8222/jsz | python3 -m json.tool

# Elasticsearch
curl -sf http://localhost:9200/_cluster/health | python3 -m json.tool
# Expected: "status": "green" or "yellow"
```

### Initialise NATS Streams

```bash
make init-nats
# — OR —
python scripts/init_nats.py
```

**Expected output:**
```
Connecting to NATS at nats://localhost:4222...

Creating JetStream streams:
  ✓ Created stream: AGENTS (10 subjects)
  ✓ Created stream: INCIDENTS (1 subjects)
  ✓ Created stream: HUMAN (2 subjects)
  ✓ Created stream: BUSINESS (4 subjects)

✅ NATS JetStream initialisation complete!
```

### Verify Streams Were Created

```bash
curl -sf http://localhost:8222/jsz | python3 -c "
import json, sys
data = json.load(sys.stdin)
for s in data.get('account_details', [{}])[0].get('stream_detail', []):
    cfg = s['config']
    print(f\"  {cfg['name']:12s} — {len(cfg['subjects'])} subjects, max_age={cfg['max_age']//1e9:.0f}s\")
"
```

### Stop Infrastructure

```bash
make infra-down
```

---

## 5. Service Health Checks

### Start Full Stack

```bash
make up
```

### Check All Health Endpoints

```bash
make health
```

### Individual Health Checks

Each service exposes a `GET /health` endpoint returning JSON:

```bash
# Phase 1 — Core
curl -sf http://localhost:8000/health | python3 -m json.tool   # API Gateway
curl -sf http://localhost:8001/health | python3 -m json.tool   # User Service
curl -sf http://localhost:8004/health | python3 -m json.tool   # Auth Service
curl -sf http://localhost:8002/health | python3 -m json.tool   # Order Service
curl -sf http://localhost:8005/health | python3 -m json.tool   # Payment Service

# Phase 2 — Extended Services
curl -sf http://localhost:8003/health | python3 -m json.tool   # Product Service
curl -sf http://localhost:8006/health | python3 -m json.tool   # Search Service
curl -sf http://localhost:8007/health | python3 -m json.tool   # Notification Worker
curl -sf http://localhost:8008/health | python3 -m json.tool   # Inventory Worker
curl -sf http://localhost:8009/health | python3 -m json.tool   # Analytics Worker

# Phase 5 — Dashboard
curl -sf http://localhost:8010/health | python3 -m json.tool   # Dashboard API
```

**Expected response format:**
```json
{
    "status": "healthy",
    "service": "user-svc",
    "version": "0.1.0",
    "dependencies": {
        "redis": "ok"
    }
}
```

**What to look for:**
- `"status": "healthy"` — all dependencies are up
- `"status": "degraded"` — one or more dependencies are down (check `dependencies` object)
- Connection refused — service itself is not running

### Observability Stack

```bash
make obs-up
```

```bash
# Prometheus
curl -sf http://localhost:9090/-/healthy
# Expected: "Prometheus Server is Healthy."

# Grafana
curl -sf http://localhost:3000/api/health | python3 -m json.tool
# Expected: {"commit":"...","database":"ok","version":"..."}

# AlertManager
curl -sf http://localhost:9093/-/healthy
# Expected: OK
```

---

## 6. Integration Tests

Integration tests require running infrastructure (PostgreSQL, NATS, Redis).

### Run Integration Tests

```bash
make test-integration
```

This will:
1. Start infrastructure via `docker-compose.infrastructure.yml`
2. Wait 10 seconds for services to become healthy
3. Run `shared/tests/` with the `integration` marker
4. Tests connect to real PostgreSQL and NATS instances

**Expected:** Tests tagged with `@pytest.mark.integration` pass.

### Manual Integration Verification

With infrastructure running (`make infra-up`):

```bash
# Verify NATS pub/sub works
python3 -c "
import asyncio, nats, json

async def test():
    nc = await nats.connect('nats://localhost:4222')
    js = nc.jetstream()

    # Publish a test message
    ack = await js.publish('agents.observer.anomalies', json.dumps({'test': True}).encode())
    print(f'Published to seq {ack.seq}')

    await nc.drain()

asyncio.run(test())
"
```

---

## 7. End-to-End Incident Lifecycle

This tests the full agent swarm pipeline: anomaly detection -> diagnosis -> safety review -> remediation -> resolution.

### Prerequisites

```bash
make up              # Start everything
make init-nats       # Ensure streams exist
```

### Simulate an Anomaly

Publish a fake anomaly to trigger the orchestrator:

```bash
python3 -c "
import asyncio, json, uuid, nats

async def inject_anomaly():
    nc = await nats.connect('nats://localhost:4222')
    js = nc.jetstream()

    anomaly = {
        'message_id': str(uuid.uuid4()),
        'correlation_id': str(uuid.uuid4()),
        'trace_id': str(uuid.uuid4()),
        'source_agent': 'test.manual',
        'target_agent': 'orchestrator',
        'message_type': 'anomaly_detected',
        'priority': 1,
        'ttl_seconds': 300,
        'timestamp': '$(date -u +%Y-%m-%dT%H:%M:%S)',
        'retry_count': 0,
        'payload': {
            'metric': 'cpu_usage',
            'service': 'user-svc',
            'severity': 'high',
            'value': 2.5,
            'threshold': 1.5,
            'description': 'CPU usage exceeded threshold on user-svc'
        },
        'context': {}
    }

    ack = await js.publish('agents.observer.anomalies', json.dumps(anomaly).encode())
    print(f'Anomaly published (seq={ack.seq}, correlation_id={anomaly[\"correlation_id\"]})')
    print(f'Track this incident with: correlation_id = {anomaly[\"correlation_id\"]}')

    await nc.drain()

asyncio.run(inject_anomaly())
"
```

### What to Expect (Happy Path)

1. **Orchestrator** receives anomaly, creates Incident in DB, transitions FSM to `diagnosing`
2. **Diagnoser** receives diagnosis request, generates RCA, publishes result
3. **Orchestrator** transitions to `proposing_remediation`, routes to safety
4. **Safety Agent** evaluates blast radius and policies
   - If auto-approved: transitions to `executing`
   - If needs human approval: transitions to `safety_review`
5. **Remediator** executes the action (container restart, scaling, etc.)
6. **Orchestrator** transitions through `verifying` -> `resolved`

### Verify via Dashboard API

```bash
# List all incidents
curl -sf http://localhost:8010/api/incidents | python3 -m json.tool

# Get incident details (replace {id} with correlation_id from above)
curl -sf http://localhost:8010/api/incidents/{id} | python3 -m json.tool

# Get incident timeline
curl -sf http://localhost:8010/api/incidents/{id}/timeline | python3 -m json.tool

# Get aggregate stats
curl -sf http://localhost:8010/api/incidents/stats | python3 -m json.tool
```

### Verify via Database

```bash
# Connect to agents DB
psql -h localhost -p 5432 -U postgres -d agents

# Check incidents
SELECT id, status, severity, created_at, resolved_at, auto_resolved FROM incidents ORDER BY created_at DESC LIMIT 5;

# Check timeline
SELECT id, status, jsonb_array_length(timeline) as events FROM incidents ORDER BY created_at DESC LIMIT 5;

# Check anomalies
SELECT id, incident_id, metric, service, severity FROM anomalies ORDER BY detected_at DESC LIMIT 5;

# Check agent heartbeats
SELECT agent_id, agent_type, status, last_seen_at FROM agent_heartbeats ORDER BY last_seen_at DESC;
```

### Verify Agent Health via Dashboard

```bash
# List all agents and their health status
curl -sf http://localhost:8010/api/agents | python3 -m json.tool
```

**Expected:** Each agent shows `"status": "healthy"` with recent `last_seen_at`.

---

## 8. Dashboard API Manual Testing

### Incidents API

```bash
# List incidents (with filters)
curl -sf "http://localhost:8010/api/incidents?status=detecting&limit=10" | python3 -m json.tool
curl -sf "http://localhost:8010/api/incidents?severity=critical" | python3 -m json.tool

# Incident stats
curl -sf http://localhost:8010/api/incidents/stats | python3 -m json.tool
# Expected:
# {
#   "total": N,
#   "by_status": {"detecting": 1, "resolved": 5, ...},
#   "by_severity": {"high": 3, "critical": 1, ...},
#   "resolved_today": N,
#   "avg_mttr_seconds": 123.4
# }
```

### Approvals API (Human-in-the-Loop)

```bash
# List pending approvals
curl -sf http://localhost:8010/api/approvals | python3 -m json.tool

# Approve an action (replace {incident_id})
curl -X POST http://localhost:8010/api/approvals/{incident_id}/approve \
  -H "Content-Type: application/json" \
  -d '{"reason": "Looks safe to proceed"}'

# Reject an action
curl -X POST http://localhost:8010/api/approvals/{incident_id}/reject \
  -H "Content-Type: application/json" \
  -d '{"reason": "Too risky during peak hours"}'
```

**What happens on approve:**
1. Dashboard API publishes to `human.approvals.responses` via NATS
2. Orchestrator receives the approval
3. FSM transitions from `safety_review` -> `executing`
4. Remediator executes the action

**What happens on reject:**
1. Same NATS publish
2. Orchestrator marks the rejection in timeline
3. Escalation manager decides next step (retry or escalate further)

### Agents API

```bash
# List all agents
curl -sf http://localhost:8010/api/agents | python3 -m json.tool

# Get specific agent
curl -sf http://localhost:8010/api/agents/{agent_id} | python3 -m json.tool
```

---

## 9. WebSocket Live Events

The dashboard exposes a WebSocket at `ws://localhost:8010/ws` that pushes real-time events.

### Test with wscat

```bash
# Install wscat if needed
npm install -g wscat

# Connect
wscat -c ws://localhost:8010/ws
```

### Test with Python

```bash
pip install websockets

python3 -c "
import asyncio, websockets, json

async def listen():
    async with websockets.connect('ws://localhost:8010/ws') as ws:
        print('Connected to WebSocket. Waiting for events...')
        async for message in ws:
            data = json.loads(message)
            print(f'[{data[\"type\"]}] {json.dumps(data, indent=2)}')

asyncio.run(listen())
"
```

### Expected Event Types

| Event Type | Trigger |
|-----------|---------|
| `incident.created` | Orchestrator creates a new incident |
| `incident.updated` | FSM state transition |
| `incident.resolved` | Incident reaches resolved state |
| `agent.heartbeat` | Agent publishes heartbeat (every 30s) |
| `agent.dead` | Agent misses heartbeats (>90s stale) |
| `approval.requested` | Incident enters `safety_review` |
| `approval.resolved` | Human approves/rejects via dashboard |

### Test Workflow

1. Open the WebSocket listener in one terminal
2. In another terminal, publish an anomaly (see Section 7)
3. Watch the events flow through in real-time:
   - `incident.created` -> `incident.updated` (diagnosing) -> `incident.updated` (proposing_remediation) -> ... -> `incident.resolved`

---

## 10. Chaos Engineering

The chaos framework injects real failures and measures how the agent swarm responds.

### Prerequisites

```bash
make up         # Full stack running
make init-nats  # Streams initialised
```

### Available Scenarios

| Scenario | What It Does |
|----------|-------------|
| `memory_leak` | Stress-test a container's memory |
| `cpu_spike` | Pin CPU on a service container |
| `network_partition` | Isolate a service from the network |
| `db_overload` | Flood a database with connections |

### Dry Run (Plan Only)

```bash
python scripts/chaos/runner.py --dry-run
```

### Run All Scenarios

```bash
python scripts/chaos/runner.py
```

### Run Single Scenario

```bash
python scripts/chaos/runner.py --scenario memory_leak
```

### What Happens

1. **Inject** — The chaos runner introduces a failure (e.g., kills a container, adds latency)
2. **Detect** — Observer agents poll Prometheus/Loki and publish anomalies
3. **Diagnose** — Diagnoser generates root cause analysis
4. **Review** — Safety agent evaluates the proposed remediation
5. **Remediate** — Remediator executes the action (restart, scale, etc.)
6. **Score** — Runner queries the DB for MTTD (Mean Time To Detect) and MTTR (Mean Time To Resolve)

### Output

A Markdown report is generated at `scripts/chaos/report_YYYYMMDD_HHMMSS.md`:

```
| Scenario | Outcome | MTTD (s) | MTTR (s) | Score |
|----------|---------|----------|----------|-------|
| memory_leak | resolved | 45.2 | 98.7 | A (92) |
| cpu_spike | resolved | 38.1 | 112.3 | A (90) |
```

### Scoring Rubric

| Grade | Points | Criteria |
|-------|--------|----------|
| A | >= 90 | MTTD < 60s AND MTTR < 120s |
| B | >= 70 | MTTD < 120s AND MTTR < 300s |
| C | >= 50 | MTTD < 300s AND MTTR < 600s |
| F | < 50 | Undetected or MTTR > 600s |

---

## 11. Linting

```bash
make lint
```

Runs [Ruff](https://docs.astral.sh/ruff/) on Python code:

```bash
cd shared && ruff check . --fix
cd services/user-service && ruff check . --fix
cd services/payment-service && ruff check . --fix
```

### Go Linting

```bash
cd services/order-service && golangci-lint run
cd services/inventory-worker && golangci-lint run
```

---

## 12. CI Pipeline

The GitHub Actions workflow (`.github/workflows/ci.yml`) runs on every push:

| Job | What It Does |
|-----|-------------|
| `lint-python` | Runs Ruff on Python code |
| `test-python` | Installs shared package, runs `pytest shared/tests/` |
| `lint-go` | Runs golangci-lint on Go services |
| `build-images` | Builds all Docker images (depends on all lint/test jobs) |

### Run CI Checks Locally

```bash
# Reproduce what CI does
make lint
python -m pytest shared/tests/ -v --tb=short
cd services/order-service && go test ./... -v
cd services/inventory-worker && go test ./... -v
docker compose build
```

---

## 13. Troubleshooting

### Tests Fail with `ModuleNotFoundError`

```bash
# Ensure shared package is installed
pip install -e "shared/[dev]"

# For agent tests, install their requirements too
pip install -r agents/observer/requirements.txt
pip install -r agents/diagnoser/requirements.txt
pip install -r agents/safety/requirements.txt
pip install -r agents/orchestrator/requirements.txt
pip install -r dashboard/requirements.txt
```

### Tests Fail with `NameError: name 'timezone' is not defined`

This was a known bug (fixed). If you see it, ensure you're on the latest code. The fix adds `timezone` to all `from datetime import datetime` statements.

### Docker Compose Fails to Start

```bash
# Check what's running
docker compose ps

# Check logs for failing service
docker compose logs user-svc --tail=50
docker compose logs orchestrator-agent --tail=50

# Common issue: ports already in use
lsof -i :8001   # Check who's using port 8001
```

### NATS Connection Refused

```bash
# Check if NATS is running
docker compose ps nats
curl http://localhost:8222/healthz

# If not running
make infra-up
make init-nats
```

### Agent Heartbeats Not Appearing

```bash
# Check if agents are running
docker compose ps | grep agent

# Check agent logs
docker compose logs orchestrator-agent --tail=20

# Verify heartbeat subject has messages
curl -sf http://localhost:8222/jsz | python3 -c "
import json, sys
data = json.load(sys.stdin)
for s in data.get('account_details', [{}])[0].get('stream_detail', []):
    print(f\"{s['config']['name']}: {s['state']['messages']} messages\")
"
```

### Dashboard Shows No Data

1. Check dashboard-api health: `curl http://localhost:8010/health`
2. Check DB connectivity: look for `"db_connected": true` in health response
3. Check NATS connectivity: look for `"nats_connected": true`
4. Verify incidents exist: `curl http://localhost:8010/api/incidents`
5. Check orchestrator is running: `docker compose logs orchestrator-agent --tail=20`

### Cleanup Everything

```bash
make clean
```

This stops all services, removes Docker volumes (data is lost), and clears Python caches.

---

## Quick Reference

| Command | What It Does | Infra Required? |
|---------|-------------|-----------------|
| `make test` | Run all unit tests | No |
| `make lint` | Run linters | No |
| `make infra-up` | Start databases, Redis, NATS, ES | - |
| `make init-nats` | Create JetStream streams | Yes |
| `make up` | Start everything | - |
| `make health` | Check all service health endpoints | Yes |
| `make obs-up` | Start Prometheus, Grafana, Loki, Tempo | Yes |
| `make agents-up` | Start all agent containers | Yes |
| `make dashboard-up` | Start Dashboard API + Frontend | Yes |
| `make test-integration` | Run integration tests | Starts infra automatically |
| `make down` | Stop all services | - |
| `make clean` | Stop + remove all volumes | - |
