# Microservices Map

This environment is the failure playground monitored and remediated by the swarm.

## Service Inventory

- API gateway: `api-gateway` (`:8000`)
- Core services: `user-svc` (`:8001`), `order-svc` (`:8002`), `auth-svc` (`:8004`), `payment-svc` (`:8005`)
- Extended services: `product-svc` (`:8003`), `search-svc` (`:8006`)
- Workers: `notification-worker` (`:8007`), `inventory-worker` (`:8008`), `analytics-worker` (`:8009`)

## Data and Messaging

- PostgreSQL: `postgres-agents`, `postgres-orders`, `postgres-payments`, `postgres-inventory`
- Redis: cache/session and analytics counters
- Elasticsearch: product and search workloads
- NATS JetStream: event and command bus

## Observability

- Prometheus (`:9090`)
- Grafana (`:3000`)
- Loki (`:3100`)
- Tempo (`:3200`)
- AlertManager (`:9093`)

## Agent and Dashboard Services

- Observer pool: `metrics-observer`, `log-observer`, `health-observer`, `synthetic-prober`
- Diagnoser: `diagnoser-agent`
- Safety: `safety-agent`
- Remediator: `remediator-agent`
- Orchestrator: `orchestrator-agent`
- Dashboard: `dashboard-api` (`:8010`), `dashboard-frontend` (`:3001`)

## Compose Layout

- `docker-compose.infrastructure.yml`: shared infra foundations
- `docker-compose.yml`: full stack including services, agents, dashboard, and observability

Use `make ps` to inspect live container status after startup.
