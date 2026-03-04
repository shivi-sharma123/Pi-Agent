"""
TimelineBuilder — pure helper for building incident timelines and postmortems.

No external dependencies. Operates on plain lists/dicts.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

EVENT_TYPES = (
    "anomaly_detected",
    "diagnosis_started",
    "diagnosis_complete",
    "remediation_proposed",
    "safety_approved",
    "safety_rejected",
    "action_executed",
    "verification_passed",
    "verification_failed",
    "escalated",
    "resolved",
    "closed",
)


def add_event(
    timeline: list[dict],
    event_type: str,
    agent: str,
    summary: str,
    details: Optional[dict[str, Any]] = None,
) -> list[dict]:
    """Append a timestamped event to the timeline. Returns the timeline for chaining."""
    timeline.append({
        "event_type": event_type,
        "agent": agent,
        "summary": summary,
        "details": details or {},
        "timestamp": datetime.utcnow().isoformat(),
    })
    return timeline


def generate_postmortem(incident: dict) -> dict:
    """
    Generate a structured postmortem summary from an incident dict.

    Expects incident to have: id, status, severity, created_at, resolved_at, timeline, diagnosis.
    """
    timeline = incident.get("timeline") or []
    created_at = incident.get("created_at")
    resolved_at = incident.get("resolved_at")

    # Duration
    duration_seconds = None
    if created_at and resolved_at:
        try:
            start = _parse_dt(created_at)
            end = _parse_dt(resolved_at)
            duration_seconds = (end - start).total_seconds()
        except (ValueError, TypeError):
            pass

    # Time-in-state breakdown
    state_durations: dict[str, float] = {}
    for i, event in enumerate(timeline):
        if i + 1 < len(timeline):
            try:
                t1 = _parse_dt(event["timestamp"])
                t2 = _parse_dt(timeline[i + 1]["timestamp"])
                state = event.get("event_type", "unknown")
                state_durations[state] = state_durations.get(state, 0) + (t2 - t1).total_seconds()
            except (ValueError, TypeError, KeyError):
                continue

    # Key decisions (safety approvals/rejections)
    key_decisions = [
        e for e in timeline
        if e.get("event_type") in ("safety_approved", "safety_rejected", "escalated")
    ]

    return {
        "incident_id": incident.get("id"),
        "severity": incident.get("severity"),
        "status": incident.get("status"),
        "duration_seconds": duration_seconds,
        "state_durations": state_durations,
        "key_decisions": key_decisions,
        "total_events": len(timeline),
        "root_cause": incident.get("root_cause_category"),
        "root_cause_service": incident.get("root_cause_service"),
        "resolution_summary": incident.get("resolution_summary"),
    }


def _parse_dt(value: Any) -> datetime:
    """Parse a datetime from string or return as-is if already datetime."""
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))
