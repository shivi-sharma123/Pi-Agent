import React, { useEffect, useState } from 'react'
import { api } from '../api/client'
import { Timeline } from './Timeline'
import type { Incident } from '../types'

interface Props {
  incidentId: string | null
}

export function IncidentDetail({ incidentId }: Props) {
  const [incident, setIncident] = useState<Incident | null>(null)

  useEffect(() => {
    if (!incidentId) {
      setIncident(null)
      return
    }
    api.getIncident(incidentId).then((data) => setIncident(data as Incident))
  }, [incidentId])

  if (!incidentId) {
    return (
      <div style={styles.empty}>Select an incident to view details</div>
    )
  }

  if (!incident) {
    return <div style={styles.empty}>Loading...</div>
  }

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <span style={styles.title}>INC-{incident.id.slice(0, 8)}</span>
        <span style={{ ...styles.statusBadge, background: statusColor(incident.status) }}>
          {incident.status}
        </span>
      </div>

      <div style={styles.grid}>
        <Field label="Severity" value={incident.severity} />
        <Field label="Service" value={incident.root_cause_service || '-'} />
        <Field label="Root Cause" value={incident.root_cause_category || '-'} />
        <Field label="Confidence" value={incident.diagnosis_confidence != null ? `${incident.diagnosis_confidence}%` : '-'} />
        <Field label="Auto-Resolved" value={incident.auto_resolved ? 'Yes' : 'No'} />
        <Field label="Duration" value={incident.duration_seconds != null ? `${Math.round(incident.duration_seconds)}s` : '-'} />
      </div>

      {incident.resolution_summary && (
        <div style={styles.section}>
          <div style={styles.sectionLabel}>Resolution</div>
          <div style={styles.sectionContent}>{incident.resolution_summary}</div>
        </div>
      )}

      {incident.escalation_reason && (
        <div style={styles.section}>
          <div style={styles.sectionLabel}>Escalation</div>
          <div style={styles.sectionContent}>{incident.escalation_reason}</div>
        </div>
      )}

      <Timeline events={incident.timeline || []} />
    </div>
  )
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div style={styles.field}>
      <div style={styles.fieldLabel}>{label}</div>
      <div style={styles.fieldValue}>{value}</div>
    </div>
  )
}

function statusColor(status: string): string {
  const map: Record<string, string> = {
    detecting: '#e74c3c',
    diagnosing: '#f39c12',
    proposing_remediation: '#f39c12',
    safety_review: '#e67e22',
    executing: '#3498db',
    verifying: '#3498db',
    resolved: '#2ecc71',
    closed: '#95a5a6',
  }
  return map[status] || '#666'
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    height: '100%',
    overflowY: 'auto',
  },
  empty: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    height: '100%',
    color: '#555',
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '12px 16px',
    borderBottom: '1px solid #333',
  },
  title: {
    fontFamily: 'monospace',
    fontSize: '16px',
    color: '#fff',
  },
  statusBadge: {
    padding: '4px 10px',
    borderRadius: '4px',
    fontSize: '12px',
    color: '#fff',
    fontWeight: 'bold',
    textTransform: 'uppercase' as const,
  },
  grid: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr 1fr',
    gap: '1px',
    padding: '12px 16px',
    borderBottom: '1px solid #333',
  },
  field: {
    padding: '4px 0',
  },
  fieldLabel: {
    fontSize: '11px',
    color: '#666',
    textTransform: 'uppercase' as const,
  },
  fieldValue: {
    fontSize: '14px',
    color: '#ddd',
  },
  section: {
    padding: '12px 16px',
    borderBottom: '1px solid #333',
  },
  sectionLabel: {
    fontSize: '11px',
    color: '#666',
    textTransform: 'uppercase' as const,
    marginBottom: '4px',
  },
  sectionContent: {
    fontSize: '13px',
    color: '#ddd',
  },
}
