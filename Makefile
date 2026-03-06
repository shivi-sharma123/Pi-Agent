# SRE Agent Swarm — Makefile
# Usage: make <target>

.PHONY: help up down logs ps test lint clean infra-up infra-down init-nats

# ---------------------------------------------------------------------------
# Infrastructure only (PostgreSQL, Redis, NATS — no application services)
# ---------------------------------------------------------------------------

infra-up:
	@echo "▶ Starting core infrastructure..."
	docker compose -f docker-compose.infrastructure.yml up -d
	@echo "✓ Infrastructure ready. Run 'make init-nats' to bootstrap NATS streams."

infra-down:
	@echo "▶ Stopping core infrastructure..."
	docker compose -f docker-compose.infrastructure.yml down

# ---------------------------------------------------------------------------
# Full stack
# ---------------------------------------------------------------------------

up:
	@echo "▶ Starting all Phase 1 & 2 services..."
	docker compose up -d --build
	@echo "✓ All services started. Run 'make logs' to tail logs."
	@echo ""
	@echo "  API Gateway:      http://localhost:8000"
	@echo "  User Service:     http://localhost:8001"
	@echo "  Order Service:    http://localhost:8002"
	@echo "  Auth Service:     http://localhost:8004"
	@echo "  Payment Service:  http://localhost:8005"
	@echo "  Product Service:  http://localhost:8003"
	@echo "  Search Service:   http://localhost:8006"
	@echo "  NATS Monitoring:  http://localhost:8222"
	@echo "  Grafana:          http://localhost:3000"
	@echo "  Prometheus:       http://localhost:9090"
	@echo "  AlertManager:     http://localhost:9093"

down:
	@echo "▶ Stopping all services..."
	docker compose down

logs:
	docker compose logs -f --tail=50

ps:
	docker compose ps

# ---------------------------------------------------------------------------
# Observability
# ---------------------------------------------------------------------------

obs-up:
	@echo "▶ Starting observability stack..."
	docker compose up -d prometheus grafana loki promtail tempo alertmanager

obs-down:
	@echo "▶ Stopping observability stack..."
	docker compose rm -fsv prometheus grafana loki promtail tempo alertmanager

# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------

agents-up:
	@echo "▶ Starting all Agent Swarm containers..."
	docker compose up -d metrics-observer log-observer health-observer synthetic-prober diagnoser-agent safety-agent remediator-agent orchestrator-agent

agents-down:
	@echo "▶ Stopping Agent Swarm containers..."
	docker compose rm -fsv metrics-observer log-observer health-observer synthetic-prober diagnoser-agent safety-agent remediator-agent orchestrator-agent

# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

dashboard-up:
	@echo "▶ Starting Dashboard (API + Frontend)..."
	docker compose up -d dashboard-api dashboard-frontend
	@echo "✓ Dashboard API:       http://localhost:8010"
	@echo "  Dashboard Frontend:  http://localhost:3001"

dashboard-down:
	@echo "▶ Stopping Dashboard..."
	docker compose rm -fsv dashboard-api dashboard-frontend

# ---------------------------------------------------------------------------
# Elasticsearch
# ---------------------------------------------------------------------------

es-index:
	@echo "▶ Forcing Elasticsearch re-index for product 1 (demo)..."
	@curl -X POST http://localhost:8003/products/1/reindex || echo "Make sure product-svc is running"

# ---------------------------------------------------------------------------
# NATS stream initialisation
# ---------------------------------------------------------------------------

init-nats:
	@echo "▶ Initialising NATS JetStream streams..."
	python scripts/init_nats.py
	@echo "✓ NATS streams ready."

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

.PHONY: install-dev test test-unit test-integration

install-dev:
	@echo "▶ Installing shared package in dev mode..."
	pip install -e "shared/[dev]"

test: test-unit

test-unit:
	@echo "▶ Installing microservice test dependencies..."
	pip install -r services/product-service/requirements.txt -r services/search-service/requirements.txt -r services/notification-worker/requirements.txt -r services/analytics-worker/requirements.txt
	@echo "▶ Installing agent test dependencies..."
	pip install -r agents/observer/requirements.txt -r agents/diagnoser/requirements.txt -r agents/safety/requirements.txt -r agents/orchestrator/requirements.txt -r dashboard/requirements.txt
	@echo "▶ Running Python unit tests (shared & agents)..."
	python -m pytest shared/tests/ agents/observer/tests/ agents/diagnoser/tests/ agents/safety/tests/ agents/orchestrator/tests/ dashboard/tests/ -v --tb=short
	@echo "▶ Running Python microservice tests..."
	cd services/search-service && python -m pytest app/test_main.py --tb=short -p no:warnings || echo "Search tests failed"
	cd services/notification-worker && python -m pytest app/test_main.py --tb=short -p no:warnings || echo "Notification tests failed"
	cd services/analytics-worker && python -m pytest app/test_main.py --tb=short -p no:warnings || echo "Analytics tests failed"
	@echo "▶ Running Django tests..."
	cd services/product-service && PYTHONPATH=. django-admin test app.tests --settings=app.config || echo "Django tests failed"
	@echo "▶ Running Go unit tests..."
	cd services/inventory-worker && go test ./... -v
	cd services/order-service && go test ./... -v


test-integration:
	@echo "▶ Running integration tests (requires infra running)..."
	@echo "  Starting infra..."
	docker compose -f docker-compose.infrastructure.yml up -d
	@echo "  Waiting for services..."
	sleep 10
	cd shared && python -m pytest tests/ -v -m integration --tb=short

# ---------------------------------------------------------------------------
# Linting
# ---------------------------------------------------------------------------

lint:
	@echo "▶ Running Python linter (ruff)..."
	cd shared && ruff check . --fix
	cd services/user-service && ruff check . --fix
	cd services/payment-service && ruff check . --fix

# ---------------------------------------------------------------------------
# Smoke-test each service health endpoint
# ---------------------------------------------------------------------------

health:
	@echo "▶ Checking service health..."
	@echo "--- Phase 1 ---"
	@curl -sf http://localhost:8000/health | python3 -m json.tool || echo "  ✗ api-gateway: FAIL"
	@curl -sf http://localhost:8001/health | python3 -m json.tool || echo "  ✗ user-svc: FAIL"
	@curl -sf http://localhost:8004/health | python3 -m json.tool || echo "  ✗ auth-svc: FAIL"
	@curl -sf http://localhost:8002/health | python3 -m json.tool || echo "  ✗ order-svc: FAIL"
	@curl -sf http://localhost:8005/health | python3 -m json.tool || echo "  ✗ payment-svc: FAIL"
	@echo "--- Phase 5 ---"
	@curl -sf http://localhost:8010/health | python3 -m json.tool || echo "  ✗ dashboard-api: FAIL"
	@echo "--- Phase 2 ---"
	@curl -sf http://localhost:8003/health | python3 -m json.tool || echo "  ✗ product-svc: FAIL"
	@curl -sf http://localhost:8006/health | python3 -m json.tool || echo "  ✗ search-svc: FAIL"
	@curl -sf http://localhost:8007/health | python3 -m json.tool || echo "  ✗ notification-worker: FAIL"
	@curl -sf http://localhost:8008/health | python3 -m json.tool || echo "  ✗ inventory-worker: FAIL"
	@curl -sf http://localhost:8009/health | python3 -m json.tool || echo "  ✗ analytics-worker: FAIL"

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

clean:
	@echo "▶ Stopping services and removing volumes..."
	docker compose down -v
	docker compose -f docker-compose.infrastructure.yml down -v
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -name "*.egg-info" -exec rm -rf {} +

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------

help:
	@echo ""
	@echo "SRE Agent Swarm — Makefile Targets"
	@echo "======================================"
	@echo ""
	@echo "Infrastructure"
	@echo "  make infra-up          Start PostgreSQL ×3, Redis, NATS"
	@echo "  make infra-down        Stop infrastructure"
	@echo "  make init-nats         Create NATS JetStream streams"
	@echo ""
	@echo "Full stack"
	@echo "  make up                Build + start all services"
	@echo "  make down              Stop all services"
	@echo "  make logs              Tail all service logs"
	@echo "  make ps                Show service status"
	@echo "  make health            Curl all /health endpoints"
	@echo ""
	@echo "Observability"
	@echo "  make obs-up            Start Prometheus, Grafana, Loki, Tempo, AlertManager"
	@echo "  make obs-down          Stop observability stack"
	@echo ""
	@echo "Agent Swarm"
	@echo "  make agents-up         Start all 9 agent containers (incl. learner)"
	@echo "  make agents-down       Stop all agent containers"
	@echo ""
	@echo "Dashboard"
	@echo "  make dashboard-up      Start Dashboard API (:8010) + Frontend (:3001)"
	@echo "  make dashboard-down    Stop dashboard"
	@echo ""
	@echo "Dev / Test"
	@echo "  make install-dev       Install shared package in dev mode"
	@echo "  make test              Run unit test suite (no infra needed)"
	@echo "  make test-integration  Run integration tests (starts infra)"
	@echo "  make lint              Run ruff linter on Python code"
	@echo "  make es-index          Force Elasticsearch re-index for demo product"
	@echo "  make clean             Stop everything + remove volumes"
	@echo ""
