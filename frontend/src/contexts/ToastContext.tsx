import { createContext, useContext, useState, useCallback, ReactNode } from 'react'
import { CheckCircle, XCircle, AlertTriangle, Info, X } from 'lucide-react'

export type ToastType = 'success' | 'error' | 'warning' | 'info'

interface ToastItem {
  id: string
  type: ToastType
  message: string
  action?: { label: string; onClick: () => void }
}

interface ToastContextType {
  toast: (opts: { type: ToastType; message: string; action?: { label: string; onClick: () => void } }) => void
}

const ToastContext = createContext<ToastContextType>({ toast: () => {} })

const ICONS = { success: CheckCircle, error: XCircle, warning: AlertTriangle, info: Info }
const COLORS: Record<ToastType, { border: string; icon: string }> = {
  success: { border: '#10b981', icon: '#10b981' },
  error:   { border: '#f43f5e', icon: '#f43f5e' },
  warning: { border: '#f59e0b', icon: '#f59e0b' },
  info:    { border: 'var(--brand)', icon: 'var(--brand)' },
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([])

  const toast = useCallback(({ type, message, action }: {
    type: ToastType; message: string; action?: { label: string; onClick: () => void }
  }) => {
    const id = Math.random().toString(36).slice(2)
    setToasts(prev => [...prev, { id, type, message, action }])
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 4500)
  }, [])

  const dismiss = (id: string) => setToasts(prev => prev.filter(t => t.id !== id))

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      {toasts.length > 0 && (
        <div className="fixed bottom-6 right-6 z-50 flex flex-col gap-2 pointer-events-none" style={{ maxWidth: 360 }}>
          {toasts.map(t => {
            const Icon = ICONS[t.type]
            const c = COLORS[t.type]
            return (
              <div key={t.id}
                className="pointer-events-auto flex items-start gap-3 p-4 rounded-2xl shadow-lg animate-in slide-in-from-right-4"
                style={{
                  background: 'var(--card)',
                  border: `1px solid ${c.border}33`,
                  boxShadow: `0 4px 24px ${c.border}22, 0 1px 4px rgba(0,0,0,0.08)`,
                }}>
                <Icon className="w-4 h-4 mt-0.5 shrink-0" style={{ color: c.icon }} />
                <span className="flex-1 text-sm leading-snug" style={{ color: 'var(--ink)' }}>{t.message}</span>
                {t.action && (
                  <button
                    onClick={() => { t.action!.onClick(); dismiss(t.id) }}
                    className="text-xs font-bold shrink-0 underline hover:no-underline"
                    style={{ color: c.icon }}>
                    {t.action.label}
                  </button>
                )}
                <button onClick={() => dismiss(t.id)} className="shrink-0 opacity-40 hover:opacity-80 transition-opacity">
                  <X className="w-3.5 h-3.5" style={{ color: 'var(--ink)' }} />
                </button>
              </div>
            )
          })}
        </div>
      )}
    </ToastContext.Provider>
  )
}

export function useToast() {
  return useContext(ToastContext)
}
