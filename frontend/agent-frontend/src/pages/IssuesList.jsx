import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getIssues } from '../api'
import StatusBanner from '../components/StatusBanner'

function IssuesList() {
  const [issues, setIssues] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const refresh = async () => {
    setLoading(true)
    try {
      setIssues(await getIssues())
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  return (
    <div>
      <div className="d-flex align-items-center justify-content-between mb-4">
        <h1 className="mb-0">Issues</h1>
        <button type="button" className="btn btn-outline-secondary btn-sm" onClick={refresh} disabled={loading}>
          {loading ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      <StatusBanner variant="error" message={error} onDismiss={() => setError(null)} />

      <table className="table table-sm table-bordered align-middle">
        <thead>
          <tr>
            <th>ID</th>
            <th>Type</th>
            <th>Status</th>
            <th>Node</th>
            <th>Severity</th>
            <th>Follow-ups</th>
            <th>Summary</th>
          </tr>
        </thead>
        <tbody>
          {issues.map((issue) => (
            <tr key={issue.id}>
              <td>
                <Link to={`/issues/${issue.id}`}>{issue.id}</Link>
              </td>
              <td>{issue.issue_type}</td>
              <td>{issue.status}</td>
              <td>{issue.current_node}</td>
              <td>{issue.severity}</td>
              <td>{issue.follow_up_count}</td>
              <td>{issue.summary}</td>
            </tr>
          ))}
          {!loading && issues.length === 0 && (
            <tr>
              <td colSpan={7} className="text-center text-muted">
                No issues yet — run Detect Issues from the Dashboard.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}

export default IssuesList
