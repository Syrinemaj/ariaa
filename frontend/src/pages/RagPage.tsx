import { useEffect, useState } from 'react'
import AppLayout from '../components/layout/AppLayout'
import { MethodBadge, SeverityBadge } from '../components/aria/Badges'
import { Risk } from '../lib/aria-data'
import { ragSearch, indexRunEmbeddings } from '../lib/analysisApi'
import { listRuns, AnalysisRun } from '../lib/registryApi'
import { Sparkles, Search, RefreshCw, ChevronDown, Cpu, Tag, AlignLeft, Layers, AlertCircle } from 'lucide-react'

// Parse "Key: value" lines from the embedding text into a structured map
function parseEmbedding(text: string): Record<string, string> {
  const map: Record<string, string> = {}
  const lines = text.split('\n')
  let current = ''
  for (const line of lines) {
    const colon = line.indexOf(': ')
    if (colon !== -1) {
      current = line.slice(0, colon).trim()
      map[current] = line.slice(colon + 2).trim()
    } else if (current && line.trim()) {
      map[current] += ' ' + line.trim()
    }
  }
  return map
}

const SUGGESTIONS = ["create an employee", "revoke a badge", "update the IBAN", "list employees", "refresh the token"]

const FILLER_WORDS = new Set([
  'bonjour','hello','salut','hi','hey','coucou','bonsoir','bonne nuit','bye','byebye',
  'test','ok','oui','non','rien','merci','thanks','thank','please','stp','sil vous plait',
  'lol','wtf','???','...',
])

function validateQuery(q: string): string {
  const t = q.trim()
  if (t.length < 4) return 'Query too short — describe an API action in a few words.'
  if (FILLER_WORDS.has(t.toLowerCase())) return 'This query does not match any API action.'
  if (!t.includes(' ') && t.length < 7) return 'Describe the action in a few words (e.g. "create an employee").'
  return ''
}

// Display-only rescale of the raw cosine score into a more legible
// "confidence" bar/percentage. Cohere Embed Multilingual v3 (the embedding
// provider — see app/core/config.py::EMBEDDING_PROVIDER) produces much lower
// raw cosine scores than the old BGE model even for confident, correct
// matches (measured empirically: ~0.70 for a well-separated match, as low as
// ~0.37 for a narrow-domain-but-correct one; garbage queries top out ~0.28).
// Showing the raw number directly made genuinely correct results look like a
// failing grade. Anchors: floor 0.30 (the backend's own relevance floor —
// app/core/config.py::PLAN_MIN_RAG_SCORE — nothing weaker is shown as
// "relevant" in the first place), ceiling 0.70 (the strongest match measured
// in validation). The raw score still drives ranking/filtering everywhere;
// this only changes what's drawn on screen.
const DISPLAY_SCORE_FLOOR = 0.30
const DISPLAY_SCORE_CEILING = 0.70
function displayConfidence(rawScore: number): number {
  return Math.max(0, Math.min(1, (rawScore - DISPLAY_SCORE_FLOOR) / (DISPLAY_SCORE_CEILING - DISPLAY_SCORE_FLOOR)))
}

type RagResult = {
  method: string; path: string; canonical: string; domain: string; action: string
  score: number; embedding: string; risk: Risk; tags: string[]; samples: number
  missingAspects: string[]
}

// How many nearest-neighbor candidates the embedding stage fetches before
// the relevance judge (app/rag/relevance_judge.py) filters them down to
// genuinely-matching ones. No longer a user-facing control — the judge runs
// on every search now (see RagPage history), so the final result count
// depends on real relevance, not this number; this only bounds how wide a
// net the first retrieval pass casts, which matters more on large real-world
// APIs (hundreds of endpoints) than on small demo runs.
const CANDIDATE_POOL_SIZE = 10

export default function RagPage() {
  const [query, setQuery]       = useState('')
  const [runs, setRuns]         = useState<AnalysisRun[]>([])
  const [runId, setRunId]       = useState('')
  const [running, setRunning]         = useState(false)
  const [indexing, setIndexing]       = useState(false)
  const [indexDone, setIndexDone]     = useState(false)
  const [expanded, setExpanded]       = useState<number | null>(null)
  const [results, setResults]         = useState<RagResult[]>([])
  const [hasSearched, setHasSearched] = useState(false)

  useEffect(() => {
    listRuns({ limit: 50 }).then(data => {
      setRuns(data.items)
      if (data.items.length > 0) setRunId(data.items[0].id)
    }).catch(() => {})
  }, [])

  const search = async () => {
    if (!query.trim() || !runId || validateQuery(query)) return
    setRunning(true)
    setExpanded(null)
    try {
      const data = await ragSearch(query, runId, CANDIDATE_POOL_SIZE)
      // The backend is the single source of truth for "is this relevant":
      // /rag/search already drops anything below score_threshold (default
      // 0.35 — app/rag/models.py::SemanticSearchRequest). A second,
      // score-based "low relevance" heuristic used to re-judge results that
      // had already cleared that bar, using thresholds tuned for the old
      // BGE embedding model — after the Cohere migration it flagged
      // essentially every query, including clearly correct ones (e.g. a
      // confident match could score as low as ~0.37 under Cohere, well
      // under the old 0.75 cutoff). Removed rather than re-tuned: nothing
      // the frontend can derive from the score shape is more reliable than
      // the backend's own filter. An empty result set (hasSearched &&
      // results.length === 0 below) already covers the real "nothing
      // relevant found" case.
      const mapped = data.results.map(r => ({
        method:    r.method,
        path:      r.path,
        canonical: r.canonical_key,
        domain:    r.business_domain ?? '—',
        action:    r.business_action ?? '—',
        score:     r.score,
        embedding: r.embedding_text,
        risk:      ((r.metadata?.risk as string) || 'low') as Risk,
        tags:      (r.metadata?.tags as string[]) || [],
        samples:   0,
        // Set by the backend relevance judge (app/rag/relevance_judge.py)
        // when this endpoint is the right core match but doesn't support
        // every specific thing named in the query (e.g. "create an
        // employee with payroll and badge" -> the create-employee
        // endpoint, but payroll/badge aren't real fields on it).
        missingAspects: (r.metadata?.missing_aspects as string[]) || [],
      }))
      setResults(mapped)
      setHasSearched(true)
    } catch {
      // keep existing results on error
    } finally {
      setRunning(false)
    }
  }

  const reindex = async () => {
    if (!runId || indexing) return
    setIndexing(true)
    setIndexDone(false)
    try {
      await indexRunEmbeddings(runId)
      setIndexDone(true)
      setTimeout(() => setIndexDone(false), 4000)
    } catch {
      // silent
    } finally {
      setIndexing(false)
    }
  }

  const runOptions = runs.map(r => ({ id: r.id, label: r.file_name }))

  return (
    <AppLayout>
      <div className="p-6 space-y-6">
        <div>
          <h2 className="text-xl font-black" style={{ color: 'var(--ink)' }}>Endpoint Search</h2>
          <p className="text-sm ink-2 mt-1">Find endpoints by describing what you want to do, in natural language.</p>
        </div>

        <div className="card pad">
          <div className="grid grid-cols-1 lg:grid-cols-[1.4fr_1fr_auto] gap-3 items-end">
            <div>
              <p className="text-[10px] font-bold tracking-widest uppercase ink-2 mb-1.5">Query</p>
              <div className="relative">
                <Sparkles className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--brand)' }} />
                <input value={query} onChange={e => setQuery(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && void search()}
                  className="input !pl-9" placeholder="e.g. revoke a badge for a terminated employee" autoComplete="off" />
              </div>
              {query.trim().length > 0 && validateQuery(query) && (
                <p className="mt-1 text-xs" style={{ color: '#f43f5e' }}>{validateQuery(query)}</p>
              )}
            </div>
            <div>
              <p className="text-[10px] font-bold tracking-widest uppercase ink-2 mb-1.5">Source analysis</p>
              <select value={runId} onChange={e => setRunId(e.target.value)} className="input appearance-none cursor-pointer">
                {runOptions.length === 0 && <option value="">— no runs —</option>}
                {runOptions.map(r => <option key={r.id} value={r.id}>{r.label}</option>)}
              </select>
            </div>
            <div className="flex gap-2">
              <button onClick={() => void search()} disabled={running || !runId || !!validateQuery(query)} className="btn-primary"
                style={{ opacity: running || !runId || !!validateQuery(query) ? 0.6 : 1 }}>
                {running ? <><RefreshCw className="w-4 h-4 animate-spin" />Searching…</> : <><Search className="w-4 h-4" />Search</>}
              </button>
              <button onClick={() => void reindex()} disabled={indexing || !runId} className="btn-secondary" title="Re-index embeddings">
                {indexing
                  ? <RefreshCw className="w-4 h-4 animate-spin" />
                  : indexDone
                    ? <Cpu className="w-4 h-4" style={{ color: '#16a34a' }} />
                    : <Cpu className="w-4 h-4" />}
              </button>
            </div>
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-2 text-xs">
            <span className="ink-2">Try:</span>
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

        {results.length === 0 && !running && !hasSearched && (
          <p className="text-sm ink-2 text-center py-6">
            {runId ? 'Enter a query and click Search to find endpoints.' : 'Select a run first, then run the search.'}
          </p>
        )}

        {results.length === 0 && !running && hasSearched && (
          <div className="p-3 rounded-xl flex items-start gap-2 text-xs"
            style={{ background: 'color-mix(in oklch, #f59e0b 8%, var(--card))', color: '#92400e', border: '1px solid color-mix(in oklch, #f59e0b 30%, var(--line))' }}>
            <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0 text-amber-500" />
            <div>
              <p className="font-semibold">No relevant endpoints found for this query.</p>
              <p className="mt-1 opacity-80">Rephrase using precise business terms (e.g. "create an employee", "retrieve orders").</p>
            </div>
          </div>
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
                  <div className="flex items-center gap-2 min-w-[140px]" title={`Raw similarity score: ${r.score.toFixed(4)}`}>
                    <div className="flex-1 h-1.5 rounded-full overflow-hidden" style={{ background: 'var(--line)' }}>
                      <div className="h-1.5 rounded-full grad-bg" style={{ width: `${displayConfidence(r.score) * 100}%` }} />
                    </div>
                    <span className="font-mono text-xs" style={{ color: 'var(--ink)' }}>{Math.round(displayConfidence(r.score) * 100)}%</span>
                  </div>
                  <button onClick={() => setExpanded(isOpen ? null : i)} className="btn-ghost !p-1.5">
                    <ChevronDown className={`w-4 h-4 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
                  </button>
                </div>
                {r.missingAspects.length > 0 && (
                  <div className="px-4 pb-3 -mt-1 flex items-start gap-1.5 text-xs" style={{ color: '#92400e' }}>
                    <AlertCircle className="w-3.5 h-3.5 mt-0.5 shrink-0 text-amber-500" />
                    <span>Partial match — this endpoint does not support: {r.missingAspects.join(', ')}</span>
                  </div>
                )}
                {isOpen && (() => {
                  const emb = parseEmbedding(r.embedding)
                  const reqFields  = (emb['Request fields']  || '').split(',').map(s => s.trim()).filter(Boolean)
                  const respFields = (emb['Response fields'] || '').split(',').map(s => s.trim()).filter(Boolean)
                  const tags       = (emb['Tags'] || '').split(',').map(s => s.trim()).filter(Boolean)
                  return (
                    <div className="px-4 pb-4 pt-3 space-y-4"
                      style={{ borderTop: '1px solid var(--line)', background: 'color-mix(in oklch, var(--brand) 2%, var(--card))' }}>

                      {/* Summary */}
                      {emb['Summary'] && (
                        <div className="flex gap-2.5">
                          <AlignLeft className="w-3.5 h-3.5 mt-0.5 shrink-0" style={{ color: 'var(--brand)' }} />
                          <p className="text-sm" style={{ color: 'var(--ink)' }}>{emb['Summary']}</p>
                        </div>
                      )}

                      {/* Description */}
                      {emb['Description'] && emb['Description'] !== emb['Summary'] && (
                        <p className="text-xs ink-2 leading-relaxed pl-6">{emb['Description']}</p>
                      )}

                      {/* Tags */}
                      {tags.length > 0 && (
                        <div className="flex items-center gap-2 flex-wrap pl-6">
                          <Tag className="w-3 h-3 ink-2 shrink-0" />
                          {tags.map(t => (
                            <span key={t} className="px-2 py-0.5 rounded-full text-[11px] font-medium"
                              style={{ background: 'color-mix(in oklch, var(--brand) 10%, var(--card))', color: 'var(--brand)', border: '1px solid color-mix(in oklch, var(--brand) 20%, var(--line))' }}>
                              {t}
                            </span>
                          ))}
                        </div>
                      )}

                      {/* Fields */}
                      {(reqFields.length > 0 || respFields.length > 0) && (
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pl-6">
                          {reqFields.length > 0 && (
                            <div>
                              <p className="text-[10px] font-bold tracking-widest uppercase ink-2 mb-1.5">Request fields</p>
                              <div className="flex flex-wrap gap-1">
                                {reqFields.map(f => (
                                  <span key={f} className="px-1.5 py-0.5 rounded text-[11px] font-mono"
                                    style={{ background: 'color-mix(in oklch, var(--ink) 5%, var(--card))', color: 'var(--ink)', border: '1px solid var(--line)' }}>
                                    {f}
                                  </span>
                                ))}
                              </div>
                            </div>
                          )}
                          {respFields.length > 0 && (
                            <div>
                              <p className="text-[10px] font-bold tracking-widest uppercase ink-2 mb-1.5">Response fields</p>
                              <div className="flex flex-wrap gap-1">
                                {respFields.map(f => (
                                  <span key={f} className="px-1.5 py-0.5 rounded text-[11px] font-mono"
                                    style={{ background: 'color-mix(in oklch, var(--ink) 5%, var(--card))', color: 'var(--ink)', border: '1px solid var(--line)' }}>
                                    {f}
                                  </span>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      )}

                      {/* Footer row: risque + canonical */}
                      <div className="flex items-center gap-4 pl-6 pt-1 flex-wrap">
                        <div className="flex items-center gap-2 text-xs">
                          <Layers className="w-3 h-3 ink-2" />
                          <span className="ink-2">Risk</span>
                          <SeverityBadge s={r.risk} />
                        </div>
                        <p className="text-[11px] font-mono ink-2 truncate">{r.canonical}</p>
                      </div>
                    </div>
                  )
                })()}
              </div>
            )
          })}
        </div>

      </div>
    </AppLayout>
  )
}
