const BASE_URL = '/api'

async function fetchJSON<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`)
  }
  return res.json()
}

export const api = {
  getIncidents: (params?: { status?: string; severity?: string; limit?: number; offset?: number }) => {
    const query = new URLSearchParams()
    if (params?.status) query.set('status', params.status)
    if (params?.severity) query.set('severity', params.severity)
    if (params?.limit) query.set('limit', String(params.limit))
    if (params?.offset) query.set('offset', String(params.offset))
    const qs = query.toString()
    return fetchJSON(`/incidents${qs ? '?' + qs : ''}`)
  },

  getIncident: (id: string) => fetchJSON(`/incidents/${id}`),

  getIncidentStats: () => fetchJSON('/incidents/stats'),

  getTimeline: (id: string) => fetchJSON(`/incidents/${id}/timeline`),

  getAgents: () => fetchJSON('/agents'),

  getApprovals: () => fetchJSON('/approvals'),

  approveAction: (incidentId: string, reason = '') =>
    fetchJSON(`/approvals/${incidentId}/approve`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),

  rejectAction: (incidentId: string, reason: string) =>
    fetchJSON(`/approvals/${incidentId}/reject`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),
}
