import { useEffect, useState, useCallback } from 'react'
import { api } from '../api/client'
import type { Incident, IncidentStats, WSEvent } from '../types'

export function useIncidents(subscribe: (h: (e: WSEvent) => void) => () => void) {
  const [incidents, setIncidents] = useState<Incident[]>([])
  const [stats, setStats] = useState<IncidentStats | null>(null)
  const [loading, setLoading] = useState(true)

  const fetchIncidents = useCallback(async () => {
    try {
      const [incData, statsData] = await Promise.all([
        api.getIncidents({ limit: 50 }) as Promise<Incident[]>,
        api.getIncidentStats() as Promise<IncidentStats>,
      ])
      setIncidents(incData)
      setStats(statsData)
    } catch (err) {
      console.error('Failed to fetch incidents:', err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchIncidents()
  }, [fetchIncidents])

  useEffect(() => {
    return subscribe((event: WSEvent) => {
      if (
        event.type === 'incident.created' ||
        event.type === 'incident.updated' ||
        event.type === 'incident.resolved'
      ) {
        fetchIncidents()
      }
    })
  }, [subscribe, fetchIncidents])

  return { incidents, stats, loading, refetch: fetchIncidents }
}
