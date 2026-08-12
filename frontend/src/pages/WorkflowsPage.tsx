import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import AppLayout from '../components/layout/AppLayout'
import { MethodBadge, SeverityBadge } from '../components/aria/Badges'
import { Workflow, WorkflowStep, Method, Risk } from '../lib/aria-data'
import {
  listRuns, getWorkflows, createWorkflow, updateWorkflow, deleteWorkflow, restoreWorkflow,
  AnalysisRun, BackendWorkflow, WorkflowStepInput,
} from '../lib/registryApi'
import { getRunEndpoints, RunEndpoint } from '../lib/analysisApi'
import { useRun } from '../contexts/RunContext'
import {
  Layers, Lock, Unlock, Package, Plus, Pencil, Trash2,
  GripVertical, Check, X, RefreshCw, Sparkles, RotateCcw,
  ChevronUp, ChevronDown, AlertCircle, Search,
} from 'lucide-react'

// ── Toast types ───────────────────────────────────────────────────────────────

interface Toast { id: string; message: string; type: 'success' | 'error' }

// ── Mappers ───────────────────────────────────────────────────────────────────

function mapWorkflow(bw: BackendWorkflow): Workflow {
  const meta = bw.metadata as Record<string, unknown> ?? {}
  const aiSummary = (meta.ai_summary as string) ?? ''
  return {
    id: bw.id,
    name: bw.name,
    description: aiSummary || `${bw.business_domain ?? 'Unknown'} · ${bw.steps.length} step${bw.steps.length !== 1 ? 's' : ''} · ${Math.round((bw.confidence ?? 0.8) * 100)}% confidence`,
    domain: bw.business_domain ?? '—',
    confidence: bw.confidence ?? 0.8,
    hasOriginal: '_original' in meta,
    isManual: (meta.created_by as string) === 'user',  // [F1]
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

// ── Draft step type ───────────────────────────────────────────────────────────

interface DraftStep {
  _key:      string
  order:     number
  method:    string
  path:      string
  canonical: string
  action:    string
  risk:      string
  auth:      boolean
}

function wfStepToDraft(s: WorkflowStep): DraftStep {
  return { _key: s.canonical + s.order, order: s.order, method: s.method, path: s.path, canonical: s.canonical, action: s.action, risk: s.risk, auth: s.auth }
}

function epToDraft(ep: RunEndpoint, order: number): DraftStep {
  return { _key: ep.canonical_key + order, order, method: ep.method, path: ep.path, canonical: ep.canonical_key, action: ep.business_action ?? '—', risk: ep.risk ?? 'low', auth: ep.auth_required ?? true }
}

function renumber(steps: DraftStep[]): DraftStep[] {
  return steps.map((s, i) => ({ ...s, order: i + 1 }))
}

// ── [F1] Workflow origin badge ────────────────────────────────────────────────

function OriginBadge({ wf }: { wf: Workflow }) {
  if (wf.isManual) return (
    <span className="pill text-[10px]" style={{ background: 'color-mix(in oklch, var(--ink) 6%, var(--card))', borderColor: 'var(--line)', color: 'var(--ink-2)' }}>Manual</span>
  )
  if (wf.hasOriginal) return (
    <span className="pill text-[10px]" style={{ background: 'color-mix(in oklch, #f59e0b 12%, var(--card))', borderColor: '#f59e0b', color: '#b45309' }}>Modified</span>
  )
  return (
    <span className="pill text-[10px]" style={{ background: 'color-mix(in oklch, #22c55e 12%, var(--card))', borderColor: '#22c55e', color: '#15803d' }}>AI</span>
  )
}

// ── [F5] Skeleton components ──────────────────────────────────────────────────

function SkeletonSidebar() {
  return (
    <div className="space-y-2">
      {[1, 2, 3, 4].map(i => (
        <div key={i} className="card pad animate-pulse" style={{ height: 72, background: 'color-mix(in oklch, var(--line) 60%, var(--card))' }} />
      ))}
    </div>
  )
}

function SkeletonPanel() {
  return (
    <div className="card pad space-y-5 animate-pulse">
      <div className="space-y-2">
        <div style={{ height: 24, width: '55%', background: 'var(--line)', borderRadius: 8 }} />
        <div style={{ height: 14, width: '35%', background: 'var(--line)', borderRadius: 6 }} />
      </div>
      {[1, 2, 3].map(i => (
        <div key={i} className="card pad !p-4" style={{ height: 60, background: 'color-mix(in oklch, var(--line) 50%, var(--card))' }} />
      ))}
    </div>
  )
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function WorkflowsPage() {
  const nav = useNavigate()
  const [searchParams] = useSearchParams()
  const { setActiveRun } = useRun()

  // Core state
  const [runs, setRuns]                     = useState<AnalysisRun[]>([])
  const [selectedRunId, setSelectedRunId]   = useState('')
  const [workflows, setWorkflows]           = useState<Workflow[]>([])
  const [activeId, setActiveId]             = useState('')
  const [loading, setLoading]               = useState(false)
  const [loadError, setLoadError]           = useState('')  // [F10]
  const [mode, setMode]                     = useState<'view' | 'edit' | 'create'>('view')

  // Draft state
  const [draftName, setDraftName]           = useState('')
  const [draftDomain, setDraftDomain]       = useState('')
  const [draftSteps, setDraftSteps]         = useState<DraftStep[]>([])
  const [saving, setSaving]                 = useState(false)
  const [deleting, setDeleting]             = useState(false)
  const [restoring, setRestoring]           = useState(false)
  const [confirmRestore, setConfirmRestore] = useState(false)
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false)  // [F2]

  // [F11] Dirty state
  const [isDirty, setIsDirty]               = useState(false)
  const [pendingSelectId, setPendingSelectId] = useState<string | null>(null)

  // [F3] Search
  const [searchQuery, setSearchQuery]       = useState('')

  // [F8+F9] Toasts
  const [toasts, setToasts]                 = useState<Toast[]>([])

  // Endpoint picker
  const [runEndpoints, setRunEndpoints]     = useState<RunEndpoint[]>([])
  const [epSearch, setEpSearch]             = useState('')       // [F4]
  const [showEpList, setShowEpList]         = useState(false)    // [F4]
  const epComboRef                          = useRef<HTMLDivElement>(null)

  // Drag & drop
  const dragIdx    = useRef(-1)
  const [dragOver, setDragOver] = useState(-1)

  // ── Toast helper ────────────────────────────────────────────────────────────
  const addToast = (message: string, type: Toast['type']) => {
    const id = Date.now().toString()
    setToasts(prev => [...prev, { id, message, type }])
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 3000)
  }

  // ── Close combobox on outside click [F4] ───────────────────────────────────
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (epComboRef.current && !epComboRef.current.contains(e.target as Node))
        setShowEpList(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  // ── Load runs ───────────────────────────────────────────────────────────────
  useEffect(() => {
    const paramRun = searchParams.get('run')
    listRuns({ limit: 50 }).then(data => {
      setRuns(data.items)
      const initial = data.items.find(r => r.id === paramRun) ?? data.items[0]
      if (initial) setSelectedRunId(initial.id)
    }).catch(() => {})
  }, [])

  useEffect(() => {
    if (!selectedRunId) return
    const run = runs.find(r => r.id === selectedRunId)
    if (run) setActiveRun({ id: run.id, name: run.file_name })
  }, [selectedRunId, runs])

  // ── Load workflows ──────────────────────────────────────────────────────────
  const loadWorkflows = (runId: string) => {
    setLoading(true)
    setLoadError('')
    setWorkflows([])
    setActiveId('')
    setMode('view')
    getWorkflows(runId)
      .then(data => {
        const mapped = data.map(mapWorkflow)
        setWorkflows(mapped)
        if (mapped.length > 0) setActiveId(mapped[0].id)
      })
      .catch((err) => setLoadError(err?.message ?? 'Error loading workflows.'))  // [F10]
      .finally(() => setLoading(false))
  }

  useEffect(() => { if (selectedRunId) loadWorkflows(selectedRunId) }, [selectedRunId])

  // ── Load endpoints (always, for descriptions in view + combobox in edit) ────
  useEffect(() => {
    if (!selectedRunId) return
    setRunEndpoints([])
    getRunEndpoints(selectedRunId)
      .then(d => setRunEndpoints(d.endpoints))
      .catch(() => {})
  }, [selectedRunId])

  // ── Enter edit ──────────────────────────────────────────────────────────────
  const enterEdit = () => {
    const wf = workflows.find(w => w.id === activeId)
    if (!wf) return
    setDraftName(wf.name)
    setDraftDomain(wf.domain === '—' ? '' : wf.domain)
    setDraftSteps(wf.steps.map(wfStepToDraft))
    setIsDirty(false)
    setMode('edit')
  }

  const enterCreate = () => {
    setDraftName('')
    setDraftDomain('')
    setDraftSteps([])
    setIsDirty(false)
    setMode('create')
  }

  const cancel = () => {
    setIsDirty(false)
    setPendingSelectId(null)
    setMode('view')
  }

  // ── [F11] Sidebar click with dirty guard ────────────────────────────────────
  const handleWorkflowSelect = (id: string) => {
    if ((mode === 'edit' || mode === 'create') && isDirty) {
      setPendingSelectId(id)
      return
    }
    setActiveId(id)
    setMode('view')
  }

  const confirmLeave = () => {
    if (!pendingSelectId) return
    setActiveId(pendingSelectId)
    setPendingSelectId(null)
    setIsDirty(false)
    setMode('view')
  }

  // ── Step manipulation ───────────────────────────────────────────────────────
  const removeStep = (idx: number) => {
    setDraftSteps(renumber(draftSteps.filter((_, i) => i !== idx)))
    setIsDirty(true)
  }

  const addStep = (ep: RunEndpoint) => {
    const already = draftSteps.some(s => s.canonical === ep.canonical_key)
    if (already) return
    setDraftSteps(renumber([...draftSteps, epToDraft(ep, draftSteps.length + 1)]))
    setEpSearch('')
    setShowEpList(false)
    setIsDirty(true)
  }

  // [F14] Move step up or down
  const moveStep = (idx: number, dir: 'up' | 'down') => {
    const arr = [...draftSteps]
    const target = dir === 'up' ? idx - 1 : idx + 1
    if (target < 0 || target >= arr.length) return
    ;[arr[idx], arr[target]] = [arr[target], arr[idx]]
    setDraftSteps(renumber(arr))
    setIsDirty(true)
  }

  // ── Save (edit) ─────────────────────────────────────────────────────────────
  const saveEdit = async () => {
    if (!draftName.trim() || !activeId) return
    setSaving(true)
    try {
      const steps: WorkflowStepInput[] = draftSteps.map(s => ({
        order: s.order, method: s.method, path: s.path,
        canonical_key: s.canonical, action: s.action, risk: s.risk, auth: s.auth,
      }))
      const updated = await updateWorkflow(activeId, { name: draftName.trim(), business_domain: draftDomain.trim() || undefined, steps })
      setWorkflows(prev => prev.map(w => w.id === activeId ? mapWorkflow(updated) : w))
      setIsDirty(false)
      setMode('view')
      addToast('Workflow saved successfully.', 'success')
    } catch (err: unknown) {
      addToast((err as Error)?.message ?? 'Error while saving.', 'error')
    } finally {
      setSaving(false)
    }
  }

  // ── Save (create) ───────────────────────────────────────────────────────────
  const saveCreate = async () => {
    if (!draftName.trim() || !selectedRunId) return
    setSaving(true)
    try {
      const steps: WorkflowStepInput[] = draftSteps.map(s => ({
        order: s.order, method: s.method, path: s.path,
        canonical_key: s.canonical, action: s.action, risk: s.risk, auth: s.auth,
      }))
      const created = await createWorkflow(selectedRunId, { name: draftName.trim(), business_domain: draftDomain.trim() || undefined, steps })
      const mapped = mapWorkflow(created)
      setWorkflows(prev => [...prev, mapped])
      setActiveId(mapped.id)
      setIsDirty(false)
      setMode('view')
      addToast('Workflow created successfully.', 'success')
    } catch (err: unknown) {
      addToast((err as Error)?.message ?? 'Error while creating.', 'error')
    } finally {
      setSaving(false)
    }
  }

  // ── Restore ─────────────────────────────────────────────────────────────────
  const doRestore = async () => {
    if (!activeId) return
    setRestoring(true)
    setConfirmRestore(false)
    try {
      const restored = await restoreWorkflow(activeId)
      setWorkflows(prev => prev.map(w => w.id === activeId ? mapWorkflow(restored) : w))
      addToast('Original version restored.', 'success')
    } catch (err: unknown) {
      addToast((err as Error)?.message ?? 'Error while restoring.', 'error')
    } finally {
      setRestoring(false)
    }
  }

  // ── Delete ──────────────────────────────────────────────────────────────────
  const doDelete = async () => {
    if (!activeId) return
    setDeleting(true)
    setConfirmDeleteOpen(false)
    try {
      await deleteWorkflow(activeId)
      const remaining = workflows.filter(w => w.id !== activeId)
      setWorkflows(remaining)
      setActiveId(remaining[0]?.id ?? '')
      setMode('view')
      addToast('Workflow deleted.', 'success')
    } catch (err: unknown) {
      addToast((err as Error)?.message ?? 'Error while deleting.', 'error')
    } finally {
      setDeleting(false)
    }
  }

  // ── Drag & drop ─────────────────────────────────────────────────────────────
  const onDragStart = (i: number) => { dragIdx.current = i }
  const onDragOver  = (e: React.DragEvent, i: number) => {
    e.preventDefault()
    if (dragIdx.current === -1 || dragIdx.current === i) { setDragOver(i); return }
    const arr  = [...draftSteps]
    const item = arr.splice(dragIdx.current, 1)[0]
    arr.splice(i, 0, item)
    dragIdx.current = i
    setDragOver(i)
    setDraftSteps(renumber(arr))
    setIsDirty(true)
  }
  const onDragEnd = () => { dragIdx.current = -1; setDragOver(-1) }

  // ── Derived ─────────────────────────────────────────────────────────────────
  const wf = workflows.find(w => w.id === activeId) ?? workflows[0]

  // [F3] Filtered workflows
  const filteredWorkflows = workflows.filter(w => {
    if (!searchQuery) return true
    const q = searchQuery.toLowerCase()
    return w.name.toLowerCase().includes(q) || w.domain.toLowerCase().includes(q)
  })

  // [F4] Available + filtered endpoints for combobox
  const availableEps = runEndpoints.filter(e => !draftSteps.some(s => s.canonical === e.canonical_key))
  const filteredEps  = availableEps.filter(e =>
    `${e.method} ${e.path}`.toLowerCase().includes(epSearch.toLowerCase())
  )

  // Lookup map for endpoint descriptions in ViewPanel
  const endpointByCanonical = Object.fromEntries(runEndpoints.map(e => [e.canonical_key, e]))

  // ── DraftPanel ───────────────────────────────────────────────────────────────
  const DraftPanel = () => (
    <div className="card pad space-y-5">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Sparkles className="w-4 h-4 shrink-0" style={{ color: 'var(--brand)' }} />
          <span className="text-sm font-bold" style={{ color: 'var(--ink)' }}>
            {mode === 'create' ? 'New workflow' : 'Edit workflow'}
          </span>
        </div>
        <div className="flex gap-2">
          <button onClick={cancel} className="btn-ghost !py-1 !px-3 text-xs">
            <X className="w-3.5 h-3.5" /> Cancel
          </button>
          <button
            onClick={mode === 'create' ? saveCreate : saveEdit}
            disabled={saving || !draftName.trim()}
            className="btn-primary !py-1 !px-3 text-xs disabled:opacity-50">
            {saving ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
            Save
          </button>
        </div>
      </div>

      {/* [F11] Dirty warning banner */}
      {pendingSelectId && (
        <div className="flex items-center justify-between gap-3 px-4 py-3 rounded-xl text-sm"
          style={{ background: 'color-mix(in oklch, #f59e0b 10%, var(--card))', border: '1px solid #f59e0b' }}>
          <span style={{ color: 'var(--ink)' }}>Unsaved changes — continue?</span>
          <div className="flex gap-2 shrink-0">
            <button onClick={confirmLeave} className="btn-ghost !py-0.5 !px-2 text-xs hover:text-red-500">Leave</button>
            <button onClick={() => setPendingSelectId(null)} className="btn-primary !py-0.5 !px-2 text-xs">Stay</button>
          </div>
        </div>
      )}

      {/* Name + Domain */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <p className="text-[10px] font-bold tracking-widest uppercase ink-2 mb-1.5">Workflow name *</p>
          <input value={draftName}
            onChange={e => { setDraftName(e.target.value); setIsDirty(true) }}
            className="input" placeholder="e.g. employee_onboarding" />
        </div>
        <div>
          <p className="text-[10px] font-bold tracking-widest uppercase ink-2 mb-1.5">Business domain</p>
          <input value={draftDomain}
            onChange={e => { setDraftDomain(e.target.value); setIsDirty(true) }}
            className="input" placeholder="e.g. HR, Finance, Auth…" />
        </div>
      </div>

      {/* Steps */}
      <div>
        <p className="text-[10px] font-bold tracking-widest uppercase ink-2 mb-2">
          Steps ({draftSteps.length})
        </p>

        {draftSteps.length === 0 && (
          <p className="text-xs ink-2 py-4 text-center">No steps yet — add endpoints below.</p>
        )}

        <div className="space-y-2">
          {draftSteps.map((s, i) => (
            <div
              key={s._key}
              draggable
              onDragStart={() => onDragStart(i)}
              onDragOver={e => onDragOver(e, i)}
              onDragEnd={onDragEnd}
              onDrop={e => e.preventDefault()}
              className="flex items-center gap-2 p-3 rounded-xl select-none transition-all"
              style={{
                background: dragOver === i && dragIdx.current !== i
                  ? 'color-mix(in oklch, var(--brand) 10%, var(--card))'
                  : 'color-mix(in oklch, var(--ink) 3%, var(--card))',
                border: dragOver === i && dragIdx.current !== i
                  ? '1px solid var(--brand)' : '1px solid var(--line)',
                opacity: dragIdx.current === i && dragOver !== i ? 0.35 : 1,
                cursor: 'grab',
              }}>
              <GripVertical className="w-4 h-4 shrink-0 ink-2" style={{ cursor: 'grab' }} />
              <span className="w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-black text-white shrink-0 grad-bg">
                {s.order}
              </span>
              <MethodBadge m={s.method as Method} />
              <span className="font-mono text-xs flex-1 truncate" style={{ color: 'var(--ink)' }}>{s.path}</span>
              {s.action !== '—' && (
                <span className="text-[11px] ink-2 hidden sm:block truncate max-w-[120px]">{s.action}</span>
              )}
              {/* [F14] Up / Down buttons */}
              <div className="flex flex-col gap-0.5 shrink-0" onMouseDown={e => e.stopPropagation()}>
                <button onClick={() => moveStep(i, 'up')} disabled={i === 0}
                  className="btn-ghost !p-0.5 disabled:opacity-20" title="Move up" style={{ cursor: 'pointer' }}>
                  <ChevronUp className="w-3 h-3" />
                </button>
                <button onClick={() => moveStep(i, 'down')} disabled={i === draftSteps.length - 1}
                  className="btn-ghost !p-0.5 disabled:opacity-20" title="Move down" style={{ cursor: 'pointer' }}>
                  <ChevronDown className="w-3 h-3" />
                </button>
              </div>
              <button
                onMouseDown={e => e.stopPropagation()}
                onClick={() => removeStep(i)}
                className="btn-ghost !p-1 shrink-0 hover:text-red-500"
                title="Delete" style={{ cursor: 'pointer' }}>
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* [F4] Combobox endpoint picker */}
      <div style={{ borderTop: '1px solid var(--line)', paddingTop: '1rem' }}>
        <p className="text-[10px] font-bold tracking-widest uppercase ink-2 mb-2">Add an endpoint</p>
        {availableEps.length === 0 ? (
          <p className="text-xs ink-2">All endpoints in this run are already in the workflow.</p>
        ) : (
          <div className="relative" ref={epComboRef}>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 ink-2 pointer-events-none" />
              <input
                className="input !pl-8 text-xs font-mono w-full"
                placeholder="Filter endpoints…"
                value={epSearch}
                onFocus={() => setShowEpList(true)}
                onChange={e => { setEpSearch(e.target.value); setShowEpList(true) }}
              />
            </div>
            {showEpList && filteredEps.length > 0 && (
              <div className="absolute z-20 left-0 right-0 mt-1 rounded-xl overflow-hidden"
                style={{ background: 'var(--card)', border: '1px solid var(--line)', boxShadow: '0 8px 24px rgba(0,0,0,0.15)', maxHeight: 220, overflowY: 'auto' }}>
                {filteredEps.slice(0, 30).map(ep => (
                  <button key={ep.canonical_key}
                    className="w-full text-left flex items-center gap-2 px-3 py-2.5 text-xs transition-colors"
                    style={{ borderBottom: '1px solid var(--line)' }}
                    onMouseEnter={e => (e.currentTarget.style.background = 'color-mix(in oklch, var(--brand) 6%, var(--card))')}
                    onMouseLeave={e => (e.currentTarget.style.background = '')}
                    onClick={() => addStep(ep)}>
                    <MethodBadge m={ep.method as Method} />
                    <span className="font-mono truncate flex-1" style={{ color: 'var(--ink)' }}>{ep.path}</span>
                    {ep.business_domain && <span className="ink-2 shrink-0">{ep.business_domain}</span>}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )

  // ── ViewPanel ─────────────────────────────────────────────────────────────
  const ViewPanel = () => wf ? (
    <div className="card pad relative">
      {/* [F2] Delete confirmation modal */}
      {confirmDeleteOpen && (
        <div className="absolute inset-0 z-10 flex items-center justify-center rounded-2xl"
          style={{ background: 'rgba(0,0,0,0.45)', backdropFilter: 'blur(4px)' }}>
          <div className="rounded-2xl px-6 py-5 space-y-4 w-80"
            style={{ background: 'var(--card)', border: '1px solid var(--line)', boxShadow: '0 8px 32px rgba(0,0,0,0.3)' }}>
            <div className="flex items-center gap-2">
              <Trash2 className="w-5 h-5 text-red-500 shrink-0" />
              <span className="font-bold text-sm" style={{ color: 'var(--ink)' }}>Delete this workflow?</span>
            </div>
            <p className="text-xs ink-2">This action is irreversible. The workflow <strong>{wf.name}</strong> will be permanently deleted.</p>
            <div className="flex gap-2 justify-end">
              <button onClick={() => setConfirmDeleteOpen(false)} className="btn-ghost !py-1.5 !px-3 text-xs">Cancel</button>
              <button onClick={doDelete} disabled={deleting}
                className="btn-ghost !py-1.5 !px-3 text-xs hover:text-red-500 disabled:opacity-40"
                style={{ color: '#ef4444', border: '1px solid #ef4444' }}>
                {deleting ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
                Confirm
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="flex items-start justify-between gap-4 mb-6">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <h3 className="text-lg font-black" style={{ color: 'var(--ink)' }}>{wf.name}</h3>
            {wf.domain !== '—' && (
              <span className="pill" style={{ background: 'color-mix(in oklch, var(--ink) 4%, var(--card))', borderColor: 'var(--line)', color: 'var(--ink-2)' }}>
                {wf.domain}
              </span>
            )}
            <OriginBadge wf={wf} />  {/* [F1] */}
          </div>
          <p className="text-sm ink-2">{wf.description}</p>
        </div>
        <div className="flex flex-col items-end gap-2 shrink-0">
          <div className="text-right">
            <p className="text-[10px] font-bold tracking-widest uppercase ink-2">Confidence</p>
            <p className="text-2xl font-black grad-text">{Math.round(wf.confidence * 100)}%</p>
          </div>
          <div className="flex gap-2 items-center">
            {wf.hasOriginal && !confirmRestore && (
              <button onClick={() => setConfirmRestore(true)} disabled={restoring}
                className="btn-ghost !py-1.5 !px-3 text-xs disabled:opacity-40" title="Restore the original AI version">
                {restoring ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <RotateCcw className="w-3.5 h-3.5" />}
                Restore
              </button>
            )}
            {confirmRestore && (
              <div className="flex items-center gap-1.5 px-2 py-1 rounded-lg text-xs"
                style={{ background: 'color-mix(in oklch, var(--brand) 8%, var(--card))', border: '1px solid var(--brand)' }}>
                <span style={{ color: 'var(--ink)' }}>Restore the AI version?</span>
                <button onClick={doRestore} className="btn-primary !py-0.5 !px-2 text-[11px]">Yes</button>
                <button onClick={() => setConfirmRestore(false)} className="btn-ghost !py-0.5 !px-2 text-[11px]">No</button>
              </div>
            )}
            <button onClick={enterEdit} className="btn-secondary !py-1.5 !px-3 text-xs">
              <Pencil className="w-3.5 h-3.5" /> Edit
            </button>
            <button onClick={() => setConfirmDeleteOpen(true)} disabled={deleting}
              className="btn-ghost !py-1.5 !px-3 text-xs hover:text-red-500 disabled:opacity-40">
              {deleting ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
            </button>
            {/* [F12] Pass workflow state when navigating to bulk */}
            <button
              onClick={() => nav(`/bulk?run=${selectedRunId}&workflow=${wf.id}`, { state: { workflowId: wf.id, steps: wf.steps } })}
              className="btn-primary !py-1.5 !px-3 text-xs">
              <Layers className="w-3.5 h-3.5" /> Automate
            </button>
          </div>
        </div>
      </div>

      <div className="relative">
        <div className="absolute left-5 top-2 bottom-2 w-0.5 rounded-full grad-bg" />
        <ol className="space-y-3">
          {wf.steps.map((s, i) => (
            <li key={s.order} className="relative pl-12" style={{ animationDelay: `${i * 60}ms` }}>
              <div className="absolute left-2 top-1.5 w-7 h-7 rounded-full grad-bg text-white text-xs font-black flex items-center justify-center ring-4"
                style={{ '--tw-ring-color': 'var(--card)' } as React.CSSProperties}>
                {s.order}
              </div>
              <div className="card pad !p-4">
                <div className="flex flex-wrap items-center gap-3">
                  <MethodBadge m={s.method} />
                  <span className="font-mono text-xs flex-1 min-w-0 truncate" style={{ color: 'var(--ink)' }}>{s.path}</span>
                  <SeverityBadge s={s.risk} />
                  {s.auth ? <Lock className="w-3.5 h-3.5 text-amber-500" /> : <Unlock className="w-3.5 h-3.5 text-emerald-500" />}
                </div>
                {(() => {
                  const ep = endpointByCanonical[s.canonical]
                  const desc = ep?.ai_description || ep?.ai_summary || (s.action !== '—' ? s.action : null)
                  const domain = ep?.business_domain
                  return (
                    <div className="mt-2 space-y-1">
                      {desc && <p className="text-sm" style={{ color: 'var(--ink)' }}>{desc}</p>}
                      <div className="flex items-center gap-3 flex-wrap">
                        {domain && (
                          <span className="pill text-[10px]" style={{ background: 'color-mix(in oklch, var(--brand) 8%, var(--card))', borderColor: 'color-mix(in oklch, var(--brand) 20%, var(--line))', color: 'var(--brand)' }}>
                            {domain}
                          </span>
                        )}
                        {s.action !== '—' && ep?.ai_description && (
                          <span className="text-xs ink-2 italic">{s.action}</span>
                        )}
                        {s.depends.length > 0 && (
                          <span className="text-xs ink-2">· depends on step {s.depends.join(', ')}</span>
                        )}
                      </div>
                    </div>
                  )
                })()}
              </div>
            </li>
          ))}
        </ol>
      </div>
    </div>
  ) : (
    <div className="card pad flex items-center justify-center text-sm ink-2 py-16">
      Select a workflow or create a new one.
    </div>
  )

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <AppLayout>
      <div className="p-6 space-y-6">

        {/* [F8+F9] Toast renderer */}
        <div className="fixed bottom-6 right-6 z-50 space-y-2 pointer-events-none">
          {toasts.map(t => (
            <div key={t.id}
              className="flex items-center gap-2.5 px-4 py-3 rounded-xl text-sm font-medium shadow-lg pointer-events-auto animate-fade-up"
              style={{
                background: t.type === 'success' ? 'color-mix(in oklch, #22c55e 15%, var(--card))' : 'color-mix(in oklch, #ef4444 15%, var(--card))',
                border: `1px solid ${t.type === 'success' ? '#22c55e' : '#ef4444'}`,
                color: t.type === 'success' ? '#15803d' : '#b91c1c',
              }}>
              {t.type === 'success'
                ? <Check className="w-4 h-4 shrink-0" />
                : <AlertCircle className="w-4 h-4 shrink-0" />}
              {t.message}
            </div>
          ))}
        </div>

        {/* Header */}
        <div className="flex items-end justify-between gap-4 flex-wrap">
          <div>
            <p className="text-xs font-semibold tracking-wider uppercase ink-2">Automation</p>
            <h2 className="text-xl font-black mt-0.5" style={{ color: 'var(--ink)' }}>Workflows</h2>
            {/* [F3] Show filtered count */}
            <p className="text-sm ink-2 mt-1">
              {searchQuery
                ? `${filteredWorkflows.length} / ${workflows.length} workflow${workflows.length !== 1 ? 's' : ''}`
                : `${workflows.length} workflow${workflows.length !== 1 ? 's' : ''} detected`}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {runs.length > 0 && (
              <select value={selectedRunId} onChange={e => setSelectedRunId(e.target.value)}
                className="input !py-1.5 !w-auto text-xs font-mono">
                {runs.map(r => <option key={r.id} value={r.id}>{r.file_name}</option>)}
              </select>
            )}
            {selectedRunId && (
              <button onClick={() => nav(`/endpoints?run=${selectedRunId}`)} className="btn-secondary">
                <Package className="w-4 h-4" /> Endpoints
              </button>
            )}
            <button onClick={enterCreate} className="btn-primary">
              <Plus className="w-4 h-4" /> New workflow
            </button>
          </div>
        </div>

        {/* [F5] Skeleton while loading */}
        {loading && (
          <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-4">
            <SkeletonSidebar />
            <SkeletonPanel />
          </div>
        )}

        {/* [F10] Load error */}
        {!loading && loadError && (
          <div className="card pad flex flex-col items-center py-12 gap-4 text-center">
            <AlertCircle className="w-8 h-8 text-red-400" />
            <p className="text-sm" style={{ color: 'var(--ink)' }}>{loadError}</p>
            <button onClick={() => loadWorkflows(selectedRunId)} className="btn-secondary text-xs">
              <RefreshCw className="w-3.5 h-3.5" /> Retry
            </button>
          </div>
        )}

        {!loading && !loadError && (
          <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-4">
            {/* Sidebar list */}
            <div className="space-y-2">

              {/* [F3] Search input */}
              {workflows.length > 0 && (
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 ink-2 pointer-events-none" />
                  <input
                    className="input !pl-8 text-xs w-full"
                    placeholder="Search workflows…"
                    value={searchQuery}
                    onChange={e => setSearchQuery(e.target.value)}
                  />
                </div>
              )}

              {filteredWorkflows.length === 0 && mode !== 'create' && (
                <div className="card pad text-center py-8 space-y-3">
                  <p className="text-sm ink-2">
                    {runs.length === 0 ? 'No analysis found.' : searchQuery ? 'No results for this search.' : 'No workflow detected for this run.'}
                  </p>
                  {runs.length === 0 && (
                    <button onClick={() => nav('/analysis')} className="btn-primary mx-auto text-xs">
                      <Package className="w-3.5 h-3.5" /> Analyze a HAR
                    </button>
                  )}
                </div>
              )}

              {filteredWorkflows.map(w => (
                <button key={w.id}
                  onClick={() => handleWorkflowSelect(w.id)}
                  className="w-full text-left card pad transition"
                  style={
                    w.id === activeId && mode !== 'create'
                      ? { outline: '2px solid var(--brand)', outlineOffset: -2 }
                      : { cursor: 'pointer' }
                  }
                  onMouseEnter={e => { if (w.id !== activeId || mode === 'create') (e.currentTarget as HTMLElement).style.borderColor = 'var(--brand)' }}
                  onMouseLeave={e => { (e.currentTarget as HTMLElement).style.borderColor = '' }}>
                  <div className="flex items-center justify-between gap-2 mb-1.5">
                    <p className="font-bold text-sm truncate" style={{ color: 'var(--ink)' }}>{w.name}</p>
                    <div className="flex items-center gap-1.5 shrink-0">
                      <OriginBadge wf={w} />  {/* [F1] */}
                      <span className="font-mono text-xs ink-2">{Math.round(w.confidence * 100)}%</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 text-xs">
                    {w.domain !== '—' && (
                      <span className="pill" style={{ background: 'color-mix(in oklch, var(--brand) 8%, var(--card))', borderColor: 'color-mix(in oklch, var(--brand) 20%, var(--line))', color: 'var(--brand)' }}>
                        {w.domain}
                      </span>
                    )}
                    <span className="font-mono ink-2">{w.steps.length} steps</span>
                  </div>
                </button>
              ))}

              {mode !== 'create' && (
                <button onClick={enterCreate} className="w-full card pad transition" style={{ borderStyle: 'dashed', cursor: 'pointer' }}>
                  <div className="text-center py-2">
                    <Plus className="w-5 h-5 mx-auto ink-2 mb-1" />
                    <p className="text-xs ink-2 font-medium">Create a workflow</p>
                  </div>
                </button>
              )}
            </div>

            {/* Detail / edit / create panel */}
            {mode === 'view'                       && <ViewPanel />}
            {(mode === 'edit' || mode === 'create') && <DraftPanel />}
          </div>
        )}
      </div>
    </AppLayout>
  )
}
