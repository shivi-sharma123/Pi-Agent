NOTE: Source Code to be added soon

# Pi (π) - Agent

> **Self-Healing Infrastructure Agent Pi (π)** — a production-grade, multi-agent system that autonomously detects, diagnoses, and remediates infrastructure incidents.

[![Tests](https://img.shields.io/badge/tests-78%20tasks%20complete-brightgreen)](docs/TODO.md)
[![Phase](https://img.shields.io/badge/phase-all%206%20complete-blue)](docs/TODO.md)

---

## 💡 The Core Idea

A Pi (π) of AI agents that continuously monitors infrastructure, detects anomalies, diagnoses root causes, proposes remediations, and (with appropriate safety gates) executes fixes autonomously — mimicking what a senior SRE team does during an incident.

The system is designed to handle complex failure scenarios in a microservices environment, such as memory leaks, CPU spikes, network partitions, and cascading timeouts, using LLM-powered reasoning to connect disparate signals across logs, metrics, and traces.

---

## 🤖 The Agent Pi (π)

The Pi (π) coordinates six specialized agent roles, each with distinct responsibilities:

| Agent | Role & Responsibility |
|-------|-----------------------|
| **Observer** | Detects anomalies from metrics, logs, health checks, and synthetic probes. It uses anomaly detection and pattern recognition to identify issues early. |
| **Diagnoser** | Investigates anomalies by pulling context (logs, traces, deployments). It uses LLM reasoning to build a **causal hypothesis** and identify the root cause. |
| **Remediator** | Maps diagnosis output to a **runbook knowledge base**. It selects, parameterizes, and executes actions like restarts, rollbacks, or scaling. |
| **Safety** | Enforces policies, calculates blast radius, and manages **human approval gates**. It ensures dangerous actions are vetted before execution. |
| **Orchestrator** | Manages the **Incident Lifecycle (FSM)**. It coordinates the flow from detection to resolution, handles timeouts, and builds the incident timeline. |
| **Learner** | Stores historical outcomes and patterns. It uses RAG to recommend successful runbooks for similar recurring incidents. |

---

## 🏗️ Architecture

### System Map
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
        │           Agent Pi (π)             │
        │  Observer → Diagnoser →           │
        │  Remediator → Safety →            │
        │  Orchestrator → Learning          │
        └───────────────────────────────────┘
```

### Core Tech Stack
- **Messaging:** NATS JetStream (Event-driven agent communication)
- **Observability:** Prometheus (Metrics), Loki (Logs), Tempo (Tracing), AlertManager
- **Persistence:** PostgreSQL (Incident state), Redis (Caching/Sessions), Elasticsearch (Search), ChromaDB (Vector store for Learner)
- **Dashboard:** FastAPI + React (Human-in-the-loop interface)
- **LLM Backends:** Gemini (Primary reasoning engine)

---

## 🔄 Incident Lifecycle (FSM)

The Orchestrator manages incidents through a formal Finite State Machine:

`detecting` → `diagnosing` → `proposing_remediation` → `safety_review` → `executing` → `verifying` → `resolved` → `closed`

- **Human-in-the-Loop:** Safety Agent can trigger a `pending_human_approval` state for high-risk actions.
- **Auto-Recovery:** The FSM includes loops for remediation retries and verification failures.
- **Escalation:** If diagnosis or remediation takes too long, the incident is escalated to human operators.

---

## 📡 Messaging Protocol

Inter-agent communication uses a structured **AgentMessage** envelope over NATS JetStream:

- **Envelope:** Includes `message_id`, `correlation_id` (incident key), `source_agent`, `payload`, and `context`.
- **Streams:**
  - `AGENTS`: Agent traffic and heartbeats.
  - `INCIDENTS`: Formal lifecycle transitions.
  - `HUMAN`: Approval requests and operator responses.
  - `BUSINESS`: Application domain events (orders, payments).

---

## 🚀 Quickstart

### Prerequisites
- Docker + Docker Compose
- Python 3.11+
- Go 1.21+

### 1. Setup Environment
```bash
cp .env.example .env
# Configure your GEMINI_API_KEY in .env
```

### 2. Launch Infrastructure
```bash
make infra-up       # PostgreSQL, Redis, NATS
make init-nats      # Bootstrap JetStream streams
make obs-up        # Start Observability stack (Grafana, Prometheus, etc.)
```

### 3. Start the Pi (π) & Services
```bash
make up             # Start microservices playground
make agents-up      # Start the Agent Pi (π)
make dashboard-up   # Start the React UI
```

### 4. Verify & Test
```bash
make health         # Check all service endpoints
make test           # Run core test suite
```

---

## 📂 Project Layout

```
.
├── agents/                 # The Pi (π): observer, diagnoser, remediator, safety, orchestrator, learner
├── services/               # Microservices playground (Python, Go, Node.js, Django)
├── shared/                 # Common Python package (sre-shared): messaging, models, logging
├── dashboard/              # React frontend + FastAPI backend for incident management
├── config/                 # Observability configs (Prometheus, Loki, Grafana, Tempo)
├── scripts/                # Utility scripts & Chaos Engineering tools
├── docs/                   # Detailed documentation (architecture, workflows, agents)
└── Makefile                # Central command hub
```

---

## 🛠️ Make Targets

| Command | Description |
|---------|-------------|
| `make infra-up` | Start core databases and message bus |
| `make obs-up` | Start the full observability stack |
| `make agents-up` | Launch the AI Agent Pi (π) |
| `make up` | Start all microservices |
| `make test` | Run unit and integration tests |
| `make chaos` | Run a chaos engineering scenario (failure injection) |
| `make clean` | Stop everything and wipe volumes |

---

## 📖 Documentation Index

- [Architecture Overview](docs/architecture/overview.md)
- [Current Project Architecture](docs/architecture/current_project_architecture.md)
- [Messaging Protocol](docs/architecture/messaging.md)
- [Incident Lifecycle](docs/workflows/incident_lifecycle.md)
- [Agent Reference](docs/agents/README.md)
- [Chaos Engineering](docs/development/chaos.md)
- [Project TODO List](docs/TODO.md)
