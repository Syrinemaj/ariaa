import { useEffect, useState } from 'react'
import AppLayout from '../components/layout/AppLayout'
import { MethodBadge, SeverityBadge } from '../components/aria/Badges'
import { Risk } from '../lib/aria-data'
import { ragSearch } from '../lib/analysisApi'
import { listRuns, AnalysisRun } from '../lib/registryApi'
import { Sparkles, Search, RefreshCw, ChevronDown } from 'lucide-react'

const SUGGESTIONS = ["créer un employé", "révoquer un badge", "mettre à jour l'IBAN", "lister les employés", "rafraîchir le token"]

type RagResult = {
  method: string; path: string; canonical: string; domain: string; action: string
  score: number; embedding: string; risk: Risk; tags: string[]; samples: number
}

export default function RagPage() {
  const [query, setQuery]     = useState('create a new employee with payroll and badge')
  const [topK, setTopK]       = useState(5)
  const [runs, setRuns]       = useState<AnalysisRun[]>([])
  const [runId, setRunId]     = useState('')
  const [running, setRunning] = useState(false)
  const [expanded, setExpanded] = useState<number | null>(null)
  const [results, setResults] = useState<RagResult[]>([])

  // Load analysis runs for the selector
  useEffect(() => {
    listRuns({ limit: 50 }).then(data => {
      setRuns(data.items)
      if (data.items.length > 0) setRunId(data.items[0].id)
    }).catch(() => {})
  }, [])

  const search = async () => {
    if (!query.trim() || !runId) return
    setRunning(true)
    setExpanded(null)
    try {
      const data = await ragSearch(query, runId, topK)
      setResults(data.results.map(r => ({
        method:    r.method,
        path:      r.path,
        canonical: r.endpoint.canonical_key,
        domain:    r.endpoint.business_domain ?? '—',
        action:    r.endpoint.business_action ?? '—',
        score:     r.score,
        embedding: `${r.method} ${r.path} canonical=${r.endpoint.canonical_key} domain=${r.endpoint.business_domain ?? '—'} action=${r.endpoint.business_action ?? '—'}`,
        risk:      (r.endpoint.risk || 'low') as Risk,
        tags:      [],
        samples:   0,
      })))
    } catch {
      // keep existing results on error
    } finally {
      setRunning(false)
    }
  }

  // Run options for selector — fall back to run IDs if no label available
  const runOptions = runs.map(r => ({ id: r.id, label: r.file_name }))

  return (
    <AppLayout>
      <div className="p-6 space-y-6">
        <div>
          <h2 className="text-xl font-black" style={{ color: 'var(--ink)' }}>Endpoint Search</h2>
          <p className="text-sm ink-2 mt-1">Trouvez des endpoints en décrivant ce que vous voulez faire, en langage naturel.</p>
        </div>

        <div className="card pad">
          <div className="grid grid-cols-1 lg:grid-cols-[1.4fr_1fr_200px_auto] gap-3 items-end">
            <div>
              <p className="text-[10px] font-bold tracking-widest uppercase ink-2 mb-1.5">Requête</p>
              <div className="relative">
                <Sparkles className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--brand)' }} />
                <input value={query} onChange={e => setQuery(e.target.value)} onKeyDown={e => e.key === 'Enter' && void search()}
                  className="input !pl-9" placeholder="ex. révoquer un badge pour un employé licencié" />
              </div>
            </div>
            <div>
              <p className="text-[10px] font-bold tracking-widest uppercase ink-2 mb-1.5">Analyse source</p>
              <select value={runId} onChange={e => setRunId(e.target.value)} className="input appearance-none cursor-pointer">
                {runOptions.length === 0 && <option value="">— no runs —</option>}
                {runOptions.map(r => <option key={r.id} value={r.id}>{r.label}</option>)}
              </select>
            </div>
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-[10px] font-bold tracking-widest uppercase ink-2">Top K</span>
                <span className="text-xs font-mono" style={{ color: 'var(--ink)' }}>{topK}</span>
              </div>
              <input type="range" min="1" max="20" value={topK} onChange={e => setTopK(+e.target.value)} className="w-full" />
            </div>
            <button onClick={() => void search()} disabled={running || !runId} className="btn-primary">
              {running ? <><RefreshCw className="w-4 h-4 animate-spin" />Recherche…</> : <><Search className="w-4 h-4" />Rechercher</>}
            </button>
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-2 text-xs">
            <span className="ink-2">Essayer :</span>
            {SUGGESTIONS.map(s => (
              <button key={s} onClick={() => setQuery(s)}
                className="px-2.5 py-1 rounded-full transition" style={{ border: '1px solid var(--line)', color: 'var(--ink-2)' }}
                onMouseEnter={e => { (e.currentTarget as HTMLElement).style.color = 'var(--brand)'; (e.currentTarget as HTMLElement).style.borderColor = 'var(--brand)' }}
                onMouseLeave={e => { (e.currentTarget as HTMLElement).style.color = 'var(--ink-2)'; (e.currentTarget as HTMLElement).style.borderColor = 'var(--line)' }}>
                {s}
              </button>
            ))}
          </div>
        </div>

        {results.length === 0 && !running && (
          <p className="text-sm ink-2 text-center py-6">
            {runId ? 'Enter a query and click Rechercher to find endpoints.' : 'Select a run first, then search.'}
          </p>
        )}

        <div className="space-y-3">
          {results.map((r, i) => {
            const isOpen = expanded === i
            return (
              <div key={i} className="card overflow-hidden">
                <div className="p-4 flex flex-wrap items-center gap-3">
                  <div className="text-2xl font-black w-8 text-center grad-text">{i + 1}</div>
                  <MethodBadge m={r.method} />
                  <span className="font-mono text-sm flex-1 min-w-[200px]" style={{ color: 'var(--ink)' }}>{r.path}</span>
                  <span className="pill" style={{ background: 'color-mix(in oklch, var(--ink) 4%, var(--card))', borderColor: 'var(--line)', color: 'var(--ink-2)' }}>{r.domain}</span>
                  <span className="pill" style={{ background: 'color-mix(in oklch, var(--ink) 4%, var(--card))', borderColor: 'var(--line)', color: 'var(--ink-2)' }}>{r.action}</span>
                  <div className="flex items-center gap-2 min-w-[140px]">
                    <div className="flex-1 h-1.5 rounded-full overflow-hidden" style={{ background: 'var(--line)' }}>
                      <div className="h-1.5 rounded-full grad-bg" style={{ width: `${r.score * 100}%` }} />
                    </div>
                    <span className="font-mono text-xs" style={{ color: 'var(--ink)' }}>{r.score.toFixed(2)}</span>
                  </div>
                  <button onClick={() => setExpanded(isOpen ? null : i)} className="btn-ghost !p-1.5">
                    <ChevronDown className={`w-4 h-4 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
                  </button>
                </div>
                {isOpen && (
                  <div className="p-4 grid grid-cols-1 lg:grid-cols-2 gap-4" style={{ borderTop: '1px solid var(--line)', background: 'color-mix(in oklch, var(--brand) 2%, var(--card))' }}>
                    <div>
                      <p className="text-[10px] font-bold tracking-widest uppercase ink-2 mb-2">Texte d&apos;embedding</p>
                      <pre className="font-mono text-xs whitespace-pre-wrap p-3 rounded-xl" style={{ background: 'color-mix(in oklch, var(--ink) 4%, var(--card))', color: 'var(--ink)', border: '1px solid var(--line)' }}>
                        {r.embedding}
                      </pre>
                    </div>
                    <div>
                      <p className="text-[10px] font-bold tracking-widest uppercase ink-2 mb-2">Contexte</p>
                      <div className="space-y-2 text-xs">
                        {[['canonical', r.canonical], ['tags', r.tags.join(', ') || '—'], ['échantillons', r.samples]].map(([k, v]) => (
                          <div key={String(k)} className="flex justify-between p-2 rounded-xl" style={{ background: 'var(--card)', border: '1px solid var(--line)' }}>
                            <span className="ink-2">{k}</span><span className="font-mono" style={{ color: 'var(--ink)' }}>{String(v)}</span>
                          </div>
                        ))}
                        <div className="flex justify-between p-2 rounded-xl" style={{ background: 'var(--card)', border: '1px solid var(--line)' }}>
                          <span className="ink-2">risque</span><SeverityBadge s={r.risk} />
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>

        <div className="card pad text-xs space-y-1">
          <p className="text-[10px] font-bold tracking-widest uppercase ink-2">Détails techniques</p>
          <p className="font-mono"><span className="ink-2">run_id</span> <span style={{ color: 'var(--ink)' }}>{runId || '—'}</span></p>
          <p className="font-mono"><span className="ink-2">Endpoint</span> <span style={{ color: 'var(--ink)' }}>POST /rag/search</span></p>
          <p className="font-mono"><span className="ink-2">top_k</span> <span style={{ color: 'var(--ink)' }}>{topK}</span></p>
        </div>
      </div>
    </AppLayout>
  )
}
