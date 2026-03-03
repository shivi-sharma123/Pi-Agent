# Self-Healing Infrastructure Agent Swarm — Low Level Design

---

## 1. Target Microservices Environment

We build a **realistic e-commerce platform** as the infrastructure target — this gives us a wide surface area of failure modes across different service types, data stores, and communication patterns.

### 1.1 Microservices Map

```
                          ┌──────────────────┐
                          │   API Gateway     │
                          │   (Kong / Nginx)  │
                          │   :8000           │
                          └────────┬──────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                     │
     ┌────────▼────────┐ ┌────────▼────────┐  ┌────────▼────────┐
     │  User Service    │ │  Order Service   │  │  Product Service │
     │  (FastAPI)       │ │  (Go + Gin)      │  │  (Django)        │
     │  :8001           │ │  :8002           │  │  :8003           │
     └────────┬─────────┘ └───┬─────────┬───┘  └────────┬────────┘
              │               │         │                │
     ┌────────▼────────┐     │    ┌────▼─────────┐  ┌───▼────────────┐
     │  Auth Service    │     │    │ Payment Svc   │  │ Search Service  │
     │  (Node.js)       │     │    │ (FastAPI)      │  │ (FastAPI)       │
     │  :8004           │     │    │ :8005          │  │ :8006           │
     └────────┬─────────┘     │    └────┬──────────┘  └───┬────────────┘
              │               │         │                  │
              ▼               ▼         ▼                  ▼
     ┌────────────────┐ ┌──────────┐ ┌──────────┐  ┌──────────────┐
     │ Redis Cluster   │ │PostgreSQL│ │PostgreSQL│  │Elasticsearch │
     │ (Session+Cache) │ │ (Orders) │ │(Payments)│  │  (Products)  │
     │ :6379           │ │ :5432    │ │ :5432    │  │  :9200       │
     └────────────────┘ └──────────┘ └──────────┘  └──────────────┘

              ┌──────────────────────────────────────┐
              │         Message Bus (NATS JetStream)  │
              │              :4222                     │
              └──────┬────────────┬──────────┬────────┘
                     │            │          │
            ┌────────▼───┐ ┌─────▼─────┐ ┌──▼──────────┐
            │Notification│ │ Inventory  │ │  Analytics   │
            │ Worker     │ │ Worker     │ │  Worker      │
            │ (Python)   │ │ (Go)       │ │  (Python)    │
            │ :8007      │ │ :8008      │ │  :8009       │
            └────────────┘ └───────────┘ └──────────────┘

     ┌─────────────────────────────────────────────────────┐
     │              Observability Stack                     │
     │  Prometheus(:9090) + Grafana(:3000) + Loki(:3100)   │
     │  + Tempo(:3200) + AlertManager(:9093)               │
     └─────────────────────────────────────────────────────┘
```

### 1.2 Service Details

| Service | Language | Framework | Database | Purpose |
|---------|----------|-----------|----------|---------|
| API Gateway | — | Kong/Nginx | — | Routing, rate limiting, SSL termination |
| User Service | Python | FastAPI | Redis (sessions) | User CRUD, profile management |
| Auth Service | Node.js | Express | Redis (tokens) | JWT auth, OAuth, token refresh |
| Order Service | Go | Gin | PostgreSQL | Order lifecycle, state machine |
| Payment Service | Python | FastAPI | PostgreSQL | Payment processing, refunds |
| Product Service | Python | Django | Elasticsearch | Catalog, search, inventory reads |
| Search Service | Python | FastAPI | Elasticsearch | Full-text search, autocomplete |
| Notification Worker | Python | — | NATS consumer | Email, SMS, push notifications |
| Inventory Worker | Go | — | NATS consumer + PostgreSQL | Stock management, reservations |
| Analytics Worker | Python | — | NATS consumer | Event tracking, metrics aggregation |

### 1.3 Inter-Service Communication Patterns

```
Synchronous (HTTP/gRPC):
  API Gateway → User Service        (REST)
  API Gateway → Order Service        (REST)
  API Gateway → Product Service      (REST)
  Order Service → Payment Service    (gRPC)
  Order Service → Inventory Worker   (gRPC for stock check)
  Auth Service → User Service        (REST for user lookup)
  Search Service → Elasticsearch     (native client)

Asynchronous (NATS JetStream):
  Order Service  ──publish──▶ "orders.created"    ──▶ Notification Worker
  Order Service  ──publish──▶ "orders.created"    ──▶ Inventory Worker
  Order Service  ──publish──▶ "orders.created"    ──▶ Analytics Worker
  Payment Service──publish──▶ "payments.completed"──▶ Order Service
  Payment Service──publish──▶ "payments.failed"   ──▶ Order Service
  Inventory Wkr  ──publish──▶ "inventory.low"     ──▶ Notification Worker
```

### 1.4 Docker Compose Structure

```yaml
# docker-compose.infrastructure.yml
# All services, databases, message bus, observability
version: "3.9"

services:
  # --- Core Databases ---
  postgres-agents:
    image: postgres:16
    environment:
      POSTGRES_DB: agents
    volumes: [pgdata-agents:/var/lib/postgresql/data]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
    deploy:
      resources:
        limits: { cpus: "1.0", memory: 512M }

  postgres-orders:
    image: postgres:16
    environment:
      POSTGRES_DB: orders
    volumes: [pgdata-orders:/var/lib/postgresql/data]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
    deploy:
      resources:
        limits: { cpus: "1.0", memory: 512M }

  postgres-payments:
    image: postgres:16
    environment:
      POSTGRES_DB: payments

  redis:
    image: redis:7-alpine
    command: redis-server --maxmemory 256mb --maxmemory-policy allkeys-lru
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]

  elasticsearch:
    image: elasticsearch:8.12.0
    environment:
      - discovery.type=single-node
      - "ES_JAVA_OPTS=-Xms512m -Xmx512m"
    deploy:
      resources:
        limits: { cpus: "2.0", memory: 1G }

  nats:
    image: nats:2.10-alpine
    command: "--js --sd /data"
    volumes: [natsdata:/data]

  # --- Observability ---
  prometheus:
    image: prom/prometheus:latest
    volumes: [./prometheus.yml:/etc/prometheus/prometheus.yml]

  grafana:
    image: grafana/grafana:latest
    depends_on: [prometheus, loki]

  loki:
    image: grafana/loki:latest

  tempo:
    image: grafana/tempo:latest

  alertmanager:
    image: prom/alertmanager:latest

  # --- Application Services ---
  api-gateway:
    build: ./services/api-gateway
    ports: ["8000:8000"]
    depends_on: [user-svc, order-svc, product-svc]

  user-svc:
    build: ./services/user-service
    depends_on: [redis]
    deploy:
      replicas: 2
      resources:
        limits: { cpus: "0.5", memory: 256M }

  auth-svc:
    build: ./services/auth-service
    depends_on: [redis, user-svc]

  order-svc:
    build: ./services/order-service
    depends_on: [postgres-orders, nats, payment-svc]
    deploy:
      replicas: 3

  payment-svc:
    build: ./services/payment-service
    depends_on: [postgres-payments]

  product-svc:
    build: ./services/product-service
    depends_on: [elasticsearch]

  search-svc:
    build: ./services/search-service
    depends_on: [elasticsearch]

  notification-worker:
    build: ./services/notification-worker
    depends_on: [nats]
    deploy:
      replicas: 2

  inventory-worker:
    build: ./services/inventory-worker
    depends_on: [nats, postgres-orders]

  analytics-worker:
    build: ./services/analytics-worker
    depends_on: [nats]
```

---

## 2. Agent System Architecture — Low Level Design

### 2.1 Complete System Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          CONTROL PLANE                                  │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                    ORCHESTRATOR AGENT                              │  │
│  │                                                                   │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────┐  │  │
│  │  │ Incident FSM │  │ Agent Router │  │ Escalation Manager     │  │  │
│  │  │ (State Mgmt) │  │ (Task Alloc) │  │ (Timeout + Escalation) │  │  │
│  │  └──────────────┘  └──────────────┘  └────────────────────────┘  │  │
│  └───────────┬────────────────┬──────────────────┬───────────────────┘  │
│              │                │                   │                      │
│  ┌───────────▼──┐  ┌─────────▼───────┐  ┌───────▼──────────┐          │
│  │  OBSERVER     │  │  DIAGNOSER      │  │  REMEDIATOR      │          │
│  │  AGENT POOL   │  │  AGENT          │  │  AGENT           │          │
│  │              │  │                 │  │                  │          │
│  │  ┌─────────┐ │  │  ┌───────────┐ │  │  ┌────────────┐ │          │
│  │  │Metrics  │ │  │  │Hypothesis │ │  │  │Runbook     │ │          │
│  │  │Observer │ │  │  │Generator  │ │  │  │Engine      │ │          │
│  │  ├─────────┤ │  │  ├───────────┤ │  │  ├────────────┤ │          │
│  │  │Log      │ │  │  │Context    │ │  │  │Action      │ │          │
│  │  │Observer │ │  │  │Collector  │ │  │  │Executor    │ │          │
│  │  ├─────────┤ │  │  ├───────────┤ │  │  ├────────────┤ │          │
│  │  │Health   │ │  │  │Correlation│ │  │  │Rollback    │ │          │
│  │  │Observer │ │  │  │Engine     │ │  │  │Manager     │ │          │
│  │  ├─────────┤ │  │  ├───────────┤ │  │  └────────────┘ │          │
│  │  │Synthetic│ │  │  │RCA Engine │ │  │                  │          │
│  │  │Prober   │ │  │  │(LLM-based)│ │  │  ┌────────────┐ │          │
│  │  └─────────┘ │  │  └───────────┘ │  │  │Verification│ │          │
│  └──────────────┘  └────────────────┘  │  │Engine      │ │          │
│                                         │  └────────────┘ │          │
│              ┌──────────────────────┐   └──────────────────┘          │
│              │    SAFETY AGENT      │                                  │
│              │                      │                                  │
│              │  ┌────────────────┐  │    ┌──────────────────────────┐ │
│              │  │Policy Engine   │  │    │    LEARNING AGENT        │ │
│              │  ├────────────────┤  │    │                          │ │
│              │  │Blast Radius    │  │    │  ┌────────────────────┐  │ │
│              │  │Calculator      │  │    │  │Incident Vectorizer │  │ │
│              │  ├────────────────┤  │    │  ├────────────────────┤  │ │
│              │  │Rate Limiter    │  │    │  │Pattern Recognizer  │  │ │
│              │  ├────────────────┤  │    │  ├────────────────────┤  │ │
│              │  │Human Approval  │  │    │  │Runbook Optimizer   │  │ │
│              │  │Gateway         │  │    │  └────────────────────┘  │ │
│              │  └────────────────┘  │    └──────────────────────────┘ │
│              └──────────────────────┘                                  │
└─────────────────────────────────────────────────────────────────────────┘
                              │
                    ┌─────────▼──────────┐
                    │  SHARED SERVICES    │
                    │                    │
                    │  • Agent Message Bus (NATS JetStream)
                    │  • Incident Store (PostgreSQL)
                    │  • Vector DB (ChromaDB / Qdrant)
                    │  • Tool Registry
                    │  • Config Store (etcd)
                    │  • Dashboard API (FastAPI)
                    │  • WebSocket Server (notifications)
                    └────────────────────┘
```

### 2.2 Agent Communication Protocol

```
┌──────────────────────────────────────────────────────────────────────┐
│                    NATS JetStream Subjects                            │
│                                                                      │
│  agents.orchestrator.commands    ← Orchestrator issues commands       │
│  agents.observer.anomalies       ← Observers publish anomalies       │
│  agents.diagnoser.requests       ← Diagnosis requests                │
│  agents.diagnoser.results        ← Diagnosis results                 │
│  agents.remediator.proposals     ← Proposed remediations             │
│  agents.safety.reviews           ← Safety review requests            │
│  agents.safety.decisions         ← Approval / rejection              │
│  agents.remediator.executions    ← Execution confirmations           │
│  agents.learning.feedback        ← Post-incident feedback            │
│  agents.heartbeat                ← Agent health monitoring           │
│  incidents.lifecycle             ← Incident state transitions        │
│  human.approvals                 ← Human-in-the-loop decisions       │
└──────────────────────────────────────────────────────────────────────┘
```

**Message Envelope Schema:**

```python
@dataclass
class AgentMessage:
    message_id: str            # UUID v4
    correlation_id: str        # Links messages in same incident
    source_agent: str          # "observer.metrics", "diagnoser.rca"
    target_agent: str          # "orchestrator", "safety", "*" (broadcast)
    message_type: str          # "anomaly_detected", "diagnosis_complete", "remediation_proposed"
    priority: int              # 0=critical, 1=high, 2=medium, 3=low
    timestamp: datetime
    payload: dict              # Type-specific data
    context: dict              # Accumulated investigation context
    ttl_seconds: int           # Message expiry
    retry_count: int           # For idempotency
    trace_id: str              # Distributed tracing
```

---

## 3. Agent Detailed Designs

### 3.1 Observer Agent Pool

Each observer is a standalone process with its own polling/streaming loop.

#### 3.1.1 Metrics Observer

```python
class MetricsObserver:
    """
    Polls Prometheus at regular intervals, runs anomaly detection
    on each metric series, and publishes anomalies.
    """

    def __init__(self, config: ObserverConfig):
        self.prom_client = PrometheusClient(config.prometheus_url)
        self.nats_client = NATSClient(config.nats_url)
        self.detector = AnomalyDetector()
        self.deduplicator = AlertDeduplicator(window_seconds=300)
        self.poll_interval = config.poll_interval  # 15 seconds

    # --- Metric Queries ---
    METRIC_QUERIES = {
        "cpu_usage": {
            "query": 'rate(container_cpu_usage_seconds_total{namespace="ecommerce"}[5m]) * 100',
            "threshold_type": "dynamic",   # z-score based
            "severity_map": {"warning": 2.0, "critical": 3.0},  # z-score thresholds
        },
        "memory_usage": {
            "query": 'container_memory_working_set_bytes{namespace="ecommerce"} / container_spec_memory_limit_bytes * 100',
            "threshold_type": "static",
            "severity_map": {"warning": 80, "critical": 95},
        },
        "error_rate": {
            "query": 'rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m]) * 100',
            "threshold_type": "dynamic",
            "severity_map": {"warning": 2.0, "critical": 3.0},
        },
        "latency_p99": {
            "query": 'histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m]))',
            "threshold_type": "dynamic",
            "severity_map": {"warning": 2.5, "critical": 3.5},
        },
        "disk_usage": {
            "query": '(node_filesystem_size_bytes - node_filesystem_avail_bytes) / node_filesystem_size_bytes * 100',
            "threshold_type": "static",
            "severity_map": {"warning": 75, "critical": 90},
        },
        "nats_consumer_lag": {
            "query": 'nats_jetstream_consumer_num_pending',
            "threshold_type": "dynamic",
            "severity_map": {"warning": 2.0, "critical": 3.0},
        },
        "pg_active_connections": {
            "query": 'pg_stat_activity_count{state="active"}',
            "threshold_type": "static",
            "severity_map": {"warning": 80, "critical": 95},
        },
        "pg_replication_lag": {
            "query": 'pg_replication_lag_seconds',
            "threshold_type": "static",
            "severity_map": {"warning": 5, "critical": 30},
        },
        "redis_memory_usage": {
            "query": 'redis_memory_used_bytes / redis_memory_max_bytes * 100',
            "threshold_type": "static",
            "severity_map": {"warning": 75, "critical": 90},
        },
        "es_cluster_health": {
            "query": 'elasticsearch_cluster_health_status{color="red"}',
            "threshold_type": "static",
            "severity_map": {"critical": 1},
        },
        "container_restarts": {
            "query": 'increase(kube_pod_container_status_restarts_total[15m])',
            "threshold_type": "static",
            "severity_map": {"warning": 2, "critical": 5},
        },
    }

    async def run(self):
        while True:
            for metric_name, config in self.METRIC_QUERIES.items():
                try:
                    result = await self.prom_client.query(config["query"])
                    anomalies = self.detector.evaluate(metric_name, result, config)
                    for anomaly in anomalies:
                        if not self.deduplicator.is_duplicate(anomaly):
                            await self.publish_anomaly(anomaly)
                except Exception as e:
                    logger.error(f"Metric query failed: {metric_name}: {e}")
            await asyncio.sleep(self.poll_interval)
```

**Anomaly Detection Algorithm:**

```python
class AnomalyDetector:
    """
    Maintains sliding windows per metric per service.
    Uses z-score for dynamic thresholds, direct comparison for static.
    """

    def __init__(self, window_size: int = 60):
        self.windows: Dict[str, deque] = defaultdict(lambda: deque(maxlen=window_size))

    def evaluate(self, metric_name: str, result: PrometheusResult, config: dict) -> List[Anomaly]:
        anomalies = []
        for series in result.series:
            key = f"{metric_name}:{series.labels.get('container', 'unknown')}"
            value = float(series.value)
            self.windows[key].append(value)

            if config["threshold_type"] == "dynamic":
                if len(self.windows[key]) < 10:
                    continue  # Not enough data
                mean = statistics.mean(self.windows[key])
                stdev = statistics.stdev(self.windows[key])
                if stdev == 0:
                    continue
                z_score = (value - mean) / stdev

                for severity, threshold in config["severity_map"].items():
                    if abs(z_score) >= threshold:
                        anomalies.append(Anomaly(
                            metric=metric_name,
                            service=series.labels.get("container"),
                            value=value,
                            z_score=z_score,
                            severity=severity,
                            labels=series.labels,
                            baseline_mean=mean,
                            baseline_stdev=stdev,
                        ))
                        break  # Highest severity first

            elif config["threshold_type"] == "static":
                for severity, threshold in sorted(
                    config["severity_map"].items(),
                    key=lambda x: x[1],
                    reverse=True
                ):
                    if value >= threshold:
                        anomalies.append(Anomaly(
                            metric=metric_name,
                            service=series.labels.get("container"),
                            value=value,
                            severity=severity,
                            labels=series.labels,
                            threshold=threshold,
                        ))
                        break
        return anomalies
```

#### 3.1.2 Log Observer

```python
class LogObserver:
    """
    Streams logs from Loki, applies pattern matching for
    error signatures, stack traces, and known bad patterns.
    """

    ERROR_PATTERNS = [
        {
            "pattern": r"OOMKilled",
            "severity": "critical",
            "category": "resource_exhaustion",
            "description": "Container killed due to out-of-memory",
        },
        {
            "pattern": r"connection refused.*(?:postgres|5432)",
            "severity": "critical",
            "category": "database_connectivity",
            "description": "PostgreSQL connection refused",
        },
        {
            "pattern": r"ECONNREFUSED.*(?:redis|6379)",
            "severity": "critical",
            "category": "cache_connectivity",
            "description": "Redis connection refused",
        },
        {
            "pattern": r"circuit breaker.*open",
            "severity": "warning",
            "category": "circuit_breaker",
            "description": "Circuit breaker tripped",
        },
        {
            "pattern": r"(?:timeout|deadline exceeded).*(?:\d+)(?:ms|s)",
            "severity": "warning",
            "category": "timeout",
            "description": "Request timeout detected",
        },
        {
            "pattern": r"panic:|SIGSEGV|segmentation fault",
            "severity": "critical",
            "category": "crash",
            "description": "Service crash detected",
        },
        {
            "pattern": r"disk.*(?:full|no space left)",
            "severity": "critical",
            "category": "disk_exhaustion",
            "description": "Disk space exhausted",
        },
        {
            "pattern": r"too many open files|EMFILE",
            "severity": "critical",
            "category": "file_descriptor_exhaustion",
            "description": "File descriptor limit reached",
        },
        {
            "pattern": r"SSL.*(?:expired|handshake failed)",
            "severity": "warning",
            "category": "tls_error",
            "description": "TLS/SSL certificate or handshake error",
        },
        {
            "pattern": r"(?:NATS|JetStream).*(?:disconnect|slow consumer)",
            "severity": "warning",
            "category": "message_bus",
            "description": "NATS connectivity or consumer issue",
        },
    ]

    async def stream_logs(self):
        """Tail Loki logs via WebSocket, apply pattern matching."""
        async for log_entry in self.loki_client.tail(
            query='{namespace="ecommerce"}',
            start=datetime.utcnow()
        ):
            for pattern_config in self.ERROR_PATTERNS:
                match = re.search(pattern_config["pattern"], log_entry.line, re.IGNORECASE)
                if match:
                    anomaly = Anomaly(
                        metric="log_pattern",
                        service=log_entry.labels.get("container"),
                        severity=pattern_config["severity"],
                        category=pattern_config["category"],
                        description=pattern_config["description"],
                        raw_log=log_entry.line,
                        log_context=await self.get_surrounding_logs(
                            log_entry.labels.get("container"),
                            log_entry.timestamp,
                            window_seconds=30
                        ),
                    )
                    if not self.deduplicator.is_duplicate(anomaly):
                        await self.publish_anomaly(anomaly)
```

#### 3.1.3 Health Check Observer

```python
class HealthObserver:
    """
    Actively probes service health endpoints and checks
    dependency connectivity.
    """

    HEALTH_ENDPOINTS = [
        {"service": "user-svc",           "url": "http://user-svc:8001/health",           "timeout": 5},
        {"service": "auth-svc",           "url": "http://auth-svc:8004/health",           "timeout": 5},
        {"service": "order-svc",          "url": "http://order-svc:8002/health",          "timeout": 5},
        {"service": "payment-svc",        "url": "http://payment-svc:8005/health",        "timeout": 5},
        {"service": "product-svc",        "url": "http://product-svc:8003/health",        "timeout": 5},
        {"service": "search-svc",         "url": "http://search-svc:8006/health",         "timeout": 5},
        {"service": "notification-worker", "url": "http://notification-worker:8007/health", "timeout": 5},
        {"service": "inventory-worker",   "url": "http://inventory-worker:8008/health",   "timeout": 5},
        {"service": "analytics-worker",   "url": "http://analytics-worker:8009/health",   "timeout": 5},
    ]

    DEPENDENCY_CHECKS = [
        {"name": "postgres-orders",  "type": "tcp", "host": "postgres-orders",  "port": 5432},
        {"name": "postgres-payments","type": "tcp", "host": "postgres-payments", "port": 5432},
        {"name": "redis",           "type": "redis","host": "redis",            "port": 6379},
        {"name": "elasticsearch",   "type": "http", "url": "http://elasticsearch:9200/_cluster/health"},
        {"name": "nats",            "type": "tcp", "host": "nats",              "port": 4222},
    ]

    async def check_health(self, endpoint: dict) -> HealthResult:
        try:
            start = time.monotonic()
            async with aiohttp.ClientSession() as session:
                resp = await session.get(
                    endpoint["url"],
                    timeout=aiohttp.ClientTimeout(total=endpoint["timeout"])
                )
                latency = time.monotonic() - start
                body = await resp.json()
                return HealthResult(
                    service=endpoint["service"],
                    status="healthy" if resp.status == 200 else "degraded",
                    latency_ms=latency * 1000,
                    details=body,
                )
        except asyncio.TimeoutError:
            return HealthResult(service=endpoint["service"], status="timeout")
        except Exception as e:
            return HealthResult(service=endpoint["service"], status="unreachable", error=str(e))
```

#### 3.1.4 Synthetic Prober

```python
class SyntheticProber:
    """
    Executes synthetic transactions against the system to detect
    end-to-end failures that individual metric/log checks would miss.
    """

    async def probe_order_flow(self) -> ProbeResult:
        """Full e2e: authenticate → browse products → place order → verify."""
        steps = []

        # Step 1: Authenticate
        auth_result = await self.http_post("http://api-gateway:8000/auth/login", {
            "email": "probe-user@synthetic.test",
            "password": "probe-password"
        })
        steps.append(ProbeStep("auth", auth_result.status, auth_result.latency))

        # Step 2: Search products
        search_result = await self.http_get(
            "http://api-gateway:8000/products/search?q=test-product",
            headers={"Authorization": f"Bearer {auth_result.token}"}
        )
        steps.append(ProbeStep("product_search", search_result.status, search_result.latency))

        # Step 3: Place order
        order_result = await self.http_post("http://api-gateway:8000/orders", {
            "product_id": "synthetic-test-product",
            "quantity": 1
        }, headers={"Authorization": f"Bearer {auth_result.token}"})
        steps.append(ProbeStep("place_order", order_result.status, order_result.latency))

        # Step 4: Verify order appeared (check async processing)
        await asyncio.sleep(2)
        verify_result = await self.http_get(
            f"http://api-gateway:8000/orders/{order_result.order_id}",
            headers={"Authorization": f"Bearer {auth_result.token}"}
        )
        steps.append(ProbeStep("verify_order", verify_result.status, verify_result.latency))

        return ProbeResult(
            probe_name="order_flow",
            success=all(s.status == "ok" for s in steps),
            total_latency_ms=sum(s.latency_ms for s in steps),
            steps=steps,
        )

    async def probe_payment_flow(self) -> ProbeResult:
        """Verify payment processing end-to-end."""
        ...

    async def probe_search_relevance(self) -> ProbeResult:
        """Verify Elasticsearch returns expected results."""
        ...

    async def probe_notification_delivery(self) -> ProbeResult:
        """Verify NATS → Notification Worker pipeline."""
        ...
```

#### 3.1.5 Alert Deduplication Engine

```python
class AlertDeduplicator:
    """
    Prevents alert storms by grouping similar anomalies.
    Uses a fingerprint based on metric + service + category.
    """

    def __init__(self, window_seconds: int = 300, max_per_window: int = 3):
        self.window_seconds = window_seconds
        self.max_per_window = max_per_window
        self.seen: Dict[str, List[datetime]] = defaultdict(list)

    def fingerprint(self, anomaly: Anomaly) -> str:
        return hashlib.sha256(
            f"{anomaly.metric}:{anomaly.service}:{anomaly.severity}".encode()
        ).hexdigest()[:16]

    def is_duplicate(self, anomaly: Anomaly) -> bool:
        fp = self.fingerprint(anomaly)
        now = datetime.utcnow()
        # Clean old entries
        self.seen[fp] = [t for t in self.seen[fp] if (now - t).seconds < self.window_seconds]
        if len(self.seen[fp]) >= self.max_per_window:
            return True
        self.seen[fp].append(now)
        return False
```

---

### 3.2 Diagnoser Agent

The most complex agent — it takes an anomaly and produces a root cause hypothesis.

```
┌──────────────────────────────────────────────────────────┐
│                    DIAGNOSER AGENT                        │
│                                                          │
│  Anomaly In ──▶ ┌─────────────────┐                     │
│                 │ Context Collector│                     │
│                 │                 │                     │
│                 │ • Pull related logs (±5 min)          │
│                 │ • Pull correlated metrics             │
│                 │ • Check recent deployments            │
│                 │ • Check dependency health             │
│                 │ • Check resource trends (1h)          │
│                 │ • Pull NATS consumer states           │
│                 │ • Check config changes                │
│                 └────────┬────────┘                     │
│                          │                              │
│                 ┌────────▼────────┐                     │
│                 │ Correlation     │                     │
│                 │ Engine          │                     │
│                 │                 │                     │
│                 │ • Temporal correlation                │
│                 │ • Service dependency mapping          │
│                 │ • Cascading failure detection         │
│                 │ • Multi-signal fusion                 │
│                 └────────┬────────┘                     │
│                          │                              │
│                 ┌────────▼────────┐                     │
│                 │ RCA Engine      │                     │
│                 │ (LLM-powered)   │                     │
│                 │                 │                     │
│                 │ Context + Corr. │                     │
│                 │ → Hypothesis    │                     │
│                 │ → Confidence    │                     │
│                 │ → Evidence      │                     │
│                 └────────┬────────┘                     │
│                          │                              │
│                 ┌────────▼────────┐                     │
│                 │ Past Incident   │                     │
│                 │ Matcher (RAG)   │                     │
│                 │                 │                     │
│                 │ Vector search over                    │
│                 │ historical incidents                  │
│                 └────────┬────────┘                     │
│                          │                              │
│                 ┌────────▼────────┐                     │
│                 │ Diagnosis       │──▶ Diagnosis Out    │
│                 │ Output Builder  │                     │
│                 └─────────────────┘                     │
└──────────────────────────────────────────────────────────┘
```

#### 3.2.1 Context Collector — Tool Definitions

```python
class DiagnoserToolkit:
    """
    Tools the Diagnoser agent can invoke to gather investigation context.
    Each tool is a callable that returns structured data.
    """

    async def get_service_logs(
        self, service: str, start: datetime, end: datetime, limit: int = 200
    ) -> List[LogEntry]:
        """Pull logs from Loki for a specific service in a time window."""
        query = f'{{container="{service}"}}'
        return await self.loki_client.query_range(query, start, end, limit)

    async def get_metric_history(
        self, query: str, start: datetime, end: datetime, step: str = "30s"
    ) -> MetricTimeSeries:
        """Pull metric time series from Prometheus."""
        return await self.prom_client.query_range(query, start, end, step)

    async def get_recent_deployments(
        self, service: str, hours: int = 24
    ) -> List[Deployment]:
        """Check if there were recent deployments to this service."""
        return await self.deployment_store.get_recent(service, hours)

    async def get_dependency_health(
        self, service: str
    ) -> Dict[str, HealthStatus]:
        """Check health of all upstream/downstream dependencies."""
        deps = self.dependency_graph.get_dependencies(service)
        results = {}
        for dep in deps:
            results[dep.name] = await self.health_checker.check(dep)
        return results

    async def get_resource_trends(
        self, service: str, hours: int = 1
    ) -> ResourceTrends:
        """Get CPU, memory, disk, network trends for a service."""
        end = datetime.utcnow()
        start = end - timedelta(hours=hours)
        return ResourceTrends(
            cpu=await self.get_metric_history(
                f'rate(container_cpu_usage_seconds_total{{container="{service}"}}[5m])',
                start, end
            ),
            memory=await self.get_metric_history(
                f'container_memory_working_set_bytes{{container="{service}"}}',
                start, end
            ),
            network_rx=await self.get_metric_history(
                f'rate(container_network_receive_bytes_total{{container="{service}"}}[5m])',
                start, end
            ),
            network_tx=await self.get_metric_history(
                f'rate(container_network_transmit_bytes_total{{container="{service}"}}[5m])',
                start, end
            ),
        )

    async def get_nats_consumer_state(
        self, stream: str
    ) -> NATSConsumerInfo:
        """Check NATS JetStream consumer lag, pending, redelivery count."""
        return await self.nats_client.consumer_info(stream)

    async def get_pg_stats(
        self, db_name: str
    ) -> PostgresStats:
        """Get PostgreSQL stats: active queries, locks, table sizes, slow queries."""
        return PostgresStats(
            active_queries=await self.pg_client.query(
                "SELECT * FROM pg_stat_activity WHERE state = 'active' AND datname = $1",
                db_name
            ),
            locks=await self.pg_client.query(
                "SELECT * FROM pg_locks WHERE NOT granted"
            ),
            table_bloat=await self.pg_client.query(
                "SELECT schemaname, tablename, pg_total_relation_size(quote_ident(tablename)) FROM pg_tables WHERE schemaname = 'public' ORDER BY pg_total_relation_size(quote_ident(tablename)) DESC LIMIT 10"
            ),
            slow_queries=await self.pg_client.query(
                "SELECT * FROM pg_stat_statements ORDER BY total_exec_time DESC LIMIT 10"
            ),
        )

    async def get_redis_info(self) -> RedisInfo:
        """Get Redis memory, connected clients, eviction stats."""
        info = await self.redis_client.info()
        return RedisInfo(
            used_memory=info["used_memory"],
            max_memory=info["maxmemory"],
            connected_clients=info["connected_clients"],
            evicted_keys=info["evicted_keys"],
            keyspace_hits=info["keyspace_hits"],
            keyspace_misses=info["keyspace_misses"],
        )

    async def get_elasticsearch_health(self) -> ESClusterHealth:
        """Get Elasticsearch cluster health, shard allocation, index stats."""
        return await self.es_client.cluster.health()

    async def get_config_changes(
        self, service: str, hours: int = 24
    ) -> List[ConfigChange]:
        """Check for recent configuration changes from etcd."""
        return await self.config_store.get_changes(service, hours)
```

#### 3.2.2 Correlation Engine

```python
class CorrelationEngine:
    """
    Finds relationships between anomalies across services and time.
    """

    def __init__(self, dependency_graph: DependencyGraph):
        self.dependency_graph = dependency_graph

    # --- Static Dependency Graph ---
    # Loaded from YAML config, represents service-to-service dependencies

    DEPENDENCY_MAP = {
        "api-gateway":          {"depends_on": ["user-svc", "order-svc", "product-svc", "auth-svc"]},
        "user-svc":             {"depends_on": ["redis"]},
        "auth-svc":             {"depends_on": ["redis", "user-svc"]},
        "order-svc":            {"depends_on": ["postgres-orders", "nats", "payment-svc", "inventory-worker"]},
        "payment-svc":          {"depends_on": ["postgres-payments", "nats"]},
        "product-svc":          {"depends_on": ["elasticsearch"]},
        "search-svc":           {"depends_on": ["elasticsearch"]},
        "notification-worker":  {"depends_on": ["nats"]},
        "inventory-worker":     {"depends_on": ["nats", "postgres-orders"]},
        "analytics-worker":     {"depends_on": ["nats"]},
    }

    def find_correlations(
        self,
        primary_anomaly: Anomaly,
        all_recent_anomalies: List[Anomaly],
        time_window_seconds: int = 300,
    ) -> CorrelationResult:
        """
        Given a primary anomaly, find related anomalies that might be
        part of the same incident.
        """

        correlated = []

        for other in all_recent_anomalies:
            if other.id == primary_anomaly.id:
                continue

            score = 0.0
            reasons = []

            # Temporal correlation: did they happen close together?
            time_diff = abs((primary_anomaly.timestamp - other.timestamp).total_seconds())
            if time_diff < time_window_seconds:
                temporal_score = 1.0 - (time_diff / time_window_seconds)
                score += temporal_score * 0.3
                reasons.append(f"Temporal proximity: {time_diff:.0f}s apart")

            # Dependency correlation: are the services related?
            if self.are_dependent(primary_anomaly.service, other.service):
                score += 0.4
                path = self.get_dependency_path(primary_anomaly.service, other.service)
                reasons.append(f"Dependency chain: {' → '.join(path)}")

            # Causal pattern: upstream dependency failing → downstream errors
            if self.is_upstream(other.service, primary_anomaly.service):
                score += 0.2
                reasons.append(f"{other.service} is upstream of {primary_anomaly.service}")

            # Same infrastructure: shared database/queue issues
            shared = self.get_shared_dependencies(primary_anomaly.service, other.service)
            if shared:
                score += 0.1
                reasons.append(f"Shared dependencies: {', '.join(shared)}")

            if score > 0.3:
                correlated.append(CorrelatedAnomaly(
                    anomaly=other,
                    correlation_score=min(score, 1.0),
                    reasons=reasons,
                ))

        # Sort by correlation score descending
        correlated.sort(key=lambda x: x.correlation_score, reverse=True)

        # Detect cascading failure pattern
        cascade = self.detect_cascade(primary_anomaly, correlated)

        return CorrelationResult(
            primary=primary_anomaly,
            correlated=correlated,
            cascade_detected=cascade is not None,
            cascade_chain=cascade,
            likely_root=cascade.root if cascade else primary_anomaly.service,
        )

    def detect_cascade(
        self,
        primary: Anomaly,
        correlated: List[CorrelatedAnomaly]
    ) -> Optional[CascadeChain]:
        """
        Detect if anomalies form a cascading failure pattern.
        Walk the dependency graph to find the root cause service.
        """
        affected_services = {primary.service} | {c.anomaly.service for c in correlated}

        # BFS from each affected service upward through dependencies
        for service in affected_services:
            path = self.trace_upstream(service, affected_services)
            if path and len(path) >= 2:
                return CascadeChain(
                    root=path[0],
                    chain=path,
                    affected_count=len(affected_services),
                )
        return None
```

#### 3.2.3 RCA Engine (LLM-Powered)

```python
class RCAEngine:
    """
    Uses an LLM to synthesize all collected context into a
    root cause hypothesis with confidence and evidence.
    """

    RCA_SYSTEM_PROMPT = """You are an expert Site Reliability Engineer performing
root cause analysis on a production incident.

You will be given:
1. The primary anomaly that triggered the investigation
2. Correlated anomalies from related services
3. Service logs around the time of the incident
4. Metric trends for affected services
5. Recent deployments and config changes
6. Dependency health status
7. Database and queue statistics
8. Similar past incidents (if any)

Your task is to:
1. Identify the most likely ROOT CAUSE (not symptoms)
2. Explain the causal chain from root cause to observed symptoms
3. Assign a confidence score (0-100)
4. List specific evidence supporting your hypothesis
5. Suggest what additional information would increase your confidence
6. Recommend specific remediation actions

Output your analysis as structured JSON."""

    RCA_OUTPUT_SCHEMA = {
        "type": "object",
        "properties": {
            "root_cause": {
                "type": "object",
                "properties": {
                    "service": {"type": "string"},
                    "category": {
                        "type": "string",
                        "enum": [
                            "memory_leak", "cpu_saturation", "disk_exhaustion",
                            "network_partition", "database_overload", "connection_pool_exhaustion",
                            "deadlock", "configuration_error", "deployment_regression",
                            "dependency_failure", "resource_limit", "data_corruption",
                            "certificate_expiry", "dns_failure", "queue_backpressure",
                        ]
                    },
                    "description": {"type": "string"},
                    "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
                }
            },
            "causal_chain": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "step": {"type": "integer"},
                        "service": {"type": "string"},
                        "event": {"type": "string"},
                        "evidence": {"type": "string"},
                    }
                }
            },
            "evidence": {"type": "array", "items": {"type": "string"}},
            "missing_info": {"type": "array", "items": {"type": "string"}},
            "recommended_actions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string"},
                        "priority": {"type": "string", "enum": ["immediate", "short_term", "long_term"]},
                        "risk": {"type": "string", "enum": ["low", "medium", "high", "varies"]},
                    }
                }
            }
        }
    }

    async def diagnose(self, investigation_context: InvestigationContext) -> Diagnosis:
        prompt = self.build_prompt(investigation_context)
        response = await self.llm_client.chat(
            model="claude-sonnet-4-20250514",
            system=self.RCA_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object", "schema": self.RCA_OUTPUT_SCHEMA},
            max_tokens=4096,
        )
        return Diagnosis.from_llm_response(response, investigation_context)

    def build_prompt(self, ctx: InvestigationContext) -> str:
        sections = []

        sections.append(f"## Primary Anomaly\n{ctx.primary_anomaly.to_summary()}")

        if ctx.correlated_anomalies:
            corr_text = "\n".join(
                f"- {c.anomaly.to_summary()} (correlation: {c.correlation_score:.2f}, reasons: {', '.join(c.reasons)})"
                for c in ctx.correlated_anomalies
            )
            sections.append(f"## Correlated Anomalies\n{corr_text}")

        if ctx.cascade:
            sections.append(
                f"## Cascade Detected\nRoot: {ctx.cascade.root} → Chain: {' → '.join(ctx.cascade.chain)}"
            )

        sections.append(f"## Service Logs (last 5 min)\n```\n{ctx.logs_summary}\n```")
        sections.append(f"## Metric Trends\n{ctx.metric_trends_summary}")
        sections.append(f"## Recent Deployments\n{ctx.deployments_summary}")
        sections.append(f"## Dependency Health\n{ctx.dependency_health_summary}")
        sections.append(f"## Database Stats\n{ctx.db_stats_summary}")
        sections.append(f"## Queue Stats\n{ctx.queue_stats_summary}")

        if ctx.similar_incidents:
            hist_text = "\n".join(
                f"- [{inc.date}] {inc.summary} → Fix: {inc.resolution}"
                for inc in ctx.similar_incidents[:5]
            )
            sections.append(f"## Similar Past Incidents\n{hist_text}")

        return "\n\n".join(sections)
```

---

### 3.3 Remediator Agent

```
┌─────────────────────────────────────────────────────────────┐
│                    REMEDIATOR AGENT                          │
│                                                             │
│  Diagnosis In ──▶ ┌─────────────────┐                      │
│                   │  Runbook Engine  │                      │
│                   │                 │                      │
│                   │  Match diagnosis│                      │
│                   │  to runbook     │                      │
│                   │  entries        │                      │
│                   └────────┬────────┘                      │
│                            │                               │
│                   ┌────────▼────────┐                      │
│                   │ Action Planner  │                      │
│                   │                 │                      │
│                   │ Build ordered   │                      │
│                   │ action sequence │                      │
│                   │ with rollback   │                      │
│                   └────────┬────────┘                      │
│                            │                               │
│                   ┌────────▼────────┐                      │
│                   │ → Safety Agent  │ (external review)    │
│                   └────────┬────────┘                      │
│                            │ (approved)                    │
│                   ┌────────▼────────┐                      │
│                   │ Action Executor │                      │
│                   │                 │                      │
│                   │ Execute actions │                      │
│                   │ via Docker API  │                      │
│                   │ / kubectl / SQL │                      │
│                   └────────┬────────┘                      │
│                            │                               │
│                   ┌────────▼────────┐                      │
│                   │  Verification   │                      │
│                   │  Engine         │                      │
│                   │                 │                      │
│                   │  Did the fix    │                      │
│                   │  actually work? │                      │
│                   └────────┬────────┘                      │
│                            │                               │
│                   ┌────────▼────────┐                      │
│                   │ Rollback Manager│ (if verification     │
│                   │                 │  fails)              │
│                   └─────────────────┘                      │
└─────────────────────────────────────────────────────────────┘
```

#### 3.3.1 Runbook Engine

```yaml
# runbooks/memory_leak.yml
---
id: runbook_memory_leak
name: "Memory Leak Remediation"
matches:
  root_cause_category: "memory_leak"
  confidence_minimum: 60

actions:
  - id: "restart_container"
    type: "container_restart"
    description: "Restart the leaking container to free memory"
    params:
      target: "{{diagnosis.root_cause.service}}"
      graceful: true
      drain_connections: true
      drain_timeout_seconds: 30
    risk: "low"
    approval_required: false
    rollback: null  # restart is self-contained

  - id: "scale_up"
    type: "container_scale"
    description: "Scale up replicas to absorb traffic during investigation"
    params:
      target: "{{diagnosis.root_cause.service}}"
      replicas: "{{current_replicas + 1}}"
      max_replicas: 5
    risk: "low"
    approval_required: false
    rollback:
      type: "container_scale"
      params:
        replicas: "{{original_replicas}}"

  - id: "increase_memory_limit"
    type: "resource_update"
    description: "Temporarily increase memory limit"
    params:
      target: "{{diagnosis.root_cause.service}}"
      resource: "memory"
      new_limit: "{{current_limit * 1.5}}"
    risk: "medium"
    approval_required: true
    rollback:
      type: "resource_update"
      params:
        resource: "memory"
        new_limit: "{{original_limit}}"

verification:
  wait_seconds: 60
  checks:
    - type: "metric"
      query: 'container_memory_working_set_bytes{container="{{service}}"}'
      condition: "value < {{threshold}}"
    - type: "health_check"
      endpoint: "{{service_health_url}}"
      expected_status: 200
```

```yaml
# runbooks/database_overload.yml
---
id: runbook_database_overload
name: "Database Overload Remediation"
matches:
  root_cause_category: "database_overload"

actions:
  - id: "kill_long_queries"
    type: "sql_execute"
    description: "Kill queries running longer than 60 seconds"
    params:
      target_db: "{{diagnosis.root_cause.service}}"
      query: |
        SELECT pg_terminate_backend(pid)
        FROM pg_stat_activity
        WHERE state = 'active'
          AND query_start < NOW() - INTERVAL '60 seconds'
          AND query NOT LIKE '%pg_stat%'
    risk: "medium"
    approval_required: true
    rollback: null

  - id: "enable_connection_pooling"
    type: "config_update"
    description: "Reduce max connections per service"
    params:
      config_key: "db.max_connections"
      new_value: "{{current_value * 0.7}}"
    risk: "medium"
    approval_required: true

  - id: "restart_pgbouncer"
    type: "container_restart"
    description: "Restart connection pooler"
    params:
      target: "pgbouncer"
    risk: "low"
    approval_required: false

verification:
  wait_seconds: 30
  checks:
    - type: "metric"
      query: 'pg_stat_activity_count{state="active"}'
      condition: "value < 80"
    - type: "metric"
      query: 'rate(http_requests_total{status=~"5.."}[1m])'
      condition: "value < 0.05"
```

```yaml
# runbooks/cascading_failure.yml
---
id: runbook_cascading_failure
name: "Cascading Failure Remediation"
matches:
  cascade_detected: true

actions:
  - id: "circuit_break_root"
    type: "circuit_breaker"
    description: "Open circuit breaker on the failing root service"
    params:
      target: "{{cascade.root}}"
      state: "open"
      fallback: "cached_response"
    risk: "medium"
    approval_required: true
    rollback:
      type: "circuit_breaker"
      params:
        state: "closed"

  - id: "fix_root_cause"
    type: "dynamic"
    description: "Apply root-cause-specific fix to the failing service"
    params:
      delegate_to: "{{lookup_runbook(diagnosis.root_cause.category)}}"
    risk: "varies"
    approval_required: true

  - id: "gradually_close_circuit"
    type: "circuit_breaker"
    description: "Gradually close circuit breaker (half-open → closed)"
    params:
      target: "{{cascade.root}}"
      state: "half-open"
      test_request_percentage: 10
      success_threshold: 5
    risk: "low"
    approval_required: false

verification:
  wait_seconds: 120
  checks:
    - type: "synthetic_probe"
      probe: "order_flow"
      expected: "success"
    - type: "metric"
      query: 'rate(http_requests_total{status=~"5.."}[5m])'
      condition: "value < 0.01"
```

Additional runbooks that should exist:

```
runbooks/
├── memory_leak.yml
├── cpu_saturation.yml
├── disk_exhaustion.yml
├── network_partition.yml
├── database_overload.yml
├── connection_pool_exhaustion.yml
├── deadlock.yml
├── configuration_error.yml
├── deployment_regression.yml
├── dependency_failure.yml
├── certificate_expiry.yml
├── dns_failure.yml
├── queue_backpressure.yml
├── cascading_failure.yml
├── elasticsearch_cluster_red.yml
├── redis_memory_full.yml
├── nats_slow_consumer.yml
└── container_crash_loop.yml
```

#### 3.3.2 Action Executor

```python
class ActionExecutor:
    """
    Executes remediation actions against the infrastructure.
    Each action type maps to a specific executor.
    """

    def __init__(self):
        self.executors: Dict[str, BaseExecutor] = {
            "container_restart":  DockerRestartExecutor(),
            "container_scale":    DockerScaleExecutor(),
            "resource_update":    DockerResourceExecutor(),
            "sql_execute":        SQLExecutor(),
            "config_update":      ConfigExecutor(),
            "circuit_breaker":    CircuitBreakerExecutor(),
            "rollback_deployment": DeploymentRollbackExecutor(),
            "clear_cache":        CacheClearExecutor(),
            "dns_update":         DNSExecutor(),
        }

    async def execute(self, action: RemediationAction) -> ActionResult:
        executor = self.executors.get(action.type)
        if not executor:
            return ActionResult(success=False, error=f"Unknown action type: {action.type}")

        # Record pre-execution state for rollback
        pre_state = await executor.capture_state(action.params)

        try:
            result = await asyncio.wait_for(
                executor.execute(action.params),
                timeout=action.timeout_seconds or 120
            )
            return ActionResult(
                success=True,
                action_id=action.id,
                pre_state=pre_state,
                output=result,
                executed_at=datetime.utcnow(),
            )
        except asyncio.TimeoutError:
            return ActionResult(
                success=False,
                action_id=action.id,
                error="Action timed out",
                pre_state=pre_state,
            )
        except Exception as e:
            return ActionResult(
                success=False,
                action_id=action.id,
                error=str(e),
                pre_state=pre_state,
            )


class DockerRestartExecutor(BaseExecutor):
    """Restart a Docker container gracefully."""

    async def execute(self, params: dict) -> dict:
        container_name = params["target"]
        graceful = params.get("graceful", True)
        drain_timeout = params.get("drain_timeout_seconds", 30)

        container = self.docker_client.containers.get(container_name)

        if graceful and params.get("drain_connections"):
            # Signal the service to stop accepting new connections
            await self.send_signal(container, signal.SIGTERM)
            await asyncio.sleep(drain_timeout)

        container.restart(timeout=drain_timeout)

        # Wait for health check to pass
        for _ in range(30):
            container.reload()
            if container.attrs["State"]["Health"]["Status"] == "healthy":
                return {"status": "restarted", "healthy": True}
            await asyncio.sleep(2)

        return {"status": "restarted", "healthy": False}


class SQLExecutor(BaseExecutor):
    """Execute SQL commands against a database."""

    # SAFETY: Only allow specific SQL patterns
    ALLOWED_PATTERNS = [
        r"^SELECT pg_terminate_backend",
        r"^SELECT pg_cancel_backend",
        r"^ALTER SYSTEM SET",
        r"^VACUUM",
        r"^REINDEX",
        r"^ANALYZE",
    ]

    async def execute(self, params: dict) -> dict:
        query = params["query"].strip()

        # Validate query against allowed patterns
        if not any(re.match(pattern, query, re.IGNORECASE) for pattern in self.ALLOWED_PATTERNS):
            raise SecurityError(f"SQL query not in allowed patterns: {query[:100]}")

        async with self.get_connection(params["target_db"]) as conn:
            result = await conn.execute(query)
            return {"rows_affected": result.rowcount, "query": query}
```

#### 3.3.3 Verification Engine

```python
class VerificationEngine:
    """
    After remediation, verify that the fix actually worked.
    """

    async def verify(
        self,
        verification_config: dict,
        diagnosis: Diagnosis,
        action_results: List[ActionResult],
    ) -> VerificationResult:

        wait_seconds = verification_config.get("wait_seconds", 60)
        logger.info(f"Waiting {wait_seconds}s before verification...")
        await asyncio.sleep(wait_seconds)

        check_results = []
        for check in verification_config["checks"]:
            result = await self.run_check(check, diagnosis)
            check_results.append(result)

        all_passed = all(r.passed for r in check_results)
        return VerificationResult(
            passed=all_passed,
            checks=check_results,
            verified_at=datetime.utcnow(),
            recommendation="close_incident" if all_passed else "escalate_or_rollback",
        )

    async def run_check(self, check: dict, diagnosis: Diagnosis) -> CheckResult:
        if check["type"] == "metric":
            value = await self.prom_client.query_instant(
                self.template(check["query"], diagnosis)
            )
            condition_met = self.evaluate_condition(value, check["condition"])
            return CheckResult(
                name=check["query"],
                passed=condition_met,
                actual_value=value,
                expected=check["condition"],
            )

        elif check["type"] == "health_check":
            try:
                resp = await self.http_client.get(
                    self.template(check["endpoint"], diagnosis),
                    timeout=10
                )
                return CheckResult(
                    name=check["endpoint"],
                    passed=resp.status == check["expected_status"],
                    actual_value=resp.status,
                )
            except Exception as e:
                return CheckResult(name=check["endpoint"], passed=False, error=str(e))

        elif check["type"] == "synthetic_probe":
            probe_result = await self.synthetic_prober.run_probe(check["probe"])
            return CheckResult(
                name=check["probe"],
                passed=probe_result.success,
                actual_value="success" if probe_result.success else "failed",
            )
```

---

### 3.4 Safety Agent

```python
class SafetyAgent:
    """
    Reviews all proposed remediations before execution.
    Enforces policies, calculates blast radius, and gates dangerous actions.
    """

    class TrustLevel(Enum):
        AUTO_APPROVE = "auto_approve"      # Container restart, cache clear
        NOTIFY_THEN_EXECUTE = "notify"     # Scale up, config tweak
        REQUIRE_HUMAN = "require_human"    # Rollback deployment, kill queries, circuit break

    # --- Policy Rules ---

    POLICIES = [
        {
            "name": "loop_prevention",
            "description": "Prevent the same remediation from running repeatedly",
            "check": lambda self, action, ctx: not self.was_attempted_recently(
                action, window_minutes=15
            ),
            "violation_message": "This action was already attempted in the last 15 minutes",
        },
        {
            "name": "blast_radius_limit",
            "description": "Prevent actions affecting more than 50% of replicas simultaneously",
            "check": lambda self, action, ctx: self.blast_radius(action) <= 0.5,
            "violation_message": "Action would affect more than 50% of service capacity",
        },
        {
            "name": "business_hours_escalation",
            "description": "High-risk actions outside business hours require human approval",
            "check": lambda self, action, ctx: (
                action.risk != "high" or self.is_business_hours()
            ),
            "violation_message": "High-risk action outside business hours",
        },
        {
            "name": "concurrent_action_limit",
            "description": "No more than 3 active remediations at once",
            "check": lambda self, action, ctx: self.active_remediation_count() < 3,
            "violation_message": "Too many concurrent remediations",
        },
        {
            "name": "deployment_freeze",
            "description": "No rollbacks during deployment freeze windows",
            "check": lambda self, action, ctx: (
                action.type != "rollback_deployment" or not self.in_freeze_window()
            ),
            "violation_message": "Deployment freeze is active",
        },
        {
            "name": "database_protection",
            "description": "All database actions require human approval",
            "check": lambda self, action, ctx: action.type != "sql_execute",
            "violation_message": "Database operations always require human approval",
            "override_trust": TrustLevel.REQUIRE_HUMAN,
        },
        {
            "name": "minimum_confidence",
            "description": "Diagnosis must have >=60% confidence for auto-remediation",
            "check": lambda self, action, ctx: ctx.diagnosis.confidence >= 60,
            "violation_message": "Diagnosis confidence too low for automated action",
        },
    ]

    async def review(
        self,
        proposed_actions: List[RemediationAction],
        diagnosis: Diagnosis,
        incident_context: IncidentContext,
    ) -> SafetyReview:

        reviews = []
        for action in proposed_actions:
            trust_level = self.determine_trust_level(action)
            policy_violations = []

            for policy in self.POLICIES:
                if not policy["check"](self, action, incident_context):
                    policy_violations.append(PolicyViolation(
                        policy=policy["name"],
                        message=policy["violation_message"],
                    ))
                    if "override_trust" in policy:
                        trust_level = policy["override_trust"]

            blast_radius = self.calculate_blast_radius(action, incident_context)

            decision = self.make_decision(trust_level, policy_violations, blast_radius)

            reviews.append(ActionReview(
                action=action,
                trust_level=trust_level,
                policy_violations=policy_violations,
                blast_radius=blast_radius,
                decision=decision,
            ))

        return SafetyReview(
            reviews=reviews,
            requires_human=any(r.decision == "require_human" for r in reviews),
            auto_approved=[r for r in reviews if r.decision == "approved"],
            blocked=[r for r in reviews if r.decision == "blocked"],
        )

    def calculate_blast_radius(
        self, action: RemediationAction, ctx: IncidentContext
    ) -> BlastRadius:
        """Estimate the impact of an action."""
        affected_services = {action.params.get("target", "unknown")}

        # Find downstream services that would be affected
        downstream = self.dependency_graph.get_all_downstream(
            action.params.get("target")
        )
        affected_services.update(downstream)

        total_services = len(self.dependency_graph.all_services())
        ratio = len(affected_services) / total_services

        # Estimate user-facing impact
        user_facing = any(
            svc in self.USER_FACING_SERVICES for svc in affected_services
        )

        return BlastRadius(
            affected_services=list(affected_services),
            ratio=ratio,
            user_facing=user_facing,
            estimated_users_affected=self.estimate_affected_users(affected_services),
            risk_score=ratio * (2.0 if user_facing else 1.0),
        )

    async def request_human_approval(
        self,
        action_review: ActionReview,
        incident: Incident,
    ) -> HumanDecision:
        """Send approval request via dashboard + Slack/PagerDuty."""

        approval_request = ApprovalRequest(
            incident_id=incident.id,
            action=action_review.action,
            diagnosis_summary=incident.diagnosis.summary,
            blast_radius=action_review.blast_radius,
            policy_violations=action_review.policy_violations,
            expires_at=datetime.utcnow() + timedelta(minutes=15),
        )

        # Publish to human approval channel
        await self.nats_client.publish(
            "human.approvals",
            approval_request.to_json()
        )

        # Also send to Slack/PagerDuty
        await self.notification_service.send_approval_request(approval_request)

        # Wait for response (with timeout)
        try:
            decision = await asyncio.wait_for(
                self.wait_for_human_decision(approval_request.id),
                timeout=900  # 15 minutes
            )
            return decision
        except asyncio.TimeoutError:
            return HumanDecision(approved=False, reason="Timed out waiting for approval")
```

---

### 3.5 Orchestrator Agent — Incident State Machine

```
┌─────────┐     anomaly      ┌─────────────┐     context      ┌──────────────┐
│         │   detected        │             │    collected      │              │
│  IDLE   ├──────────────────▶│  DETECTING  ├─────────────────▶│  DIAGNOSING  │
│         │                   │             │                   │              │
└─────────┘                   └──────┬──────┘                   └──────┬───────┘
     ▲                               │                                 │
     │                               │ duplicate /                     │ diagnosis
     │                               │ false positive                  │ complete
     │                               ▼                                 ▼
     │                        ┌──────────────┐                  ┌──────────────┐
     │                        │   DISMISSED  │                  │  PROPOSING   │
     │                        └──────────────┘                  │  REMEDIATION │
     │                                                          └──────┬───────┘
     │                                                                 │
     │                                                                 │ actions proposed
     │                                                                 ▼
     │                                                          ┌──────────────┐
     │                        ┌──────────────┐   approved       │   SAFETY     │
     │                        │  EXECUTING   │◀─────────────────│   REVIEW     │
     │                        │              │                  └──────┬───────┘
     │                        └──────┬───────┘                         │
     │                               │                                 │ blocked
     │                               │ actions complete                ▼
     │                               ▼                          ┌──────────────┐
     │                        ┌──────────────┐                  │   WAITING    │
     │                        │  VERIFYING   │                  │   HUMAN      │
     │                        │              │                  │   APPROVAL   │
     │                        └──────┬───────┘                  └──────┬───────┘
     │                               │                                 │
     │               ┌───────────────┼───────────────┐                 │ approved
     │               │               │               │                 │
     │               ▼               ▼               ▼                 │
     │        ┌────────────┐  ┌────────────┐  ┌────────────┐          │
     │        │  RESOLVED  │  │  ROLLING   │  │ ESCALATED  │◀─────────┘
     │        │            │  │  BACK      │  │            │  (rejected)
     │        └──────┬─────┘  └──────┬─────┘  └────────────┘
     │               │               │
     │               ▼               ▼
     │        ┌────────────┐  ┌────────────┐
     └────────│  CLOSED    │  │  FAILED    │
              └────────────┘  └────────────┘
```

```python
class IncidentStateMachine:
    """
    Manages the lifecycle of an incident through all states.
    Persisted in PostgreSQL for durability.
    """

    TRANSITIONS = {
        "idle":              ["detecting"],
        "detecting":         ["diagnosing", "dismissed"],
        "diagnosing":        ["proposing_remediation", "escalated"],
        "proposing_remediation": ["safety_review"],
        "safety_review":     ["executing", "waiting_human_approval", "escalated"],
        "waiting_human_approval": ["executing", "escalated"],
        "executing":         ["verifying"],
        "verifying":         ["resolved", "rolling_back", "escalated"],
        "rolling_back":      ["failed", "detecting"],  # retry after rollback
        "resolved":          ["closed"],
        "escalated":         ["closed"],
        "failed":            ["closed"],
        "dismissed":         ["closed"],
    }

    TIMEOUTS = {
        "detecting":         timedelta(minutes=2),
        "diagnosing":        timedelta(minutes=5),
        "proposing_remediation": timedelta(minutes=2),
        "safety_review":     timedelta(minutes=1),
        "waiting_human_approval": timedelta(minutes=15),
        "executing":         timedelta(minutes=10),
        "verifying":         timedelta(minutes=5),
        "rolling_back":      timedelta(minutes=5),
    }
```

#### 3.5.1 Orchestrator Main Loop

```python
class OrchestratorAgent:

    async def run(self):
        """Main orchestrator event loop."""

        # Subscribe to all agent channels
        await self.nats.subscribe("agents.observer.anomalies", self.handle_anomaly)
        await self.nats.subscribe("agents.diagnoser.results", self.handle_diagnosis)
        await self.nats.subscribe("agents.safety.decisions", self.handle_safety_decision)
        await self.nats.subscribe("agents.remediator.executions", self.handle_execution_result)
        await self.nats.subscribe("human.approvals.responses", self.handle_human_decision)

        # Timeout checker runs every 30s
        asyncio.create_task(self.check_timeouts())

        # Agent health checker
        asyncio.create_task(self.monitor_agent_health())

    async def handle_anomaly(self, msg: AgentMessage):
        """New anomaly detected by an observer."""

        anomaly = Anomaly.from_dict(msg.payload)

        # Check if this anomaly belongs to an existing incident
        existing = await self.incident_store.find_active_for_service(
            anomaly.service, window_minutes=10
        )

        if existing:
            # Add to existing incident
            await existing.add_anomaly(anomaly)
            logger.info(f"Added anomaly to existing incident {existing.id}")
            return

        # Create new incident
        incident = Incident(
            id=str(uuid4()),
            status="detecting",
            primary_anomaly=anomaly,
            created_at=datetime.utcnow(),
            severity=anomaly.severity,
        )
        await self.incident_store.create(incident)

        # Request diagnosis
        await self.nats.publish("agents.diagnoser.requests", AgentMessage(
            correlation_id=incident.id,
            source_agent="orchestrator",
            target_agent="diagnoser",
            message_type="diagnose_request",
            payload={"incident_id": incident.id, "anomaly": anomaly.to_dict()},
        ))

        await incident.transition_to("diagnosing")

    async def handle_diagnosis(self, msg: AgentMessage):
        """Diagnosis complete from diagnoser."""

        incident = await self.incident_store.get(msg.correlation_id)
        diagnosis = Diagnosis.from_dict(msg.payload)
        incident.diagnosis = diagnosis

        if diagnosis.confidence < 60:
            await incident.transition_to("escalated")
            await self.escalate_to_human(incident, reason="Low confidence diagnosis")
            return

        # Request remediation proposal
        await incident.transition_to("proposing_remediation")
        await self.nats.publish("agents.remediator.proposals", AgentMessage(
            correlation_id=incident.id,
            message_type="propose_remediation",
            payload={
                "incident_id": incident.id,
                "diagnosis": diagnosis.to_dict(),
            },
        ))

    async def check_timeouts(self):
        """Periodically check for stuck incidents."""
        while True:
            active_incidents = await self.incident_store.get_active()
            for incident in active_incidents:
                timeout = self.TIMEOUTS.get(incident.status)
                if timeout and incident.state_entered_at + timeout < datetime.utcnow():
                    logger.warning(f"Incident {incident.id} timed out in {incident.status}")
                    await incident.transition_to("escalated")
                    await self.escalate_to_human(
                        incident,
                        reason=f"Timed out in state: {incident.status}"
                    )
            await asyncio.sleep(30)
```

---

### 3.6 Learning Agent

```python
class LearningAgent:
    """
    Post-incident analysis and continuous improvement.
    Stores incidents in a vector DB for RAG-based similarity search.
    """

    async def process_closed_incident(self, incident: Incident):
        """After an incident is closed, extract learnings."""

        # 1. Vectorize the incident for future similarity search
        embedding = await self.embed(incident.to_summary_text())
        await self.vector_db.upsert(
            collection="incidents",
            id=incident.id,
            vector=embedding,
            metadata={
                "root_cause_category": incident.diagnosis.root_cause.category,
                "service": incident.diagnosis.root_cause.service,
                "resolution": incident.resolution_summary,
                "duration_seconds": incident.duration_seconds,
                "auto_resolved": incident.auto_resolved,
                "date": incident.created_at.isoformat(),
            },
            document=incident.to_summary_text(),
        )

        # 2. Update runbook effectiveness scores
        if incident.remediation_results:
            for result in incident.remediation_results:
                await self.runbook_store.update_stats(
                    runbook_id=result.runbook_id,
                    success=result.verification_passed,
                    time_to_resolve=result.time_to_resolve,
                )

        # 3. Detect recurring patterns
        similar = await self.vector_db.query(
            collection="incidents",
            vector=embedding,
            top_k=10,
            filter={"date": {"$gte": (datetime.utcnow() - timedelta(days=30)).isoformat()}},
        )

        if len(similar) >= 3:
            # Same issue happening repeatedly — flag for root cause fix
            await self.alert_recurring_pattern(incident, similar)

        # 4. Generate post-mortem draft
        postmortem = await self.generate_postmortem(incident)
        await self.incident_store.attach_postmortem(incident.id, postmortem)

    async def find_similar_incidents(
        self, anomaly: Anomaly, top_k: int = 5
    ) -> List[HistoricalIncident]:
        """Find past incidents similar to the current anomaly."""
        query_text = (
            f"Service: {anomaly.service}, "
            f"Metric: {anomaly.metric}, "
            f"Severity: {anomaly.severity}, "
            f"Category: {anomaly.category}"
        )
        embedding = await self.embed(query_text)
        results = await self.vector_db.query(
            collection="incidents",
            vector=embedding,
            top_k=top_k,
        )
        return [HistoricalIncident.from_vector_result(r) for r in results]
```

---

## 4. Chaos Engineering — Failure Injection Scenarios

```python
class ChaosEngine:
    """
    Intentionally inject failures to test the agent swarm.
    Each scenario maps to real-world production incidents.
    """

    SCENARIOS = {
        # --- Resource Exhaustion ---
        "memory_leak": {
            "description": "Simulate memory leak in Order Service",
            "target": "order-svc",
            "injection": "stress-ng --vm 1 --vm-bytes 80% --vm-hang 0",
            "expected_detection": "memory_usage metric > 90%",
            "expected_diagnosis": "memory_leak in order-svc",
            "expected_remediation": "restart_container + scale_up",
        },
        "cpu_spike": {
            "description": "CPU saturation in Payment Service",
            "target": "payment-svc",
            "injection": "stress-ng --cpu 4 --timeout 300",
            "expected_detection": "cpu_usage > 95%",
            "expected_diagnosis": "cpu_saturation in payment-svc",
        },
        "disk_fill": {
            "description": "Fill disk on Analytics Worker",
            "target": "analytics-worker",
            "injection": "dd if=/dev/zero of=/tmp/fillfile bs=1M count=900",
            "expected_detection": "disk_usage > 90%",
        },

        # --- Network Failures ---
        "network_partition_db": {
            "description": "Network partition between Order Service and PostgreSQL",
            "target": "order-svc",
            "injection": "iptables -A OUTPUT -d postgres-orders -j DROP",
            "cleanup": "iptables -D OUTPUT -d postgres-orders -j DROP",
            "expected_detection": "connection refused in logs + error_rate spike",
            "expected_diagnosis": "database_connectivity failure",
        },
        "network_latency": {
            "description": "Add 500ms latency to Redis",
            "target": "redis",
            "injection": "tc qdisc add dev eth0 root netem delay 500ms",
            "cleanup": "tc qdisc del dev eth0 root netem",
            "expected_detection": "latency_p99 spike in auth-svc and user-svc",
        },

        # --- Dependency Failures ---
        "redis_crash": {
            "description": "Redis OOM crash",
            "target": "redis",
            "injection": "docker stop redis",
            "cleanup": "docker start redis",
            "expected_detection": "health check failure + ECONNREFUSED in logs",
            "expected_diagnosis": "dependency_failure: redis down → auth-svc + user-svc affected",
        },
        "elasticsearch_crash": {
            "description": "Elasticsearch cluster goes red",
            "target": "elasticsearch",
            "injection": "curl -X PUT 'localhost:9200/_cluster/settings' -d '{\"transient\":{\"cluster.routing.allocation.enable\":\"none\"}}'",
            "expected_detection": "es_cluster_health red + search-svc errors",
        },
        "nats_slow_consumer": {
            "description": "NATS slow consumer — notification worker can't keep up",
            "target": "notification-worker",
            "injection": "Add 2s sleep to message handler",
            "expected_detection": "nats_consumer_lag increasing",
        },

        # --- Cascading Failures ---
        "cascade_from_postgres": {
            "description": "PostgreSQL overload causes cascade through order-svc to payment-svc",
            "target": "postgres-orders",
            "injection": "pgbench -c 200 -j 20 -T 300 orders",
            "expected_detection": "pg_active_connections + order-svc errors + payment-svc timeouts",
            "expected_diagnosis": "cascading failure rooted at postgres-orders",
        },

        # --- Application-Level Failures ---
        "deployment_regression": {
            "description": "Deploy a broken version of User Service",
            "target": "user-svc",
            "injection": "Deploy user-svc:v2-broken (returns 500 for /health after 30s)",
            "expected_detection": "error_rate spike + health check failure",
            "expected_remediation": "rollback_deployment to previous version",
        },
        "connection_pool_exhaustion": {
            "description": "Order Service connection pool leaks",
            "target": "order-svc",
            "injection": "Open connections without releasing (connection leak simulation)",
            "expected_detection": "pg_active_connections at limit + order-svc timeouts",
        },
        "deadlock": {
            "description": "Database deadlock in Payment Service",
            "target": "postgres-payments",
            "injection": "Two concurrent transactions locking same rows in opposite order",
            "expected_detection": "pg_locks not granted + payment-svc latency spike",
        },
    }

    async def run_scenario(self, scenario_name: str) -> ChaosResult:
        scenario = self.SCENARIOS[scenario_name]
        logger.info(f"🔥 Injecting chaos: {scenario['description']}")

        # Record start state
        start_metrics = await self.capture_metrics()

        # Inject failure
        await self.inject(scenario)

        # Wait for agent swarm to detect and respond
        detection_time = await self.wait_for_detection(timeout=120)
        diagnosis_time = await self.wait_for_diagnosis(timeout=300)
        remediation_time = await self.wait_for_remediation(timeout=600)

        # Cleanup
        if "cleanup" in scenario:
            await self.cleanup(scenario)

        return ChaosResult(
            scenario=scenario_name,
            detection_latency=detection_time,
            diagnosis_latency=diagnosis_time,
            remediation_latency=remediation_time,
            total_mttr=detection_time + diagnosis_time + remediation_time,
            correct_diagnosis=self.validate_diagnosis(scenario),
            successful_remediation=self.validate_remediation(scenario),
        )
```

---

## 5. Data Models — Database Schema

```sql
-- Incident Store (PostgreSQL)

CREATE TABLE incidents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    status          VARCHAR(50) NOT NULL DEFAULT 'detecting',
    severity        VARCHAR(20) NOT NULL,  -- critical, warning, info
    primary_service VARCHAR(100),
    title           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at     TIMESTAMPTZ,
    state_entered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    auto_resolved   BOOLEAN DEFAULT FALSE,
    escalated       BOOLEAN DEFAULT FALSE,
    duration_seconds INTEGER GENERATED ALWAYS AS (
        EXTRACT(EPOCH FROM (COALESCE(resolved_at, NOW()) - created_at))
    ) STORED
);

CREATE INDEX idx_incidents_status ON incidents(status) WHERE status NOT IN ('closed', 'dismissed');
CREATE INDEX idx_incidents_service ON incidents(primary_service, created_at DESC);

CREATE TABLE incident_anomalies (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id     UUID NOT NULL REFERENCES incidents(id),
    metric          VARCHAR(100) NOT NULL,
    service         VARCHAR(100) NOT NULL,
    severity        VARCHAR(20) NOT NULL,
    value           DOUBLE PRECISION,
    threshold       DOUBLE PRECISION,
    z_score         DOUBLE PRECISION,
    category        VARCHAR(50),
    raw_data        JSONB,
    detected_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_anomalies_incident ON incident_anomalies(incident_id);
CREATE INDEX idx_anomalies_service_time ON incident_anomalies(service, detected_at DESC);

CREATE TABLE incident_diagnoses (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id       UUID NOT NULL REFERENCES incidents(id),
    root_cause_service VARCHAR(100),
    root_cause_category VARCHAR(50),
    root_cause_description TEXT,
    confidence        INTEGER CHECK (confidence BETWEEN 0 AND 100),
    causal_chain      JSONB,
    evidence          JSONB,
    missing_info      JSONB,
    similar_incidents JSONB,
    llm_raw_response  JSONB,
    diagnosed_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE incident_remediations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id     UUID NOT NULL REFERENCES incidents(id),
    runbook_id      VARCHAR(100),
    action_type     VARCHAR(50) NOT NULL,
    action_params   JSONB NOT NULL,
    risk_level      VARCHAR(20),
    trust_level     VARCHAR(30),
    safety_approved BOOLEAN,
    human_approved  BOOLEAN,
    approved_by     VARCHAR(100),
    pre_state       JSONB,
    execution_result JSONB,
    success         BOOLEAN,
    error_message   TEXT,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    rolled_back     BOOLEAN DEFAULT FALSE,
    rolled_back_at  TIMESTAMPTZ
);

CREATE INDEX idx_remediations_incident ON incident_remediations(incident_id);

CREATE TABLE incident_verifications (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id     UUID NOT NULL REFERENCES incidents(id),
    remediation_id  UUID REFERENCES incident_remediations(id),
    check_type      VARCHAR(50),
    check_name      TEXT,
    passed          BOOLEAN NOT NULL,
    actual_value    TEXT,
    expected_value  TEXT,
    verified_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE incident_timeline (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id     UUID NOT NULL REFERENCES incidents(id),
    event_type      VARCHAR(50) NOT NULL,
    agent           VARCHAR(50) NOT NULL,
    description     TEXT NOT NULL,
    metadata        JSONB,
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_timeline_incident ON incident_timeline(incident_id, timestamp);

CREATE TABLE incident_postmortems (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id     UUID NOT NULL REFERENCES incidents(id),
    summary         TEXT,
    root_cause      TEXT,
    impact          TEXT,
    timeline_summary TEXT,
    action_items    JSONB,
    generated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Runbook Stats (for learning agent)
CREATE TABLE runbook_stats (
    runbook_id      VARCHAR(100) PRIMARY KEY,
    total_executions INTEGER DEFAULT 0,
    successful       INTEGER DEFAULT 0,
    failed           INTEGER DEFAULT 0,
    avg_time_to_resolve DOUBLE PRECISION,
    last_executed    TIMESTAMPTZ,
    effectiveness_score DOUBLE PRECISION GENERATED ALWAYS AS (
        CASE WHEN total_executions > 0
            THEN successful::DOUBLE PRECISION / total_executions
            ELSE 0
        END
    ) STORED
);

-- Agent Health
CREATE TABLE agent_heartbeats (
    agent_id        VARCHAR(100) NOT NULL,
    agent_type      VARCHAR(50) NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'healthy',
    last_heartbeat  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata        JSONB,
    PRIMARY KEY (agent_id)
);
```

---

## 6. Project Directory Structure

```
self-healing-agent-swarm/
├── docker-compose.yml                   # Full environment
├── docker-compose.agents.yml            # Agent system only
├── docker-compose.observability.yml     # Prometheus, Grafana, Loki
├── Makefile                             # Build, run, test commands
├── README.md
│
├── infrastructure/                      # Target microservices
│   ├── api-gateway/
│   │   ├── Dockerfile
│   │   ├── nginx.conf
│   │   └── kong.yml
│   ├── user-service/                    # FastAPI (Python)
│   │   ├── Dockerfile
│   │   ├── app/
│   │   │   ├── main.py
│   │   │   ├── routes/
│   │   │   ├── models/
│   │   │   └── health.py               # /health endpoint
│   │   └── requirements.txt
│   ├── auth-service/                    # Express (Node.js)
│   │   ├── Dockerfile
│   │   ├── src/
│   │   │   ├── index.ts
│   │   │   ├── routes/
│   │   │   └── middleware/
│   │   └── package.json
│   ├── order-service/                   # Gin (Go)
│   │   ├── Dockerfile
│   │   ├── cmd/server/main.go
│   │   ├── internal/
│   │   │   ├── handlers/
│   │   │   ├── models/
│   │   │   └── repository/
│   │   └── go.mod
│   ├── payment-service/                 # FastAPI (Python)
│   ├── product-service/                 # Django (Python)
│   ├── search-service/                  # FastAPI (Python)
│   ├── notification-worker/             # Python
│   ├── inventory-worker/                # Go
│   └── analytics-worker/               # Python
│
├── agents/                              # Agent system
│   ├── common/
│   │   ├── __init__.py
│   │   ├── message.py                   # AgentMessage schema
│   │   ├── nats_client.py              # NATS JetStream wrapper
│   │   ├── models.py                    # Shared data models
│   │   ├── config.py                    # Configuration management
│   │   └── logging.py                   # Structured logging
│   │
│   ├── observer/
│   │   ├── __init__.py
│   │   ├── metrics_observer.py
│   │   ├── log_observer.py
│   │   ├── health_observer.py
│   │   ├── synthetic_prober.py
│   │   ├── anomaly_detector.py
│   │   ├── alert_deduplicator.py
│   │   └── probes/
│   │       ├── order_flow.py
│   │       ├── payment_flow.py
│   │       └── search_flow.py
│   │
│   ├── diagnoser/
│   │   ├── __init__.py
│   │   ├── diagnoser_agent.py
│   │   ├── context_collector.py
│   │   ├── correlation_engine.py
│   │   ├── rca_engine.py
│   │   ├── dependency_graph.py
│   │   └── toolkit/
│   │       ├── prometheus_tools.py
│   │       ├── loki_tools.py
│   │       ├── docker_tools.py
│   │       ├── postgres_tools.py
│   │       ├── redis_tools.py
│   │       ├── elasticsearch_tools.py
│   │       └── nats_tools.py
│   │
│   ├── remediator/
│   │   ├── __init__.py
│   │   ├── remediator_agent.py
│   │   ├── runbook_engine.py
│   │   ├── action_planner.py
│   │   ├── verification_engine.py
│   │   ├── rollback_manager.py
│   │   └── executors/
│   │       ├── base.py
│   │       ├── docker_executor.py
│   │       ├── sql_executor.py
│   │       ├── config_executor.py
│   │       ├── circuit_breaker_executor.py
│   │       └── cache_executor.py
│   │
│   ├── safety/
│   │   ├── __init__.py
│   │   ├── safety_agent.py
│   │   ├── policy_engine.py
│   │   ├── blast_radius_calculator.py
│   │   ├── rate_limiter.py
│   │   └── human_approval_gateway.py
│   │
│   ├── orchestrator/
│   │   ├── __init__.py
│   │   ├── orchestrator_agent.py
│   │   ├── incident_state_machine.py
│   │   ├── agent_router.py
│   │   ├── escalation_manager.py
│   │   └── timeout_checker.py
│   │
│   └── learning/
│       ├── __init__.py
│       ├── learning_agent.py
│       ├── incident_vectorizer.py
│       ├── pattern_recognizer.py
│       ├── runbook_optimizer.py
│       └── postmortem_generator.py
│
├── runbooks/                            # YAML runbook definitions
│   ├── memory_leak.yml
│   ├── cpu_saturation.yml
│   ├── disk_exhaustion.yml
│   ├── network_partition.yml
│   ├── database_overload.yml
│   ├── connection_pool_exhaustion.yml
│   ├── deadlock.yml
│   ├── deployment_regression.yml
│   ├── cascading_failure.yml
│   ├── redis_memory_full.yml
│   ├── elasticsearch_cluster_red.yml
│   ├── nats_slow_consumer.yml
│   └── container_crash_loop.yml
│
├── chaos/                               # Chaos engineering
│   ├── engine.py
│   ├── scenarios/
│   │   ├── memory_leak.py
│   │   ├── cpu_spike.py
│   │   ├── network_partition.py
│   │   ├── redis_crash.py
│   │   ├── cascade_postgres.py
│   │   └── deployment_regression.py
│   └── evaluator.py                     # Score agent performance
│
├── dashboard/                           # Monitoring dashboard
│   ├── backend/
│   │   ├── main.py                      # FastAPI
│   │   ├── routes/
│   │   │   ├── incidents.py
│   │   │   ├── agents.py
│   │   │   ├── approvals.py
│   │   │   └── chaos.py
│   │   └── websocket.py                 # Real-time updates
│   └── frontend/
│       ├── src/
│       │   ├── App.tsx
│       │   ├── components/
│       │   │   ├── IncidentTimeline.tsx
│       │   │   ├── AgentStatusPanel.tsx
│       │   │   ├── ServiceDependencyGraph.tsx
│       │   │   ├── ApprovalModal.tsx
│       │   │   ├── ChaosControls.tsx
│       │   │   └── MetricsDashboard.tsx
│       │   └── hooks/
│       └── package.json
│
├── config/
│   ├── prometheus.yml
│   ├── alertmanager.yml
│   ├── grafana/
│   │   └── dashboards/
│   ├── loki-config.yml
│   ├── dependency_graph.yml
│   └── agent_config.yml
│
├── migrations/                          # DB migrations
│   ├── 001_create_incidents.sql
│   ├── 002_create_anomalies.sql
│   ├── 003_create_diagnoses.sql
│   ├── 004_create_remediations.sql
│   └── 005_create_agent_health.sql
│
├── tests/
│   ├── unit/
│   │   ├── test_anomaly_detector.py
│   │   ├── test_correlation_engine.py
│   │   ├── test_safety_policies.py
│   │   ├── test_runbook_engine.py
│   │   └── test_state_machine.py
│   ├── integration/
│   │   ├── test_observer_to_diagnoser.py
│   │   ├── test_full_incident_lifecycle.py
│   │   └── test_human_approval_flow.py
│   └── chaos/
│       ├── test_memory_leak_scenario.py
│       ├── test_cascade_scenario.py
│       └── test_all_scenarios.py
│
└── scripts/
    ├── setup.sh                         # Bootstrap everything
    ├── seed_data.sh                     # Seed test data
    ├── run_chaos.sh                     # Run chaos scenarios
    └── generate_load.sh                 # Traffic generation
```

---

## 7. Key Configuration Files

### 7.1 Dependency Graph (YAML)

```yaml
# config/dependency_graph.yml
services:
  api-gateway:
    type: gateway
    user_facing: true
    depends_on:
      - {service: user-svc, protocol: http, critical: true}
      - {service: order-svc, protocol: http, critical: true}
      - {service: product-svc, protocol: http, critical: true}
      - {service: auth-svc, protocol: http, critical: true}
      - {service: search-svc, protocol: http, critical: false}

  user-svc:
    type: application
    user_facing: false
    replicas: 2
    depends_on:
      - {service: redis, protocol: tcp, critical: true, purpose: sessions}

  auth-svc:
    type: application
    user_facing: false
    depends_on:
      - {service: redis, protocol: tcp, critical: true, purpose: tokens}
      - {service: user-svc, protocol: http, critical: true}

  order-svc:
    type: application
    user_facing: false
    replicas: 3
    depends_on:
      - {service: postgres-orders, protocol: tcp, critical: true}
      - {service: nats, protocol: tcp, critical: true}
      - {service: payment-svc, protocol: grpc, critical: true}
      - {service: inventory-worker, protocol: grpc, critical: false}

  payment-svc:
    type: application
    user_facing: false
    depends_on:
      - {service: postgres-payments, protocol: tcp, critical: true}
      - {service: nats, protocol: tcp, critical: true}

  product-svc:
    type: application
    user_facing: false
    depends_on:
      - {service: elasticsearch, protocol: http, critical: true}

  search-svc:
    type: application
    user_facing: false
    depends_on:
      - {service: elasticsearch, protocol: http, critical: true}

  notification-worker:
    type: worker
    user_facing: false
    replicas: 2
    depends_on:
      - {service: nats, protocol: tcp, critical: true}

  inventory-worker:
    type: worker
    user_facing: false
    depends_on:
      - {service: nats, protocol: tcp, critical: true}
      - {service: postgres-orders, protocol: tcp, critical: true}

  analytics-worker:
    type: worker
    user_facing: false
    depends_on:
      - {service: nats, protocol: tcp, critical: true}

  # --- Infrastructure ---
  redis:
    type: datastore
    technology: redis
    max_memory: 256M

  postgres-orders:
    type: datastore
    technology: postgresql
    max_connections: 100

  postgres-payments:
    type: datastore
    technology: postgresql
    max_connections: 50

  elasticsearch:
    type: datastore
    technology: elasticsearch

  nats:
    type: messaging
    technology: nats-jetstream
```

### 7.2 Agent Configuration

```yaml
# config/agent_config.yml
agents:
  observer:
    metrics:
      poll_interval_seconds: 15
      anomaly_window_size: 60
      dedup_window_seconds: 300

    logs:
      loki_url: "http://loki:3100"
      tail_delay_seconds: 1

    health:
      check_interval_seconds: 30
      timeout_seconds: 5
      consecutive_failures_threshold: 3

    synthetic:
      probe_interval_seconds: 60
      probes: ["order_flow", "payment_flow", "search_relevance"]

  diagnoser:
    llm:
      model: "claude-sonnet-4-20250514"
      max_tokens: 4096
      temperature: 0.1
    context_window_minutes: 5
    max_log_lines: 200
    similar_incidents_count: 5

  remediator:
    max_concurrent_actions: 3
    action_timeout_seconds: 120
    verification_wait_seconds: 60

  safety:
    auto_approve_risk_levels: ["low"]
    human_approval_timeout_seconds: 900
    max_concurrent_remediations: 3
    blast_radius_limit: 0.5
    min_diagnosis_confidence: 60

  orchestrator:
    timeout_check_interval_seconds: 30
    incident_dedup_window_minutes: 10

  learning:
    vector_db: "chromadb"
    embedding_model: "text-embedding-3-small"
    recurring_pattern_threshold: 3
    recurring_pattern_window_days: 30

nats:
  url: "nats://nats:4222"
  stream_name: "AGENTS"
  max_deliver: 3
  ack_wait_seconds: 30

database:
  url: "postgresql://agents:password@postgres-agents:5432/agents"
  pool_size: 20
```

---

## 8. Dashboard Wireframe

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  🛡️ Self-Healing Agent Swarm Dashboard                     [Chaos] [Config] │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─ Active Incidents ──────────────────────────────────────────────────────┐ │
│  │ 🔴 INC-0042  order-svc  CPU Saturation     DIAGNOSING    2m ago       │ │
│  │ 🟡 INC-0041  redis      Memory at 82%      RESOLVED      15m ago     │ │
│  │ 🟢 INC-0040  nats       Slow consumer      CLOSED        1h ago      │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌─ Agent Status ──────────────┐  ┌─ Service Dependency Graph ───────────┐  │
│  │ ✅ Observer (Metrics)  OK   │  │                                       │  │
│  │ ✅ Observer (Logs)     OK   │  │    [API GW] ──→ [Order] ──→ [PG]    │  │
│  │ ✅ Observer (Health)   OK   │  │       │           │ 🔴                │  │
│  │ ✅ Diagnoser           OK   │  │       ├──→ [User] ──→ [Redis]       │  │
│  │ ✅ Remediator          OK   │  │       │                              │  │
│  │ ✅ Safety              OK   │  │       └──→ [Product] ──→ [ES]       │  │
│  │ ✅ Orchestrator        OK   │  │                                       │  │
│  │ ✅ Learning            OK   │  │  (🔴 = anomaly detected)             │  │
│  └─────────────────────────────┘  └───────────────────────────────────────┘  │
│                                                                              │
│  ┌─ Incident INC-0042 Timeline ────────────────────────────────────────────┐ │
│  │ 14:32:15  [Observer]      CPU at 97% on order-svc (z=3.2)             │ │
│  │ 14:32:16  [Orchestrator]  Incident created, requesting diagnosis       │ │
│  │ 14:32:18  [Diagnoser]     Collecting context: logs, metrics, deps...   │ │
│  │ 14:32:25  [Diagnoser]     Correlation: payment-svc timeout co-occur    │ │
│  │ 14:32:45  [Diagnoser]     RCA: CPU spike from runaway goroutine        │ │
│  │           [Diagnoser]     Confidence: 78% | Category: cpu_saturation   │ │
│  │ 14:32:46  [Remediator]    Proposing: restart + scale up                │ │
│  │ 14:32:47  [Safety]        ✅ Auto-approved (low risk)                  │ │
│  │ 14:32:48  [Remediator]    Executing restart on order-svc-1...          │ │
│  │ 14:33:50  [Remediator]    ⏳ Waiting 60s for verification...           │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌─ Pending Approvals ─────────────────────────────────────────────────────┐ │
│  │ (none)                                                                  │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌─ Chaos Controls ────────────────────────────────────────────────────────┐ │
│  │ [Memory Leak] [CPU Spike] [Redis Crash] [DB Overload] [Cascade] [...]  │ │
│  │                                                                         │ │
│  │ Last chaos run: cascade_from_postgres | MTTR: 4m 23s | Score: 87%     │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 9. Metrics & Success Criteria

| Metric | Target | How Measured |
|--------|--------|-------------|
| Mean Time to Detect (MTTD) | < 30 seconds | Time from failure injection to first anomaly alert |
| Mean Time to Diagnose | < 2 minutes | Time from alert to root cause hypothesis |
| Mean Time to Remediate (MTTR) | < 5 minutes | Time from alert to verified fix |
| Diagnosis Accuracy | > 80% | Correct root cause vs. injected failure |
| False Positive Rate | < 10% | Anomalies that don't correspond to real issues |
| Auto-Resolution Rate | > 60% | Incidents resolved without human intervention |
| Remediation Success Rate | > 85% | Fixes that pass verification on first attempt |
| Cascade Detection Rate | 100% | All injected cascading failures identified |
| Safety Gate Accuracy | 100% | No dangerous actions executed without approval |

---

## 10. Implementation Priority

| Phase | What to Build | Complexity |
|-------|--------------|------------|
| **P0** | Docker Compose for 4-5 services + Prometheus + Loki | Medium |
| **P0** | Agent message bus (NATS) + message envelope schema | Low |
| **P0** | Metrics Observer with basic anomaly detection | Medium |
| **P0** | Orchestrator with incident state machine | High |
| **P1** | Log Observer + Health Observer | Medium |
| **P1** | Diagnoser with context collection + LLM RCA | High |
| **P1** | Remediator with 3-4 basic runbooks | Medium |
| **P1** | Safety Agent with policy engine | Medium |
| **P2** | Synthetic Prober | Medium |
| **P2** | Correlation Engine + cascade detection | High |
| **P2** | Dashboard (FastAPI + React) | Medium |
| **P2** | Human approval flow | Medium |
| **P3** | Learning Agent + vector DB | High |
| **P3** | Chaos Engine with 10+ scenarios | Medium |
| **P3** | Post-mortem generation | Low |
| **P3** | Runbook optimizer | High |