import React, { createContext, useContext, useState, useEffect } from 'react'
import { AuthUser } from '../types'

interface LoginResult {
  success: boolean
  error?: string
  status?: 'pending' | 'rejected'
  reason?: string
}

interface AuthContextType {
  user: AuthUser | null
  isAuthenticated: boolean
  loading: boolean
  login: (email: string, password: string) => Promise<LoginResult>
  logout: () => void
}

const AuthContext = createContext<AuthContextType | null>(null)

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [loading, setLoading] = useState(true)

  // Restore session from localStorage on mount
  useEffect(() => {
    const stored = localStorage.getItem('aria_auth_user')
    if (stored) {
      try {
        setUser(JSON.parse(stored))
      } catch {
        localStorage.removeItem('aria_auth_user')
      }
    }
    setLoading(false)
  }, [])

  const login = async (email: string, password: string): Promise<LoginResult> => {
    try {
      // Step 1 — obtain JWT tokens
      const tokenRes = await fetch('/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      })

      if (!tokenRes.ok) {
        const body = await tokenRes.json().catch(() => ({})) as { detail?: unknown }
        const rawDetail = body.detail
        const detail = typeof rawDetail === 'string' ? rawDetail : ''
        if (detail === 'Account pending approval') {
          return { success: false, status: 'pending' }
        }
        if (detail === 'Account deactivated') {
          return { success: false, status: 'rejected', reason: 'Votre accès a été révoqué par un administrateur.' }
        }
        return { success: false, error: detail || 'Email ou mot de passe invalide.' }
      }

      const tokens = await tokenRes.json() as { access_token: string; refresh_token: string }
      localStorage.setItem('access_token', tokens.access_token)
      localStorage.setItem('refresh_token', tokens.refresh_token)

      // Step 2 — fetch user profile
      const meRes = await fetch('/auth/me', {
        headers: { Authorization: `Bearer ${tokens.access_token}` },
      })
      if (!meRes.ok) {
        return { success: false, error: 'Could not load user profile' }
      }

      const me = await meRes.json() as {
        id: string; email: string; full_name: string; role: string; is_active: boolean
      }
      const authUser: AuthUser = {
        id: me.id,
        name: me.full_name,
        email: me.email,
        role: me.role,
      }
      setUser(authUser)
      localStorage.setItem('aria_auth_user', JSON.stringify(authUser))
      return { success: true }
    } catch {
      return { success: false, error: 'Network error — make sure the backend is running.' }
    }
  }

  const logout = async () => {
    try {
      const token = localStorage.getItem('access_token')
      if (token) {
        await fetch('/auth/logout', {
          method: 'POST',
          headers: { Authorization: `Bearer ${token}` },
        }).catch(() => {})
      }
    } finally {
      setUser(null)
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      localStorage.removeItem('aria_auth_user')
    }
  }

  return (
    <AuthContext.Provider value={{ user, isAuthenticated: !!user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = (): AuthContextType => {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
