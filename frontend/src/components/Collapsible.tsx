import { useState, type ReactNode } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'

type Props = {
  title: string
  defaultOpen?: boolean
  storageKey?: string
  headerExtra?: ReactNode
  children: ReactNode
}

export default function Collapsible({
  title,
  defaultOpen = true,
  storageKey,
  headerExtra,
  children,
}: Props) {
  const [open, setOpen] = useState(() => {
    if (!storageKey) return defaultOpen
    try {
      const v = localStorage.getItem(`collapsible:${storageKey}`)
      return v === null ? defaultOpen : v === '1'
    } catch {
      return defaultOpen
    }
  })

  const toggle = () => {
    const next = !open
    setOpen(next)
    if (storageKey) {
      try { localStorage.setItem(`collapsible:${storageKey}`, next ? '1' : '0') } catch { /* ignore */ }
    }
  }

  return (
    <div className="settings-section">
      <div className="collapsible-header">
        <button
          type="button"
          className="collapsible-toggle"
          aria-expanded={open}
          onClick={toggle}
        >
          {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
          <span>{title}</span>
        </button>
        {headerExtra && <div className="collapsible-header-extra">{headerExtra}</div>}
      </div>
      {open && <div className="collapsible-body">{children}</div>}
    </div>
  )
}
