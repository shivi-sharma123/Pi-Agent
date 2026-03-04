import { useEffect, useState, useCallback } from 'react'
import { api } from '../api/client'
import type { Agent, WSEvent } from '../types'

export function useAgents(subscribe: (h: (e: WSEvent) => void) => () => void) {
  const [agents, setAgents] = useState<Agent[]>([])

  const fetchAgents = useCallback(async () => {
    try {
      const data = await api.getAgents() as Agent[]
      setAgents(data)
    } catch (err) {
      console.error('Failed to fetch agents:', err)
    }
  }, [])

  useEffect(() => {
    fetchAgents()
    const interval = setInterval(fetchAgents, 30000) // poll every 30s as fallback
    return () => clearInterval(interval)
  }, [fetchAgents])

  useEffect(() => {
    return subscribe((event: WSEvent) => {
      if (event.type === 'agent.heartbeat' || event.type === 'agent.dead') {
        fetchAgents()
      }
    })
  }, [subscribe, fetchAgents])

  return { agents, refetch: fetchAgents }
}
