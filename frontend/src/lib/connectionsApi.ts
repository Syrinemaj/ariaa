import { api } from './api'

export interface Connection {
  id: string
  name: string
  base_url: string
  environment: 'test' | 'preprod' | 'prod'
  auth_type: 'service_account' | 'oauth_client_credentials' | 'api_key'
  status: 'active' | 'revoked'
  secret_rotated_at: string | null
  created_by: string | null
  created_at: string | null
  updated_at: string | null
  operator_ids?: string[]
}

export interface ConnectionTestResult {
  success: boolean
  status_code: number | null
  message: string
}

export function listConnections(): Promise<{ connections: Connection[] }> {
  return api.get('/connections')
}

export function getConnection(id: string): Promise<Connection> {
  return api.get(`/connections/${encodeURIComponent(id)}`)
}

export function createConnection(body: {
  name: string
  base_url: string
  environment: string
  auth_type: string
  secret: string
}): Promise<Connection> {
  return api.post('/connections', body)
}

export function updateConnection(
  id: string,
  body: { name?: string; base_url?: string; environment?: string; auth_type?: string },
): Promise<Connection> {
  return api.patch(`/connections/${encodeURIComponent(id)}`, body)
}

export function rotateConnectionSecret(id: string, secret: string): Promise<Connection> {
  return api.post(`/connections/${encodeURIComponent(id)}/rotate-secret`, { secret })
}

export function revokeConnection(id: string): Promise<Connection> {
  return api.post(`/connections/${encodeURIComponent(id)}/revoke`)
}

export function reactivateConnection(id: string): Promise<Connection> {
  return api.post(`/connections/${encodeURIComponent(id)}/reactivate`)
}

export function deleteConnection(id: string): Promise<void> {
  return api.del(`/connections/${encodeURIComponent(id)}`)
}

export function testConnection(id: string): Promise<ConnectionTestResult> {
  return api.post(`/connections/${encodeURIComponent(id)}/test`)
}

export function assignOperator(connectionId: string, userId: string): Promise<{ connection_id: string; user_id: string }> {
  return api.post(`/connections/${encodeURIComponent(connectionId)}/operators`, { user_id: userId })
}

export function unassignOperator(connectionId: string, userId: string): Promise<void> {
  return api.del(`/connections/${encodeURIComponent(connectionId)}/operators/${encodeURIComponent(userId)}`)
}
