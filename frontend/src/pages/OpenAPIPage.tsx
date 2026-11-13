import { useCallback, useEffect, useMemo, useState } from 'react'
import AppLayout from '../components/layout/AppLayout'
import { OPENAPI_DOC } from '../lib/aria-data'
import { api } from '../lib/api'
import { listRuns, AnalysisRun } from '../lib/registryApi'
import { RefreshCw, Copy, Download, Maximize2, Minimize2 } from 'lucide-react'

// Specs at or below this many paths render fully expanded by default — for
// a normal analysis run (tens of endpoints) nothing is hidden behind a
// click. Above it, default back to the lazy 2-level behavior: a 100+-
// endpoint doc has tens of thousands of JSON nodes, and mounting every one
// open (each with its own useState) is what actually made this page slow,
// not spec generation itself (~0.3s). Either way, Expand all/Collapse all
// below overrides this for a one-off look at a large doc.
const AUTO_EXPAND_PATH_THRESHOLD = 30

function JsonNode({ data, depth = 0, maxOpenDepth }: { data: unknown; depth?: number; maxOpenDepth: number }) {
  const [open, setOpen] = useState(depth < maxOpenDepth)
  if (data === null) return <span className="text-rose-500">null</span>
  if (typeof data === 'boolean') return <span className="text-amber-500">{String(data)}</span>
  if (typeof data === 'number') return <span className="text-sky-500">{data}</span>
  if (typeof data === 'string') return <span className="text-emerald-500">&quot;{data}&quot;</span>
  if (Array.isArray(data)) {
    if (!data.length) return <span className="ink-2">[]</span>
    return <span><button onClick={() => setOpen(o => !o)} className="ink-2">[{!open && `…${data.length}]`}</button>{open && <><div style={{ marginLeft: (depth + 1) * 14 }}>{data.map((item, i) => <div key={i}><JsonNode data={item} depth={depth + 1} maxOpenDepth={maxOpenDepth} />{i < data.length - 1 && <span className="ink-2">,</span>}</div>)}</div><span className="ink-2">]</span></>}</span>
  }
  if (typeof data === 'object') {
    const entries = Object.entries(data as Record<string, unknown>)
    if (!entries.length) return <span className="ink-2">{'{}'}</span>
    return <span><button onClick={() => setOpen(o => !o)} className="ink-2">{'{'}{!open && `…${entries.length}}`}</button>{open && <><div style={{ marginLeft: (depth + 1) * 14 }}>{entries.map(([k, v], i) => <div key={k}><span style={{ color: 'var(--brand)' }}>&quot;{k}&quot;</span><span className="ink-2">: </span><JsonNode data={v} depth={depth + 1} maxOpenDepth={maxOpenDepth} />{i < entries.length - 1 && <span className="ink-2">,</span>}</div>)}</div><span className="ink-2">{'}'}</span></>}</span>
  }
  return <span style={{ color: 'var(--ink)' }}>{String(data)}</span>
}

export default function OpenAPIPage() {
  const [runs, setRuns]     = useState<AnalysisRun[]>([])
  const [runId, setRunId]   = useState('')
  const [doc, setDoc]       = useState<unknown>(OPENAPI_DOC)
  const [loading, setLoading] = useState(false)
  const [copied, setCopied] = useState(false)
  // 'auto' = size-based default (see AUTO_EXPAND_PATH_THRESHOLD); 'all'/'none'
  // = explicit override from the Expand all/Collapse all button below.
  const [expandMode, setExpandMode] = useState<'auto' | 'all' | 'none'>('auto')

  const fetchDoc = useCallback(async (id: string) => {
    if (!id) return
    setLoading(true)
    try {
      const data = await api.get<unknown>(`/openapi/spec/${id}`)
      setDoc(data)
      setExpandMode('auto')
    } catch {
      // Keep existing doc on error
    } finally {
      setLoading(false)
    }
  }, [])

  // Load runs on mount; auto-fetch doc for first run
  useEffect(() => {
    listRuns({ limit: 50 }).then(data => {
      setRuns(data.items)
      if (data.items.length > 0) {
        setRunId(data.items[0].id)
        void fetchDoc(data.items[0].id)
      }
    }).catch(() => {})
  }, [fetchDoc])

  const pathCount = useMemo(() => {
    if (typeof doc !== 'object' || !doc || !('paths' in (doc as Record<string, unknown>))) return 0
    return Object.keys((doc as Record<string, unknown>).paths as object).length
  }, [doc])

  const maxOpenDepth =
    expandMode === 'all'  ? Infinity :
    expandMode === 'none' ? 0 :
    pathCount <= AUTO_EXPAND_PATH_THRESHOLD ? Infinity : 2

  const docStr = JSON.stringify(doc, null, 2)

  return (
    <AppLayout>
      <div className="p-6 space-y-6">
        <div className="flex items-end justify-between gap-4 flex-wrap">
          <div>
            <h2 className="text-xl font-black" style={{ color: 'var(--ink)' }}>OpenAPI document</h2>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => void fetchDoc(runId)} disabled={loading || !runId} className="btn-secondary">
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} /> Refresh
            </button>
            <button onClick={() => { navigator.clipboard.writeText(docStr); setCopied(true); setTimeout(() => setCopied(false), 1500) }} className="btn-secondary">
              <Copy className="w-4 h-4" /> {copied ? 'Copied!' : 'Copy'}
            </button>
            <button onClick={() => { const u = URL.createObjectURL(new Blob([docStr], { type: 'application/json' })); Object.assign(document.createElement('a'), { href: u, download: 'openapi.json' }).click(); URL.revokeObjectURL(u) }} className="btn-primary">
              <Download className="w-4 h-4" /> Download
            </button>
          </div>
        </div>

        <div className="card overflow-hidden">
          <div className="p-4 flex flex-wrap items-center gap-3" style={{ borderBottom: '1px solid var(--line)' }}>
            
            {/* Run selector — dropdown if runs loaded, manual input as fallback */}
            {runs.length > 0 ? (
              <select value={runId} onChange={e => { setRunId(e.target.value); void fetchDoc(e.target.value) }}
                className="input !py-1.5 max-w-[280px] font-mono text-xs">
                {runs.map(r => <option key={r.id} value={r.id}>{r.file_name} — {r.id.slice(0, 8)}</option>)}
              </select>
            ) : (
              <input value={runId} onChange={e => setRunId(e.target.value)}
                className="input !py-1.5 max-w-[280px] font-mono text-xs" placeholder="run…" autoComplete="off" />
            )}
            <span className="pill bg-emerald-50 text-emerald-700 border-emerald-200">openapi 3.1.0</span>
            <span className="pill" style={{ background: 'color-mix(in oklch, var(--ink) 4%, var(--card))', borderColor: 'var(--line)', color: 'var(--ink-2)' }}>
              {pathCount > 0 ? `${pathCount} paths` : '—'}
            </span>
            <button onClick={() => setExpandMode(m => m === 'all' ? 'none' : 'all')} className="btn-secondary !py-1.5">
              {expandMode === 'all'
                ? <><Minimize2 className="w-3.5 h-3.5" /> Collapse all</>
                : <><Maximize2 className="w-3.5 h-3.5" /> Expand all</>}
            </button>
            <span className="ml-auto text-xs font-mono ink-2">~{(docStr.length / 1024).toFixed(1)} KB</span>
          </div>
          <div className="p-4 overflow-x-auto max-h-[600px] overflow-y-auto"
            style={{ background: 'color-mix(in oklch, var(--ink) 2%, var(--card))' }}>
            {loading ? (
              <p className="text-sm ink-2 text-center py-8">Loading OpenAPI spec…</p>
            ) : (
              <pre className="font-mono text-sm leading-relaxed" style={{ color: 'var(--ink)' }}>
                <JsonNode key={`${runId}-${maxOpenDepth}`} data={doc} maxOpenDepth={maxOpenDepth} />
              </pre>
            )}
          </div>
        </div>
      </div>
    </AppLayout>
  )
}
