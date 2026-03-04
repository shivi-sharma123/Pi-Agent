"""
Dashboard API — FastAPI application for the SRE Agent Swarm Dashboard.

Serves REST endpoints for incidents, agents, and approvals.
Also hosts the WebSocket endpoint for real-time updates.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.deps import close_nats, dispose_db, get_nats
from api.routes import agents, approvals, health, incidents
from api.websocket.manager import ConnectionManager
from api.websocket.handlers import setup_nats_bridge, ws_endpoint

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

manager = ConnectionManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    logger.info("Dashboard API starting up")
    try:
        nats = await get_nats()
        await setup_nats_bridge(nats, manager)
        logger.info("NATS bridge established")
    except Exception as exc:
        logger.warning("Could not connect to NATS on startup: %s", exc)
    yield
    logger.info("Dashboard API shutting down")
    await close_nats()
    await dispose_db()


app = FastAPI(
    title="SRE Agent Swarm Dashboard",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# REST routes
app.include_router(incidents.router, prefix="/api")
app.include_router(agents.router, prefix="/api")
app.include_router(approvals.router, prefix="/api")
app.include_router(health.router)

# WebSocket endpoint
app.websocket("/ws")(ws_endpoint(manager))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8010, reload=False)
