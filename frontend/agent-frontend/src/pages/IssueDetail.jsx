import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getIssue, verifyIssue, markIssueReceived, updateIssueShipment } from '../api'
import { humanStatus } from '../format'
import StatusBanner from '../components/StatusBanner'

function formatDate(value) {
  return value ? new Date(value).toLocaleString() : '—'
}

function toDatetimeLocal(value) {
  return value ? value.slice(0, 16) : ''
}

const SHIPMENT_FIELDS = [
  ['logistics_status', 'Logistics status', 'text'],
  ['delivered_at', 'Delivered at', 'datetime-local'],
  ['carrier_name', 'Carrier', 'text'],
  ['tracking_number', 'Tracking number', 'text'],
]

function IssueDetail() {
  const { issueId } = useParams()
  const [issue, setIssue] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [successMessage, setSuccessMessage] = useState(null)
  const [pendingAction, setPendingAction] = useState(null)

  const [editingShipment, setEditingShipment] = useState(false)
  const [shipmentForm, setShipmentForm] = useState({})

  const refresh = async () => {
    setLoading(true)
    try {
      const data = await getIssue(issueId)
      setIssue(data)
      setError(null)
      if (data.mismatch) {
        setShipmentForm({
          logistics_status: data.mismatch.shipment.logistics_status ?? '',
          delivered_at: toDatetimeLocal(data.mismatch.shipment.delivered_at),
          carrier_name: data.mismatch.shipment.carrier_name ?? '',
          tracking_number: data.mismatch.shipment.tracking_number ?? '',
        })
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [issueId])

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

  const saveShipment = (event) => {
    event.preventDefault()
    runAction(
      'shipment',
      () => updateIssueShipment(issueId, shipmentForm),
      (result) => `Shipment updated — issue is now ${humanStatus(result.status)}.`,
    )
    setEditingShipment(false)
  }

  if (loading && !issue) return <p>Loading…</p>
  if (error && !issue) return <StatusBanner variant="error" message={error} />
  if (!issue) return null

  const resolved = issue.status === 'Closed'

  return (
    <div>
      <Link to="/issues">&larr; Back to Issues</Link>
      <h1 className="mt-2 mb-4">
        Issue #{issue.id} — {issue.issue_type}
      </h1>

      <StatusBanner variant="error" message={error} onDismiss={() => setError(null)} />
      <StatusBanner variant="success" message={successMessage} onDismiss={() => setSuccessMessage(null)} />

      <div className="row g-3 mb-4">
        <div className="col-md-8">
          <div className="card h-100">
            <div className="card-header">Summary</div>
            <div className="card-body">
              <p>{issue.summary}</p>
              <dl className="row mb-0 small">
                <dt className="col-sm-4">Status</dt>
                <dd className="col-sm-8">{issue.status}</dd>
                <dt className="col-sm-4">Current node</dt>
                <dd className="col-sm-8">{issue.current_node}</dd>
                <dt className="col-sm-4">Severity</dt>
                <dd className="col-sm-8">{issue.severity}</dd>
                <dt className="col-sm-4">Follow-ups sent</dt>
                <dd className="col-sm-8">{issue.follow_up_count}</dd>
                <dt className="col-sm-4">Created</dt>
                <dd className="col-sm-8">{formatDate(issue.created_at)}</dd>
                <dt className="col-sm-4">Resolved</dt>
                <dd className="col-sm-8">{formatDate(issue.resolved_at)}</dd>
              </dl>
            </div>
          </div>
        </div>
        <div className="col-md-4">
          <div className="card h-100">
            <div className="card-header">Actions</div>
            <div className="card-body d-flex flex-column gap-2">
              <button
                type="button"
                className="btn btn-outline-secondary"
                disabled={resolved || pendingAction !== null}
                onClick={() =>
                  runAction(
                    'recheck',
                    () => verifyIssue(issueId),
                    (result) => `Rechecked — issue is now ${humanStatus(result.status)}.`,
                  )
                }
              >
                {pendingAction === 'recheck' ? 'Rechecking…' : 'Recheck'}
              </button>
              {resolved && <p className="text-muted small mb-0">This issue is closed.</p>}
            </div>
          </div>
        </div>
      </div>

      {issue.mismatch && (
        <div className="card mb-4">
          <div className="card-header d-flex align-items-center justify-content-between">
            Shipment causing the mismatch
            {!resolved && (
              <button
                type="button"
                className="btn btn-sm btn-outline-secondary"
                onClick={() => setEditingShipment((prev) => !prev)}
              >
                {editingShipment ? 'Cancel' : 'Edit'}
              </button>
            )}
          </div>
          <div className="card-body">
            {editingShipment ? (
              <form onSubmit={saveShipment} className="row g-2">
                {SHIPMENT_FIELDS.map(([field, label, type]) => (
                  <div className="col-md-6" key={field}>
                    <label className="form-label small mb-0">{label}</label>
                    <input
                      type={type}
                      className="form-control form-control-sm"
                      value={shipmentForm[field] ?? ''}
                      onChange={(event) =>
                        setShipmentForm((prev) => ({ ...prev, [field]: event.target.value }))
                      }
                    />
                  </div>
                ))}
                <div className="col-12">
                  <button type="submit" className="btn btn-primary btn-sm" disabled={pendingAction !== null}>
                    {pendingAction === 'shipment' ? 'Saving…' : 'Save shipment fields'}
                  </button>
                </div>
              </form>
            ) : (
              <dl className="row mb-0 small">
                <dt className="col-sm-3">Shipment</dt>
                <dd className="col-sm-9">{issue.mismatch.shipment.shipment_id}</dd>
                <dt className="col-sm-3">Logistics status</dt>
                <dd className="col-sm-9">{issue.mismatch.shipment.logistics_status}</dd>
                <dt className="col-sm-3">Delivered at</dt>
                <dd className="col-sm-9">{formatDate(issue.mismatch.shipment.delivered_at)}</dd>
                <dt className="col-sm-3">Carrier</dt>
                <dd className="col-sm-9">{issue.mismatch.shipment.carrier_name}</dd>
                <dt className="col-sm-3">Tracking number</dt>
                <dd className="col-sm-9">{issue.mismatch.shipment.tracking_number}</dd>
              </dl>
            )}
          </div>

          <div className="card-header border-top">Kits on this shipment</div>
          <div className="table-responsive">
            <table className="table table-sm mb-0">
              <thead>
                <tr>
                  <th>Kit</th>
                  <th>Status</th>
                  <th>Dispensed</th>
                  <th>Product</th>
                  <th>Expires</th>
                </tr>
              </thead>
              <tbody>
                {issue.mismatch.kits.map((kit) => (
                  <tr key={kit.kit_id} className={kit.pending ? 'table-warning' : ''}>
                    <td>{kit.kit_id}</td>
                    <td>{kit.kit_status}</td>
                    <td>{formatDate(kit.dispensed_at)}</td>
                    <td>{kit.product_label}</td>
                    <td>{formatDate(kit.expiration_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="card-body">
            <button
              type="button"
              className="btn btn-success btn-sm"
              disabled={resolved || pendingAction !== null}
              onClick={() =>
                runAction(
                  'mark-received',
                  () => markIssueReceived(issueId),
                  (result) => `Shipment marked as received — issue is now ${humanStatus(result.status)}.`,
                )
              }
            >
              {pendingAction === 'mark-received' ? 'Marking…' : 'Mark Shipment as Received'}
            </button>
          </div>
        </div>
      )}

      {issue.delay_context && (
        <div className="card mb-4">
          <div className="card-header">Delayed shipment</div>
          <div className="card-body">
            <dl className="row mb-0 small">
              <dt className="col-sm-3">Shipment</dt>
              <dd className="col-sm-9">{issue.delay_context.shipment.shipment_id}</dd>
              <dt className="col-sm-3">Logistics status</dt>
              <dd className="col-sm-9">{issue.delay_context.shipment.logistics_status}</dd>
              <dt className="col-sm-3">Requested</dt>
              <dd className="col-sm-9">{formatDate(issue.delay_context.shipment.requested_at)}</dd>
              <dt className="col-sm-3">Shipped</dt>
              <dd className="col-sm-9">{formatDate(issue.delay_context.shipment.shipped_at)}</dd>
              <dt className="col-sm-3">Days in transit</dt>
              <dd className="col-sm-9">{issue.delay_context.shipment.days_in_transit ?? '—'}</dd>
              <dt className="col-sm-3">Carrier</dt>
              <dd className="col-sm-9">{issue.delay_context.shipment.carrier_name}</dd>
              <dt className="col-sm-3">Tracking number</dt>
              <dd className="col-sm-9">{issue.delay_context.shipment.tracking_number}</dd>
              <dt className="col-sm-3">Product</dt>
              <dd className="col-sm-9">{issue.delay_context.shipment.product_label}</dd>
            </dl>
          </div>
        </div>
      )}

      <div className="card mb-4">
        <div className="card-header">Evidence</div>
        <ul className="list-group list-group-flush">
          {issue.evidence.map((item) => (
            <li className="list-group-item" key={item.id}>
              <strong>{item.source_system}</strong>: {item.summary}
            </li>
          ))}
          {issue.evidence.length === 0 && <li className="list-group-item text-muted">No evidence recorded.</li>}
        </ul>
      </div>

      <div className="card mb-4">
        <div className="card-header">Email / action history</div>
        <div className="table-responsive">
          <table className="table table-sm mb-0">
            <thead>
              <tr>
                <th>Type</th>
                <th>Status</th>
                <th>Subject</th>
                <th>Sent</th>
              </tr>
            </thead>
            <tbody>
              {issue.actions.map((action) => (
                <tr key={action.id}>
                  <td>{action.type}</td>
                  <td>{action.status}</td>
                  <td>{action.subject}</td>
                  <td>{formatDate(action.created_at)}</td>
                </tr>
              ))}
              {issue.actions.length === 0 && (
                <tr>
                  <td colSpan={4} className="text-center text-muted">
                    No actions recorded.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

export default IssueDetail
