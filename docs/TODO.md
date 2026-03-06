# SRE Agent Swarm — Progress Tracker

> **Project:** Self-Healing Infrastructure Agent Swarm
> **Started:** March 2026
> **Last Updated:** 2026-03-05
> **Phase 1 Status:** ✅ Complete (committed: `a1d09df`)
> **Phase 2 Status:** ✅ Complete
> **Phase 3 Status:** ✅ Complete
> **Phase 4 Status:** ✅ Complete
> **Phase 5 Status:** ✅ Complete
> **Phase 6 Status:** ✅ Complete

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
| 1.1.1 | Set up project repo structure & CI/CD tooling | `[x]` | None | Monorepo, `Makefile`, `.env.example`, `.gitignore` |
| 1.1.2 | Create shared Python package for agent base class | `[x]` | 1.1.1 | `shared/agents/base.py` — `BaseAgent` with lifecycle, heartbeat, signal handling |
| 1.1.3 | Set up configuration management (env/.env) | `[x]` | 1.1.1 | `shared/config/settings.py` — Pydantic `BaseSettings` |
| 1.1.4 | Setup structured logging for agents/services | `[x]` | 1.1.1 | `shared/logging/logger.py` — `structlog` JSON with correlation ID context vars |
| 1.1.5 | Create `docker-compose.infrastructure.yml` (Core) | `[x]` | None | PostgreSQL ×3 (5432/5433/5434), Redis (:6379), NATS JetStream (:4222/:8222) — all healthy |

### 1.2 MVP Microservices Environment

| # | Task | Status | Dependencies | Notes |
|---|------|--------|--------------|-------|
| 1.2.1 | Build API Gateway (Nginx) | `[x]` | 1.1.5 | `nginx.conf` routing `/users` `/auth` `/orders` `/payments` → upstreams |
| 1.2.2 | Build User Service (FastAPI, :8001) | `[x]` | 1.1.5 | User CRUD backed by Redis, Prometheus metrics, `/health` |
| 1.2.3 | Build Auth Service (Node.js/Express, :8004) | `[x]` | 1.2.2 | JWT access+refresh tokens, Redis blacklist, `/login` `/verify` `/refresh` `/logout` |
| 1.2.4 | Build Order Service (Go/Gin, :8002) | `[x]` | 1.1.5 | Order state machine (pending→confirmed→…), PostgreSQL, publishes `orders.created` to NATS |
| 1.2.5 | Build Payment Service (FastAPI, :8005) | `[x]` | 1.2.4 | asyncpg pool, refund endpoint, publishes `payments.completed`/`payments.failed` to NATS |

### 1.3 Agent Backbone

| # | Task | Status | Dependencies | Notes |
|---|------|--------|--------------|-------|
| 1.3.1 | Define `AgentMessage` envelope schema | `[x]` | None | `shared/messaging/schema.py` — dataclass with UUID, TTL, priority, correlation_id |
| 1.3.2 | Set up NATS JetStream subjects & streams | `[x]` | 1.1.5 | `shared/messaging/subjects.py` + `scripts/init_nats.py` creates 4 streams (AGENTS/INCIDENTS/HUMAN/BUSINESS) |
| 1.3.3 | Build shared NATS client library | `[x]` | 1.3.1, 1.3.2 | `shared/messaging/nats_client.py` — pub/subscribe/request-reply with exponential backoff retry |
| 1.3.4 | Build agent heartbeat system | `[x]` | 1.1.2, 1.3.3 | Built into `BaseAgent` — publishes to `agents.heartbeat` every 30s |
| 1.3.5 | Set up PostgreSQL for incident state | `[x]` | 1.1.5 | `shared/db/models.py` — `Incident`, `Anomaly`, `AgentHeartbeat` (SQLAlchemy async) |

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
| 2.1.1 | Update `docker-compose` with Elasticsearch | `[x]` | 1.1.5 | Required for Product/Search |
| 2.1.2 | Build Product Service (Django, :8003) | `[x]` | 2.1.1 | Catalog, search |
| 2.1.3 | Build Search Service (FastAPI, :8006) | `[x]` | 2.1.1 | Full-text search via ES |
| 2.1.4 | Build Notification Worker (Python, :8007) | `[x]` | 1.1.5 | NATS consumer |
| 2.1.5 | Build Inventory Worker (Go, :8008) | `[x]` | 1.2.4 | NATS consumer + Postgres |
| 2.1.6 | Build Analytics Worker (Python, :8009) | `[x]` | 1.1.5 | NATS consumer, metrics aggregation |
| 2.1.7 | Set up inter-service comms (sync + async) | `[x]` | 1.2.1, 2.1.6 | Validate HTTP/gRPC routing |
| 2.1.8 | Verify full docker-compose up works end-to-end | `[x]` | 2.1.7 | All health checks pass |

### 2.2 Observability Stack

| # | Task | Status | Dependencies | Notes |
|---|------|--------|--------------|-------|
| 2.2.1 | Configure Prometheus (:9090) | `[x]` | 2.1.8 | Scrape configs |
| 2.2.2 | Configure Grafana (:3000) & Dashboards | `[x]` | 2.2.1 | Dashboards for each service |
| 2.2.3 | Configure Loki (:3100) | `[x]` | 1.1.4 | Log aggregation from containers |
| 2.2.4 | Configure Tempo (:3200) | `[x]` | 2.1.8 | Distributed tracing backend |
| 2.2.5 | Configure AlertManager (:9093) | `[x]` | 2.2.1 | Alerting rules |
| 2.2.6 | Add Prometheus metrics to all services | `[x]` | 2.2.1 | HTTP metrics, custom business metrics |
| 2.2.7 | Add distributed tracing to services & agents | `[x]` | 2.2.4 | Trace ID propagation |
| 2.2.8 | Implement CI/CD pipeline | `[x]` | 1.1.1 | Lint, test, build Docker images |

---

## Phase 3 — Observer & Diagnosis (Target: Week 5-6)

**Definition of Done (DoD):**
- Observer pool detects injected anomalies within an MTTD < 60s.
- Diagnoser accurately generates root cause hypothesis (RCA) for at least 3 distinct failure modes with >60% confidence.
- Observers and Diagnosers have >80% code coverage on core logic.

### 3.1 Observer Agent Pool

| # | Task | Status | Dependencies | Notes |
|---|------|--------|--------------|-------|
| 3.1.1 | Build `AnomalyDetector` class | `[x]` | 1.1.2 | Dynamic/static thresholds, z-score |
| 3.1.2 | Build `AlertDeduplicator` | `[x]` | 1.1.2 | Fingerprint-based dedup (5m window) |
| 3.1.3 | Build **Metrics Observer** | `[x]` | 2.2.6, 3.1.2 | PromQL anomaly logic (11 queries) |
| 3.1.4 | Build **Log Observer** | `[x]` | 2.2.3, 3.1.2 | Loki log pattern matching |
| 3.1.5 | Build **Health Check Observer** | `[x]` | 2.1.8 | Actively probe endpoints |
| 3.1.6 | Build **Synthetic Prober** | `[x]` | 2.1.8 | E2E transaction scenarios |
| 3.1.7 | Unit tests for anomaly detection & dedup | `[x]` | 3.1.1, 3.1.2 | |

### 3.2 Diagnoser Agent

| # | Task | Status | Dependencies | Notes |
|---|------|--------|--------------|-------|
| 3.2.1 | Build `ContextCollector` | `[x]` | 2.2.1, 2.2.3 | Gather recent logs, metrics, deps |
| 3.2.2 | Build `CorrelationEngine` | `[x]` | 3.2.1 | Temporal/topological mapped anomalies |
| 3.2.3 | Build `HypothesisGenerator` (LLM-based) | `[x]` | 3.2.2 | Prompt with context → causal logic |
| 3.2.4 | Build `RCAEngine` (Root Cause Analysis) | `[x]` | 3.2.3 | Combine signals + LLM reasoning |
| 3.2.5 | Build evidence-gathering tools for Diagnoser | `[x]` | 3.2.1 | Action invocations for context checking |
| 3.2.6 | Define diagnosis confidence scoring | `[x]` | 3.2.4 | High/medium/low assessment |
| 3.2.7 | Unit + integration tests for Diagnoser | `[x]` | 3.2.4 | Simulate known failure inputs |

---

## Phase 4 — Remediation & Safety (Target: Week 7-8)

**Definition of Done (DoD):**
- Safety agent successfully parses trust hierarchy and blocks unauthorized/high-risk actions.
- Remediator manages executing requested basic fixes (restarts, scale-ups) and correctly applies rollbacks if verification fails.
- MTTR targets start tracking under 5 minutes for auto-remediated issues.

### 4.1 Remediator Agent

| # | Task | Status | Dependencies | Notes |
|---|------|--------|--------------|-------|
| 4.1.1 | Design runbook YAML schema | `[x]` | None | Conditions, risk levels, rollbacks |
| 4.1.2 | Build `RunbookEngine` | `[x]` | 4.1.1, 3.2.4 | Match RCA to appropriate runbook |
| 4.1.3 | Build `ActionExecutor` | `[x]` | 4.1.2 | Issue explicit Docker/k8s commands |
| 4.1.4 | Build `RollbackManager` | `[x]` | 4.1.3 | Revert state via captured initial values |
| 4.1.5 | Build `VerificationEngine` | `[x]` | 3.1.3 | Follow-up health checks |
| 4.1.6 | Write initial runbooks | `[x]` | 4.1.1 | Restart, scale, limits, circuit_break |
| 4.1.7 | Tests for each runbook action | `[x]` | 4.1.6 | `agents/remediator/tests/test_remediator.py` — 12 per-runbook tests (match, confidence, action type, approval, targets) |

### 4.2 Safety Agent

| # | Task | Status | Dependencies | Notes |
|---|------|--------|--------------|-------|
| 4.2.1 | Build `PolicyEngine` | `[x]` | 1.1.2 | Rule-based evaluation |
| 4.2.2 | Build `BlastRadiusCalculator` | `[x]` | 3.2.2 | Estimate dependency impact |
| 4.2.3 | Build `RateLimiter` for actions | `[x]` | 1.3.5 | Prevent loop identical fixes |
| 4.2.4 | Build `HumanApprovalGateway` | `[x]` | 4.2.1 | Pending dashboard/WS notifications |
| 4.2.5 | Define trust hierarchy | `[x]` | 4.2.1 | Auto-approve vs review |
| 4.2.6 | Integration tests for safety gates | `[x]` | 4.2.5 | Verify policy blocks correctly |

---

## Phase 5 — Orchestration & Dashboard (Target: Week 9-10)

**Definition of Done (DoD):**
- Entire incident lifecycle operates successfully from `detected` -> `verified` -> `closed`.
- Operator dashboard renders live incident timelines, visualizes active agents and processes approvals.

### 5.1 Orchestrator Agent

| # | Task | Status | Dependencies | Notes |
|---|------|--------|--------------|-------|
| 5.1.1 | Build Incident FSM (Finite State Machine) | `[x]` | 1.3.5 | `agents/orchestrator/src/incident_fsm.py` — 8 states, timeouts, retries |
| 5.1.2 | Build `AgentRouter` | `[x]` | 5.1.1 | `agents/orchestrator/src/agent_router.py` — heartbeat registry, routing |
| 5.1.3 | Build `EscalationManager` | `[x]` | 5.1.1 | `agents/orchestrator/src/escalation_manager.py` — timeouts, retries, human escalation |
| 5.1.4 | Wire full incident lifecycle | `[x]` | 3.1, 3.2, 4.1, 4.2 | `agents/orchestrator/src/orchestrator_agent.py` — subscribes to 6 NATS subjects |
| 5.1.5 | Build incident timeline generation | `[x]` | 5.1.4 | `agents/orchestrator/src/timeline_builder.py` — events + postmortem |
| 5.1.6 | Add retry logic & timeout handling | `[x]` | 5.1.4 | Built into FSM + EscalationManager (max 2 retries per state) |
| 5.1.7 | End-to-end integration tests | `[x]` | 5.1.4 | `agents/orchestrator/tests/test_orchestrator_integration.py` |

### 5.2 Dashboard & API

| # | Task | Status | Dependencies | Notes |
|---|------|--------|--------------|-------|
| 5.2.1 | Build Dashboard API (FastAPI) | `[x]` | 1.3.5 | `dashboard/api/` — incidents, agents, approvals, health endpoints on :8010 |
| 5.2.2 | Build WebSocket server | `[x]` | 5.2.1 | `dashboard/api/websocket/` — NATS-to-WebSocket bridge, ConnectionManager |
| 5.2.3 | Build Frontend (React/Vite) UI | `[x]` | 5.2.1 | `dashboard/frontend/` — React + TypeScript + Vite, served on :3001 |
| 5.2.4 | Human approval UI in dashboard | `[x]` | 4.2.4, 5.2.3 | `ApprovalBar.tsx` — approve/reject with reason modal |

---

## Phase 6 — Advanced Features (Target: Week 11+)

**Definition of Done (DoD):**
- Automated Chaos pipeline repeatedly tests entire agent workflow stability.
- Documentation mapping runbooks and architectures finalized.
- Learning agent actively tracks and recalls historic incidents.

### 6.1 Learning Agent

| # | Task | Status | Dependencies | Notes |
|---|------|--------|--------------|-------|
| 6.1.1 | Build `IncidentVectorizer` | `[x]` | 5.1.5 | `agents/learner/src/incident_vectorizer.py` — ChromaDB + sentence-transformers |
| 6.1.2 | Build `PatternRecognizer` | `[x]` | 6.1.1 | `agents/learner/src/pattern_recognizer.py` — RAG similarity + runbook ranking |
| 6.1.3 | Build `RunbookOptimizer` | `[x]` | 6.1.2 | `agents/learner/src/runbook_optimizer.py` — PostgreSQL success-rate stats |
| 6.1.4 | Build `LearnerAgent` | `[x]` | 6.1.3 | `agents/learner/src/main.py` — subscribes feedback + query endpoints |
| 6.1.5 | Tests | `[x]` | 6.1.4 | `agents/learner/tests/test_learner.py` — 9/9 passing |

### 6.2 Chaos Engineering

| # | Task | Status | Dependencies | Notes |
|---|------|--------|--------------|-------|
| 6.2.1 | Build chaos injection scripts | `[x]` | None | `scripts/chaos/injector.py` — kill, pause, cpu/memory/network/disk |
| 6.2.2 | Automated chaos scenario runner | `[x]` | 6.2.1 | `scripts/chaos/runner.py` — MTTD/MTTR polling, cooldown, Markdown reports |
| 6.2.3 | Scoring system for agent performance | `[x]` | 6.2.2 | `scripts/chaos/scoring.py` — A💚/B🟡/C🟠/F🔴 letter grades |
| 6.2.4 | Chaos scenarios | `[x]` | 6.2.1 | `scenarios/` — memory_leak, cpu_spike, network_partition, db_overload |

### 6.3 Predictive Detection & Polish

| # | Task | Status | Dependencies | Notes |
|---|------|--------|--------------|-------|
| 6.3.1 | Trend-based prediction capabilities | `[x]` | 3.1.3 | `agents/observer/src/predictor.py` — OLS regression, 30-min early warnings |
| 6.3.2 | Multi-agent debate mechanism | `[x]` | 3.2.3 | `agents/diagnoser/src/debate_engine.py` — 3-rubric scoring, 2 alternative hypotheses |
| 6.3.3 | Tests | `[x]` | None | `agents/observer/tests/test_predictor.py` — 10/10 passing |

---

## Summary

| Phase | Total Tasks | Done | In Progress | Blocked |
|-------|-------------|------|-------------|---------|
| Phase 1 — Core Foundation & MVP Infra | 15 | **15** | 0 | 0 |
| Phase 2 — Extended Infra & Observability | 16 | **16** | 0 | 0 |
| Phase 3 — Observer & Diagnosis | 14 | **14** | 0 | 0 |
| Phase 4 — Remediation & Safety | 13 | **13** | 0 | 0 |
| Phase 5 — Orchestration & Dashboard | 11 | **11** | 0 | 0 |
| Phase 6 — Advanced Features | 9 | **9** | 0 | 0 |
| **Total** | **78** | **78** | **0** | **0** |

---

## Phase 1 — What Was Delivered

| Component | File(s) | Notes |
|-----------|---------|-------|
| Monorepo scaffold | `Makefile`, `.env.example`, `.gitignore` | `make infra-up`, `make test`, `make health` targets |
| Agent base class | `shared/agents/base.py` | Lifecycle, heartbeat (30s), SIGTERM handler |
| AgentMessage schema | `shared/messaging/schema.py` | UUID, TTL, priority, correlation_id — 8 unit tests |
| NATS client | `shared/messaging/nats_client.py` | Pub/subscribe/request-reply, exponential backoff |
| NATS subjects & streams | `shared/messaging/subjects.py`, `scripts/init_nats.py` | 4 streams: AGENTS, INCIDENTS, HUMAN, BUSINESS |
| Pydantic config | `shared/config/settings.py` | Reads `.env`, all DB/Redis/NATS URLs — 5 unit tests |
| JSON logger | `shared/logging/logger.py` | `structlog` with async `correlation_id` context vars |
| DB models | `shared/db/models.py`, `shared/db/session.py` | `Incident`, `Anomaly`, `AgentHeartbeat` (SQLAlchemy async) |
| API Gateway | `services/api-gateway/` | Nginx, port 8000 |
| User Service | `services/user-service/` | FastAPI + Redis CRUD, Prometheus metrics |
| Auth Service | `services/auth-service/` | Node.js/Express, JWT access+refresh, Redis blacklist |
| Order Service | `services/order-service/` | Go/Gin, state machine, NATS publish |
| Payment Service | `services/payment-service/` | FastAPI + asyncpg, NATS publish |
| Infrastructure | `docker-compose.infrastructure.yml` | PostgreSQL ×3, Redis, NATS — all healthy |
| Full stack compose | `docker-compose.yml` | All 5 services with healthcheck dependencies |
| Unit tests | `shared/tests/` | **18/18 passing** |

---

## Phase 2 — What Was Delivered

| Component | File(s) | Notes |
|-----------|---------|-------|
| Product Service | `services/product-service/` | Django + Elasticsearch, catalog & indexing |
| Search Service | `services/search-service/` | FastAPI + ES full-text search |
| Notification Worker | `services/notification-worker/` | Python NATS consumer |
| Inventory Worker | `services/inventory-worker/` | Go NATS consumer + PostgreSQL stock management |
| Analytics Worker | `services/analytics-worker/` | Python NATS consumer + Redis metrics aggregation |
| Prometheus | `prometheus.yml` | Scrape configs for all 10+ services |
| Grafana | `grafana/` | Per-service dashboards |
| Loki | config | Log aggregation from all containers |
| Tempo | config | Distributed tracing backend |
| AlertManager | config | Alert rules for critical metrics |
| Distributed tracing | All services | Trace ID propagation across Python/Go/Node.js |
| CI/CD pipeline | `.github/` or `Makefile` | Lint, test, build Docker images |

---

## Phase 3 — What Was Delivered

| Component | File(s) | Notes |
|-----------|---------|-------|
| AnomalyDetector | `agents/observer/src/detector.py` | Dynamic z-score + static threshold detection, sliding window |
| AlertDeduplicator | `agents/observer/src/deduplicator.py` | Fingerprint-based dedup (5-min window) |
| Metrics Observer | `agents/observer/src/metrics_observer.py` | Polls Prometheus every 15s, 11 metric queries (CPU, memory, error rate, latency p99, disk, NATS lag, PG connections, etc.) |
| Log Observer | `agents/observer/src/log_observer.py` | Loki log streaming, pattern matching (OOMKilled, stack traces, panics) |
| Health Check Observer | `agents/observer/src/health_observer.py` | Active `/health` endpoint probing, tracks status transitions |
| Synthetic Prober | `agents/observer/src/synthetic_prober.py` | E2E transaction scenarios (login, order, payment flows) |
| ContextCollector | `agents/diagnoser/src/context_collector.py` | Gathers recent logs from Loki, correlated metrics from Prometheus, recent deploy info |
| CorrelationEngine | `agents/diagnoser/src/correlation_engine.py` | Temporal + topological anomaly grouping, saves incident state to PostgreSQL |
| HypothesisGenerator | `agents/diagnoser/src/hypothesis_generator.py` | LLM-powered RCA (GPT-4o-mini), structured diagnosis with confidence score (0-100), fallback dummy generator for local dev |
| RCAEngine | `agents/diagnoser/src/rca_engine.py` | Orchestrates context → correlation → LLM reasoning, publishes to `agents.diagnoser.results` |
| Observer + Diagnoser tests | `agents/observer/tests/`, `agents/diagnoser/tests/` | Unit tests for detector, deduplicator, RCA engine; integration simulation tests |

---

## Phase 4 — What Was Delivered

| Component | File(s) | Notes |
|-----------|---------|-------|
| RunbookEngine | `agents/remediator/src/runbook_engine.py` | Loads YAML runbooks, matches RCA category → runbook, template parameter interpolation |
| ActionExecutor | `agents/remediator/src/action_executor.py` | Executes Docker commands (restart, scale, resource limits), captures pre-action state |
| RollbackManager | `agents/remediator/src/rollback_manager.py` | Automatic rollback to captured pre-action state on verification failure |
| VerificationEngine | `agents/remediator/src/verification_engine.py` | Post-remediation health checks, waits for service stabilization |
| RemediatorAgent | `agents/remediator/src/main.py` | Full orchestrator: subscribes `diagnoser.results` → proposes to Safety → executes on approval → verifies |
| Runbook: memory_leak | `agents/remediator/runbooks/memory_leak.yml` | Restart container → verify health |
| Runbook: network_partition | `agents/remediator/runbooks/network_partition.yml` | Wait + retry logic |
| Runbook: database_overload | `agents/remediator/runbooks/database_overload.yml` | Scale up replicas |
| PolicyEngine | `agents/safety/src/policy_engine.py` | Rule-based evaluation (human approval, risk level, banned combos, scale limits) |
| BlastRadiusCalculator | `agents/safety/src/blast_radius.py` | Service dependency impact estimation (low/medium/high) |
| RateLimiter | `agents/safety/src/rate_limiter.py` | Prevents repeated identical fixes (5-min window loop prevention) |
| HumanApprovalGateway | `agents/safety/src/approval_gateway.py` | Formats approval requests, publishes to `human.approvals` |
| SafetyAgent | `agents/safety/src/main.py` | Subscribes `safety.reviews`, evaluates policy → blast radius → rate limit, returns approved/rejected/pending_human_approval |
| Trust hierarchy | `agents/safety/src/policy_engine.py` | Low risk = auto-approve (restart non-critical), Medium = human approval (rollback), High = escalate (DB ops, data deletion) |
| Safety integration tests | `agents/safety/tests/` | Policy engine, blast radius, rate limiter tests |
| **Remaining** | Task 4.1.7 | Tests for individual runbook actions not yet written |
