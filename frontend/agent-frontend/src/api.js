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

function withQuery(path, params) {
  const query = new URLSearchParams(
    Object.entries(params ?? {}).filter(([, value]) => value !== undefined && value !== null && value !== ''),
  ).toString()
  return query ? `${path}?${query}` : path
}

export const seedData = () => request('/seed_data')
export const resetDatabase = () => request('/reset-database')

export const detectIssues = (scope) => request('/workflows/run', { body: JSON.stringify(scope ?? {}) })
export const checkDueIssues = () => request('/workflows/check-due-issues')

export const getDashboard = () => request('/dashboard', { method: 'GET' })
export const getStudies = () => request('/studies', { method: 'GET' })
export const getStudySites = (studyId) => request(`/studies/${studyId}/sites`, { method: 'GET' })
export const getCountries = (params) => request(withQuery('/countries', params), { method: 'GET' })
export const getSites = (params) => request(withQuery('/sites', params), { method: 'GET' })
export const getPatients = (params) => request(withQuery('/patients', params), { method: 'GET' })
export const getShipments = (params) => request(withQuery('/shipments', params), { method: 'GET' })
export const getKits = (params) => request(withQuery('/kits', params), { method: 'GET' })

export const getIssues = () => request('/issues', { method: 'GET' })
export const getIssue = (issueId) => request(`/issues/${issueId}`, { method: 'GET' })
export const verifyIssue = (issueId) =>
  request(`/workflows/delivery_not_registered/issues/${issueId}/verify`)
export const markIssueReceived = (issueId) =>
  request(`/workflows/delivery_not_registered/issues/${issueId}/mark-received`)
export const updateIssueShipment = (issueId, updates) =>
  request(`/workflows/delivery_not_registered/issues/${issueId}/shipment`, {
    method: 'PATCH',
    body: JSON.stringify(updates),
  })
