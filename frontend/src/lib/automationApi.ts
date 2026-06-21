import { api } from './api'

// ── Types matching backend app/planner/models.py ───────────────────────────

export interface BackendPlanStep {
  order: number
  endpoint_id: string
  method: string
  path: string
  canonical_key: string
  action?: string
  business_domain?: string
  depends_on: string[]
  request_schema?: Record<string, unknown>
  response_schema?: Record<string, unknown>
  auth_required: boolean
  risk_level: string
}

export interface BackendBusinessIntent {
  instruction: string
  intent: string
  business_domain?: string
  quantity?: number
  entities: string[]
  action: string
  confidence: number
  requires_bulk_execution: boolean
  reason?: string
}

export interface BackendAutomationPlan {
  run_id: string
  instruction: string
  intent: BackendBusinessIntent
  workflow_name: string
  steps: BackendPlanStep[]
  requires_approval: boolean
  dry_run_default: boolean
  metadata: Record<string, unknown>
}

export interface BackendPlanValidationIssue {
  level: string
  message: string
  step_order?: number
  canonical_key?: string
}

export interface BackendPlanValidationResult {
  is_valid: boolean
  issues: BackendPlanValidationIssue[]
}

export interface CreatePlanResponse {
  plan: BackendAutomationPlan
  validation: BackendPlanValidationResult
}

export interface ExecutePlanResponse {
  automation_run_id: string
  status: string
  dry_run: boolean
  success_count: number
  failed_count: number
  total_steps: number
  result: Record<string, unknown>
}

// ── API calls ───────────────────────────────────────────────────────────────

export function createPlan(runId: string, instruction: string, topK: number) {
  return api.post<CreatePlanResponse>('/automation/plan', {
    run_id: runId,
    instruction,
    top_k: topK,
  })
}

export function executePlan(
  plan: BackendAutomationPlan,
  inputRows: Record<string, unknown>[],
  baseUrl: string,
  authHeaders: Record<string, string>,
  dryRun: boolean,
  approvalGranted: boolean,
) {
  return api.post<ExecutePlanResponse>('/automation/execute', {
    plan,
    input_rows: inputRows,
    base_url: baseUrl || undefined,
    auth_headers: authHeaders,
    dry_run: dryRun,
    approval_granted: approvalGranted,
  })
}
