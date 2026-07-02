import { useEffect, useId } from 'react'
import { createPortal } from 'react-dom'
import { useFocusTrap } from '../hooks/useFocusTrap'

interface Props {
  title: React.ReactNode
  onClose: () => void
  children: React.ReactNode
}

/**
 * Generic modal dialog: backdrop + focus trap + Escape-to-close + dialog
 * semantics. For simple confirm prompts use ConfirmModal; use this when the
 * body needs arbitrary interactive content (checklists, forms).
 */
export default function ModalDialog({ title, onClose, children }: Props) {
  const trapRef = useFocusTrap<HTMLDivElement>()
  const titleId = useId()

  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  return createPortal(
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal"
        onClick={e => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        ref={trapRef}
      >
        <h2 className="modal-title" id={titleId}>{title}</h2>
        {children}
      </div>
    </div>,
    document.body,
  )
}
