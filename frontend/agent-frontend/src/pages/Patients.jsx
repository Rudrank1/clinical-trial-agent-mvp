import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getPatients, getStudies } from '../api'
import StatusBanner from '../components/StatusBanner'

function formatDate(value) {
  return value ? new Date(value).toLocaleString() : '—'
}

function Patients() {
  const [studies, setStudies] = useState([])
  const [studyId, setStudyId] = useState('')
  const [patients, setPatients] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    getStudies().then(setStudies).catch((err) => setError(err.message))
  }, [])

  useEffect(() => {
    setLoading(true)
    getPatients({ study_id: studyId || undefined })
      .then(setPatients)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [studyId])

  return (
    <div>
      <div className="d-flex align-items-center justify-content-between mb-4">
        <h1 className="mb-0">Patients</h1>
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
            <th>Patient</th>
            <th>Site</th>
            <th>Status</th>
            <th>Next visit</th>
          </tr>
        </thead>
        <tbody>
          {patients.map((patient) => (
            <tr key={`${patient.study_id}-${patient.subject_id}`}>
              <td>
                <Link to={`/studies/${patient.study_id}`}>{patient.study_id}</Link>
              </td>
              <td>{patient.subject_id}</td>
              <td>{patient.site_id}</td>
              <td>{patient.subject_status}</td>
              <td>{formatDate(patient.next_visit_at)}</td>
            </tr>
          ))}
          {!loading && patients.length === 0 && (
            <tr>
              <td colSpan={5} className="text-center text-muted">
                No patients found.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}

export default Patients
