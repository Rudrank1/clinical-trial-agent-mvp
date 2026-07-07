const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

async function request(path, options) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  const data = await response.json()
  if (!response.ok) {
    throw new Error(data.detail ?? `Request to ${path} failed (${response.status})`)
  }
  return data
}

export const seedData = () => request('/seed_data')
export const resetDatabase = () => request('/reset-database')

export const detectIssues = () => request('/workflows/run')
export const checkDueIssues = () => request('/workflows/check-due-issues')

export const getDashboard = () => request('/dashboard', { method: 'GET' })
export const getStudies = () => request('/studies', { method: 'GET' })
export const getStudySites = (studyId) => request(`/studies/${studyId}/sites`, { method: 'GET' })

export const getIssues = () => request('/issues', { method: 'GET' })
export const getIssue = (issueId) => request(`/issues/${issueId}`, { method: 'GET' })
export const verifyIssue = (issueId) =>
  request(`/workflows/delivery_not_registered/issues/${issueId}/verify`)
export const markIssueReceived = (issueId, kitIds) =>
  request(`/workflows/delivery_not_registered/issues/${issueId}/mark-received`, {
    body: JSON.stringify({ kit_ids: kitIds }),
  })
export const updateIssueShipment = (issueId, updates) =>
  request(`/workflows/delivery_not_registered/issues/${issueId}/shipment`, {
    method: 'PATCH',
    body: JSON.stringify(updates),
  })
