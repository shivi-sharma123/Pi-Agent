"""Pydantic response models for the Dashboard API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class IncidentSummary(BaseModel):
    id: str
    status: str
    severity: str
    created_at: datetime
    updated_at: datetime
    root_cause_category: Optional[str] = None
    root_cause_service: Optional[str] = None
    auto_resolved: bool = False
    duration_seconds: Optional[float] = None


class TimelineEvent(BaseModel):
    event_type: str
    agent: str
    summary: str
    details: dict[str, Any] = {}
    timestamp: str


class IncidentDetail(BaseModel):
    id: str
    status: str
    severity: str
    created_at: datetime
    updated_at: datetime
    state_entered_at: datetime
    resolved_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    diagnosis: Optional[dict] = None
    diagnosis_confidence: Optional[int] = None
    root_cause_category: Optional[str] = None
    root_cause_service: Optional[str] = None
    runbook_id: Optional[str] = None
    remediation_actions: Optional[list] = None
    auto_resolved: bool = False
    escalation_reason: Optional[str] = None
    resolution_summary: Optional[str] = None
    postmortem: Optional[dict] = None
    timeline: Optional[list[TimelineEvent]] = None
    duration_seconds: Optional[float] = None


class IncidentStats(BaseModel):
    total: int = 0
    by_status: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    avg_mttd_seconds: Optional[float] = None
    avg_mttr_seconds: Optional[float] = None
    resolved_today: int = 0


class AgentStatus(BaseModel):
    agent_id: str
    agent_type: str
    hostname: str = ""
    status: str = "unknown"
    last_seen_at: Optional[datetime] = None
    metrics: dict[str, Any] = {}


class ApprovalRequest(BaseModel):
    id: str
    incident_id: str
    action_type: str = ""
    risk_level: str = ""
    blast_radius: dict[str, Any] = {}
    reason: str = ""
    created_at: datetime
    status: str = "pending"


class ApprovalAction(BaseModel):
    reason: str = ""


class HealthResponse(BaseModel):
    status: str
    service: str = "dashboard-api"
    nats_connected: bool = False
    db_connected: bool = False
