import { api } from './api'

export type EnvironmentPolicyMode = 'full_access' | 'writes_require_approval' | 'read_only' | 'forbidden'

export interface GovernancePolicy {
  id: string
  risk_threshold_low: number
  risk_threshold_high: number
  environment_policies: Record<'test' | 'preprod' | 'prod', EnvironmentPolicyMode>
  updated_by: string | null
  updated_at: string | null
}

export interface ForbiddenEndpointRule {
  id: string
  method: string | null
  path_pattern: string
  created_by: string | null
  created_at: string | null
}

export function getPolicy(): Promise<GovernancePolicy> {
  return api.get('/governance/policy')
}

export function updatePolicy(body: {
  risk_threshold_low?: number
  risk_threshold_high?: number
  environment_policies?: Partial<Record<'test' | 'preprod' | 'prod', EnvironmentPolicyMode>>
}): Promise<GovernancePolicy> {
  return api.patch('/governance/policy', body)
}

export function listForbiddenRules(): Promise<{ rules: ForbiddenEndpointRule[] }> {
  return api.get('/governance/forbidden-rules')
}

export function createForbiddenRule(body: { method?: string; path_pattern: string }): Promise<ForbiddenEndpointRule> {
  return api.post('/governance/forbidden-rules', body)
}

export function deleteForbiddenRule(id: string): Promise<void> {
  return api.del(`/governance/forbidden-rules/${encodeURIComponent(id)}`)
}
