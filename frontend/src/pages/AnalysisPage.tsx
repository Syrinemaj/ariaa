import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import AppLayout from '../components/layout/AppLayout'
import { MethodBadge } from '../components/aria/Badges'
import { useHarAnalysis } from '../hooks/useHarAnalysis'
import { useRun } from '../contexts/RunContext'
import { useToast } from '../contexts/ToastContext'
import { listRuns, AnalysisRun } from '../lib/registryApi'
import { Upload, Play, RefreshCw, Sparkles, Search, ArrowRight, FileCode2, Lock, Unlock, Database, Check, Network, Layers, Zap, Clock, List } from 'lucide-react'

const PIPELINE_STEPS = [
  'Cleaning HTTP requests',
  'Normalizing endpoints',
  'Inferring schemas',
  'Persisting to database',
  'Detecting workflows',
  'AI enrichment ',
]

export default function AnalysisPage() {
  const nav  = useNavigate()
  const { setActiveRun } = useRun()
  const { toast } = useToast()
  const [filename, setFilename] = useState('')
  const [file, setFile]         = useState<File | null>(null)
  const [query, setQuery]       = useState('')
  const [historyRuns, setHistoryRuns] = useState<AnalysisRun[]>([])
  const [progressStep, setProgressStep] = useState(0)
  const fileRef = useRef<HTMLInputElement>(null)
  const progressRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const {
    phase,
    result,
    endpoints,
    indexState,
    searchResults,
    searching,
    error,
    upload,
    triggerIndex,
    search,
  } = useHarAnalysis()

  const isLoading   = phase === 'uploading' || phase === 'processing'
  const showResults = phase === 'done' && result !== null
  const indexed     = indexState === 'done'

  // Animate progress steps while processing
  useEffect(() => {
    if (phase === 'processing') {
      setProgressStep(0)
      progressRef.current = setInterval(() => {
        setProgressStep(prev => (prev < PIPELINE_STEPS.length - 1 ? prev + 1 : prev))
      }, 2800)
    } else {
      if (progressRef.current) clearInterval(progressRef.current)
      if (phase === 'done') setProgressStep(PIPELINE_STEPS.length)
    }
    return () => { if (progressRef.current) clearInterval(progressRef.current) }
  }, [phase])

  // When analysis completes, update RunContext + show toast
  useEffect(() => {
    if (showResults && result) {
      setActiveRun({ id: result.run_id, name: filename || 'capture.har' })
      toast({
        type: 'success',
        message: `Analysis complete · ${result.normalized_endpoints} endpoints · ${result.saved_workflows} workflows`,
        action: { label: 'Explore →', onClick: () => nav(`/endpoints?run=${result.run_id}`) },
      })
      // Refresh history
      listRuns({ limit: 6 }).then(data => setHistoryRuns(data.items)).catch(() => {})
    }
  }, [showResults])

  // Load history on mount
  useEffect(() => {
    listRuns({ limit: 6 }).then(data => setHistoryRuns(data.items)).catch(() => {})
  }, [])

  function handleFileSelect(f: File) {
    setFile(f)
    setFilename(f.name)
  }

  function statusIcon(s: string) {
    if (s === 'completed' || s === 'done') return '✦'
    if (s === 'processing' || s === 'running') return '◌'
    if (s === 'failed') return '✕'
    return '○'
  }
  function statusColor(s: string) {
    if (s === 'completed' || s === 'done') return 'text-violet-500'
    if (s === 'processing' || s === 'running') return 'text-amber-500'
    if (s === 'failed') return 'text-red-500'
    return 'ink-2'
  }

  return (
    <AppLayout>
      <div className="p-6 space-y-6">
        <div className="flex items-end justify-between gap-4 flex-wrap">
          <div>
            <h2 className="text-xl font-black" style={{ color: 'var(--ink)' }}>Analyze a HAR file</h2>
            <p className="text-sm ink-2 mt-1">Upload a .har / .jmx file to discover your endpoints, infer schemas, and detect workflows.</p>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => nav('/rag')} className="btn-secondary"><Sparkles className="w-4 h-4" /> Endpoint Search</button>
            <button onClick={() => nav('/openapi')} className="btn-secondary"><FileCode2 className="w-4 h-4" /> View OpenAPI</button>
          </div>
        </div>

        {/* Upload zone */}
        <div className="card overflow-hidden">
          <div className="grid lg:grid-cols-[1.2fr_1fr]">
            <div className="p-6">
              <input ref={fileRef} type="file" accept=".har,.jmx" className="hidden"
                onChange={e => { const f = e.target.files?.[0]; if (f) handleFileSelect(f) }} />
              <div onClick={() => fileRef.current?.click()}
                onDragOver={e => e.preventDefault()}
                onDrop={e => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) handleFileSelect(f) }}
                className="cursor-pointer rounded-2xl border-2 border-dashed p-8 text-center transition"
                style={{ borderColor: 'var(--line)', background: 'color-mix(in oklch, var(--brand) 3%, var(--card))' }}
                onMouseEnter={e => (e.currentTarget.style.borderColor = 'var(--brand)')}
                onMouseLeave={e => (e.currentTarget.style.borderColor = 'var(--line)')}>
                <div className="w-14 h-14 rounded-2xl grad-bg mx-auto flex items-center justify-center mb-4 shadow-lg">
                  <Upload className="w-6 h-6 text-white" />
                </div>
                <p className="font-semibold" style={{ color: 'var(--ink)' }}>Drop your .har file here</p>
                <p className="text-xs ink-2 mt-1">or click to browse · .har, .jmx</p>
                {filename && (
                  <div className="mt-4 inline-flex items-center gap-2 px-3 py-1.5 rounded-xl text-xs font-mono"
                    style={{ background: 'var(--card)', border: '1px solid var(--line)', color: 'var(--ink)' }}>
                    {filename}
                  </div>
                )}
              </div>
              <div className="mt-4">
                <label className="block text-xs font-semibold uppercase tracking-wider mb-1.5 ink-2">HAR file name</label>
                <input type="text" value={filename} onChange={e => setFilename(e.target.value)}
                  placeholder="e.g. capture-prod-2026.har" className="input w-full" />
              </div>
              {phase === 'error' && error && <p className="mt-3 text-xs text-red-600">{error}</p>}
              <div className="flex flex-wrap items-center gap-4 mt-4">
                <div className="flex-1" />
                <button onClick={() => file && void upload(file, filename)}
                  disabled={isLoading || !file} className="btn-primary">
                  {isLoading ? <><RefreshCw className="w-4 h-4 animate-spin" />Analyzing…</> : <><Play className="w-4 h-4" />Run analysis</>}
                </button>
              </div>
            </div>
            <div className="p-6" style={{ background: 'color-mix(in oklch, var(--ink) 3%, var(--card))', borderLeft: '1px solid var(--line)' }}>
              <p className="text-[10px] font-bold tracking-widest uppercase ink-2 mb-3">Pipeline</p>
              <ol className="space-y-2">
                {PIPELINE_STEPS.map((s, i) => {
                  const done    = phase === 'done' || progressStep > i
                  const current = phase === 'processing' && progressStep === i
                  return (
                    <li key={i} className="flex items-center gap-3 text-sm">
                      <span className={`w-6 h-6 rounded-lg text-xs font-bold flex items-center justify-center shrink-0 transition-all ${done ? 'grad-bg text-white' : current ? 'bg-amber-100 text-amber-700' : ''}`}
                        style={!done && !current ? { background: 'color-mix(in oklch, var(--ink) 8%, var(--card))', color: 'var(--ink-2)' } : {}}>
                        {done ? <Check className="w-3 h-3" /> : current ? <RefreshCw className="w-3 h-3 animate-spin" /> : i + 1}
                      </span>
                      <span style={{ color: done ? 'var(--ink)' : 'var(--ink-2)' }}>{s}</span>
                    </li>
                  )
                })}
              </ol>
            </div>
          </div>
        </div>

        {showResults && (
          <>
            {/* CTA block */}
            <div className="card pad flex flex-wrap items-center gap-3">
              <div className="flex-1 min-w-0">
                <p className="text-sm font-bold" style={{ color: 'var(--ink)' }}>Analysis complete — what would you like to do?</p>
                <p className="text-xs ink-2 mt-0.5">{result.normalized_endpoints} endpoints · {result.saved_workflows} workflows · ✦ AI enrichment active</p>
              </div>
              <button onClick={() => nav(`/endpoints?run=${result.run_id}`)} className="btn-primary">
                <Database className="w-4 h-4" /> Explore endpoints
              </button>
              <button onClick={() => nav(`/workflows?run=${result.run_id}`)} className="btn-secondary">
                <Network className="w-4 h-4" /> View workflows
              </button>
              <button onClick={() => nav(`/bulk?run=${result.run_id}`)} className="btn-secondary">
                <Zap className="w-4 h-4" /> Create a plan
              </button>
            </div>

            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              {[
                { l: 'Run ID',                v: result.run_id.slice(0, 8) },
                { l: 'Cleaned HTTP calls',    v: result.cleaned_api_calls.toLocaleString() },
                { l: 'Normalized endpoints',  v: result.normalized_endpoints.toString() },
                { l: 'Workflows detected',    v: result.saved_workflows.toString() },
              ].map((c, i) => (
                <div key={i} className="card p-3">
                  <p className="text-[10px] font-bold tracking-widest uppercase ink-2">{c.l}</p>
                  <p className="text-lg font-black mt-1" style={{ color: 'var(--ink)' }}>{c.v}</p>
                </div>
              ))}
            </div>

            {/* Endpoints preview */}
            <div className="card overflow-hidden">
              <div className="flex items-center justify-between px-5 pt-5 pb-3">
                <div>
                  <p className="text-sm font-bold" style={{ color: 'var(--ink)' }}>Endpoints detected</p>
                  <p className="text-xs ink-2">{result.normalized_endpoints} endpoints</p>
                </div>
                <button onClick={() => nav(`/endpoints?run=${result.run_id}`)} className="btn-ghost text-xs">Open catalog <ArrowRight className="w-3.5 h-3.5" /></button>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="aria-thead">
                    <tr>{['Method', 'Path', 'Canonical key', 'Domain · action', 'Auth', 'Statuses'].map(h => <th key={h} className="text-left px-3 py-2.5">{h}</th>)}</tr>
                  </thead>
                  <tbody>
                    {endpoints.slice(0, 8).map((e, i) => (
                      <tr key={e.id ?? i} className="border-t" style={{ borderColor: 'var(--line)' }}>
                        <td className="px-3 py-2.5"><MethodBadge m={e.method} /></td>
                        <td className="px-3 py-2.5 font-mono text-xs" style={{ color: 'var(--ink)' }}>{e.path}</td>
                        <td className="px-3 py-2.5 font-mono text-xs ink-2">{e.canonical_key}</td>
                        <td className="px-3 py-2.5 text-xs"><span className="font-semibold" style={{ color: 'var(--ink)' }}>{e.business_domain ?? '—'}</span><span className="ink-2"> · {e.business_action ?? '—'}</span></td>
                        <td className="px-3 py-2.5">{e.auth_required ? <Lock className="w-3.5 h-3.5 text-amber-500" /> : <Unlock className="w-3.5 h-3.5 text-emerald-500" />}</td>
                        <td className="px-3 py-2.5 font-mono text-xs ink-2">{e.status_codes.join(' · ')}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* RAG strip */}
            <div className="grid grid-cols-1 lg:grid-cols-[1fr_1.4fr] gap-4">
              <div className="card pad flex flex-col gap-4">
                <div>
                  <p className="text-sm font-bold" style={{ color: 'var(--ink)' }}>RAG indexing</p>
                  <p className="text-xs ink-2 mt-1">Embed {result.normalized_endpoints} endpoints for natural-language search.</p>
                </div>
                <div className="flex items-center gap-3">
                  <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${indexed ? 'bg-emerald-50 text-emerald-600' : ''}`}
                    style={indexed ? {} : { background: 'color-mix(in oklch, var(--ink) 6%, var(--card))', color: 'var(--ink-2)' }}>
                    {indexState === 'indexing'
                      ? <RefreshCw className="w-5 h-5 animate-spin" />
                      : indexed ? <Check className="w-5 h-5" />
                      : <Database className="w-5 h-5" />}
                  </div>
                  <div>
                    <p className="text-sm font-semibold" style={{ color: 'var(--ink)' }}>{indexed ? 'Indexed' : 'Not indexed'}</p>
                    <p className="text-xs font-mono ink-2">{indexed ? `${result.saved_endpoints} vectors` : '—'}</p>
                  </div>
                  <div className="flex-1" />
                  <button onClick={() => void triggerIndex()} disabled={indexState === 'indexing'}
                    className={indexed ? 'btn-secondary' : 'btn-primary'}>
                    {indexed ? <><RefreshCw className="w-3.5 h-3.5" /> Re-index</> : <><Sparkles className="w-3.5 h-3.5" /> Index for AI</>}
                  </button>
                </div>
                <p className="font-mono text-xs ink-2">POST /rag/index/{result.run_id}</p>
              </div>
              <div className="card pad">
                <p className="text-sm font-bold mb-1" style={{ color: 'var(--ink)' }}>Quick endpoint search</p>
                <p className="text-xs ink-2 mb-3">Find an endpoint using natural language.</p>
                <div className="flex items-center gap-2">
                  <div className="relative flex-1">
                    <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 ink-2" />
                    <input value={query} onChange={e => setQuery(e.target.value)}
                      onKeyDown={e => e.key === 'Enter' && void search(query)}
                      className="input !pl-9" placeholder="find users endpoints" />
                  </div>
                  <button onClick={() => void search(query)} disabled={searching} className="btn-primary">
                    {searching ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
                  </button>
                </div>
                <div className="mt-3 space-y-2">
                  {(searchResults.length > 0 ? searchResults : endpoints.slice(3, 6).map(e => ({ method: e.method, path: e.path, score: 0, endpoint: e }))).map((r, i) => (
                    <div key={i} className="flex items-center gap-3 p-2.5 rounded-xl" style={{ border: '1px solid var(--line)' }}>
                      <MethodBadge m={r.method} />
                      <span className="font-mono text-xs flex-1 truncate" style={{ color: 'var(--ink)' }}>{r.path}</span>
                      <span className="font-mono text-xs ink-2">{r.score > 0 ? r.score.toFixed(2) : ''}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </>
        )}

        {/* History — runs précédents */}
        {historyRuns.length > 0 && !showResults && (
          <div className="card overflow-hidden">
            <div className="flex items-center justify-between px-5 pt-5 pb-3">
              <div>
                <p className="text-sm font-bold" style={{ color: 'var(--ink)' }}>Previous analyses</p>
                <p className="text-xs ink-2">{historyRuns.length} recent runs · click to explore</p>
              </div>
              <button onClick={() => nav('/runs')} className="btn-ghost text-xs">
                <List className="w-3.5 h-3.5" /> View all <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </div>
            <div className="divide-y" style={{ borderColor: 'var(--line)' }}>
              {historyRuns.map(r => (
                <div key={r.id} className="flex items-center gap-4 px-5 py-3 transition cursor-pointer"
                  onMouseEnter={e => (e.currentTarget.style.background = 'color-mix(in oklch, var(--brand) 4%, var(--card))')}
                  onMouseLeave={e => (e.currentTarget.style.background = '')}
                  onClick={() => nav(`/endpoints?run=${r.id}`)}>
                  <span className={`text-lg font-bold shrink-0 ${statusColor(r.status)}`}>{statusIcon(r.status)}</span>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold truncate" style={{ color: 'var(--ink)' }}>{r.file_name}</p>
                    <p className="text-xs ink-2">{r.total_normalized_endpoints} endpoints · {new Date(r.created_at).toLocaleDateString()}</p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <button onClick={e => { e.stopPropagation(); nav(`/endpoints?run=${r.id}`) }} className="btn-ghost text-xs">
                      <Database className="w-3.5 h-3.5" /> Endpoints
                    </button>
                    <button onClick={e => { e.stopPropagation(); nav(`/workflows?run=${r.id}`) }} className="btn-ghost text-xs">
                      <Network className="w-3.5 h-3.5" /> Workflows
                    </button>
                    <button onClick={e => { e.stopPropagation(); nav(`/bulk?run=${r.id}`) }} className="btn-ghost text-xs">
                      <Layers className="w-3.5 h-3.5" /> Bulk
                    </button>
                  </div>
                  <Clock className="w-4 h-4 ink-2 shrink-0" />
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </AppLayout>
  )
}
