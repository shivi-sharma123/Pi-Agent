import React from 'react'
import type { Incident } from '../types'

interface Props {
  incidents: Incident[]
  selectedId: string | null
  onSelect: (id: string) => void
}

const SEVERITY_COLORS: Record<string, string> = {
  critical: '#e74c3c',
  high: '#e67e22',
  medium: '#f1c40f',
  low: '#2ecc71',
}

const STATUS_LABELS: Record<string, string> = {
  detecting: 'DET',
  diagnosing: 'DX',
  proposing_remediation: 'PROP',
  safety_review: 'REV',
  executing: 'EXEC',
  verifying: 'VER',
  resolved: 'OK',
  closed: 'CL',
}

export function IncidentList({ incidents, selectedId, onSelect }: Props) {
  return (
    <div style={styles.container}>
      <div style={styles.header}>Incidents ({incidents.length})</div>
      <div style={styles.list}>
        {incidents.map((inc) => (
          <div
            key={inc.id}
            style={{
              ...styles.card,
              ...(selectedId === inc.id ? styles.selected : {}),
            }}
            onClick={() => onSelect(inc.id)}
          >
            <div style={styles.cardTop}>
              <span
                style={{
                  ...styles.badge,
                  background: SEVERITY_COLORS[inc.severity] || '#666',
                }}
              >
                {inc.severity.toUpperCase()}
              </span>
              <span style={styles.status}>
                {STATUS_LABELS[inc.status] || inc.status}
              </span>
            </div>
            <div style={styles.cardId}>INC-{inc.id.slice(0, 8)}</div>
            <div style={styles.cardMeta}>
              {inc.root_cause_service && (
                <span>{inc.root_cause_service}</span>
              )}
              <span style={styles.time}>
                {new Date(inc.created_at).toLocaleTimeString()}
              </span>
            </div>
          </div>
        ))}
        {incidents.length === 0 && (
          <div style={styles.empty}>No incidents</div>
        )}
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    height: '100%',
    borderRight: '1px solid #333',
  },
  header: {
    padding: '10px 16px',
    fontWeight: 'bold',
    color: '#aaa',
    fontSize: '13px',
    textTransform: 'uppercase',
    borderBottom: '1px solid #333',
  },
  list: {
    flex: 1,
    overflowY: 'auto',
  },
  card: {
    padding: '10px 16px',
    borderBottom: '1px solid #2a2a3e',
    cursor: 'pointer',
  },
  selected: {
    background: '#16213e',
  },
  cardTop: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '4px',
  },
  badge: {
    padding: '2px 6px',
    borderRadius: '3px',
    fontSize: '10px',
    fontWeight: 'bold',
    color: '#fff',
  },
  status: {
    fontSize: '11px',
    color: '#888',
    fontFamily: 'monospace',
  },
  cardId: {
    fontSize: '13px',
    color: '#ddd',
    fontFamily: 'monospace',
  },
  cardMeta: {
    display: 'flex',
    justifyContent: 'space-between',
    fontSize: '11px',
    color: '#666',
    marginTop: '4px',
  },
  time: {
    color: '#555',
  },
  empty: {
    padding: '20px',
    color: '#555',
    textAlign: 'center',
  },
}
