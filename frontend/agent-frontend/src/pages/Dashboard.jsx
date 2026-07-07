import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getDashboard, getStudies, detectIssues, checkDueIssues } from '../api'
import { summarizeDetectIssues, summarizeCheckDueIssues } from '../format'
import StatusBanner from '../components/StatusBanner'

const STAT_LABELS = [
  ['studies', 'Studies'],
  ['countries', 'Countries'],
  ['sites', 'Sites'],
  ['patients', 'Patients'],
  ['shipments', 'Shipments'],
  ['kits', 'Kits'],
]

const STATUS_BADGE = {
  Open: 'text-bg-primary',
  'Waiting for Response': 'text-bg-warning',
  Escalated: 'text-bg-danger',
  Closed: 'text-bg-secondary',
}

function Dashboard() {
  const [dashboard, setDashboard] = useState(null)
  const [studies, setStudies] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [pendingAction, setPendingAction] = useState(null)
  const [successMessage, setSuccessMessage] = useState(null)

  const refresh = async () => {
    setLoading(true)
    try {
      const [dashboardData, studiesData] = await Promise.all([getDashboard(), getStudies()])
      setDashboard(dashboardData)
      setStudies(studiesData)
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

  const runAction = async (key, fn, summarize) => {
    setPendingAction(key)
    setError(null)
    setSuccessMessage(null)
    try {
      const data = await fn()
      setSuccessMessage(summarize(data))
      await refresh()
    } catch (err) {
      setError(err.message)
    } finally {
      setPendingAction(null)
    }
  }

  return (
    <div>
      <h1 className="mb-4">Dashboard</h1>

      <StatusBanner variant="error" message={error} onDismiss={() => setError(null)} />
      <StatusBanner variant="success" message={successMessage} onDismiss={() => setSuccessMessage(null)} />

      <div className="row g-3 mb-4">
        {STAT_LABELS.map(([key, label]) => (
          <div className="col-6 col-md-2" key={key}>
            <div className="card text-center h-100">
              <div className="card-body">
                <div className="fs-3 fw-semibold">{dashboard ? dashboard.totals[key] : '—'}</div>
                <div className="text-muted small">{label}</div>
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="card mb-4">
        <div className="card-header">Issues by stage</div>
        <div className="card-body d-flex flex-wrap gap-2">
          {dashboard
            ? Object.entries(dashboard.issues_by_status).map(([status, count]) => (
                <span key={status} className={`badge ${STATUS_BADGE[status] ?? 'text-bg-light'} fs-6`}>
                  {status}: {count}
                </span>
              ))
            : '—'}
        </div>
      </div>

      <div className="d-flex flex-wrap gap-2 mb-4">
        <button
          type="button"
          className="btn btn-primary"
          disabled={pendingAction !== null}
          onClick={() => runAction('detect', detectIssues, summarizeDetectIssues)}
        >
          {pendingAction === 'detect' ? 'Detecting…' : 'Detect Issues'}
        </button>
        <button
          type="button"
          className="btn btn-outline-primary"
          disabled={pendingAction !== null}
          onClick={() => runAction('check-due', checkDueIssues, summarizeCheckDueIssues)}
        >
          {pendingAction === 'check-due' ? 'Checking…' : 'Check Due Issues'}
        </button>
        <Link className="btn btn-outline-secondary" to="/issues">
          View Issues
        </Link>
      </div>

      <h2 className="h5 mb-2">Studies</h2>
      <table className="table table-sm table-bordered align-middle">
        <thead>
          <tr>
            <th>Study</th>
            <th>Status</th>
            <th>Countries</th>
            <th>Sites</th>
            <th>Patients</th>
            <th>Open issues</th>
          </tr>
        </thead>
        <tbody>
          {studies.map((study) => (
            <tr key={study.study_id}>
              <td>
                <Link to={`/studies/${study.study_id}`}>{study.study_id}</Link>
              </td>
              <td>{study.study_status}</td>
              <td>{study.countries}</td>
              <td>{study.sites}</td>
              <td>{study.patients}</td>
              <td>{study.open_issues}</td>
            </tr>
          ))}
          {!loading && studies.length === 0 && (
            <tr>
              <td colSpan={6} className="text-center text-muted">
                No studies yet — seed the database from the Admin page to get started.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}

export default Dashboard
