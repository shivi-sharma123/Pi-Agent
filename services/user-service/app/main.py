"""
User Service — FastAPI application.

Provides user CRUD endpoints backed by Redis for session storage.
Prometheus metrics are exposed on /metrics.

Endpoints:
  GET  /health                 → liveness probe
  POST /users                  → create a new user
  GET  /users/{user_id}        → get user profile
  PUT  /users/{user_id}        → update user profile
  DELETE /users/{user_id}      → soft-delete user
"""

from __future__ import annotations

import json
import time
import uuid
from contextlib import asynccontextmanager
from typing import Optional

import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from pydantic import BaseModel, EmailStr, Field

# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class UserCreate(BaseModel):
    email: EmailStr
    name: str = Field(..., min_length=1, max_length=200)
    phone: Optional[str] = None


class UserUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    phone: Optional[str] = None


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    phone: Optional[str]
    created_at: str
    updated_at: str

# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency",
    ["method", "endpoint"],
)

# ---------------------------------------------------------------------------
# Redis connection (module scope, shared across requests)
# ---------------------------------------------------------------------------

_redis: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    if _redis is None:
        raise RuntimeError("Redis not initialised — did startup run?")
    return _redis


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Connect to Redis on startup, disconnect on shutdown."""
    global _redis
    import os
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    _redis = aioredis.from_url(redis_url, decode_responses=True)
    yield
    if _redis:
        await _redis.aclose()


app = FastAPI(
    title="User Service",
    description="User profile management for the SRE Agent Swarm demo",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Middleware — request timing & metrics
# ---------------------------------------------------------------------------

@app.middleware("http")
async def metrics_middleware(request, call_next):
    start = time.monotonic()
    response = await call_next(request)
    elapsed = time.monotonic() - start
    endpoint = request.url.path
    REQUEST_COUNT.labels(
        method=request.method,
        endpoint=endpoint,
        status_code=response.status_code,
    ).inc()
    REQUEST_LATENCY.labels(method=request.method, endpoint=endpoint).observe(elapsed)
    return response


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    """Liveness probe — used by docker-compose healthchecks and HealthObserver."""
    redis_ok = False
    try:
        await get_redis().ping()
        redis_ok = True
    except Exception:
        pass

    status = "healthy" if redis_ok else "degraded"
    return {
        "status": status,
        "service": "user-svc",
        "version": "0.1.0",
        "dependencies": {"redis": "ok" if redis_ok else "down"},
    }


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint — scraped by Prometheus every 15s."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/users", status_code=201, response_model=UserResponse)
async def create_user(payload: UserCreate):
    """Create a new user; store in Redis with a 7-day TTL."""
    r = get_redis()

    # Check for duplicate email
    email_key = f"user:email:{payload.email}"
    if await r.exists(email_key):
        raise HTTPException(status_code=409, detail="User with this email already exists")

    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    user_id = str(uuid.uuid4())
    user = {
        "id": user_id,
        "email": payload.email,
        "name": payload.name,
        "phone": payload.phone or "",
        "created_at": now,
        "updated_at": now,
    }

    user_key = f"user:{user_id}"
    # Store user data
    await r.set(user_key, json.dumps(user))
    # Index email → id
    await r.set(email_key, user_id)

    return UserResponse(**user)


@app.get("/users/{user_id}", response_model=UserResponse)
async def get_user(user_id: str):
    """Retrieve a user by ID."""
    r = get_redis()
    data = await r.get(f"user:{user_id}")
    if not data:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse(**json.loads(data))


@app.put("/users/{user_id}", response_model=UserResponse)
async def update_user(user_id: str, payload: UserUpdate):
    """Update mutable user fields."""
    r = get_redis()
    user_key = f"user:{user_id}"
    data = await r.get(user_key)
    if not data:
        raise HTTPException(status_code=404, detail="User not found")

    user = json.loads(data)
    if payload.name is not None:
        user["name"] = payload.name
    if payload.phone is not None:
        user["phone"] = payload.phone
    user["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    await r.set(user_key, json.dumps(user))
    return UserResponse(**user)


@app.delete("/users/{user_id}", status_code=204)
async def delete_user(user_id: str):
    """Soft-delete: remove from Redis. In a real system this would set a deleted_at flag."""
    r = get_redis()
    user_key = f"user:{user_id}"
    data = await r.get(user_key)
    if not data:
        raise HTTPException(status_code=404, detail="User not found")

    user = json.loads(data)
    # Remove email index
    await r.delete(f"user:email:{user['email']}")
    await r.delete(user_key)
