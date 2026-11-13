import { api } from './api'
import { BackendAutomationPlan } from './automationApi'

// ── Types matching backend services ──────────────────────────────────────────

export interface DataFileUploadResult {
  data_file_id: string
  file_name: string
  file_type: string
  rows_count: number
  columns: string[]
  preview: Record<string, unknown>[]
}

export interface MappingSuggestion {
  id: string | null
  source_field: string
  target_field: string | null
  target_endpoint?: string
  confidence: number
  source: string
  approved: boolean
}

export interface MappingResult {
  data_file_id: string
  columns: string[]
  mappings: MappingSuggestion[]
  validation: Record<string, unknown>
}

export interface ValidationError {
  row_index: number
  field_name?: string
  error_code: string
  message: string
}

export interface ValidationResult {
  validation_run_id: string
  data_file_id: string
  total_rows: number
  valid_rows: number
  invalid_rows: number
  ready_for_execution: boolean
  can_execute_partial: boolean
  errors: ValidationError[]
}

export interface DryRunResult {
  mode: string
  total_rows: number
  valid_rows: number
  invalid_rows: number
  steps_count: number
  estimated_api_calls: number
  estimated_duration_seconds: number
  ready_for_execution: boolean
  allow_partial_execution: boolean
  recommendation: string
}

export interface BulkExecuteResult {
  job_id: string
  automation_run_id: string
  status: string
  total_rows: number
  invalid_rows: number
  batches: number
  batches_enqueued: number
  batches_skipped: number
  message: string
}

export interface BulkJobProgress {
  job_id: string
  status: string
  total: number
  completed: number
  failed: number
  batches: number
  batches_done: number
  automation_run_id: string | null
  progress_pct: number
  dry_run: boolean
}

export interface BatchSummary {
  batch_number: number
  status: string
  success_count: number
  failed_count: number
  start_row?: number
  end_row?: number
}

export interface RowError {
  row_index: number
  error_code: string
  message: string
}

export interface BulkReport {
  bulk_report_id: string
  automation_run_id: string
  status: string
  success_count: number
  failed_count: number
  batch_summary: BatchSummary[]
  row_errors: RowError[]
  // Rows whose create hit a 409 "already exists" and were auto-resolved to
  // the existing record instead of failing — see
  // app/bulk_execution/conflict_resolution.py. Not failures: counted in
  // success_count, just worth showing separately from a brand-new create.
  duplicate_rows: RowError[]
}

// ── API calls ─────────────────────────────────────────────────────────────────

export function uploadDataFile(file: File, analysisRunId: string): Promise<DataFileUploadResult> {
  const form = new FormData()
  form.append('file', file)
  return api.post(`/bulk/data/upload?analysis_run_id=${encodeURIComponent(analysisRunId)}`, form)
}

export function suggestMapping(
  analysisRunId: string,
  dataFileId: string,
  plan: BackendAutomationPlan,
): Promise<MappingResult> {
  return api.post('/bulk/mapping/suggest', {
    analysis_run_id: analysisRunId,
    data_file_id: dataFileId,
    plan,
  })
}

export interface MappingApproveResult {
  id: string
  source_field: string
  target_field: string | null
  approved: boolean
}

export function approveMapping(mappingId: string, approved: boolean = true): Promise<MappingApproveResult> {
  return api.patch(`/bulk/mapping/${encodeURIComponent(mappingId)}/approve`, { approved })
}

export function validateBulk(
  analysisRunId: string,
  dataFileId: string,
  plan: BackendAutomationPlan,
): Promise<ValidationResult> {
  return api.post('/bulk/validate', {
    analysis_run_id: analysisRunId,
    data_file_id: dataFileId,
    plan,
  })
}

export function dryRunBulk(
  dataFileId: string,
  plan: BackendAutomationPlan,
  allowPartial: boolean,
): Promise<DryRunResult> {
  return api.post('/bulk/dry-run', {
    data_file_id: dataFileId,
    plan,
    allow_partial_execution: allowPartial,
  })
}

export function executeBulk(
  plan: BackendAutomationPlan,
  dataFileId: string,
  connectionId: string,
  dryRun: boolean,
  batchSize: number,
  allowPartial: boolean,
  approvalGranted: boolean,
): Promise<BulkExecuteResult> {
  return api.post('/bulk/execute', {
    plan,
    data_file_id: dataFileId,
    connection_id: connectionId,
    dry_run: dryRun,
    batch_size: batchSize,
    allow_partial_execution: allowPartial,
    approval_granted: approvalGranted,
  })
}

// Same call every time, on the first click AND every poll tick while waiting
// on admin approval — the backend (app/api/bulk.py) finds any existing
// "pending_approval" run for this exact data_file+user before creating a new
// one, so repeating it is "check the decision", not "submit again". See
// AutomationPage.tsx's callExecute for the identical pattern.
export interface BulkApprovalCheckResult {
  code: 'APPROVED' | 'NOT_REQUIRED'
  message: string
  automation_run_id: string | null
}

// Governance/approval check ONLY — never starts execution, even when the
// answer is "approved" (see app/api/bulk.py::request_bulk_approval). Used by
// the wizard's Approval step to request/poll real admin sign-off before the
// operator ever reaches the separate "Execute for real" step.
export function requestBulkApproval(
  plan: BackendAutomationPlan,
  dataFileId: string,
  connectionId: string,
): Promise<BulkApprovalCheckResult> {
  return api.post('/bulk/request-approval', {
    plan,
    data_file_id: dataFileId,
    connection_id: connectionId,
  })
}

export function executeBulkReal(
  plan: BackendAutomationPlan,
  dataFileId: string,
  connectionId: string,
  batchSize: number,
  allowPartial: boolean,
): Promise<BulkExecuteResult> {
  return api.post('/bulk/execute', {
    plan,
    data_file_id: dataFileId,
    connection_id: connectionId,
    dry_run: false,
    batch_size: batchSize,
    allow_partial_execution: allowPartial,
    approval_granted: true,
  })
}

export function getBulkJobProgress(jobId: string): Promise<BulkJobProgress> {
  return api.get(`/jobs/${jobId}/progress`)
}

// Cooperative cancel — in-flight rows finish, nothing new starts. See
// app/api/jobs.py::cancel_bulk_job for the full behavior.
export function cancelBulkJob(jobId: string): Promise<{ job_id: string; status: string }> {
  return api.post(`/jobs/${jobId}/cancel`)
}

export function getBulkReport(automationRunId: string): Promise<BulkReport> {
  return api.get(`/bulk/reports/${automationRunId}`)
}

export async function downloadRowErrorsCsv(automationRunId: string): Promise<void> {
  const blob = await api.blob(`/bulk/reports/${encodeURIComponent(automationRunId)}/errors.csv`)
  const url  = URL.createObjectURL(blob)
  const a    = document.createElement('a')
  a.href     = url
  a.download = `errors_${automationRunId.slice(0, 8)}.csv`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}
