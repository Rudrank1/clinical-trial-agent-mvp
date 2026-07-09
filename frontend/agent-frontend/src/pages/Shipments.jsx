import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getShipments, getStudies } from '../api'
import StatusBanner from '../components/StatusBanner'

function formatDate(value) {
  return value ? new Date(value).toLocaleString() : '—'
}

function Shipments() {
  const [studies, setStudies] = useState([])
  const [studyId, setStudyId] = useState('')
  const [shipments, setShipments] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    getStudies().then(setStudies).catch((err) => setError(err.message))
  }, [])

  useEffect(() => {
    setLoading(true)
    getShipments({ study_id: studyId || undefined })
      .then(setShipments)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [studyId])

  return (
    <div>
      <div className="d-flex align-items-center justify-content-between mb-4">
        <h1 className="mb-0">Shipments</h1>
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
            <th>Shipment</th>
            <th>Site</th>
            <th>Status</th>
            <th>Delivered</th>
            <th>Carrier</th>
            <th>Tracking</th>
            <th>Product</th>
          </tr>
        </thead>
        <tbody>
          {shipments.map((shipment) => (
            <tr key={`${shipment.study_id}-${shipment.shipment_id}`}>
              <td>
                <Link to={`/studies/${shipment.study_id}`}>{shipment.study_id}</Link>
              </td>
              <td>{shipment.shipment_id}</td>
              <td>{shipment.site_id}</td>
              <td>{shipment.logistics_status}</td>
              <td>{formatDate(shipment.delivered_at)}</td>
              <td>{shipment.carrier_name}</td>
              <td>{shipment.tracking_number}</td>
              <td>{shipment.product_label}</td>
            </tr>
          ))}
          {!loading && shipments.length === 0 && (
            <tr>
              <td colSpan={8} className="text-center text-muted">
                No shipments found.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}

export default Shipments
