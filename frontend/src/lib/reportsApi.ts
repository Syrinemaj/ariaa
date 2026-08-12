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

export interface DailyTrendPoint {
  date: string    // YYYY-MM-DD
  count: number
}

export interface KpiWindow {
  current: number
  previous: number
}

export interface KpiTrends {
  window_days: number
  analysis_runs: KpiWindow
  endpoints_catalogued: KpiWindow
  automation_runs: KpiWindow
  global_success_rate: KpiWindow    // 0-1
}

// ── API calls ─────────────────────────────────────────────────────────────────

export function getSummary(): Promise<GlobalSummary> {
  return api.get<GlobalSummary>('/reports/summary')
}

export function getDailyTrend(days = 30): Promise<DailyTrendPoint[]> {
  return api.get<DailyTrendPoint[]>(`/reports/daily?days=${days}`)
}

export function getKpiTrends(windowDays = 7): Promise<KpiTrends> {
  return api.get<KpiTrends>(`/reports/kpi-trends?window_days=${windowDays}`)
}

export function listAutomationRuns(params?: { limit?: number; page?: number; status?: string }) {
  // Backend /reports/runs paginates via page/page_size (see app/core/pagination.py) —
  // `limit` here maps to page_size for callers that only care about a cap.
  const query: Record<string, string> = {}
  if (params?.status) query.status = params.status
  if (params?.limit !== undefined) query.page_size = String(params.limit)
  if (params?.page !== undefined) query.page = String(params.page)
  const qs = new URLSearchParams(query).toString()
  return api.get<{ items: AutomationRun[]; total: number; page: number; page_size: number; total_pages: number }>(
    `/reports/runs${qs ? `?${qs}` : ''}`
  )
}

export function getAutomationReport(id: string): Promise<AutomationExecutionReport> {
  return api.get<AutomationExecutionReport>(`/reports/automation/${id}`)
}

export function updateAutomationRun(id: string, body: { workflow_name?: string }): Promise<{ id: string; workflow_name: string }> {
  return api.patch<{ id: string; workflow_name: string }>(`/reports/automation-runs/${id}`, body)
}

export function deleteAutomationRun(id: string): Promise<void> {
  return api.del(`/reports/automation-runs/${id}`)
}

export function getAnalysisReport(runId: string): Promise<AnalysisRunReport> {
  return api.get<AnalysisRunReport>(`/reports/run/${runId}`)
}
