import React, { useState } from 'react'
import type { Approval } from '../types'

interface Props {
  approvals: Approval[]
  onApprove: (incidentId: string) => void
  onReject: (incidentId: string, reason: string) => void
}

export function ApprovalBar({ approvals, onApprove, onReject }: Props) {
  const [collapsed, setCollapsed] = useState(false)
  const [rejectId, setRejectId] = useState<string | null>(null)
  const [rejectReason, setRejectReason] = useState('')

  if (approvals.length === 0) return null

  return (
    <div style={styles.container}>
      <div style={styles.header} onClick={() => setCollapsed(!collapsed)}>
        <span>Pending Approvals ({approvals.length})</span>
        <span>{collapsed ? '+' : '-'}</span>
      </div>
      {!collapsed && (
        <div style={styles.list}>
          {approvals.map((a) => (
            <div key={a.id} style={styles.card}>
              <div style={styles.info}>
                <span style={styles.incId}>INC-{a.incident_id.slice(0, 8)}</span>
                <span style={styles.action}>{a.action_type || 'Action pending'}</span>
                {a.reason && <span style={styles.reason}>{a.reason}</span>}
              </div>
              <div style={styles.buttons}>
                {rejectId === a.id ? (
                  <div style={styles.rejectForm}>
                    <input
                      style={styles.input}
                      placeholder="Rejection reason..."
                      value={rejectReason}
                      onChange={(e) => setRejectReason(e.target.value)}
                    />
                    <button
                      style={{ ...styles.btn, background: '#e74c3c' }}
                      onClick={() => {
                        onReject(a.incident_id, rejectReason)
                        setRejectId(null)
                        setRejectReason('')
                      }}
                    >
                      Confirm Reject
                    </button>
                    <button
                      style={{ ...styles.btn, background: '#555' }}
                      onClick={() => setRejectId(null)}
                    >
                      Cancel
                    </button>
                  </div>
                ) : (
                  <>
                    <button
                      style={{ ...styles.btn, background: '#2ecc71' }}
                      onClick={() => onApprove(a.incident_id)}
                    >
                      Approve
                    </button>
                    <button
                      style={{ ...styles.btn, background: '#e74c3c' }}
                      onClick={() => setRejectId(a.id)}
                    >
                      Reject
                    </button>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    borderTop: '2px solid #e67e22',
    background: '#1a1a2e',
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    padding: '8px 16px',
    cursor: 'pointer',
    color: '#e67e22',
    fontWeight: 'bold',
    fontSize: '13px',
  },
  list: {
    maxHeight: '200px',
    overflowY: 'auto',
  },
  card: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '8px 16px',
    borderBottom: '1px solid #2a2a3e',
  },
  info: {
    display: 'flex',
    gap: '12px',
    alignItems: 'center',
  },
  incId: {
    fontFamily: 'monospace',
    color: '#ddd',
    fontSize: '13px',
  },
  action: {
    color: '#aaa',
    fontSize: '12px',
  },
  reason: {
    color: '#888',
    fontSize: '11px',
    fontStyle: 'italic',
  },
  buttons: {
    display: 'flex',
    gap: '8px',
  },
  btn: {
    border: 'none',
    padding: '4px 12px',
    borderRadius: '3px',
    color: '#fff',
    fontSize: '12px',
    cursor: 'pointer',
    fontWeight: 'bold',
  },
  rejectForm: {
    display: 'flex',
    gap: '8px',
    alignItems: 'center',
  },
  input: {
    background: '#2a2a3e',
    border: '1px solid #444',
    color: '#ddd',
    padding: '4px 8px',
    borderRadius: '3px',
    fontSize: '12px',
    width: '180px',
  },
}
