import { useCallback, useEffect, useState } from 'react'
import AppLayout from '../components/layout/AppLayout'
import { OPENAPI_DOC } from '../lib/aria-data'
import { api } from '../lib/api'
import { listRuns, AnalysisRun } from '../lib/registryApi'
import { RefreshCw, Copy, Download } from 'lucide-react'

function JsonNode({ data, depth = 0 }: { data: unknown; depth?: number }) {
  const [open, setOpen] = useState(true)
  if (data === null) return <span className="text-rose-500">null</span>
  if (typeof data === 'boolean') return <span className="text-amber-500">{String(data)}</span>
  if (typeof data === 'number') return <span className="text-sky-500">{data}</span>
  if (typeof data === 'string') return <span className="text-emerald-500">&quot;{data}&quot;</span>
  if (Array.isArray(data)) {
    if (!data.length) return <span className="ink-2">[]</span>
    return <span><button onClick={() => setOpen(o => !o)} className="ink-2">[{!open && `…${data.length}]`}</button>{open && <><div style={{ marginLeft: (depth + 1) * 14 }}>{data.map((item, i) => <div key={i}><JsonNode data={item} depth={depth + 1} />{i < data.length - 1 && <span className="ink-2">,</span>}</div>)}</div><span className="ink-2">]</span></>}</span>
  }
  if (typeof data === 'object') {
    const entries = Object.entries(data as Record<string, unknown>)
    if (!entries.length) return <span className="ink-2">{'{}'}</span>
    return <span><button onClick={() => setOpen(o => !o)} className="ink-2">{'{'}{!open && `…${entries.length}}`}</button>{open && <><div style={{ marginLeft: (depth + 1) * 14 }}>{entries.map(([k, v], i) => <div key={k}><span style={{ color: 'var(--brand)' }}>&quot;{k}&quot;</span><span className="ink-2">: </span><JsonNode data={v} depth={depth + 1} />{i < entries.length - 1 && <span className="ink-2">,</span>}</div>)}</div><span className="ink-2">{'}'}</span></>}</span>
  }
  return <span style={{ color: 'var(--ink)' }}>{String(data)}</span>
}

export default function OpenAPIPage() {
  const [runs, setRuns]     = useState<AnalysisRun[]>([])
  const [runId, setRunId]   = useState('')
  const [doc, setDoc]       = useState<unknown>(OPENAPI_DOC)
  const [loading, setLoading] = useState(false)
  const [copied, setCopied] = useState(false)

  const fetchDoc = useCallback(async (id: string) => {
    if (!id) return
    setLoading(true)
    try {
      const data = await api.get<unknown>(`/openapi/spec/${id}`)
      setDoc(data)
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
            <span className="text-[10px] font-bold tracking-widest uppercase ink-2">run_id</span>
            {/* Run selector — dropdown if runs loaded, manual input as fallback */}
            {runs.length > 0 ? (
              <select value={runId} onChange={e => { setRunId(e.target.value); void fetchDoc(e.target.value) }}
                className="input !py-1.5 max-w-[280px] font-mono text-xs">
                {runs.map(r => <option key={r.id} value={r.id}>{r.file_name} — {r.id.slice(0, 8)}</option>)}
              </select>
            ) : (
              <input value={runId} onChange={e => setRunId(e.target.value)}
                className="input !py-1.5 max-w-[280px] font-mono text-xs" placeholder="run_id…" />
            )}
            <span className="pill bg-emerald-50 text-emerald-700 border-emerald-200">openapi 3.1.0</span>
            <span className="pill" style={{ background: 'color-mix(in oklch, var(--ink) 4%, var(--card))', borderColor: 'var(--line)', color: 'var(--ink-2)' }}>
              {typeof doc === 'object' && doc && 'paths' in (doc as Record<string, unknown>)
                ? `${Object.keys((doc as Record<string, unknown>).paths as object).length} paths`
                : '—'}
            </span>
            <span className="ml-auto text-xs font-mono ink-2">~{(docStr.length / 1024).toFixed(1)} KB</span>
          </div>
          <div className="p-4 overflow-x-auto max-h-[600px] overflow-y-auto"
            style={{ background: 'color-mix(in oklch, var(--ink) 2%, var(--card))' }}>
            {loading ? (
              <p className="text-sm ink-2 text-center py-8">Loading OpenAPI spec…</p>
            ) : (
              <pre className="font-mono text-sm leading-relaxed" style={{ color: 'var(--ink)' }}>
                <JsonNode data={doc} />
              </pre>
            )}
          </div>
        </div>
      </div>
    </AppLayout>
  )
}
