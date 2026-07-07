import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getStudySites } from '../api'
import StatusBanner from '../components/StatusBanner'

function StudyDetail() {
  const { studyId } = useParams()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    setLoading(true)
    getStudySites(studyId)
      .then(setData)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [studyId])

  if (loading && !data) return <p>Loading…</p>
  if (error && !data) return <StatusBanner variant="error" message={error} />
  if (!data) return null

  return (
    <div>
      <Link to="/studies">&larr; Back to Studies</Link>
      <h1 className="mt-2 mb-4">
        {data.study_id} <span className="text-muted fs-5">({data.study_status})</span>
      </h1>

      <StatusBanner variant="error" message={error} onDismiss={() => setError(null)} />

      <table className="table table-sm table-bordered align-middle">
        <thead>
          <tr>
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
          {data.sites.map((site) => (
            <tr key={site.site_id}>
              <td>{site.site_id}</td>
              <td>{site.country_id}</td>
              <td>{site.site_status}</td>
              <td>{site.institution_name}</td>
              <td>{site.investigator_name}</td>
              <td>{site.patients}</td>
              <td>{site.shipments}</td>
            </tr>
          ))}
          {data.sites.length === 0 && (
            <tr>
              <td colSpan={7} className="text-center text-muted">
                No sites for this study.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}

export default StudyDetail
