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
	@echo "▶ Starting all Phase 1 services..."
	docker compose up -d --build
	@echo "✓ All services started. Run 'make logs' to tail logs."
	@echo ""
	@echo "  API Gateway:      http://localhost:8000"
	@echo "  User Service:     http://localhost:8001"
	@echo "  Order Service:    http://localhost:8002"
	@echo "  Auth Service:     http://localhost:8004"
	@echo "  Payment Service:  http://localhost:8005"
	@echo "  NATS Monitoring:  http://localhost:8222"

down:
	@echo "▶ Stopping all services..."
	docker compose down

logs:
	docker compose logs -f --tail=50

ps:
	docker compose ps

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
	@echo "▶ Running unit tests..."
	cd shared && python -m pytest tests/ -v --tb=short

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
	@curl -sf http://localhost:8000/health | python3 -m json.tool || echo "  ✗ api-gateway: FAIL"
	@curl -sf http://localhost:8001/health | python3 -m json.tool || echo "  ✗ user-svc: FAIL"
	@curl -sf http://localhost:8004/health | python3 -m json.tool || echo "  ✗ auth-svc: FAIL"
	@curl -sf http://localhost:8002/health | python3 -m json.tool || echo "  ✗ order-svc: FAIL"
	@curl -sf http://localhost:8005/health | python3 -m json.tool || echo "  ✗ payment-svc: FAIL"

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
	@echo "  make infra-up       Start PostgreSQL, Redis, NATS"
	@echo "  make infra-down     Stop infrastructure"
	@echo "  make init-nats      Create NATS JetStream streams"
	@echo "  make up             Start all Phase 1 services (builds Docker images)"
	@echo "  make down           Stop all services"
	@echo "  make logs           Tail all service logs"
	@echo "  make ps             Show service status"
	@echo "  make health         Curl all /health endpoints"
	@echo ""
	@echo "  make install-dev    Install shared package in dev mode"
	@echo "  make test           Run unit tests"
	@echo "  make lint           Run ruff linter"
	@echo "  make clean          Stop everything + remove volumes"
	@echo ""
