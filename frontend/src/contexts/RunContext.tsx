import { createContext, useContext, useState, useEffect, ReactNode } from 'react'
import { useAuth } from './AuthContext'

interface ActiveRun {
  id: string
  name: string
}

interface RunContextType {
  activeRun: ActiveRun | null
  setActiveRun: (run: ActiveRun | null) => void
}

const RunContext = createContext<RunContextType>({
  activeRun: null,
  setActiveRun: () => {},
})

// Per-user key — a flat "aria_active_run" key used to leak the last-opened
// run across every account that logged into the same browser.
const LEGACY_KEY = 'aria_active_run'
function storageKey(userId: string): string {
  return `aria_active_run_${userId}`
}

export function RunProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  const [activeRun, setActiveRunState] = useState<ActiveRun | null>(null)

  useEffect(() => {
    try { localStorage.removeItem(LEGACY_KEY) } catch { /* ignore */ }

    if (!user) { setActiveRunState(null); return }
    try {
      const stored = localStorage.getItem(storageKey(user.id))
      setActiveRunState(stored ? (JSON.parse(stored) as ActiveRun) : null)
    } catch { setActiveRunState(null) }
  }, [user?.id])

  function setActiveRun(run: ActiveRun | null) {
    setActiveRunState(run)
    if (!user) return
    try {
      if (run) localStorage.setItem(storageKey(user.id), JSON.stringify(run))
      else localStorage.removeItem(storageKey(user.id))
    } catch { /* ignore */ }
  }

  return (
    <RunContext.Provider value={{ activeRun, setActiveRun }}>
      {children}
    </RunContext.Provider>
  )
}

export function useRun() {
  return useContext(RunContext)
}
