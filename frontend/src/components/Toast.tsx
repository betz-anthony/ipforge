import { useEffect } from 'react'

export type ToastVariant = 'success' | 'error'

interface ToastProps {
  message: string
  variant: ToastVariant
  onDismiss: () => void
}

export default function Toast({ message, variant, onDismiss }: ToastProps) {
  useEffect(() => {
    const t = setTimeout(onDismiss, 4000)
    return () => clearTimeout(t)
  }, [onDismiss])

  return (
    <div className={`toast toast-${variant}`}>
      <span>{message}</span>
      <button className="toast-close" onClick={onDismiss}>×</button>
    </div>
  )
}
