import { useEffect, useState, useCallback } from 'react'
import { api } from '../api/client'
import type { Approval, WSEvent } from '../types'

export function useApprovals(subscribe: (h: (e: WSEvent) => void) => () => void) {
  const [approvals, setApprovals] = useState<Approval[]>([])

  const fetchApprovals = useCallback(async () => {
    try {
      const data = await api.getApprovals() as Approval[]
      setApprovals(data)
    } catch (err) {
      console.error('Failed to fetch approvals:', err)
    }
  }, [])

  useEffect(() => {
    fetchApprovals()
  }, [fetchApprovals])

  useEffect(() => {
    return subscribe((event: WSEvent) => {
      if (event.type === 'approval.requested' || event.type === 'approval.resolved') {
        fetchApprovals()
      }
    })
  }, [subscribe, fetchApprovals])

  const approve = useCallback(async (incidentId: string) => {
    await api.approveAction(incidentId)
    fetchApprovals()
  }, [fetchApprovals])

  const reject = useCallback(async (incidentId: string, reason: string) => {
    await api.rejectAction(incidentId, reason)
    fetchApprovals()
  }, [fetchApprovals])

  return { approvals, approve, reject, refetch: fetchApprovals }
}
