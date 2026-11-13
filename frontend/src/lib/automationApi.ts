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

// Matches app/automation/payload_mapper.py::required_input_fields() — fields
// the operator must actually supply, i.e. NOT already covered by an explicit
// field_mapping rule or auto-resolved from an earlier step's response
// (e.g. employee_id after a "Create Employee" step never appears here).
export interface RequiredInputField {
  field: string
  type: string
  first_needed_at_step: number
}

export interface CreatePlanResponse {
  plan: BackendAutomationPlan
  validation: BackendPlanValidationResult
  required_input_fields: RequiredInputField[]
}

// Matches app/automation/models.py::StepExecutionResult
export interface BackendStepExecutionResult {
  step_order: number
  method: string
  path: string
  url?: string | null
  status: string
  status_code?: number | null
  request_payload?: Record<string, unknown> | null
  response_payload?: unknown
  error_message?: string | null
  warnings: string[]
}

export interface ExecutePlanResponse {
  automation_run_id: string
  status: string
  dry_run: boolean
  success_count: number
  failed_count: number
  total_steps: number
  result: { results: BackendStepExecutionResult[]; metadata: Record<string, unknown> }
}

// ── API calls ───────────────────────────────────────────────────────────────

export function createPlan(runId: string, instruction: string, topK: number) {
  return api.post<CreatePlanResponse>('/automation/plan', {
    run_id: runId,
    instruction,
    top_k: topK,
  })
}

export interface ValidateTokenResponse {
  valid: boolean
  error_code: string | null
  message: string
  status_code: number | null
}

export function validateToken(
  baseUrl: string,
  tokenType: 'bearer' | 'api_key' | 'basic',
  tokenValue: string,
  probePath = '/',
): Promise<ValidateTokenResponse> {
  return api.post<ValidateTokenResponse>('/automation/validate-token', {
    base_url: baseUrl,
    token_type: tokenType,
    token_value: tokenValue,
    probe_path: probePath,
  })
}

export function planFromWorkflow(workflowId: string): Promise<CreatePlanResponse> {
  return api.post<CreatePlanResponse>('/automation/plan-from-workflow', { workflow_id: workflowId })
}

export function recordApproval(automationRunId: string, comment?: string): Promise<void> {
  return api.post(`/approvals/${encodeURIComponent(automationRunId)}/approve`, {
    comment: comment ?? null,
  })
}

export function executePlan(
  plan: BackendAutomationPlan,
  inputRows: Record<string, unknown>[],
  connectionId: string,
  dryRun: boolean,
  approvalGranted: boolean,
) {
  return api.post<ExecutePlanResponse>('/automation/execute', {
    plan,
    input_rows: inputRows,
    connection_id: connectionId,
    dry_run: dryRun,
    approval_granted: approvalGranted,
  })
}
