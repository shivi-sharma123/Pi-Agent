import React from 'react'
import type { TimelineEvent } from '../types'

interface Props {
  events: TimelineEvent[]
}

const EVENT_COLORS: Record<string, string> = {
  anomaly_detected: '#e74c3c',
  diagnosis_started: '#f39c12',
  diagnosis_complete: '#f39c12',
  remediation_proposed: '#3498db',
  safety_approved: '#2ecc71',
  safety_rejected: '#e74c3c',
  action_executed: '#3498db',
  verification_passed: '#2ecc71',
  verification_failed: '#e74c3c',
  escalated: '#e67e22',
  resolved: '#2ecc71',
  closed: '#95a5a6',
}

export function Timeline({ events }: Props) {
  if (!events || events.length === 0) {
    return <div style={styles.empty}>No timeline events</div>
  }

  return (
    <div style={styles.container}>
      <div style={styles.header}>Timeline</div>
      {events.map((event, i) => (
        <div key={i} style={styles.event}>
          <div
            style={{
              ...styles.dot,
              background: EVENT_COLORS[event.event_type] || '#666',
            }}
          />
          <div style={styles.line} />
          <div style={styles.content}>
            <div style={styles.eventType}>{event.event_type}</div>
            <div style={styles.summary}>{event.summary}</div>
            <div style={styles.meta}>
              <span>{event.agent}</span>
              <span>{new Date(event.timestamp).toLocaleTimeString()}</span>
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    padding: '0 16px 16px',
  },
  header: {
    color: '#aaa',
    fontSize: '12px',
    textTransform: 'uppercase',
    fontWeight: 'bold',
    marginBottom: '8px',
  },
  event: {
    display: 'flex',
    position: 'relative',
    paddingBottom: '12px',
  },
  dot: {
    width: '10px',
    height: '10px',
    borderRadius: '50%',
    marginTop: '4px',
    flexShrink: 0,
  },
  line: {
    position: 'absolute',
    left: '4px',
    top: '16px',
    bottom: '0',
    width: '2px',
    background: '#333',
  },
  content: {
    marginLeft: '12px',
    flex: 1,
  },
  eventType: {
    fontSize: '11px',
    color: '#888',
    fontFamily: 'monospace',
    textTransform: 'uppercase',
  },
  summary: {
    fontSize: '13px',
    color: '#ddd',
    marginTop: '2px',
  },
  meta: {
    display: 'flex',
    justifyContent: 'space-between',
    fontSize: '11px',
    color: '#555',
    marginTop: '2px',
  },
  empty: {
    padding: '20px',
    color: '#555',
    textAlign: 'center',
  },
}
