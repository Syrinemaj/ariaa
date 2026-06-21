import { api } from './api'

// ── Types ─────────────────────────────────────────────────────────────────────

export interface GlobalSummary {
  total_automation_runs: number
  dry_runs: number
  real_runs: number
  total_steps: number
  total_success: number
  total_failed: number
  global_success_rate: number     // 0-1
  status_breakdown: Record<string, number>
}

export interface AutomationRun {
  id: string
  workflow_name: string
  dry_run: boolean
  status: string
  total_steps: number
  success_count: number
  failed_count: number
  duration_seconds?: number
  created_at: string
  updated_at?: string
  instruction?: string
}

export interface StepLog {
  step_order: number
  method: string
  path: string
  status: string
  status_code: number | null
  request_payload: Record<string, unknown> | null
  response_payload: unknown | null
  error_message: string | null
}

export interface AutomationExecutionReport {
  automation_run_id: string
  analysis_run_id: string
  instruction: string
  workflow_name: string
  status: string
  dry_run: boolean
  total_steps: number
  success_count: number
  failed_count: number
  duration_seconds: number
  success_rate: number    // 0-1
  error_rate: number      // 0-1
  logs: StepLog[]
  errors: StepLog[]
  result: Record<string, unknown>
}

export interface AnalysisRunReport {
  analysis_run_id: string
  total_automation_runs: number
  total_steps: number
  total_success: number
  total_failed: number
  average_success_rate: number    // 0-1
}

// ── API calls ─────────────────────────────────────────────────────────────────

export function getSummary(): Promise<GlobalSummary> {
  return api.get<GlobalSummary>('/reports/summary')
}

export function listAutomationRuns(params?: { limit?: number; status?: string }) {
  const qs = params
    ? Object.entries(params)
        .filter(([, v]) => v !== undefined)
        .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
        .join('&')
    : ''
  return api.get<{ items: AutomationRun[]; total: number; page: number; page_size: number; total_pages: number }>(
    `/reports/runs${qs ? `?${qs}` : ''}`
  )
}

export function getAutomationReport(id: string): Promise<AutomationExecutionReport> {
  return api.get<AutomationExecutionReport>(`/reports/automation/${id}`)
}

export function getAnalysisReport(runId: string): Promise<AnalysisRunReport> {
  return api.get<AnalysisRunReport>(`/reports/run/${runId}`)
}
