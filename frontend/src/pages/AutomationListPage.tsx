import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppLayout from '../components/layout/AppLayout'
import { StatusBadge } from '../components/aria/Badges'
import {
  listAutomationRuns, updateAutomationRun, deleteAutomationRun, AutomationRun,
} from '../lib/reportsApi'
import {
  FlaskConical, Plus, BarChart2, ChevronLeft, ChevronRight,
  Layers, Clock, CheckCircle2, XCircle, Pencil, Trash2,
  Check, X, RefreshCw, TriangleAlert,
} from 'lucide-react'

// ── Helpers ────────────────────────────────────────────────────────────────────

const PAGE_SIZE = 20

function formatDuration(sec?: number) {
  if (sec == null) return '—'
  if (sec < 60) return `${sec.toFixed(1)}s`
  return `${Math.floor(sec / 60)}m ${(sec % 60).toFixed(0)}s`
}

function formatDate(iso: string) {
  const d = new Date(iso)
  return {
    date: d.toLocaleDateString('en-US', { day: '2-digit', month: 'short', year: 'numeric' }),
    time: d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }),
  }
}

function SkeletonRow() {
  return (
    <tr className="border-t animate-pulse" style={{ borderColor: 'var(--line)' }}>
      {[160, 180, 80, 90, 90, 90, 120, 100].map((w, i) => (
        <td key={i} className="px-3 py-3">
          <div className="h-4 rounded" style={{ width: w, background: 'color-mix(in oklch, var(--ink) 8%, var(--card))' }} />
        </td>
      ))}
    </tr>
  )
}

// ── Delete modal ───────────────────────────────────────────────────────────────

function DeleteModal({
  run,
  deleting,
  onConfirm,
  onCancel,
}: {
  run: AutomationRun
  deleting: boolean
  onConfirm: () => void
  onCancel: () => void
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgba(0,0,0,0.45)', backdropFilter: 'blur(4px)' }}
      onClick={onCancel}>
      <div
        className="card pad w-full max-w-sm space-y-4"
        style={{ boxShadow: '0 20px 60px rgba(0,0,0,0.25)' }}
        onClick={e => e.stopPropagation()}>

        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0"
            style={{ background: 'color-mix(in oklch, #f43f5e 12%, var(--card))', border: '1px solid color-mix(in oklch, #f43f5e 25%, var(--line))' }}>
            <TriangleAlert className="w-5 h-5 text-rose-500" />
          </div>
          <div>
            <p className="font-bold text-sm" style={{ color: 'var(--ink)' }}>Delete this automation?</p>
            <p className="text-xs ink-2 mt-0.5">This action is irreversible — all logs will be lost.</p>
          </div>
        </div>

        <div className="px-3 py-2 rounded-xl font-mono text-xs truncate"
          style={{ background: 'color-mix(in oklch, var(--ink) 4%, var(--card))', border: '1px solid var(--line)', color: 'var(--ink)' }}>
          {run.workflow_name || run.id.slice(0, 16) + '…'}
        </div>

        <div className="flex justify-end gap-2 pt-1">
          <button onClick={onCancel} disabled={deleting} className="btn-secondary">Cancel</button>
          <button onClick={onConfirm} disabled={deleting} className="btn-danger" style={{ minWidth: '7rem' }}>
            {deleting
              ? <><RefreshCw className="w-3.5 h-3.5 animate-spin" /> Deleting…</>
              : <><Trash2 className="w-3.5 h-3.5" /> Delete</>
            }
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Main page ──────────────────────────────────────────────────────────────────

export default function AutomationListPage() {
  const nav = useNavigate()

  const [runs, setRuns]         = useState<AutomationRun[]>([])
  const [loading, setLoading]   = useState(true)
  const [statusFilter, setStatusFilter] = useState('all')
  const [modeFilter, setModeFilter]     = useState('all')
  const [page, setPage]         = useState(1)

  // Inline rename state
  const [editingId, setEditingId]   = useState<string | null>(null)
  const [editName, setEditName]     = useState('')
  const [savingEdit, setSavingEdit] = useState(false)

  // Delete state
  const [pendingDelete, setPendingDelete] = useState<AutomationRun | null>(null)
  const [deletingId, setDeletingId]       = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    listAutomationRuns({ limit: 100 })
      .then(data => setRuns(data.items))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const filtered = runs.filter(r => {
    const statusOk = statusFilter === 'all' || r.status === statusFilter
    const modeOk   = modeFilter === 'all'
      || (modeFilter === 'simulation' && r.dry_run)
      || (modeFilter === 'live' && !r.dry_run)
    return statusOk && modeOk
  })

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const safePage   = Math.min(page, totalPages)
  const pageItems  = filtered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE)

  function handleFilterChange(setter: (v: string) => void) {
    return (v: string) => { setter(v); setPage(1) }
  }

  // ── Rename ──────────────────────────────────────────────────────────────────

  function startEdit(run: AutomationRun, e: React.MouseEvent) {
    e.stopPropagation()
    setEditingId(run.id)
    setEditName(run.workflow_name || '')
  }

  async function doSaveEdit() {
    if (!editingId || !editName.trim()) return
    setSavingEdit(true)
    try {
      const updated = await updateAutomationRun(editingId, { workflow_name: editName.trim() })
      setRuns(prev => prev.map(r => r.id === updated.id ? { ...r, workflow_name: updated.workflow_name } : r))
      setEditingId(null)
    } catch { /* keep editing on error */ }
    finally { setSavingEdit(false) }
  }

  function doCancelEdit() { setEditingId(null) }

  // ── Delete ──────────────────────────────────────────────────────────────────

  function handleDelete(run: AutomationRun, e: React.MouseEvent) {
    e.stopPropagation()
    setPendingDelete(run)
  }

  async function confirmDelete() {
    if (!pendingDelete) return
    setDeletingId(pendingDelete.id)
    try {
      await deleteAutomationRun(pendingDelete.id)
      setRuns(prev => prev.filter(x => x.id !== pendingDelete.id))
      setPendingDelete(null)
    } catch { /* ignore */ }
    finally { setDeletingId(null) }
  }

  return (
    <AppLayout>
      <div className="p-6 space-y-6">

        {/* Header */}
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div>
            <h2 className="text-xl font-black" style={{ color: 'var(--ink)' }}>Simple Automation</h2>
            <p className="text-sm ink-2 mt-1">History of all automation runs — simulations and live executions.</p>
          </div>
          <button onClick={() => nav('/automation')} className="btn-primary">
            <Plus className="w-4 h-4" /> New automation
          </button>
        </div>

        {/* Info banner */}
        <div className="card overflow-hidden">
          <div className="grid lg:grid-cols-[1fr_auto] items-stretch">
            <div className="p-5 flex items-start gap-4">
              <div className="w-10 h-10 rounded-xl grad-bg text-white flex items-center justify-center flex-shrink-0">
                <FlaskConical className="w-5 h-5" />
              </div>
              <div>
                <p className="font-bold" style={{ color: 'var(--ink)' }}>Simple Automation — one row at a time</p>
                <p className="text-sm ink-2 mt-1 max-w-xl">
                  Each run corresponds to a test of an API workflow on one or a few JSON rows.
                  For large-scale executions, use <span className="font-semibold">Bulk Execution</span>.
                </p>
              </div>
            </div>
            <div className="p-5 flex items-center"
              style={{ background: 'color-mix(in oklch, var(--brand) 4%, var(--card))', borderLeft: '1px solid var(--line)' }}>
              <button onClick={() => nav('/bulk')} className="btn-secondary">
                <Layers className="w-4 h-4" /> Bulk Execution
              </button>
            </div>
          </div>
        </div>

        {/* Filters */}
        <div className="flex items-center gap-3 flex-wrap">
          <div>
            <p className="text-[10px] font-bold tracking-widest uppercase ink-2 mb-1">Status</p>
            <select value={statusFilter} onChange={e => handleFilterChange(setStatusFilter)(e.target.value)}
              className="input !py-1.5 text-xs">
              <option value="all">All</option>
              <option value="completed">Completed</option>
              <option value="running">In progress</option>
              <option value="failed">Failed</option>
            </select>
          </div>
          <div>
            <p className="text-[10px] font-bold tracking-widest uppercase ink-2 mb-1">Mode</p>
            <select value={modeFilter} onChange={e => handleFilterChange(setModeFilter)(e.target.value)}
              className="input !py-1.5 text-xs">
              <option value="all">All</option>
              <option value="simulation">Simulation</option>
              <option value="live">Live</option>
            </select>
          </div>
          {!loading && (
            <div className="self-end pb-0.5">
              <p className="text-xs ink-2">{filtered.length} run{filtered.length !== 1 ? 's' : ''}</p>
            </div>
          )}
        </div>

        {/* Table */}
        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="aria-thead">
                <tr>
                  {['Workflow', 'Instruction', 'Mode', 'Status', 'Success / Total', 'Duration', 'Date', 'Actions'].map(h => (
                    <th key={h} className="text-left px-3 py-2.5 text-xs">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {loading
                  ? Array.from({ length: 6 }).map((_, i) => <SkeletonRow key={i} />)
                  : pageItems.length === 0
                    ? (
                      <tr>
                        <td colSpan={8} className="px-3 py-16 text-center">
                          <div className="flex flex-col items-center gap-3">
                            <div className="w-14 h-14 rounded-2xl flex items-center justify-center"
                              style={{ background: 'color-mix(in oklch, var(--brand) 10%, var(--card))' }}>
                              <FlaskConical className="w-7 h-7" style={{ color: 'var(--brand)' }} />
                            </div>
                            <p className="font-semibold" style={{ color: 'var(--ink)' }}>No runs found</p>
                            <p className="text-xs ink-2">Adjust the filters or start your first automation.</p>
                            <button onClick={() => nav('/automation')} className="btn-primary mt-1">
                              <Plus className="w-4 h-4" /> New automation
                            </button>
                          </div>
                        </td>
                      </tr>
                    )
                    : pageItems.map(run => {
                      const { date, time } = formatDate(run.created_at)
                      const isEditing = editingId === run.id
                      return (
                        <tr key={run.id}
                          className="border-t transition-colors"
                          style={{ borderColor: 'var(--line)' }}
                          onMouseEnter={e => { if (!isEditing) e.currentTarget.style.background = 'color-mix(in oklch, var(--ink) 3%, var(--card))' }}
                          onMouseLeave={e => { e.currentTarget.style.background = '' }}>

                          {/* Workflow name — inline editable */}
                          <td className="px-3 py-2.5" onClick={e => isEditing && e.stopPropagation()}>
                            {isEditing ? (
                              <div className="flex items-center gap-1.5" onClick={e => e.stopPropagation()}>
                                <input
                                  autoFocus
                                  value={editName}
                                  onChange={e => setEditName(e.target.value)}
                                  onKeyDown={e => { if (e.key === 'Enter') doSaveEdit(); if (e.key === 'Escape') doCancelEdit() }}
                                  className="input !py-1 !px-2 text-xs w-44"
                                />
                                <button onClick={e => { e.stopPropagation(); doSaveEdit() }} disabled={savingEdit}
                                  className="btn-ghost !p-1 text-emerald-600 disabled:opacity-40" title="Save">
                                  {savingEdit ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
                                </button>
                                <button onClick={e => { e.stopPropagation(); doCancelEdit() }}
                                  className="btn-ghost !p-1 hover:text-rose-500" title="Cancel">
                                  <X className="w-3.5 h-3.5" />
                                </button>
                              </div>
                            ) : (
                              <div>
                                <p className="font-semibold text-xs" style={{ color: 'var(--ink)' }}>
                                  {run.workflow_name || '—'}
                                </p>
                                <p className="text-[10px] font-mono ink-2 mt-0.5">{run.id.slice(0, 8)}…</p>
                              </div>
                            )}
                          </td>

                          {/* Instruction */}
                          <td className="px-3 py-2.5 max-w-[180px]">
                            <span className="text-xs ink-2 truncate block" title={run.instruction ?? ''}>
                              {run.instruction
                                ? (run.instruction.length > 50 ? run.instruction.slice(0, 50) + '…' : run.instruction)
                                : '—'}
                            </span>
                          </td>

                          {/* Mode */}
                          <td className="px-3 py-2.5">
                            {run.dry_run
                              ? <span className="pill bg-sky-50 text-sky-700 border-sky-200">Simulation</span>
                              : <span className="pill bg-rose-50 text-rose-700 border-rose-200 font-bold">Live</span>
                            }
                          </td>

                          {/* Status */}
                          <td className="px-3 py-2.5">
                            <StatusBadge s={run.status as 'completed' | 'running' | 'failed' | 'pending'} />
                          </td>

                          {/* Success / Total */}
                          <td className="px-3 py-2.5">
                            <div className="flex items-center gap-1.5 text-xs">
                              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 flex-shrink-0" />
                              <span className="font-semibold text-emerald-600">{run.success_count}</span>
                              <span className="ink-2">/</span>
                              <span style={{ color: 'var(--ink)' }}>{run.total_steps}</span>
                              {run.failed_count > 0 && (
                                <>
                                  <XCircle className="w-3.5 h-3.5 text-rose-500 flex-shrink-0 ml-1" />
                                  <span className="font-semibold text-rose-600">{run.failed_count}</span>
                                </>
                              )}
                            </div>
                          </td>

                          {/* Duration */}
                          <td className="px-3 py-2.5">
                            <div className="flex items-center gap-1 text-xs ink-2">
                              <Clock className="w-3 h-3 flex-shrink-0" />
                              {formatDuration(run.duration_seconds)}
                            </div>
                          </td>

                          {/* Date */}
                          <td className="px-3 py-2.5">
                            <p className="text-xs" style={{ color: 'var(--ink)' }}>{date}</p>
                            <p className="text-[10px] ink-2">{time}</p>
                          </td>

                          {/* Actions */}
                          <td className="px-3 py-2.5" onClick={e => e.stopPropagation()}>
                            <div className="flex items-center gap-1">
                              {/* Rename */}
                              <button
                                onClick={e => startEdit(run, e)}
                                className="btn-ghost !p-1.5 text-xs"
                                title="Rename"
                                disabled={isEditing}>
                                <Pencil className="w-3.5 h-3.5" />
                              </button>

                              {/* Delete */}
                              <button
                                onClick={e => handleDelete(run, e)}
                                className="btn-ghost !p-1.5 text-xs hover:text-rose-600 hover:border-rose-200"
                                title="Delete">
                                <Trash2 className="w-3.5 h-3.5" />
                              </button>

                              {/* View report */}
                              <button
                                onClick={() => nav(`/reports?tab=automation&run=${run.id}`)}
                                className="btn-ghost !p-1.5 !px-2 text-xs"
                                title="View report">
                                <BarChart2 className="w-3.5 h-3.5" />
                                <span className="ml-1 hidden sm:inline">Report</span>
                              </button>
                            </div>
                          </td>
                        </tr>
                      )
                    })
                }
              </tbody>
            </table>
          </div>
        </div>

        {/* Pagination */}
        {!loading && totalPages > 1 && (
          <div className="flex items-center justify-between gap-4">
            <p className="text-xs ink-2">
              Page {safePage} / {totalPages} · {filtered.length} results
            </p>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={safePage === 1}
                className="btn-ghost !p-2"
                style={{ opacity: safePage === 1 ? 0.4 : 1 }}>
                <ChevronLeft className="w-4 h-4" />
              </button>
              {Array.from({ length: totalPages }, (_, i) => i + 1)
                .filter(p => p === 1 || p === totalPages || Math.abs(p - safePage) <= 1)
                .reduce<(number | '…')[]>((acc, p, i, arr) => {
                  if (i > 0 && (p as number) - (arr[i - 1] as number) > 1) acc.push('…')
                  acc.push(p)
                  return acc
                }, [])
                .map((p, i) =>
                  p === '…'
                    ? <span key={`ellipsis-${i}`} className="text-xs ink-2 px-1">…</span>
                    : (
                      <button key={p} onClick={() => setPage(p as number)}
                        className="w-8 h-8 rounded-lg text-xs font-semibold transition"
                        style={{
                          background: p === safePage ? 'var(--brand)' : 'transparent',
                          color: p === safePage ? '#fff' : 'var(--ink-2)',
                        }}>
                        {p}
                      </button>
                    )
                )}
              <button
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                disabled={safePage === totalPages}
                className="btn-ghost !p-2"
                style={{ opacity: safePage === totalPages ? 0.4 : 1 }}>
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}

      </div>

      {/* Delete confirmation modal */}
      {pendingDelete && (
        <DeleteModal
          run={pendingDelete}
          deleting={deletingId === pendingDelete.id}
          onConfirm={confirmDelete}
          onCancel={() => setPendingDelete(null)}
        />
      )}

    </AppLayout>
  )
}
