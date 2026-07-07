import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getStudies } from '../api'
import StatusBanner from '../components/StatusBanner'

function Studies() {
  const [studies, setStudies] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    getStudies()
      .then(setStudies)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div>
      <h1 className="mb-4">Studies</h1>

      <StatusBanner variant="error" message={error} onDismiss={() => setError(null)} />

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

export default Studies
