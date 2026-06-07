import { useEffect, useState } from 'react'

export type ToastVariant = 'success' | 'error'

interface ToastProps {
  message: string
  variant: ToastVariant
  hint?: string
  detail?: string
  onDismiss: () => void
}

export default function Toast({ message, variant, hint, detail, onDismiss }: ToastProps) {
  const [showDetail, setShowDetail] = useState(false)
  useEffect(() => {
    // Errors with detail stay until dismissed; others auto-close.
    if (variant === 'error' && detail) return
    const t = setTimeout(onDismiss, 4000)
    return () => clearTimeout(t)
  }, [onDismiss, variant, detail])

  return (
    <div className={`toast toast-${variant}`}>
      <div className="toast-body">
        <span>{message}</span>
        {hint && <span className="toast-hint">{hint}</span>}
        {detail && (
          <>
            <button className="toast-detail-toggle" onClick={() => setShowDetail(s => !s)}>
              {showDetail ? 'Hide details' : 'Details'}
            </button>
            {showDetail && <pre className="toast-detail">{detail}</pre>}
          </>
        )}
      </div>
      <button className="toast-close" onClick={onDismiss}>×</button>
    </div>
  )
}
