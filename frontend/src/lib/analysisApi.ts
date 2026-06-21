import { api } from './api'

// ── Response types ────────────────────────────────────────────────────────────

export interface AnalyzeJobResponse {
  job_id: string
  status: string
  file_name: string
  message: string
}

export interface JobResult {
  run_id: string
  cleaned_api_calls: number
  normalized_endpoints: number
  schema_results: number
  saved_endpoints: number
  saved_workflows: number
  workflow_names: string[]
}

export interface JobStatus {
  job_id: string
  status: 'queued' | 'processing' | 'completed' | 'failed'
  updated_at: string | null
  result?: JobResult
  error?: string
}

export interface RunEndpoint {
  id: string
  method: string
  path: string
  canonical_key: string
  business_domain: string | null
  business_action: string | null
  auth_required: boolean | null
  auth_type: string | null
  status_codes: number[]
  risk: string
  confidence: number
  ai_summary: string | null
  ai_description: string | null
  ai_tags: string[]
  ai_confidence: number | null
}

export interface HarTokenEstimate {
  model: string
  har_stats: {
    total_entries: number
    min_api_candidates: number
    max_api_candidates: number
    min_unique_endpoints: number
    max_unique_endpoints: number
  }
  min_estimate: {
    api_candidates: number
    unique_endpoints: number
    total_tokens: number
    estimated_cost_usd: number
    breakdown: Record<string, number>
  }
  max_estimate: {
    api_candidates: number
    unique_endpoints: number
    total_tokens: number
    estimated_cost_usd: number
    breakdown: Record<string, number>
  }
}

export interface RagSearchResult {
  endpoint: RunEndpoint
  score: number
  method: string
  path: string
}

// ── API calls ─────────────────────────────────────────────────────────────────

export function analyzeHar(file: File, label?: string): Promise<AnalyzeJobResponse> {
  const form = new FormData()
  form.append('file', file)
  if (label?.trim()) form.append('label', label.trim())
  return api.post('/upload/har/analyze', form)
}

export function pollJob(jobId: string): Promise<JobStatus> {
  return api.get(`/jobs/${jobId}`)
}

export function getRunEndpoints(runId: string): Promise<{ total: number; endpoints: RunEndpoint[] }> {
  return api.get(`/registry/runs/${runId}/endpoints`)
}

export function estimateHarTokens(file: File): Promise<HarTokenEstimate> {
  const form = new FormData()
  form.append('file', file)
  return api.post('/llm/estimate/har', form)
}

export function indexRunEmbeddings(runId: string): Promise<{ run_id: string; indexed_embeddings: number }> {
  return api.post(`/rag/index/${runId}`)
}

export function ragSearch(
  query: string,
  runId: string,
  topK = 5,
): Promise<{ query: string; results: RagSearchResult[] }> {
  return api.post('/rag/search', { query, run_id: runId, top_k: topK })
}
