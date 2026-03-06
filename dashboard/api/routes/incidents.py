"""Incident REST endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db.models import Incident

from api.deps import get_db
from api.schemas import IncidentDetail, IncidentStats, IncidentSummary, TimelineEvent

router = APIRouter(tags=["incidents"])


@router.get("/incidents", response_model=list[IncidentSummary])
async def list_incidents(
    status: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List incidents with optional filters."""
    query = select(Incident).order_by(Incident.created_at.desc())
    if status:
        query = query.where(Incident.status == status)
    if severity:
        query = query.where(Incident.severity == severity)
    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    incidents = result.scalars().all()
    return [
        IncidentSummary(
            id=inc.id,
            status=inc.status,
            severity=inc.severity,
            created_at=inc.created_at,
            updated_at=inc.updated_at,
            root_cause_category=inc.root_cause_category,
            root_cause_service=inc.root_cause_service,
            auto_resolved=inc.auto_resolved,
            duration_seconds=inc.duration_seconds,
        )
        for inc in incidents
    ]


@router.get("/incidents/stats", response_model=IncidentStats)
async def incident_stats(db: AsyncSession = Depends(get_db)):
    """Aggregate incident statistics."""
    # Total count
    total_result = await db.execute(select(func.count(Incident.id)))
    total = total_result.scalar() or 0

    # By status
    status_result = await db.execute(
        select(Incident.status, func.count(Incident.id)).group_by(Incident.status)
    )
    by_status = {row[0]: row[1] for row in status_result.all()}

    # By severity
    severity_result = await db.execute(
        select(Incident.severity, func.count(Incident.id)).group_by(Incident.severity)
    )
    by_severity = {row[0]: row[1] for row in severity_result.all()}

    # Resolved today
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    resolved_result = await db.execute(
        select(func.count(Incident.id)).where(
            Incident.resolved_at >= today_start,
        )
    )
    resolved_today = resolved_result.scalar() or 0

    # Avg MTTR (Mean Time To Resolve) — for resolved incidents
    mttr_result = await db.execute(
        select(
            func.avg(
                func.extract("epoch", Incident.resolved_at) - func.extract("epoch", Incident.created_at)
            )
        ).where(Incident.resolved_at.isnot(None))
    )
    avg_mttr = mttr_result.scalar()

    return IncidentStats(
        total=total,
        by_status=by_status,
        by_severity=by_severity,
        resolved_today=resolved_today,
        avg_mttr_seconds=float(avg_mttr) if avg_mttr else None,
    )


@router.get("/incidents/{incident_id}", response_model=IncidentDetail)
async def get_incident(incident_id: str, db: AsyncSession = Depends(get_db)):
    """Get full incident details with timeline."""
    result = await db.execute(select(Incident).where(Incident.id == incident_id))
    incident = result.scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    timeline_events = None
    if incident.timeline:
        timeline_events = [TimelineEvent(**e) for e in incident.timeline]

    return IncidentDetail(
        id=incident.id,
        status=incident.status,
        severity=incident.severity,
        created_at=incident.created_at,
        updated_at=incident.updated_at,
        state_entered_at=incident.state_entered_at,
        resolved_at=incident.resolved_at,
        closed_at=incident.closed_at,
        diagnosis=incident.diagnosis,
        diagnosis_confidence=incident.diagnosis_confidence,
        root_cause_category=incident.root_cause_category,
        root_cause_service=incident.root_cause_service,
        runbook_id=incident.runbook_id,
        remediation_actions=incident.remediation_actions,
        auto_resolved=incident.auto_resolved,
        escalation_reason=incident.escalation_reason,
        resolution_summary=incident.resolution_summary,
        postmortem=incident.postmortem,
        timeline=timeline_events,
        duration_seconds=incident.duration_seconds,
    )


@router.get("/incidents/{incident_id}/timeline", response_model=list[TimelineEvent])
async def get_timeline(incident_id: str, db: AsyncSession = Depends(get_db)):
    """Get the timeline for a specific incident."""
    result = await db.execute(select(Incident).where(Incident.id == incident_id))
    incident = result.scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    if not incident.timeline:
        return []
    return [TimelineEvent(**e) for e in incident.timeline]
