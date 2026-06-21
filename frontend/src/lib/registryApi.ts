import { api } from './api'

// ── Types ─────────────────────────────────────────────────────────────────────

export interface AnalysisRun {
  id: string
  file_name: string
  status: string
  total_cleaned_api_calls: number
  total_normalized_endpoints: number
  total_schema_results: number
  created_at: string
  updated_at: string
  org_id: string
  created_by_user_id: string
}

export interface BackendWorkflow {
  id: string
  run_id: string
  name: string
  business_domain?: string
  confidence?: number
  steps: BackendWorkflowStep[]
}

export interface BackendWorkflowStep {
  order: number
  method: string
  path: string
  canonical: string
  action?: string
  depends: number[]
  risk: string
  auth: boolean
}

// ── API calls ─────────────────────────────────────────────────────────────────

export function listRuns(params?: { limit?: number; offset?: number; status?: string }) {
  const qs = params
    ? Object.entries(params)
        .filter(([, v]) => v !== undefined)
        .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
        .join('&')
    : ''
  return api.get<{ total: number; items: AnalysisRun[] }>(
    `/registry/runs${qs ? `?${qs}` : ''}`
  )
}

export function getRun(runId: string) {
  return api.get<AnalysisRun>(`/registry/runs/${runId}`)
}

export function getWorkflows(runId: string) {
  return api
    .get<{ run_id: string; total: number; workflows: BackendWorkflow[] }>(
      `/registry/runs/${runId}/workflows`
    )
    .then(r => r.workflows)
}
