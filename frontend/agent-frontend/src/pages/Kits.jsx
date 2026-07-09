import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getKits, getStudies } from '../api'
import StatusBanner from '../components/StatusBanner'

function formatDate(value) {
  return value ? new Date(value).toLocaleString() : '—'
}

function Kits() {
  const [studies, setStudies] = useState([])
  const [studyId, setStudyId] = useState('')
  const [kits, setKits] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    getStudies().then(setStudies).catch((err) => setError(err.message))
  }, [])

  useEffect(() => {
    setLoading(true)
    getKits({ study_id: studyId || undefined })
      .then(setKits)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [studyId])

  return (
    <div>
      <div className="d-flex align-items-center justify-content-between mb-4">
        <h1 className="mb-0">Kits</h1>
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
            <th>Kit</th>
            <th>Shipment</th>
            <th>Site</th>
            <th>Status</th>
            <th>Dispensed</th>
            <th>Product</th>
            <th>Expires</th>
          </tr>
        </thead>
        <tbody>
          {kits.map((kit) => (
            <tr key={`${kit.study_id}-${kit.kit_id}`}>
              <td>
                <Link to={`/studies/${kit.study_id}`}>{kit.study_id}</Link>
              </td>
              <td>{kit.kit_id}</td>
              <td>{kit.shipment_id}</td>
              <td>{kit.site_id}</td>
              <td>{kit.kit_status}</td>
              <td>{formatDate(kit.dispensed_at)}</td>
              <td>{kit.product_label}</td>
              <td>{formatDate(kit.expiration_at)}</td>
            </tr>
          ))}
          {!loading && kits.length === 0 && (
            <tr>
              <td colSpan={8} className="text-center text-muted">
                No kits found.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}

export default Kits
