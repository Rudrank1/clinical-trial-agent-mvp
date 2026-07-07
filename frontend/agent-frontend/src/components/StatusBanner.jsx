function CheckIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <circle cx="10" cy="10" r="9" fill="currentColor" opacity="0.15" />
      <path
        d="M6 10.2l2.5 2.5 5.5-5.5"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function ErrorIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <circle cx="10" cy="10" r="9" fill="currentColor" opacity="0.15" />
      <path d="M7 7l6 6M13 7l-6 6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  )
}

function StatusBanner({ variant, message, onDismiss }) {
  if (!message) return null

  return (
    <div className={`status-banner status-banner-${variant}`} role="alert">
      <span className="status-banner-icon">{variant === 'success' ? <CheckIcon /> : <ErrorIcon />}</span>
      <span className="status-banner-message">{message}</span>
      {onDismiss && (
        <button type="button" className="status-banner-close" onClick={onDismiss} aria-label="Dismiss">
          &times;
        </button>
      )}
    </div>
  )
}

export default StatusBanner
