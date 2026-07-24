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

const SUGGESTIONS = ["créer un employé", "révoquer un badge", "mettre à jour l'IBAN", "lister les employés", "rafraîchir le token"]

const FILLER_WORDS = new Set([
  'bonjour','hello','salut','hi','hey','coucou','bonsoir','bonne nuit','bye','byebye',
  'test','ok','oui','non','rien','merci','thanks','thank','please','stp','sil vous plait',
  'lol','wtf','???','...',
])

function validateQuery(q: string): string {
  const t = q.trim()
  if (t.length < 4) return 'Requête trop courte — décrivez une action API en quelques mots.'
  if (FILLER_WORDS.has(t.toLowerCase())) return 'Cette requête ne correspond à aucune action API.'
  if (!t.includes(' ') && t.length < 7) return 'Décrivez l\'action en quelques mots (ex : "créer un employé").'
  return ''
}

type RagResult = {
  method: string; path: string; canonical: string; domain: string; action: string
  score: number; embedding: string; risk: Risk; tags: string[]; samples: number
}

export default function RagPage() {
  const [query, setQuery]       = useState('create a new employee with payroll and badge')
  const [topK, setTopK]         = useState(5)
  const [runs, setRuns]         = useState<AnalysisRun[]>([])
  const [runId, setRunId]       = useState('')
  const [running, setRunning]         = useState(false)
  const [indexing, setIndexing]       = useState(false)
  const [indexDone, setIndexDone]     = useState(false)
  const [expanded, setExpanded]       = useState<number | null>(null)
  const [results, setResults]         = useState<RagResult[]>([])
  const [lowRelevance, setLowRelevance] = useState(false)

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
    setLowRelevance(false)
    try {
      const data = await ragSearch(query, runId, topK)
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
      }))
      setResults(mapped)
      if (mapped.length > 0) {
        const scores = mapped.map(r => r.score)
        const maxScore = Math.max(...scores)
        const scoreSpread = maxScore - Math.min(...scores)
        setLowRelevance(maxScore < 0.75 || scoreSpread < 0.03)
      }
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
          <p className="text-sm ink-2 mt-1">Trouvez des endpoints en décrivant ce que vous voulez faire, en langage naturel.</p>
        </div>

        <div className="card pad">
          <div className="grid grid-cols-1 lg:grid-cols-[1.4fr_1fr_200px_auto] gap-3 items-end">
            <div>
              <p className="text-[10px] font-bold tracking-widest uppercase ink-2 mb-1.5">Requête</p>
              <div className="relative">
                <Sparkles className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--brand)' }} />
                <input value={query} onChange={e => { setQuery(e.target.value); setLowRelevance(false) }}
                  onKeyDown={e => e.key === 'Enter' && void search()}
                  className="input !pl-9" placeholder="ex. révoquer un badge pour un employé licencié" />
              </div>
              {query.trim().length > 0 && validateQuery(query) && (
                <p className="mt-1 text-xs" style={{ color: '#f43f5e' }}>{validateQuery(query)}</p>
              )}
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
            <div className="flex gap-2">
              <button onClick={() => void search()} disabled={running || !runId || !!validateQuery(query)} className="btn-primary"
                style={{ opacity: running || !runId || !!validateQuery(query) ? 0.6 : 1 }}>
                {running ? <><RefreshCw className="w-4 h-4 animate-spin" />Recherche…</> : <><Search className="w-4 h-4" />Rechercher</>}
              </button>
              <button onClick={() => void reindex()} disabled={indexing || !runId} className="btn-secondary" title="Re-indexer les embeddings">
                {indexing
                  ? <RefreshCw className="w-4 h-4 animate-spin" />
                  : indexDone
                    ? <Cpu className="w-4 h-4" style={{ color: '#16a34a' }} />
                    : <Cpu className="w-4 h-4" />}
              </button>
            </div>
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
            {runId ? 'Saisissez une requête et cliquez sur Rechercher pour trouver des endpoints.' : 'Sélectionnez d\'abord un run, puis lancez la recherche.'}
          </p>
        )}

        {lowRelevance && results.length > 0 && (
          <div className="p-3 rounded-xl flex items-start gap-2 text-xs"
            style={{ background: 'color-mix(in oklch, #f59e0b 8%, var(--card))', color: '#92400e', border: '1px solid color-mix(in oklch, #f59e0b 30%, var(--line))' }}>
            <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0 text-amber-500" />
            <div>
              <p className="font-semibold">Résultats de faible pertinence — la requête ne semble pas correspondre aux endpoints indexés.</p>
              <p className="mt-1 opacity-80">La recherche sémantique retourne toujours les {results.length} endpoints les plus proches, même sans correspondance réelle. Reformulez avec des termes métier précis (ex : "créer un employé", "récupérer les commandes").</p>
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
                              <p className="text-[10px] font-bold tracking-widest uppercase ink-2 mb-1.5">Champs requête</p>
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
                              <p className="text-[10px] font-bold tracking-widest uppercase ink-2 mb-1.5">Champs réponse</p>
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
                          <span className="ink-2">Risque</span>
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
