# SRE Agent Swarm

> **Self-Healing Infrastructure Agent Swarm** — a production-grade, multi-agent system that autonomously detects, diagnoses, and remediates infrastructure incidents.

[![Tests](https://img.shields.io/badge/tests-55%20passing-brightgreen)](shared/tests/)
[![Phase](https://img.shields.io/badge/phase-1%20complete-blue)](docs/TODO.md)

---

## Architecture Overview

```
┌────────────────────────────────────────────────────────┐
│                      API Gateway                        │
│                    Nginx :8000                          │
└──────────┬─────────┬──────────┬──────────┬─────────────┘
           │         │          │          │
      /users   /auth     /orders    /payments
           │         │          │          │
     ┌─────┴──┐ ┌───┴────┐ ┌──┴─────┐ ┌──┴──────┐
     │User Svc│ │Auth Svc│ │Order   │ │Payment  │
     │FastAPI │ │Node.js │ │Go/Gin  │ │FastAPI  │
     │  :8001 │ │  :8004 │ │  :8002 │ │  :8005  │
     └────────┘ └────────┘ └────────┘ └─────────┘
           │         │          │          │
           └─────────┴──────────┴──────────┘
                          │
              ┌───────────┴───────────┐
              │    NATS JetStream     │   ← Agent message bus
              │       :4222           │
              └───────────────────────┘
                          │
        ┌─────────────────┴─────────────────┐
        │           Agent Swarm             │
        │  Observer → Diagnoser →           │
        │  Remediator → Safety →            │
        │  Orchestrator → Learning          │
        └───────────────────────────────────┘
```

## Quickstart

### Prerequisites
- Docker + Docker Compose
- Python 3.11+ (for running tests / scripts locally)
- Go 1.21+ (order-service local dev)

### 1. Configure environment

```bash
cp .env.example .env
# Edit .env if needed (defaults work for local dev)
```

### 2. Start infrastructure

```bash
make infra-up       # PostgreSQL ×3, Redis, NATS JetStream
make init-nats      # Create JetStream streams
```

### 3. Start all services

```bash
make up             # Builds images + starts all 5 services
make health         # Verify all /health endpoints respond
```

### 4. Develop / test

```bash
make install-dev    # Install shared package in dev venv
make test           # Run 55-test suite (no infra required)
make lint           # Run ruff on Python code
```

## Project Layout

```
.
├── services/
│   ├── api-gateway/        # Nginx reverse proxy (:8000)
│   ├── user-service/       # FastAPI + Redis (:8001)
│   ├── order-service/      # Go/Gin + PostgreSQL (:8002)
│   ├── auth-service/       # Node.js/Express + JWT (:8004)
│   └── payment-service/    # FastAPI + asyncpg (:8005)
├── shared/                 # Shared Python package (sre-shared)
│   ├── agents/             # BaseAgent abstract class
│   ├── config/             # Pydantic settings
│   ├── db/                 # SQLAlchemy models + Alembic migrations
│   ├── logging/            # structlog JSON logger
│   ├── messaging/          # NATS client, AgentMessage schema, subjects
│   └── tests/              # 55 unit tests
├── scripts/
│   └── init_nats.py        # Bootstrap NATS JetStream streams
├── docs/
│   ├── TODO.md             # Phase-by-phase progress tracker
│   ├── lld.md              # Low-level design
│   └── idea.md             # Problem statement
├── docker-compose.yml               # Full stack
├── docker-compose.infrastructure.yml # Infra only
└── Makefile
```

## Services

| Service | Lang | Port | Key Features |
|---------|------|------|--------------|
| API Gateway | Nginx | 8000 | Reverse proxy, routing |
| User Service | Python/FastAPI | 8001 | User CRUD, Redis sessions, Prometheus |
| Auth Service | Node.js | 8004 | JWT (bcrypt), Redis blacklist, `/register` `/login` `/refresh` `/logout` |
| Order Service | Go/Gin | 8002 | Order state machine, PostgreSQL, NATS publish |
| Payment Service | Python/FastAPI | 8005 | asyncpg, refund, NATS publish |

## NATS JetStream Streams

| Stream | Subjects | Retention | Storage |
|--------|----------|-----------|---------|
| AGENTS | `agents.*` | 24 h | File |
| INCIDENTS | `incidents.*` | 7 days | File |
| HUMAN | `human.*` | 1 h | Memory |
| BUSINESS | `orders.*`, `payments.*` | 3 days | File |

## Database Migrations (Alembic)

```bash
# Apply initial schema to postgres-agents
pip install alembic psycopg2-binary
alembic -c shared/db/alembic.ini upgrade head

# Create a new migration after model changes
alembic -c shared/db/alembic.ini revision --autogenerate -m "add_field"
```

## Make Targets

| Command | Description |
|---------|-------------|
| `make infra-up` | Start PostgreSQL ×3, Redis, NATS |
| `make infra-down` | Stop infrastructure |
| `make init-nats` | Create JetStream streams |
| `make up` | Build + start all 5 services |
| `make down` | Stop all services |
| `make health` | Curl all `/health` endpoints |
| `make test` | Run unit tests |
| `make lint` | Run ruff linter |
| `make clean` | Stop + remove all volumes |

## Progress

See [docs/TODO.md](docs/TODO.md) for the full breakdown.

| Phase | Status | Tasks |
|-------|--------|-------|
| Phase 1 — Core Foundation & MVP Infra | ✅ Complete | 15 / 15 |
| Phase 2 — Extended Infra & Observability | Planned | 0 / 16 |
| Phase 3 — Observer & Diagnosis | Planned | 0 / 14 |
| Phase 4 — Remediation & Safety | Planned | 0 / 13 |
| Phase 5 — Orchestration & Dashboard | Planned | 0 / 11 |
| Phase 6 — Advanced Features | Planned | 0 / 9 |
