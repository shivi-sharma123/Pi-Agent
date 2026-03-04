import React, { useState } from 'react'
import { useWebSocket } from './hooks/useWebSocket'
import { useIncidents } from './hooks/useIncidents'
import { useAgents } from './hooks/useAgents'
import { useApprovals } from './hooks/useApprovals'
import { StatsBar } from './components/StatsBar'
import { IncidentList } from './components/IncidentList'
import { IncidentDetail } from './components/IncidentDetail'
import { ApprovalBar } from './components/ApprovalBar'
import { AgentPool } from './components/AgentPool'

const WS_URL = `ws://${window.location.hostname}:${window.location.port || '8010'}/ws`

export default function App() {
  const { connected, subscribe } = useWebSocket(WS_URL)
  const { incidents, stats, loading } = useIncidents(subscribe)
  const { agents } = useAgents(subscribe)
  const { approvals, approve, reject } = useApprovals(subscribe)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  return (
    <div style={styles.app}>
      {/* Header */}
      <div style={styles.header}>
        <span style={styles.title}>SRE Agent Swarm Dashboard</span>
        <span style={{ ...styles.connDot, background: connected ? '#2ecc71' : '#e74c3c' }}>
          {connected ? 'Connected' : 'Disconnected'}
        </span>
      </div>

      {/* Stats */}
      <StatsBar stats={stats} />

      {/* Main content */}
      <div style={styles.main}>
        <div style={styles.sidebar}>
          <IncidentList
            incidents={incidents}
            selectedId={selectedId}
            onSelect={setSelectedId}
          />
        </div>
        <div style={styles.detail}>
          <IncidentDetail incidentId={selectedId} />
        </div>
      </div>

      {/* Approvals */}
      <ApprovalBar approvals={approvals} onApprove={approve} onReject={reject} />

      {/* Agent pool */}
      <AgentPool agents={agents} />
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  app: {
    display: 'flex',
    flexDirection: 'column',
    height: '100vh',
    background: '#0f0f23',
    color: '#ddd',
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace',
    fontSize: '14px',
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '10px 16px',
    background: '#16213e',
    borderBottom: '1px solid #333',
  },
  title: {
    fontWeight: 'bold',
    fontSize: '16px',
    color: '#fff',
  },
  connDot: {
    padding: '4px 10px',
    borderRadius: '12px',
    fontSize: '11px',
    color: '#fff',
  },
  main: {
    display: 'flex',
    flex: 1,
    overflow: 'hidden',
  },
  sidebar: {
    width: '35%',
    minWidth: '280px',
    overflow: 'hidden',
  },
  detail: {
    flex: 1,
    overflow: 'hidden',
  },
}
