import { createContext, useContext, useState, useCallback, useRef } from 'react'
import Toast, { type ToastVariant } from '../components/Toast'

interface ToastOpts { hint?: string; detail?: string }
interface ToastItem { id: number; message: string; variant: ToastVariant; hint?: string; detail?: string }
interface ToastContextValue {
  showToast: (message: string, variant: ToastVariant, opts?: ToastOpts) => void
}

const ToastContext = createContext<ToastContextValue>({ showToast: () => {} })

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([])
  const nextId = useRef(0)

  const showToast = useCallback((message: string, variant: ToastVariant, opts?: ToastOpts) => {
    const id = nextId.current++
    setToasts(t => [...t, { id, message, variant, hint: opts?.hint, detail: opts?.detail }])
  }, [])

  const dismiss = useCallback((id: number) => {
    setToasts(t => t.filter(item => item.id !== id))
  }, [])

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      <div className="toast-container">
        {toasts.map(t => (
          <Toast key={t.id} message={t.message} variant={t.variant}
                 hint={t.hint} detail={t.detail} onDismiss={() => dismiss(t.id)} />
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  return useContext(ToastContext)
}
