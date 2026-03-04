"""Agent status REST endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db.models import AgentHeartbeat

from api.deps import get_db
from api.schemas import AgentStatus

router = APIRouter(tags=["agents"])


@router.get("/agents", response_model=list[AgentStatus])
async def list_agents(db: AsyncSession = Depends(get_db)):
    """List all known agents with their health status."""
    result = await db.execute(
        select(AgentHeartbeat).order_by(AgentHeartbeat.agent_type)
    )
    agents = result.scalars().all()
    return [
        AgentStatus(
            agent_id=a.agent_id,
            agent_type=a.agent_type,
            hostname=a.hostname or "",
            status=a.status,
            last_seen_at=a.last_seen_at,
            metrics=a.metrics or {},
        )
        for a in agents
    ]


@router.get("/agents/{agent_id}", response_model=AgentStatus)
async def get_agent(agent_id: str, db: AsyncSession = Depends(get_db)):
    """Get a specific agent's status."""
    result = await db.execute(
        select(AgentHeartbeat).where(AgentHeartbeat.agent_id == agent_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return AgentStatus(
        agent_id=agent.agent_id,
        agent_type=agent.agent_type,
        hostname=agent.hostname or "",
        status=agent.status,
        last_seen_at=agent.last_seen_at,
        metrics=agent.metrics or {},
    )
