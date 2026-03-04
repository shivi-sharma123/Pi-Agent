import React from 'react'
import type { IncidentStats } from '../types'

interface Props {
  stats: IncidentStats | null
}

export function StatsBar({ stats }: Props) {
  if (!stats) return null

  const active = (stats.by_status['detecting'] || 0) +
    (stats.by_status['diagnosing'] || 0) +
    (stats.by_status['proposing_remediation'] || 0) +
    (stats.by_status['safety_review'] || 0)
  const executing = stats.by_status['executing'] || 0
  const diagnosing = stats.by_status['diagnosing'] || 0

  return (
    <div style={styles.bar}>
      <Stat label="Active" value={active} color="#e74c3c" />
      <Stat label="Diagnosing" value={diagnosing} color="#f39c12" />
      <Stat label="Executing" value={executing} color="#3498db" />
      <Stat label="Resolved Today" value={stats.resolved_today} color="#2ecc71" />
      {stats.avg_mttr_seconds != null && (
        <Stat label="Avg MTTR" value={`${Math.round(stats.avg_mttr_seconds)}s`} color="#9b59b6" />
      )}
    </div>
  )
}

function Stat({ label, value, color }: { label: string; value: number | string; color: string }) {
  return (
    <div style={{ ...styles.stat, borderLeft: `3px solid ${color}` }}>
      <span style={styles.statValue}>{value}</span>
      <span style={styles.statLabel}>{label}</span>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  bar: {
    display: 'flex',
    gap: '12px',
    padding: '8px 16px',
    background: '#1a1a2e',
    borderBottom: '1px solid #333',
    flexWrap: 'wrap',
  },
  stat: {
    padding: '6px 12px',
    display: 'flex',
    gap: '8px',
    alignItems: 'center',
  },
  statValue: {
    fontWeight: 'bold',
    fontSize: '18px',
    color: '#fff',
  },
  statLabel: {
    color: '#aaa',
    fontSize: '12px',
    textTransform: 'uppercase' as const,
  },
}
