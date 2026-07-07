import { useState } from 'react'
import { seedData, resetDatabase } from '../api'
import StatusBanner from '../components/StatusBanner'

function Admin() {
  const [pendingAction, setPendingAction] = useState(null)
  const [successMessage, setSuccessMessage] = useState(null)
  const [error, setError] = useState(null)

  const runAction = async (key, fn) => {
    setPendingAction(key)
    setError(null)
    setSuccessMessage(null)
    try {
      const data = await fn()
      setSuccessMessage(data.message)
    } catch (err) {
      setError(err.message)
    } finally {
      setPendingAction(null)
    }
  }

  return (
    <div>
      <h1 className="mb-4">Admin</h1>
      <p className="text-muted">
        Development-only controls for resetting or regenerating the mock dataset. Not part of the
        normal day-to-day workflow.
      </p>

      <StatusBanner variant="error" message={error} onDismiss={() => setError(null)} />
      <StatusBanner variant="success" message={successMessage} onDismiss={() => setSuccessMessage(null)} />

      <div className="d-flex flex-wrap gap-2 mb-4">
        <button
          type="button"
          className="btn btn-primary"
          disabled={pendingAction !== null}
          onClick={() => runAction('seed', seedData)}
        >
          {pendingAction === 'seed' ? 'Seeding…' : 'Seed Data'}
        </button>
        <button
          type="button"
          className="btn btn-outline-danger"
          disabled={pendingAction !== null}
          onClick={() => runAction('reset', resetDatabase)}
        >
          {pendingAction === 'reset' ? 'Resetting…' : 'Reset Database'}
        </button>
      </div>
    </div>
  )
}

export default Admin
