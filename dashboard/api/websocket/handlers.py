"""WebSocket handlers — NATS-to-WebSocket bridge and endpoint factory."""

from __future__ import annotations

import logging
from collections.abc import Callable

from fastapi import WebSocket, WebSocketDisconnect

from shared.messaging.nats_client import NATSClient
from shared.messaging.schema import AgentMessage
from shared.messaging.subjects import (
    AGENT_HEARTBEAT,
    HUMAN_APPROVALS,
    INCIDENTS_LIFECYCLE,
)

from api.websocket.manager import ConnectionManager

logger = logging.getLogger(__name__)

# Map NATS message types to WebSocket event types
EVENT_MAP = {
    "incident.created": "incident.created",
    "incident.updated": "incident.updated",
    "incident.resolved": "incident.resolved",
    "heartbeat": "agent.heartbeat",
    "escalation": "approval.requested",
    "human_approval_response": "approval.resolved",
}


async def setup_nats_bridge(nats: NATSClient, manager: ConnectionManager) -> None:
    """Subscribe to NATS subjects and bridge events to WebSocket clients."""

    async def _handle_lifecycle(msg: AgentMessage) -> None:
        event_type = EVENT_MAP.get(msg.message_type, "incident.updated")
        await manager.broadcast(event_type, {
            "incident_id": msg.payload.get("incident_id", msg.correlation_id),
            "message_type": msg.message_type,
            **msg.payload,
        })

    async def _handle_heartbeat(msg: AgentMessage) -> None:
        await manager.broadcast("agent.heartbeat", msg.payload)

    async def _handle_approvals(msg: AgentMessage) -> None:
        event_type = "approval.requested"
        if msg.message_type == "human_approval_response":
            event_type = "approval.resolved"
        await manager.broadcast(event_type, {
            "incident_id": msg.correlation_id,
            **msg.payload,
        })

    await nats.subscribe(
        INCIDENTS_LIFECYCLE,
        handler=_handle_lifecycle,
        durable="dashboard-lifecycle",
    )
    await nats.subscribe(
        AGENT_HEARTBEAT,
        handler=_handle_heartbeat,
        durable="dashboard-heartbeat",
    )
    await nats.subscribe(
        HUMAN_APPROVALS,
        handler=_handle_approvals,
        durable="dashboard-approvals",
    )
    logger.info("NATS-to-WebSocket bridge established")


def ws_endpoint(manager: ConnectionManager) -> Callable:
    """Create a WebSocket endpoint handler."""

    async def websocket_handler(websocket: WebSocket) -> None:
        await manager.connect(websocket)
        try:
            while True:
                # Keep connection alive, handle client messages (ping/pong)
                data = await websocket.receive_text()
                if data == "ping":
                    await websocket.send_text("pong")
        except WebSocketDisconnect:
            manager.disconnect(websocket)
        except Exception:
            manager.disconnect(websocket)

    return websocket_handler
