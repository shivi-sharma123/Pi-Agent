import React from 'react'
import type { Agent } from '../types'

interface Props {
  agents: Agent[]
}

const STATUS_COLORS: Record<string, string> = {
  healthy: '#2ecc71',
  degraded: '#f39c12',
  dead: '#e74c3c',
  unknown: '#666',
}

export function AgentPool({ agents }: Props) {
  // Group by agent_type for display
  const grouped = agents.reduce<Record<string, Agent[]>>((acc, a) => {
    const type = a.agent_type.replace('agents.', '')
    if (!acc[type]) acc[type] = []
    acc[type].push(a)
    return acc
  }, {})

  return (
    <div style={styles.container}>
      {Object.entries(grouped).map(([type, items]) => {
        const worstStatus = items.some((a) => a.status === 'dead')
          ? 'dead'
          : items.some((a) => a.status === 'degraded')
            ? 'degraded'
            : 'healthy'
        return (
          <div key={type} style={styles.agent}>
            <span
              style={{
                ...styles.dot,
                background: STATUS_COLORS[worstStatus] || '#666',
              }}
            />
            <span style={styles.label}>{type}</span>
            <span style={styles.count}>({items.length})</span>
          </div>
        )
      })}
      {agents.length === 0 && (
        <span style={styles.empty}>No agents reporting</span>
      )}
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    gap: '16px',
    padding: '8px 16px',
    background: '#0f0f23',
    borderTop: '1px solid #333',
    flexWrap: 'wrap',
    alignItems: 'center',
  },
  agent: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
  },
  dot: {
    width: '8px',
    height: '8px',
    borderRadius: '50%',
  },
  label: {
    color: '#aaa',
    fontSize: '12px',
  },
  count: {
    color: '#555',
    fontSize: '11px',
  },
  empty: {
    color: '#555',
    fontSize: '12px',
  },
}
