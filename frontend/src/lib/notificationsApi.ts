import { api } from './api'

export interface AriaNotification {
  id: string
  operator_name: string
  action: string
  har_file_name: string | null
  is_read: boolean
  created_at: string
}

export function getNotifications(unreadOnly = false, limit = 50): Promise<AriaNotification[]> {
  const params = new URLSearchParams({ limit: String(limit) })
  if (unreadOnly) params.set('unread_only', 'true')
  return api.get(`/notifications?${params.toString()}`)
}

export function getUnreadNotificationCount(): Promise<{ count: number }> {
  return api.get('/notifications/unread-count')
}

export function markNotificationRead(id: string): Promise<{ success: boolean }> {
  return api.post(`/notifications/${id}/read`)
}

export function markAllNotificationsRead(): Promise<{ marked: number }> {
  return api.post('/notifications/read-all')
}
