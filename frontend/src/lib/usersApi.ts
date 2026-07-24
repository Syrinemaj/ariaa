import { api } from './api'

// ── Types ─────────────────────────────────────────────────────────────────────

export interface BackendUser {
  id: string
  org_id: string
  email: string
  full_name: string
  role: string
  is_active: boolean
  last_login_at: string | null
}

// ── API calls ─────────────────────────────────────────────────────────────────

export function listUsers() {
  return api.get<{ users: BackendUser[] }>('/users').then(r => r.users)
}

export function createUser(body: {
  email: string
  password: string
  full_name: string
  role: string
}) {
  return api.post<BackendUser>('/users', body)
}

export function activateUser(id: string) {
  return api.patch<BackendUser>(`/users/${id}/activate`)
}

export function deactivateUser(id: string) {
  return api.patch<BackendUser>(`/users/${id}/deactivate`)
}

export function updateUserRole(id: string, role: string) {
  return api.patch<BackendUser>(`/users/${id}/role`, { role })
}
