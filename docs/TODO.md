# SRE Agent Swarm — Progress Tracker

> **Project:** Self-Healing Infrastructure Agent Swarm
> **Started:** March 2026
> **Last Updated:** 2026-03-03

**Legend:** `[ ]` Not started | `[~]` In progress | `[x]` Done | `[!]` Blocked

---

## Phase 1 — Core Foundation & MVP Infra (Target: Week 1-2)

**Definition of Done (DoD):**
- Project repository and CI/CD basics are in place.
- Core agent communication backbone (NATS JetStream) is operational.
- Minimal MVP subset of microservices (Gateway, User, Auth, Order, Payment) are running and communicating successfully.
- Cross-cutting concerns (shared logger, config, agent base class) are established and used by early services.

### 1.1 Core Setup & Back-end

| # | Task | Status | Dependencies | Notes |
|---|------|--------|--------------|-------|
| 1.1.1 | Set up project repo structure & CI/CD tooling | `[ ]` | None | Monorepo layout, linting, pipelines |
| 1.1.2 | Create shared Python package for agent base class | `[ ]` | 1.1.1 | Common init, heartbeat logic |
| 1.1.3 | Set up configuration management (etcd/env) | `[ ]` | 1.1.1 | Centralized config for all agents |
| 1.1.4 | Setup structured logging for agents/services | `[ ]` | 1.1.1 | JSON logs with correlation IDs |
| 1.1.5 | Create `docker-compose.infrastructure.yml` (Core) | `[ ]` | None | PostgreSQL, Redis, NATS |

### 1.2 MVP Microservices Environment

| # | Task | Status | Dependencies | Notes |
|---|------|--------|--------------|-------|
| 1.2.1 | Build API Gateway (Kong/Nginx) | `[ ]` | 1.1.5 | Port 8000, routing config |
| 1.2.2 | Build User Service (FastAPI, :8001) | `[ ]` | 1.1.5 | User CRUD, profile management |
| 1.2.3 | Build Auth Service (Node.js/Express, :8004) | `[ ]` | 1.2.2 | JWT auth, OAuth, token refresh |
| 1.2.4 | Build Order Service (Go/Gin, :8002) | `[ ]` | 1.1.5 | Order lifecycle, state machine |
| 1.2.5 | Build Payment Service (FastAPI, :8005) | `[ ]` | 1.2.4 | Payment processing, refunds |

### 1.3 Agent Backbone

| # | Task | Status | Dependencies | Notes |
|---|------|--------|--------------|-------|
| 1.3.1 | Define `AgentMessage` envelope schema | `[ ]` | None | message_id, correlation_id, etc. |
| 1.3.2 | Set up NATS JetStream subjects (`agents.*`) | `[ ]` | 1.1.5 | `incidents.*`, `human.*` |
| 1.3.3 | Build shared NATS client library | `[ ]` | 1.3.1, 1.3.2 | Pub/sub, request-reply, retry logic |
| 1.3.4 | Build agent heartbeat system | `[ ]` | 1.1.2, 1.3.3 | Health monitoring via `agents.heartbeat` |
| 1.3.5 | Set up PostgreSQL for incident state | `[ ]` | 1.1.5 | `postgres-agents` |

---

## Phase 2 — Extended Infra & Observability (Target: Week 3-4)

**Definition of Done (DoD):**
- Remaining microservices (Product, Search, Workers) are fully deployed (10-15 total containers).
- Prometheus is scraping all metrics, Loki is aggregating structured logs.
- Distributed tracing (Tempo/OpenTelemetry) flows from Gateway to backend and agent nodes.
- Full `docker-compose up` works end-to-end without failing health checks.

### 2.1 Extended Microservices Environment

| # | Task | Status | Dependencies | Notes |
|---|------|--------|--------------|-------|
| 2.1.1 | Update `docker-compose` with Elasticsearch | `[ ]` | 1.1.5 | Required for Product/Search |
| 2.1.2 | Build Product Service (Django, :8003) | `[ ]` | 2.1.1 | Catalog, search |
| 2.1.3 | Build Search Service (FastAPI, :8006) | `[ ]` | 2.1.1 | Full-text search via ES |
| 2.1.4 | Build Notification Worker (Python, :8007) | `[ ]` | 1.1.5 | NATS consumer |
| 2.1.5 | Build Inventory Worker (Go, :8008) | `[ ]` | 1.2.4 | NATS consumer + Postgres |
| 2.1.6 | Build Analytics Worker (Python, :8009) | `[ ]` | 1.1.5 | NATS consumer, metrics aggregation |
| 2.1.7 | Set up inter-service comms (sync + async) | `[ ]` | 1.2.1, 2.1.6 | Validate HTTP/gRPC routing |
| 2.1.8 | Verify full docker-compose up works end-to-end | `[ ]` | 2.1.7 | All health checks pass |

### 2.2 Observability Stack

| # | Task | Status | Dependencies | Notes |
|---|------|--------|--------------|-------|
| 2.2.1 | Configure Prometheus (:9090) | `[ ]` | 2.1.8 | Scrape configs |
| 2.2.2 | Configure Grafana (:3000) & Dashboards | `[ ]` | 2.2.1 | Dashboards for each service |
| 2.2.3 | Configure Loki (:3100) | `[ ]` | 1.1.4 | Log aggregation from containers |
| 2.2.4 | Configure Tempo (:3200) | `[ ]` | 2.1.8 | Distributed tracing backend |
| 2.2.5 | Configure AlertManager (:9093) | `[ ]` | 2.2.1 | Alerting rules |
| 2.2.6 | Add Prometheus metrics to all services | `[ ]` | 2.2.1 | HTTP metrics, custom business metrics |
| 2.2.7 | Add distributed tracing to services & agents | `[ ]` | 2.2.4 | Trace ID propagation |
| 2.2.8 | Implement CI/CD pipeline | `[ ]` | 1.1.1 | Lint, test, build Docker images |

---

## Phase 3 — Observer & Diagnosis (Target: Week 5-6)

**Definition of Done (DoD):**
- Observer pool detects injected anomalies within an MTTD < 60s.
- Diagnoser accurately generates root cause hypothesis (RCA) for at least 3 distinct failure modes with >60% confidence.
- Observers and Diagnosers have >80% code coverage on core logic.

### 3.1 Observer Agent Pool

| # | Task | Status | Dependencies | Notes |
|---|------|--------|--------------|-------|
| 3.1.1 | Build `AnomalyDetector` class | `[ ]` | 1.1.2 | Dynamic/static thresholds, z-score |
| 3.1.2 | Build `AlertDeduplicator` | `[ ]` | 1.1.2 | Fingerprint-based dedup (5m window) |
| 3.1.3 | Build **Metrics Observer** | `[ ]` | 2.2.6, 3.1.2 | PromQL anomaly logic (11 queries) |
| 3.1.4 | Build **Log Observer** | `[ ]` | 2.2.3, 3.1.2 | Loki log pattern matching |
| 3.1.5 | Build **Health Check Observer** | `[ ]` | 2.1.8 | Actively probe endpoints |
| 3.1.6 | Build **Synthetic Prober** | `[ ]` | 2.1.8 | E2E transaction scenarios |
| 3.1.7 | Unit tests for anomaly detection & dedup | `[ ]` | 3.1.1, 3.1.2 | |

### 3.2 Diagnoser Agent

| # | Task | Status | Dependencies | Notes |
|---|------|--------|--------------|-------|
| 3.2.1 | Build `ContextCollector` | `[ ]` | 2.2.1, 2.2.3 | Gather recent logs, metrics, deps |
| 3.2.2 | Build `CorrelationEngine` | `[ ]` | 3.2.1 | Temporal/topological mapped anomalies |
| 3.2.3 | Build `HypothesisGenerator` (LLM-based) | `[ ]` | 3.2.2 | Prompt with context → causal logic |
| 3.2.4 | Build `RCAEngine` (Root Cause Analysis) | `[ ]` | 3.2.3 | Combine signals + LLM reasoning |
| 3.2.5 | Build evidence-gathering tools for Diagnoser | `[ ]` | 3.2.1 | Action invocations for context checking |
| 3.2.6 | Define diagnosis confidence scoring | `[ ]` | 3.2.4 | High/medium/low assessment |
| 3.2.7 | Unit + integration tests for Diagnoser | `[ ]` | 3.2.4 | Simulate known failure inputs |

---

## Phase 4 — Remediation & Safety (Target: Week 7-8)

**Definition of Done (DoD):**
- Safety agent successfully parses trust hierarchy and blocks unauthorized/high-risk actions.
- Remediator manages executing requested basic fixes (restarts, scale-ups) and correctly applies rollbacks if verification fails.
- MTTR targets start tracking under 5 minutes for auto-remediated issues.

### 4.1 Remediator Agent

| # | Task | Status | Dependencies | Notes |
|---|------|--------|--------------|-------|
| 4.1.1 | Design runbook YAML schema | `[ ]` | None | Conditions, risk levels, rollbacks |
| 4.1.2 | Build `RunbookEngine` | `[ ]` | 4.1.1, 3.2.4 | Match RCA to appropriate runbook |
| 4.1.3 | Build `ActionExecutor` | `[ ]` | 4.1.2 | Issue explicit Docker/k8s commands |
| 4.1.4 | Build `RollbackManager` | `[ ]` | 4.1.3 | Revert state via captured initial values |
| 4.1.5 | Build `VerificationEngine` | `[ ]` | 3.1.3 | Follow-up health checks |
| 4.1.6 | Write initial runbooks | `[ ]` | 4.1.1 | Restart, scale, limits, circuit_break |
| 4.1.7 | Tests for each runbook action | `[ ]` | 4.1.6 | |

### 4.2 Safety Agent

| # | Task | Status | Dependencies | Notes |
|---|------|--------|--------------|-------|
| 4.2.1 | Build `PolicyEngine` | `[ ]` | 1.1.2 | Rule-based evaluation |
| 4.2.2 | Build `BlastRadiusCalculator` | `[ ]` | 3.2.2 | Estimate dependency impact |
| 4.2.3 | Build `RateLimiter` for actions | `[ ]` | 1.3.5 | Prevent loop identical fixes |
| 4.2.4 | Build `HumanApprovalGateway` | `[ ]` | 4.2.1 | Pending dashboard/WS notifications |
| 4.2.5 | Define trust hierarchy | `[ ]` | 4.2.1 | Auto-approve vs review |
| 4.2.6 | Integration tests for safety gates | `[ ]` | 4.2.5 | Verify policy blocks correctly |

---

## Phase 5 — Orchestration & Dashboard (Target: Week 9-10)

**Definition of Done (DoD):**
- Entire incident lifecycle operates successfully from `detected` -> `verified` -> `closed`.
- Operator dashboard renders live incident timelines, visualizes active agents and processes approvals.

### 5.1 Orchestrator Agent

| # | Task | Status | Dependencies | Notes |
|---|------|--------|--------------|-------|
| 5.1.1 | Build Incident FSM (Finite State Machine) | `[ ]` | 1.3.5 | Life cycle statuses |
| 5.1.2 | Build `AgentRouter` | `[ ]` | 5.1.1 | Route jobs between agent silos |
| 5.1.3 | Build `EscalationManager` | `[ ]` | 5.1.1 | Timeout-based fallback to humans |
| 5.1.4 | Wire full incident lifecycle | `[ ]` | 3.1, 3.2, 4.1, 4.2 | Detect → Assess → Fix |
| 5.1.5 | Build incident timeline generation | `[ ]` | 5.1.4 | Export for post-mortem usage |
| 5.1.6 | Add retry logic & timeout handling | `[ ]` | 5.1.4 | Ensure idempotency |
| 5.1.7 | End-to-end integration tests | `[ ]` | 5.1.4 | Full pipeline tracking |

### 5.2 Dashboard & API

| # | Task | Status | Dependencies | Notes |
|---|------|--------|--------------|-------|
| 5.2.1 | Build Dashboard API (FastAPI) | `[ ]` | 1.3.5 | REST exposure of states |
| 5.2.2 | Build WebSocket server | `[ ]` | 5.2.1 | Sub-second state streaming |
| 5.2.3 | Build Frontend (React/Streamlit) UI | `[ ]` | 5.2.1 | UI layout & components |
| 5.2.4 | Human approval UI in dashboard | `[ ]` | 4.2.4, 5.2.3 | Review and approve popups |

---

## Phase 6 — Advanced Features (Target: Week 11+)

**Definition of Done (DoD):**
- Automated Chaos pipeline repeatedly tests entire agent workflow stability.
- Documentation mapping runbooks and architectures finalized.
- Learning agent actively tracks and recalls historic incidents.

### 6.1 Learning Agent

| # | Task | Status | Dependencies | Notes |
|---|------|--------|--------------|-------|
| 6.1.1 | Build `IncidentVectorizer` | `[ ]` | 5.1.5 | Embed incidents into ChromaDB |
| 6.1.2 | Build `PatternRecognizer` | `[ ]` | 6.1.1 | RAG over historical similarities |
| 6.1.3 | Build `RunbookOptimizer` | `[ ]` | 6.1.2 | Success rate-based learning |

### 6.2 Chaos Engineering

| # | Task | Status | Dependencies | Notes |
|---|------|--------|--------------|-------|
| 6.2.1 | Build chaos injection scripts | `[ ]` | None | Simulate network/OOM/CPU issues |
| 6.2.2 | Automated chaos scenario runner | `[ ]` | 6.2.1 | Systematically iterate regressions |
| 6.2.3 | Scoring system for agent performance | `[ ]` | 6.2.2 | Record and display MTTD/MTTR |

### 6.3 Predictive Detection & Polish

| # | Task | Status | Dependencies | Notes |
|---|------|--------|--------------|-------|
| 6.3.1 | Trend-based prediction capabilities | `[ ]` | 3.1.3 | Issue early pre-outage alerts |
| 6.3.2 | Multi-agent debate mechanism | `[ ]` | 3.2.3 | Handle ambiguous RCAs |
| 6.3.3 | Documentation wrap-up | `[ ]` | None | Guides: architecture, deployment |

---

## Summary

| Phase | Total Tasks | Done | In Progress | Blocked |
|-------|-------------|------|-------------|---------|
| Phase 1 — Core Foundation & MVP Infra | 15 | 0 | 0 | 0 |
| Phase 2 — Extended Infra & Observability | 16 | 0 | 0 | 0 |
| Phase 3 — Observer & Diagnosis | 14 | 0 | 0 | 0 |
| Phase 4 — Remediation & Safety | 13 | 0 | 0 | 0 |
| Phase 5 — Orchestration & Dashboard | 11 | 0 | 0 | 0 |
| Phase 6 — Advanced Features | 9 | 0 | 0 | 0 |
| **Total** | **78** | **0** | **0** | **0** |
