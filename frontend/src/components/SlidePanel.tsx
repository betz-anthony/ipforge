import { useEffect, useId } from 'react'
import { X } from 'lucide-react'
import { useFocusTrap } from '../hooks/useFocusTrap'

interface Props {
  title: string
  subtitle?: string
  onClose: () => void
  children: React.ReactNode
}

export default function SlidePanel({ title, subtitle, onClose, children }: Props) {
  const trapRef = useFocusTrap<HTMLDivElement>()
  const titleId = useId()

  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  return (
    <>
      <div className="detail-backdrop" onClick={onClose} aria-hidden="true" />
      <div className="detail-panel" role="dialog" aria-modal="true" aria-labelledby={titleId} ref={trapRef}>
        <div className="detail-panel-header">
          <div style={{ minWidth: 0 }}>
            <div className="detail-panel-title" id={titleId}>{title}</div>
            {subtitle && <div className="detail-panel-subtitle">{subtitle}</div>}
          </div>
          <button
            className="btn-ghost btn-sm"
            onClick={onClose}
            aria-label="Close"
            style={{ padding: '0.25rem', flexShrink: 0 }}
          >
            <X size={14} />
          </button>
        </div>
        <div className="detail-panel-body">
          {children}
        </div>
      </div>
    </>
  )
}
