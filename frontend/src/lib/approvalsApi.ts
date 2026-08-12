import { api } from './api'

// ── Types ─────────────────────────────────────────────────────────────────────

export interface BackendApprovalRun {
  id: string
  workflow_name: string
  dry_run: boolean
  status: string
  total_steps: number
  success_count: number
  failed_count: number
  duration_seconds?: number
  created_at: string
}

export interface BackendApproval {
  id: string
  automation_run_id: string
  status: string
  approved_by?: string
  comment?: string
  approved_at?: string
  created_at: string
  run?: BackendApprovalRun
}

// ── API calls ─────────────────────────────────────────────────────────────────

export function listApprovals(status: string = 'pending') {
  return api
    .get<{ items: BackendApproval[]; total: number }>(`/approvals?status=${status}`)
    .then(r => r.items)
}

export function approveApproval(id: string, comment?: string) {
  return api.post<void>(`/approvals/${id}/approve`, { comment })
}

export function rejectApproval(id: string, reason: string) {
  return api.post<void>(`/approvals/${id}/reject`, { reason })
}
