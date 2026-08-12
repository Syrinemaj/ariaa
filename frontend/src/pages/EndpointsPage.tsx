import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import AppLayout from '../components/layout/AppLayout'
import { MethodBadge, SeverityBadge } from '../components/aria/Badges'
import { Method, Risk } from '../lib/aria-data'
import { getRunEndpoints, RunEndpoint } from '../lib/analysisApi'
import { listRuns, AnalysisRun } from '../lib/registryApi'
import { useRun } from '../contexts/RunContext'
import { useToast } from '../contexts/ToastContext'
import { Search, Download, FileCode2, Lock, Unlock, ChevronRight, Sparkles, Layers, Network } from 'lucide-react'

export default function EndpointsPage() {
  const nav = useNavigate()
  const [searchParams] = useSearchParams()
  const { setActiveRun } = useRun()
  const { toast } = useToast()
  const [q, setQ] = useState('')
  const [method, setMethod] = useState('ALL')
  const [domain, setDomain] = useState('ALL')
  const [authOnly, setAuthOnly] = useState(false)
  const [openRow, setOpenRow] = useState<number | null>(null)

  // Run selector state
  const [runs, setRuns] = useState<AnalysisRun[]>([])
  const [selectedRunId, setSelectedRunId] = useState('')
  const [endpoints, setEndpoints] = useState<RunEndpoint[]>([])
  const [loading, setLoading] = useState(false)

  // Load runs list on mount — honour ?run= query param for context navigation
  useEffect(() => {
    const paramRun = searchParams.get('run')
    listRuns({ limit: 50 }).then(data => {
      setRuns(data.items)
      const initial = data.items.find(r => r.id === paramRun) ?? data.items[0]
      if (initial) setSelectedRunId(initial.id)
    }).catch(() => {})
  }, [])

  // Sync active run into RunContext whenever selection changes
  useEffect(() => {
    if (!selectedRunId) return
    const run = runs.find(r => r.id === selectedRunId)
    if (run) setActiveRun({ id: run.id, name: run.file_name })
  }, [selectedRunId, runs])

  // Load endpoints when a run is selected
  useEffect(() => {
    if (!selectedRunId) return
    setLoading(true)
    setOpenRow(null)
    getRunEndpoints(selectedRunId)
      .then(data => setEndpoints(data.endpoints))
      .catch(() => setEndpoints([]))
      .finally(() => setLoading(false))
  }, [selectedRunId])

  const domains  = ['ALL', ...Array.from(new Set(endpoints.map(e => e.business_domain ?? '—')))]
  const filtered = endpoints.filter(e =>
    (method === 'ALL' || e.method === method) &&
    (domain === 'ALL' || (e.business_domain ?? '—') === domain) &&
    (!authOnly || e.auth_required) &&
    (q === '' || (e.path + e.canonical_key + (e.business_action ?? '') + (e.ai_tags ?? []).join(' ')).toLowerCase().includes(q.toLowerCase()))
  )

  const selectedRun = runs.find(r => r.id === selectedRunId)

  return (
    <AppLayout>
      <div className="p-6 space-y-6">
        <div className="flex items-end justify-between gap-4 flex-wrap">
          <div>
            <h2 className="text-xl font-black" style={{ color: 'var(--ink)' }}>Endpoints catalog</h2>
            {selectedRun ? (
              <p className="text-sm ink-2 mt-1">
                <span className="font-mono font-semibold" style={{ color: 'var(--ink)' }}>{selectedRun.file_name}</span>
                {' · '}{endpoints.length} endpoints
              </p>
            ) : (
              <p className="text-sm ink-2 mt-1">{endpoints.length} endpoints discovered</p>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => {
              const blob = new Blob([JSON.stringify(filtered, null, 2)], { type: 'application/json' })
              const url = URL.createObjectURL(blob)
              const a = document.createElement('a')
              a.href = url
              a.download = `endpoints-${selectedRunId || 'export'}.json`
              a.click()
              URL.revokeObjectURL(url)
              toast({ type: 'success', message: `File downloaded · ${filtered.length} endpoints` })
            }} className="btn-secondary"><Download className="w-4 h-4" /> Export JSON</button>
            <button onClick={() => nav('/openapi')} className="btn-secondary"><FileCode2 className="w-4 h-4" /> View OpenAPI</button>
            {selectedRunId && (
              <button onClick={() => nav(`/workflows?run=${selectedRunId}`)} className="btn-secondary">
                <Network className="w-4 h-4" /> Workflows
              </button>
            )}
            {selectedRunId && (
              <button onClick={() => nav(`/bulk?run=${selectedRunId}`)} className="btn-primary">
                <Layers className="w-4 h-4" /> Automate
              </button>
            )}
          </div>
        </div>

        <div className="card overflow-hidden">
          {/* Filters */}
          <div className="p-4 flex flex-wrap items-center gap-3" style={{ borderBottom: '1px solid var(--line)' }}>
            {/* Run selector */}
            {runs.length > 0 && (
              <label className="flex items-center gap-2 px-3 py-2 rounded-xl text-sm cursor-pointer"
                style={{ border: '1px solid var(--line)', background: 'var(--card)' }}>
                <span className="text-xs font-medium ink-2">Run</span>
                <select value={selectedRunId} onChange={e => setSelectedRunId(e.target.value)}
                  className="bg-transparent outline-none text-xs font-mono font-medium max-w-[180px] truncate" style={{ color: 'var(--ink)' }}>
                  {runs.map(r => <option key={r.id} value={r.id}>{r.file_name}</option>)}
                </select>
              </label>
            )}
            <div className="relative flex-1 min-w-[240px]">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 ink-2" />
              <input value={q} onChange={e => setQ(e.target.value)} className="input !pl-9" placeholder="Search path, canonical key, tag…" />
            </div>
            {[
              { label: 'Method', value: method, options: ['ALL', 'GET', 'POST', 'PUT', 'PATCH', 'DELETE'], set: setMethod },
              { label: 'Domain', value: domain, options: domains, set: setDomain },
            ].map(s => (
              <label key={s.label} className="flex items-center gap-2 px-3 py-2 rounded-xl text-sm cursor-pointer"
                style={{ border: '1px solid var(--line)', background: 'var(--card)' }}>
                <span className="text-xs font-medium ink-2">{s.label}</span>
                <select value={s.value} onChange={e => s.set(e.target.value)}
                  className="bg-transparent outline-none text-sm font-medium" style={{ color: 'var(--ink)' }}>
                  {s.options.map(o => <option key={o}>{o}</option>)}
                </select>
              </label>
            ))}
            <label className="flex items-center gap-2 px-3 py-2 rounded-xl text-sm cursor-pointer"
              style={{ border: '1px solid var(--line)', background: 'var(--card)' }}>
              <input type="checkbox" checked={authOnly} onChange={e => setAuthOnly(e.target.checked)} />
              <Lock className="w-3.5 h-3.5 ink-2" /> Auth only
            </label>
            <span className="ml-auto text-xs font-mono ink-2">{filtered.length} / {endpoints.length}</span>
          </div>

          {/* Table */}
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="aria-thead">
                <tr>
                  <th className="px-4 py-2.5 w-8" />
                  {['Method', 'Path', 'Canonical key', 'Domain', 'Action', 'Auth', 'Risk', 'Statuses', 'AI'].map(h => (
                    <th key={h} className="text-left px-2 py-2.5">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {loading && (
                  <tr><td colSpan={10} className="px-4 py-10 text-center ink-2 text-sm">Loading endpoints…</td></tr>
                )}
                {!loading && filtered.length === 0 && (
                  <tr><td colSpan={10} className="px-4 py-10 text-center ink-2 text-sm">
                    {endpoints.length === 0 ? 'Select a run to view its endpoints.' : 'No endpoints match — try clearing filters.'}
                  </td></tr>
                )}
                {!loading && filtered.map((e, i) => {
                  const isOpen = openRow === i
                  const domain = e.business_domain ?? '—'
                  const action = e.business_action ?? '—'
                  const tags   = e.ai_tags ?? []
                  return [
                    <tr key={`r-${i}`}
                      className="border-t cursor-pointer transition"
                      style={{ borderColor: 'var(--line)', background: isOpen ? 'color-mix(in oklch, var(--brand) 3%, var(--card))' : '' }}
                      onMouseEnter={ev => { if (!isOpen) ev.currentTarget.style.background = 'color-mix(in oklch, var(--brand) 4%, var(--card))' }}
                      onMouseLeave={ev => { if (!isOpen) ev.currentTarget.style.background = '' }}
                      onClick={() => setOpenRow(isOpen ? null : i)}>
                      <td className="px-4 py-3"><ChevronRight className={`w-4 h-4 ink-2 transition-transform ${isOpen ? 'rotate-90' : ''}`} /></td>
                      <td className="px-2 py-3"><MethodBadge m={e.method as Method} /></td>
                      <td className="px-2 py-3 font-mono text-xs" style={{ color: 'var(--ink)' }}>{e.path}</td>
                      <td className="px-2 py-3 font-mono text-xs ink-2">{e.canonical_key}</td>
                      <td className="px-2 py-3"><span className="pill" style={{ background: 'color-mix(in oklch, var(--ink) 4%, var(--card))', borderColor: 'var(--line)', color: 'var(--ink-2)' }}>{domain}</span></td>
                      <td className="px-2 py-3 text-xs ink-2">{action}</td>
                      <td className="px-2 py-3 text-center">
                        {e.auth_required ? <Lock className="w-3.5 h-3.5 inline text-amber-500" /> : <Unlock className="w-3.5 h-3.5 inline text-emerald-500" />}
                      </td>
                      <td className="px-2 py-3"><SeverityBadge s={(e.risk || 'low') as Risk} /></td>
                      <td className="px-2 py-3 font-mono text-xs ink-2">{(e.status_codes ?? []).join(' · ')}</td>
                      <td className="px-2 py-3 font-mono text-xs text-right font-bold" style={{ color: 'var(--ink)' }}>
                        {e.ai_confidence != null ? <span title="AI enriched"><Sparkles className="w-3.5 h-3.5 inline text-violet-400" /></span> : null}
                      </td>
                    </tr>,
                    isOpen && (
                      <tr key={`x-${i}`} className="border-t" style={{ borderColor: 'var(--line)', background: 'color-mix(in oklch, var(--brand) 2%, var(--card))' }}>
                        <td colSpan={10} className="px-4 py-5">
                          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                            {/* AI Summary */}
                            <div>
                              <p className="text-[10px] font-bold tracking-widest uppercase ink-2 mb-2 flex items-center gap-1.5">
                                <Sparkles className="w-3 h-3 text-violet-400" /> AI Summary
                              </p>
                              {e.ai_summary ? (
                                <>
                                  <p className="text-sm" style={{ color: 'var(--ink)' }}>{e.ai_summary}</p>
                                  {e.ai_description && (
                                    <p className="text-xs ink-2 mt-1.5">{e.ai_description}</p>
                                  )}
                                </>
                              ) : (
                                <p className="text-xs ink-2 italic">Not enriched — rerun ingestion to get the Groq analysis.</p>
                              )}
                              <div className="flex flex-wrap gap-1 mt-2">
                                {tags.map(t => (
                                  <span key={t} className="pill" style={{ background: 'color-mix(in oklch, var(--ink) 4%, var(--card))', borderColor: 'var(--line)', color: 'var(--ink-2)' }}>#{t}</span>
                                ))}
                              </div>
                            </div>
                            {/* Details */}
                            <div>
                              <p className="text-[10px] font-bold tracking-widest uppercase ink-2 mb-2">Details</p>
                              <div className="space-y-1.5">
                                <div className="flex justify-between p-2 rounded-xl text-xs" style={{ background: 'color-mix(in oklch, var(--ink) 4%, var(--card))', border: '1px solid var(--line)' }}>
                                  <span className="ink-2">canonical</span>
                                  <span className="font-mono text-right" style={{ color: 'var(--ink)' }}>{e.canonical_key}</span>
                                </div>
                                <div className="flex justify-between p-2 rounded-xl text-xs" style={{ background: 'color-mix(in oklch, var(--ink) 4%, var(--card))', border: '1px solid var(--line)' }}>
                                  <span className="ink-2 flex items-center gap-1">
                                    confidence
                                    {e.ai_confidence != null && <Sparkles className="w-3 h-3 text-violet-400" />}
                                  </span>
                                  {(() => {
                                    const confidence = e.ai_confidence ?? e.confidence
                                    const pct = Math.round(confidence * 100)
                                    const color = confidence >= 0.9 ? 'text-emerald-600' : confidence >= 0.7 ? 'text-amber-600' : 'text-rose-600'
                                    return <span className={`font-mono font-bold ${color}`}>{pct}%</span>
                                  })()}
                                </div>
                                <div className="flex justify-between p-2 rounded-xl text-xs" style={{ background: 'color-mix(in oklch, var(--ink) 4%, var(--card))', border: '1px solid var(--line)' }}>
                                  <span className="ink-2">statuses</span>
                                  <span className="font-mono" style={{ color: 'var(--ink)' }}>{(e.status_codes ?? []).join(', ') || '—'}</span>
                                </div>
                              </div>
                            </div>
                            {/* Auth & Risk */}
                            <div>
                              <p className="text-[10px] font-bold tracking-widest uppercase ink-2 mb-2">Auth &amp; Risk</p>
                              <div className="space-y-1.5">
                                <div className="flex justify-between p-2 rounded-xl text-xs" style={{ background: 'color-mix(in oklch, var(--ink) 4%, var(--card))', border: '1px solid var(--line)' }}>
                                  <span className="ink-2">auth required</span>
                                  {e.auth_required ? <Lock className="w-3.5 h-3.5 text-amber-500" /> : <Unlock className="w-3.5 h-3.5 text-emerald-500" />}
                                </div>
                                <div className="flex justify-between p-2 rounded-xl text-xs" style={{ background: 'color-mix(in oklch, var(--ink) 4%, var(--card))', border: '1px solid var(--line)' }}>
                                  <span className="ink-2">risk</span><SeverityBadge s={(e.risk || 'low') as Risk} />
                                </div>
                                <div className="flex justify-between p-2 rounded-xl text-xs" style={{ background: 'color-mix(in oklch, var(--ink) 4%, var(--card))', border: '1px solid var(--line)' }}>
                                  <span className="ink-2">auth type</span><span className="font-mono" style={{ color: 'var(--ink)' }}>{e.auth_type ?? '—'}</span>
                                </div>
                              </div>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )
                  ]
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </AppLayout>
  )
}
