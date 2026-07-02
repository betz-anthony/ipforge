import { useEffect, useId } from 'react'
import type React from 'react'
import { createPortal } from 'react-dom'
import { useFocusTrap } from '../hooks/useFocusTrap'

interface ConfirmModalProps {
  title: string
  message: string
  confirmLabel?: string
  danger?: boolean
  onConfirm: () => void
  onCancel: () => void
  extra?: React.ReactNode
}

export default function ConfirmModal({
  title, message, confirmLabel = 'Delete', danger = true, onConfirm, onCancel, extra,
}: ConfirmModalProps) {
  const trapRef = useFocusTrap<HTMLDivElement>()
  const titleId = useId()
  const msgId = useId()

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Enter') { e.preventDefault(); onConfirm() }
      if (e.key === 'Escape') onCancel()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onConfirm, onCancel])

  return createPortal(
    <div className="modal-backdrop" onClick={onCancel}>
      <div
        className="modal"
        onClick={e => e.stopPropagation()}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={msgId}
        ref={trapRef}
      >
        <h2 className="modal-title" id={titleId}>{title}</h2>
        <p className="modal-message" id={msgId}>{message}</p>
        {extra && <div className="modal-extra">{extra}</div>}
        <div className="modal-actions">
          <button className="btn btn-ghost" onClick={onCancel}>Cancel</button>
          <button
            className={`btn ${danger ? 'btn-danger' : 'btn-primary'}`}
            onClick={onConfirm}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  )
}
