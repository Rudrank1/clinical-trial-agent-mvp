import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getCountries, getStudies } from '../api'
import StatusBanner from '../components/StatusBanner'

function Countries() {
  const [studies, setStudies] = useState([])
  const [studyId, setStudyId] = useState('')
  const [countries, setCountries] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    getStudies().then(setStudies).catch((err) => setError(err.message))
  }, [])

  useEffect(() => {
    setLoading(true)
    getCountries({ study_id: studyId || undefined })
      .then(setCountries)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [studyId])

  return (
    <div>
      <div className="d-flex align-items-center justify-content-between mb-4">
        <h1 className="mb-0">Countries</h1>
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
            <th>Country</th>
            <th>Name</th>
            <th>Status</th>
            <th>Sites</th>
            <th>Patients</th>
          </tr>
        </thead>
        <tbody>
          {countries.map((country) => (
            <tr key={`${country.study_id}-${country.country_id}`}>
              <td>
                <Link to={`/studies/${country.study_id}`}>{country.study_id}</Link>
              </td>
              <td>{country.country_id}</td>
              <td>{country.country_name}</td>
              <td>{country.country_status}</td>
              <td>{country.sites}</td>
              <td>{country.patients}</td>
            </tr>
          ))}
          {!loading && countries.length === 0 && (
            <tr>
              <td colSpan={6} className="text-center text-muted">
                No countries found.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}

export default Countries
