import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  getDashboard,
  getStudies,
  getCountries,
  getSites,
  detectIssues,
  checkDueIssues,
} from '../api'
import { summarizeDetectIssues, summarizeCheckDueIssues } from '../format'
import StatusBanner from '../components/StatusBanner'

const STAT_CARDS = [
  ['studies', 'Studies', '/studies'],
  ['countries', 'Countries', '/countries'],
  ['sites', 'Sites', '/sites'],
  ['patients', 'Patients', '/patients'],
  ['shipments', 'Shipments', '/shipments'],
  ['kits', 'Kits', '/kits'],
]

const STATUS_BADGE = {
  Open: 'text-bg-primary',
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

  const [scopeStudyId, setScopeStudyId] = useState('')
  const [scopeCountryId, setScopeCountryId] = useState('')
  const [scopeSiteId, setScopeSiteId] = useState('')
  const [scopeCountries, setScopeCountries] = useState([])
  const [scopeSites, setScopeSites] = useState([])

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

  useEffect(() => {
    getCountries({ study_id: scopeStudyId || undefined })
      .then(setScopeCountries)
      .catch((err) => setError(err.message))
    setScopeCountryId('')
    setScopeSiteId('')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scopeStudyId])

  useEffect(() => {
    getSites({ study_id: scopeStudyId || undefined, country_id: scopeCountryId || undefined })
      .then(setScopeSites)
      .catch((err) => setError(err.message))
    setScopeSiteId('')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scopeCountryId])

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

  const runDetect = () =>
    runAction(
      'detect',
      () =>
        detectIssues({
          study_id: scopeStudyId || undefined,
          country_id: scopeCountryId || undefined,
          site_id: scopeSiteId || undefined,
        }),
      summarizeDetectIssues,
    )

  return (
    <div>
      <h1 className="mb-4">Dashboard</h1>

      <StatusBanner variant="error" message={error} onDismiss={() => setError(null)} />
      <StatusBanner variant="success" message={successMessage} onDismiss={() => setSuccessMessage(null)} />

      <div className="row g-3 mb-4">
        {STAT_CARDS.map(([key, label, to]) => (
          <div className="col-6 col-md-2" key={key}>
            <Link to={to} className="card text-center h-100 text-decoration-none stat-card">
              <div className="card-body">
                <div className="fs-3 fw-semibold">{dashboard ? dashboard.totals[key] : '—'}</div>
                <div className="text-muted small">{label}</div>
              </div>
            </Link>
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

      <div className="card mb-4">
        <div className="card-header">Detect issues</div>
        <div className="card-body">
          <div className="row g-2 mb-3">
            <div className="col-md-4">
              <label className="form-label small mb-1">Study</label>
              <select
                className="form-select form-select-sm"
                value={scopeStudyId}
                onChange={(e) => setScopeStudyId(e.target.value)}
              >
                <option value="">All studies</option>
                {studies.map((study) => (
                  <option key={study.study_id} value={study.study_id}>
                    {study.study_id}
                  </option>
                ))}
              </select>
            </div>
            <div className="col-md-4">
              <label className="form-label small mb-1">Country</label>
              <select
                className="form-select form-select-sm"
                value={scopeCountryId}
                onChange={(e) => setScopeCountryId(e.target.value)}
              >
                <option value="">All countries</option>
                {scopeCountries.map((country) => (
                  <option key={`${country.study_id}-${country.country_id}`} value={country.country_id}>
                    {country.country_name} ({country.country_id})
                  </option>
                ))}
              </select>
            </div>
            <div className="col-md-4">
              <label className="form-label small mb-1">Site</label>
              <select
                className="form-select form-select-sm"
                value={scopeSiteId}
                onChange={(e) => setScopeSiteId(e.target.value)}
              >
                <option value="">All sites</option>
                {scopeSites.map((site) => (
                  <option key={`${site.study_id}-${site.site_id}`} value={site.site_id}>
                    {site.site_id}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="d-flex flex-wrap gap-2">
            <button type="button" className="btn btn-primary" disabled={pendingAction !== null} onClick={runDetect}>
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
        </div>
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
