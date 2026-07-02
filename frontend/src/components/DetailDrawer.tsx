import { useState, useEffect, useId } from 'react'
import { X } from 'lucide-react'
import { useFocusTrap } from '../hooks/useFocusTrap'

export interface DetailField {
  label: string
  value: React.ReactNode
}

interface Props {
  title: string
  subtitle?: string
  fields: DetailField[]
  children: React.ReactNode
  viewExtra?: React.ReactNode
  onSave: () => void
  isSaving?: boolean
  onClose: () => void
}

export default function DetailDrawer({
  title, subtitle, fields, children, viewExtra, onSave, isSaving, onClose,
}: Props) {
  const [editing, setEditing] = useState(false)
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
          {editing ? (
            <div>
              <div className="detail-section-title">Edit</div>
              <div className="form-grid" style={{ marginBottom: '0.75rem' }}>
                {children}
              </div>
              <div className="form-actions">
                <button
                  className="btn-primary btn-sm"
                  onClick={() => { onSave(); setEditing(false) }}
                  disabled={isSaving}
                >
                  {isSaving ? 'Saving…' : 'Save'}
                </button>
                <button className="btn-ghost btn-sm" onClick={() => setEditing(false)}>
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <div>
              <div
                className="detail-section-title"
                style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
              >
                Details
                <button
                  className="btn-ghost btn-sm"
                  onClick={() => setEditing(true)}
                  style={{ fontSize: '0.7rem', fontWeight: 500 }}
                >
                  Edit
                </button>
              </div>
              <div className="detail-fields">
                {fields.map((f, i) => (
                  <div key={i} className="detail-field">
                    <span className="detail-field-label">{f.label}</span>
                    <span className="detail-field-value">{f.value}</span>
                  </div>
                ))}
              </div>
              {viewExtra}
            </div>
          )}
        </div>
      </div>
    </>
  )
}
