import { useState } from 'react'
import { AlertTriangle, Info, X } from 'lucide-react'

type Props = {
  variant?: 'info' | 'warning'
  storageKey?: string  // if set, dismissal persists in localStorage
  children: React.ReactNode
}

export default function Banner({ variant = 'warning', storageKey, children }: Props) {
  const [dismissed, setDismissed] = useState(() => {
    if (!storageKey) return false
    try { return localStorage.getItem(`banner-dismissed:${storageKey}`) === '1' } catch { return false }
  })

  if (dismissed) return null

  const dismiss = () => {
    setDismissed(true)
    if (storageKey) {
      try { localStorage.setItem(`banner-dismissed:${storageKey}`, '1') } catch { /* ignore */ }
    }
  }

  const Icon = variant === 'warning' ? AlertTriangle : Info

  return (
    <div className={`app-banner app-banner-${variant}`} role={variant === 'warning' ? 'alert' : 'status'}>
      <Icon size={14} className="app-banner-icon" />
      <div className="app-banner-body">{children}</div>
      <button
        type="button"
        className="app-banner-close"
        onClick={dismiss}
        aria-label="Dismiss"
      >
        <X size={13} />
      </button>
    </div>
  )
}
