import { type ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'

interface Props {
  allowedRoles: string[]
  children: ReactNode
}

export default function RequireRole({ allowedRoles, children }: Props) {
  const { user, isAuthenticated, loading } = useAuth()
  if (loading) return null
  if (!isAuthenticated) return <Navigate to="/login" replace />
  const role = (user?.role ?? '').toUpperCase()
  if (!allowedRoles.includes(role)) return <Navigate to="/dashboard" replace />
  return <>{children}</>
}
