import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppLayout from '../components/layout/AppLayout'
import { MethodBadge, SeverityBadge } from '../components/aria/Badges'
import { Workflow, WorkflowStep, Method, Risk } from '../lib/aria-data'
import { listRuns, getWorkflows, AnalysisRun, BackendWorkflow } from '../lib/registryApi'
import { Wand2, Layers, Plus, Lock, Unlock } from 'lucide-react'

// Map backend workflow → UI Workflow shape
function mapWorkflow(bw: BackendWorkflow): Workflow {
  return {
    id: bw.id,
    name: bw.name,
    description: `${bw.business_domain ?? 'Unknown'} workflow — ${bw.steps.length} step${bw.steps.length !== 1 ? 's' : ''}, ${Math.round((bw.confidence ?? 0.8) * 100)}% confidence`,
    domain: bw.business_domain ?? '—',
    confidence: bw.confidence ?? 0.8,
    steps: bw.steps
      .slice()
      .sort((a, b) => a.order - b.order)
      .map(s => ({
        order:    s.order,
        method:   s.method as Method,
        path:     s.path,
        canonical: s.canonical,
        action:   s.action ?? '—',
        depends:  s.depends,
        risk:     s.risk as Risk,
        auth:     s.auth,
      } satisfies WorkflowStep)),
  }
}

export default function WorkflowsPage() {
  const nav = useNavigate()

  const [runs, setRuns]             = useState<AnalysisRun[]>([])
  const [selectedRunId, setSelectedRunId] = useState('')
  const [workflows, setWorkflows]   = useState<Workflow[]>([])
  const [activeId, setActiveId]     = useState('')
  const [loading, setLoading]       = useState(false)

  // Load runs on mount
  useEffect(() => {
    listRuns({ limit: 50 }).then(data => {
      setRuns(data.items)
      if (data.items.length > 0) setSelectedRunId(data.items[0].id)
    }).catch(() => {})
  }, [])

  // Load workflows when selectedRunId changes
  useEffect(() => {
    if (!selectedRunId) return
    setLoading(true)
    setWorkflows([])
    setActiveId('')
    getWorkflows(selectedRunId)
      .then(data => {
        const mapped = data.map(mapWorkflow)
        setWorkflows(mapped)
        if (mapped.length > 0) setActiveId(mapped[0].id)
      })
      .catch(() => setWorkflows([]))
      .finally(() => setLoading(false))
  }, [selectedRunId])

  const wf = workflows.find(w => w.id === activeId) ?? workflows[0]

  return (
    <AppLayout>
      <div className="p-6 space-y-6">
        <div className="flex items-end justify-between gap-4 flex-wrap">
          <div>
            <h2 className="text-xl font-black" style={{ color: 'var(--ink)' }}>Detected workflows</h2>
            <p className="text-sm ink-2 mt-1">{workflows.length} workflows inferred from session traffic</p>
          </div>
          <div className="flex items-center gap-2">
            {/* Run selector */}
            {runs.length > 0 && (
              <select value={selectedRunId} onChange={e => setSelectedRunId(e.target.value)}
                className="input !py-1.5 !w-auto text-xs font-mono">
                {runs.map(r => <option key={r.id} value={r.id}>{r.file_name}</option>)}
              </select>
            )}
            <button onClick={() => nav('/automation')} className="btn-secondary"><Wand2 className="w-4 h-4" /> Generate plan</button>
            <button onClick={() => nav('/bulk')} className="btn-primary"><Layers className="w-4 h-4" /> Run bulk</button>
          </div>
        </div>

        {loading && (
          <div className="card pad text-center py-12 text-sm ink-2">Loading workflows…</div>
        )}

        {!loading && (
          <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-4">
            {/* List */}
            <div className="space-y-3">
              {workflows.length === 0 && (
                <div className="card pad text-center py-8 text-sm ink-2">
                  {runs.length === 0 ? 'No analysis runs found.' : 'No workflows detected for this run.'}
                </div>
              )}
              {workflows.map(w => (
                <button key={w.id} onClick={() => setActiveId(w.id)}
                  className="w-full text-left card pad transition"
                  style={w.id === activeId ? { outline: '2px solid var(--brand)', outlineOffset: -2 } : { cursor: 'pointer' }}
                  onMouseEnter={e => { if (w.id !== activeId) (e.currentTarget as HTMLElement).style.borderColor = 'var(--brand)' }}
                  onMouseLeave={e => { if (w.id !== activeId) (e.currentTarget as HTMLElement).style.borderColor = '' }}>
                  <div className="flex items-center justify-between gap-2 mb-2">
                    <p className="font-bold text-sm" style={{ color: 'var(--ink)' }}>{w.name}</p>
                    <span className="font-mono text-xs ink-2">{Math.round(w.confidence * 100)}%</span>
                  </div>
                  <p className="text-xs ink-2 mb-3 line-clamp-2">{w.description}</p>
                  <div className="flex items-center gap-2 text-xs">
                    <span className="pill" style={{ background: 'color-mix(in oklch, var(--ink) 4%, var(--card))', borderColor: 'var(--line)', color: 'var(--ink-2)' }}>{w.domain}</span>
                    <span className="font-mono ink-2">{w.steps.length} steps</span>
                  </div>
                </button>
              ))}
              <button className="w-full card pad transition" style={{ borderStyle: 'dashed', cursor: 'pointer' }}>
                <div className="text-center py-2">
                  <Plus className="w-5 h-5 mx-auto ink-2 mb-1" />
                  <p className="text-xs ink-2 font-medium">Discover more</p>
                </div>
              </button>
            </div>

            {/* Detail */}
            {wf ? (
              <div className="card pad">
                <div className="flex items-start justify-between gap-4 mb-6">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <h3 className="text-lg font-black" style={{ color: 'var(--ink)' }}>{wf.name}</h3>
                      <span className="pill" style={{ background: 'color-mix(in oklch, var(--ink) 4%, var(--card))', borderColor: 'var(--line)', color: 'var(--ink-2)' }}>{wf.domain}</span>
                    </div>
                    <p className="text-sm ink-2">{wf.description}</p>
                  </div>
                  <div className="text-right flex-shrink-0">
                    <p className="text-[10px] font-bold tracking-widest uppercase ink-2">Confidence</p>
                    <p className="text-2xl font-black grad-text">{Math.round(wf.confidence * 100)}%</p>
                  </div>
                </div>

                <div className="relative">
                  <div className="absolute left-5 top-2 bottom-2 w-0.5 rounded-full grad-bg" />
                  <ol className="space-y-3">
                    {wf.steps.map((s, i) => (
                      <li key={s.order} className="relative pl-12" style={{ animationDelay: `${i * 60}ms` }}>
                        <div className="absolute left-2 top-1.5 w-7 h-7 rounded-full grad-bg text-white text-xs font-black flex items-center justify-center ring-4" style={{ '--tw-ring-color': 'var(--card)' } as React.CSSProperties}>
                          {s.order}
                        </div>
                        <div className="card pad !p-4">
                          <div className="flex flex-wrap items-center gap-3">
                            <MethodBadge m={s.method} />
                            <span className="font-mono text-xs flex-1 min-w-0 truncate" style={{ color: 'var(--ink)' }}>{s.path}</span>
                            <SeverityBadge s={s.risk} />
                            {s.auth ? <Lock className="w-3.5 h-3.5 text-amber-500" /> : <Unlock className="w-3.5 h-3.5 text-emerald-500" />}
                          </div>
                          <p className="mt-2 text-sm" style={{ color: 'var(--ink)' }}>{s.action}</p>
                          <div className="mt-1 flex items-center gap-2 text-xs ink-2">
                            <span className="font-mono">{s.canonical}</span>
                            {s.depends.length > 0 && <span>· depends on step {s.depends.join(', ')}</span>}
                          </div>
                        </div>
                      </li>
                    ))}
                  </ol>
                </div>
              </div>
            ) : (
              <div className="card pad flex items-center justify-center text-sm ink-2 py-16">
                Select a workflow to view its steps.
              </div>
            )}
          </div>
        )}
      </div>
    </AppLayout>
  )
}
