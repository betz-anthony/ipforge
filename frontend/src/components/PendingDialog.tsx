import { useEffect, useId, useState } from 'react'
import { createPortal } from 'react-dom'

interface Props {
  pending: boolean
  message: string
}

// Avoid a flash for calls that return almost immediately.
const SHOW_DELAY_MS = 250
// After this long, offer to dismiss; the mutation keeps running and its
// result still arrives as a toast.
const SLOW_AFTER_MS = 8000

/**
 * Centered "waiting for provider" dialog shown while a DNS/DHCP write is in
 * flight. Blocks the page to prevent double-submits; on slow calls the user
 * can dismiss it and rely on the final result toast.
 */
export default function PendingDialog({ pending, message }: Props) {
  const [visible, setVisible] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [dismissed, setDismissed] = useState(false)
  const msgId = useId()

  useEffect(() => {
    if (!pending) {
      setVisible(false)
      setElapsed(0)
      setDismissed(false)
      return
    }
    const start = Date.now()
    const show = setTimeout(() => setVisible(true), SHOW_DELAY_MS)
    const tick = setInterval(() => setElapsed(Date.now() - start), 1000)
    return () => { clearTimeout(show); clearInterval(tick) }
  }, [pending])

  const slow = elapsed >= SLOW_AFTER_MS

  useEffect(() => {
    if (!pending || !slow) return
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') setDismissed(true) }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [pending, slow])

  if (!pending || !visible || dismissed) return null

  return createPortal(
    <div className="modal-backdrop pending-backdrop">
      <div className="modal pending-dialog" role="alertdialog" aria-modal="true"
           aria-busy="true" aria-describedby={msgId}>
        <div className="pending-spinner" aria-hidden="true" />
        <p className="modal-message pending-message" id={msgId}>{message}</p>
        {slow && (
          <>
            <p className="pending-slow">
              Still waiting on the provider ({Math.floor(elapsed / 1000)}s).
            </p>
            <div className="modal-actions">
              <button className="btn btn-ghost" onClick={() => setDismissed(true)}>
                Dismiss
              </button>
            </div>
            <p className="pending-slow-hint">
              The request keeps running. The result will appear as a notification.
            </p>
          </>
        )}
      </div>
    </div>,
    document.body,
  )
}
