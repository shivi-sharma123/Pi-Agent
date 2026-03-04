export interface Incident {
  id: string
  status: string
  severity: string
  created_at: string
  updated_at: string
  state_entered_at?: string
  resolved_at?: string | null
  closed_at?: string | null
  diagnosis?: Record<string, unknown> | null
  diagnosis_confidence?: number | null
  root_cause_category?: string | null
  root_cause_service?: string | null
  runbook_id?: string | null
  remediation_actions?: unknown[] | null
  auto_resolved?: boolean
  escalation_reason?: string | null
  resolution_summary?: string | null
  postmortem?: Record<string, unknown> | null
  timeline?: TimelineEvent[] | null
  duration_seconds?: number | null
}

export interface TimelineEvent {
  event_type: string
  agent: string
  summary: string
  details: Record<string, unknown>
  timestamp: string
}

export interface IncidentStats {
  total: number
  by_status: Record<string, number>
  by_severity: Record<string, number>
  avg_mttd_seconds?: number | null
  avg_mttr_seconds?: number | null
  resolved_today: number
}

export interface Agent {
  agent_id: string
  agent_type: string
  hostname: string
  status: string
  last_seen_at?: string | null
  metrics: Record<string, unknown>
}

export interface Approval {
  id: string
  incident_id: string
  action_type: string
  risk_level: string
  blast_radius: Record<string, unknown>
  reason: string
  created_at: string
  status: string
}

export interface WSEvent {
  type: string
  data: Record<string, unknown>
}
