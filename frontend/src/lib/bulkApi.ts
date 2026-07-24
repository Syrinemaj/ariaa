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
}

export interface BatchSummary {
  batch_index: number
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
  baseUrl: string,
  authHeaders: Record<string, string>,
  dryRun: boolean,
  batchSize: number,
  allowPartial: boolean,
  approvalGranted: boolean,
): Promise<BulkExecuteResult> {
  return api.post('/bulk/execute', {
    plan,
    data_file_id: dataFileId,
    base_url: baseUrl,
    auth_headers: authHeaders,
    dry_run: dryRun,
    batch_size: batchSize,
    allow_partial_execution: allowPartial,
    approval_granted: approvalGranted,
  })
}

export function getBulkJobProgress(jobId: string): Promise<BulkJobProgress> {
  return api.get(`/jobs/${jobId}/progress`)
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
