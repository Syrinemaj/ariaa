import { createContext, useContext, useState, ReactNode } from 'react'

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

export function RunProvider({ children }: { children: ReactNode }) {
  const [activeRun, setActiveRunState] = useState<ActiveRun | null>(() => {
    try {
      const stored = localStorage.getItem('aria_active_run')
      return stored ? (JSON.parse(stored) as ActiveRun) : null
    } catch { return null }
  })

  function setActiveRun(run: ActiveRun | null) {
    setActiveRunState(run)
    if (run) localStorage.setItem('aria_active_run', JSON.stringify(run))
    else localStorage.removeItem('aria_active_run')
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
