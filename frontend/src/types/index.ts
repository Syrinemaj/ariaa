export type UserRole = 'manager' | 'developer' | 'qa' | 'security'
export type UserStatus = 'pending' | 'active' | 'rejected'
export type ToastType = 'success' | 'error' | 'warning' | 'info'

export interface User {
  id: string
  name: string
  email: string
  role: UserRole | null
  status: UserStatus
  requestedAt: string
  approvedAt?: string
  rejectedAt?: string
  rejectionReason?: string
}

export interface AuthUser {
  id: string
  name: string
  email: string
  role: string
}

export interface ActivityItem {
  id: string
  userName: string
  action: string
  timestamp: string
  color: string
}

export interface Toast {
  id: string
  type: ToastType
  message: string
  duration?: number
}
