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
  metadata?: Record<string, unknown>
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

export interface WorkflowStepInput {
  order: number
  method: string
  path: string
  canonical_key: string
  action?: string
  risk?: string
  auth?: boolean
}

export interface WorkflowUpdateInput {
  name?: string
  business_domain?: string
  steps?: WorkflowStepInput[]
}

export interface WorkflowCreateInput {
  name: string
  business_domain?: string
  steps: WorkflowStepInput[]
}

export function updateRun(runId: string, body: { file_name?: string }): Promise<{ id: string; file_name: string }> {
  return api.patch(`/registry/runs/${runId}`, body)
}

export function deleteRun(runId: string): Promise<void> {
  return api.del(`/registry/runs/${runId}`)
}

export function createWorkflow(runId: string, body: WorkflowCreateInput): Promise<BackendWorkflow> {
  return api.post(`/registry/runs/${runId}/workflows`, body)
}

export function updateWorkflow(workflowId: string, body: WorkflowUpdateInput): Promise<BackendWorkflow> {
  return api.patch(`/registry/workflows/${workflowId}`, body)
}

export function deleteWorkflow(workflowId: string): Promise<void> {
  return api.del(`/registry/workflows/${workflowId}`)
}

export function restoreWorkflow(workflowId: string): Promise<BackendWorkflow> {
  return api.post(`/registry/workflows/${workflowId}/restore`, {})
}
