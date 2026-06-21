import { useCallback, useEffect, useRef, useState } from 'react'
import {
  analyzeHar,
  estimateHarTokens,
  getRunEndpoints,
  HarTokenEstimate,
  indexRunEmbeddings,
  JobResult,
  pollJob,
  ragSearch,
  RagSearchResult,
  RunEndpoint,
} from '../lib/analysisApi'

export type AnalysisPhase = 'idle' | 'estimating' | 'uploading' | 'processing' | 'done' | 'error'
export type IndexState = 'idle' | 'indexing' | 'done' | 'error'

const POLL_INTERVAL_MS = 2_000

export function useHarAnalysis() {
  const [phase, setPhase]               = useState<AnalysisPhase>('idle')
  const [jobId, setJobId]               = useState<string | null>(null)
  const [result, setResult]             = useState<JobResult | null>(null)
  const [endpoints, setEndpoints]       = useState<RunEndpoint[]>([])
  const [tokenEstimate, setTokenEstimate] = useState<HarTokenEstimate | null>(null)
  const [indexState, setIndexState]     = useState<IndexState>('idle')
  const [searchResults, setSearchResults] = useState<RagSearchResult[]>([])
  const [searching, setSearching]       = useState(false)
  const [error, setError]               = useState<string | null>(null)

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }, [])

  // Called on file select — estimates token usage before upload (non-blocking)
  const estimate = useCallback(async (file: File) => {
    setTokenEstimate(null)
    setPhase('estimating')
    try {
      const est = await estimateHarTokens(file)
      setTokenEstimate(est)
    } catch {
      // Estimation failure is not critical — just hide the widget
    }
    setPhase('idle')
  }, [])

  // Upload file and start polling
  const upload = useCallback(async (file: File, label?: string) => {
    stopPolling()
    setPhase('uploading')
    setError(null)
    setResult(null)
    setEndpoints([])
    setSearchResults([])
    setIndexState('idle')

    try {
      const job = await analyzeHar(file, label)
      setJobId(job.job_id)
      setPhase('processing')

      pollRef.current = setInterval(async () => {
        try {
          const status = await pollJob(job.job_id)

          if (status.status === 'completed' && status.result) {
            stopPolling()
            setResult(status.result)
            setPhase('done')
            // Fetch endpoint preview in background — failure is silent
            getRunEndpoints(status.result.run_id)
              .then(r => setEndpoints(r.endpoints.slice(0, 10)))
              .catch(() => {})
          } else if (status.status === 'failed') {
            stopPolling()
            setError(status.error ?? 'Pipeline failed')
            setPhase('error')
          }
        } catch (pollErr) {
          stopPolling()
          setError(pollErr instanceof Error ? pollErr.message : 'Polling failed')
          setPhase('error')
        }
      }, POLL_INTERVAL_MS)
    } catch (err) {
      setPhase('error')
      setError(err instanceof Error ? err.message : 'Upload failed')
    }
  }, [stopPolling])

  const triggerIndex = useCallback(async () => {
    if (!result?.run_id) return
    setIndexState('indexing')
    try {
      await indexRunEmbeddings(result.run_id)
      setIndexState('done')
    } catch {
      setIndexState('error')
    }
  }, [result])

  const search = useCallback(async (query: string) => {
    if (!result?.run_id || !query.trim()) return
    setSearching(true)
    try {
      const res = await ragSearch(query, result.run_id)
      setSearchResults(res.results)
    } catch {
      setSearchResults([])
    } finally {
      setSearching(false)
    }
  }, [result])

  const reset = useCallback(() => {
    stopPolling()
    setPhase('idle')
    setJobId(null)
    setResult(null)
    setEndpoints([])
    setTokenEstimate(null)
    setIndexState('idle')
    setSearchResults([])
    setSearching(false)
    setError(null)
  }, [stopPolling])

  useEffect(() => () => stopPolling(), [stopPolling])

  return {
    phase,
    jobId,
    result,
    endpoints,
    tokenEstimate,
    indexState,
    searchResults,
    searching,
    error,
    estimate,
    upload,
    triggerIndex,
    search,
    reset,
  }
}
