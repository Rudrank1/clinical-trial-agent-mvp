import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getSites, getStudies } from '../api'
import StatusBanner from '../components/StatusBanner'

function Sites() {
  const [studies, setStudies] = useState([])
  const [studyId, setStudyId] = useState('')
  const [sites, setSites] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    getStudies().then(setStudies).catch((err) => setError(err.message))
  }, [])

  useEffect(() => {
    setLoading(true)
    getSites({ study_id: studyId || undefined })
      .then(setSites)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [studyId])

  return (
    <div>
      <div className="d-flex align-items-center justify-content-between mb-4">
        <h1 className="mb-0">Sites</h1>
        <select className="form-select form-select-sm w-auto" value={studyId} onChange={(e) => setStudyId(e.target.value)}>
          <option value="">All studies</option>
          {studies.map((study) => (
            <option key={study.study_id} value={study.study_id}>
              {study.study_id}
            </option>
          ))}
        </select>
      </div>

      <StatusBanner variant="error" message={error} onDismiss={() => setError(null)} />

      <table className="table table-sm table-bordered align-middle">
        <thead>
          <tr>
            <th>Study</th>
            <th>Site</th>
            <th>Country</th>
            <th>Status</th>
            <th>Institution</th>
            <th>Investigator</th>
            <th>Patients</th>
            <th>Shipments</th>
          </tr>
        </thead>
        <tbody>
          {sites.map((site) => (
            <tr key={`${site.study_id}-${site.site_id}`}>
              <td>
                <Link to={`/studies/${site.study_id}`}>{site.study_id}</Link>
              </td>
              <td>{site.site_id}</td>
              <td>{site.country_id}</td>
              <td>{site.site_status}</td>
              <td>{site.institution_name}</td>
              <td>{site.investigator_name}</td>
              <td>{site.patients}</td>
              <td>{site.shipments}</td>
            </tr>
          ))}
          {!loading && sites.length === 0 && (
            <tr>
              <td colSpan={8} className="text-center text-muted">
                No sites found.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}

export default Sites
