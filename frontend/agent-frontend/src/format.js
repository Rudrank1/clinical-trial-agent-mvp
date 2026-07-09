const STATUS_LABELS = {
  closed: 'closed',
  open: 'open',
  escalated: 'escalated',
}

export function humanStatus(status) {
  return STATUS_LABELS[status] ?? status
}

export function summarizeDetectIssues(data) {
  const results = data.results ?? []
  if (results.length === 0) return 'Scan complete — no issues detected.'

  const counts = {}
  for (const result of results) {
    counts[result.status] = (counts[result.status] ?? 0) + 1
  }
  const parts = Object.entries(counts).map(([status, count]) => `${count} ${humanStatus(status)}`)
  return `Scan complete — ${results.length} issue(s) processed (${parts.join(', ')}).`
}

export function summarizeCheckDueIssues(data) {
  const count = data.processed_count ?? 0
  return count === 0 ? 'No issues were due for a check.' : `${count} issue(s) rechecked.`
}
