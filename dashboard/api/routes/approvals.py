"""Human approval REST endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db.models import Incident
from shared.messaging.nats_client import build_message
from shared.messaging.subjects import HUMAN_APPROVALS_RESPONSES

from api.deps import get_db, get_nats
from api.schemas import ApprovalAction, ApprovalRequest

router = APIRouter(tags=["approvals"])


@router.get("/approvals", response_model=list[ApprovalRequest])
async def list_pending_approvals(db: AsyncSession = Depends(get_db)):
    """List incidents that are pending human approval (status = safety_review)."""
    result = await db.execute(
        select(Incident)
        .where(Incident.status == "safety_review")
        .order_by(Incident.created_at.desc())
    )
    incidents = result.scalars().all()

    approvals = []
    for inc in incidents:
        # Extract action info from timeline or diagnosis
        action_type = ""
        risk_level = ""
        blast_radius = {}
        reason = inc.escalation_reason or ""

        if inc.remediation_actions:
            last_action = inc.remediation_actions[-1] if inc.remediation_actions else {}
            action_type = last_action.get("action_type", "")

        approvals.append(ApprovalRequest(
            id=inc.id,
            incident_id=inc.id,
            action_type=action_type,
            risk_level=risk_level,
            blast_radius=blast_radius,
            reason=reason,
            created_at=inc.state_entered_at,
            status="pending",
        ))

    return approvals


@router.post("/approvals/{incident_id}/approve")
async def approve_action(
    incident_id: str,
    body: ApprovalAction | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Approve a pending action — publishes to NATS for orchestrator."""
    result = await db.execute(
        select(Incident).where(Incident.id == incident_id)
    )
    incident = result.scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    if incident.status != "safety_review":
        raise HTTPException(status_code=400, detail="Incident is not pending approval")

    nats = await get_nats()
    msg = build_message(
        source_agent="dashboard",
        target_agent="orchestrator",
        message_type="human_approval_response",
        payload={
            "incident_id": incident_id,
            "decision": "approve",
            "reason": body.reason if body else "",
            "approved_by": "operator",
            "approved_at": datetime.utcnow().isoformat(),
        },
        correlation_id=incident_id,
        priority=0,
    )
    await nats.publish(HUMAN_APPROVALS_RESPONSES, msg)

    return {"status": "approved", "incident_id": incident_id}


@router.post("/approvals/{incident_id}/reject")
async def reject_action(
    incident_id: str,
    body: ApprovalAction,
    db: AsyncSession = Depends(get_db),
):
    """Reject a pending action — publishes to NATS for orchestrator."""
    result = await db.execute(
        select(Incident).where(Incident.id == incident_id)
    )
    incident = result.scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    if incident.status != "safety_review":
        raise HTTPException(status_code=400, detail="Incident is not pending approval")

    nats = await get_nats()
    msg = build_message(
        source_agent="dashboard",
        target_agent="orchestrator",
        message_type="human_approval_response",
        payload={
            "incident_id": incident_id,
            "decision": "reject",
            "reason": body.reason,
            "rejected_by": "operator",
            "rejected_at": datetime.utcnow().isoformat(),
        },
        correlation_id=incident_id,
        priority=0,
    )
    await nats.publish(HUMAN_APPROVALS_RESPONSES, msg)

    return {"status": "rejected", "incident_id": incident_id, "reason": body.reason}
