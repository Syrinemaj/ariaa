import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppLayout from '../components/layout/AppLayout'
import { listRuns, updateRun, deleteRun, AnalysisRun } from '../lib/registryApi'
import { listUsers, BackendUser } from '../lib/usersApi'
import { useAuth } from '../contexts/AuthContext'
import { useRun } from '../contexts/RunContext'
import {
  Upload, Database, Network, Layers, Search,
  RefreshCw, ChevronLeft, ChevronRight, Sparkles,
  Shield, User, Trash2, Pencil, Check, X, TriangleAlert,
} from 'lucide-react'

// ── Delete confirmation modal ──────────────────────────────────────────────────

function DeleteModal({
  run,
  deleting,
  onConfirm,
  onCancel,
}: {
  run: AnalysisRun
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

        {/* Icon + title */}
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0"
            style={{ background: 'color-mix(in oklch, #f43f5e 12%, var(--card))', border: '1px solid color-mix(in oklch, #f43f5e 25%, var(--line))' }}>
            <TriangleAlert className="w-5 h-5 text-rose-500" />
          </div>
          <div>
            <p className="font-bold text-sm" style={{ color: 'var(--ink)' }}>Delete this analysis?</p>
            <p className="text-xs ink-2 mt-0.5">This action is irreversible.</p>
          </div>
        </div>

        {/* File name */}
        <div className="px-3 py-2 rounded-xl font-mono text-xs truncate"
          style={{ background: 'color-mix(in oklch, var(--ink) 4%, var(--card))', border: '1px solid var(--line)', color: 'var(--ink)' }}>
          {run.file_name}
        </div>

        {/* Actions */}
        <div className="flex justify-end gap-2 pt-1">
          <button onClick={onCancel} disabled={deleting} className="btn-secondary">
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={deleting}
            className="btn-danger"
            style={{ minWidth: '7rem' }}>
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

// ── Status pill ────────────────────────────────────────────────────────────────

const STATUS_META: Record<string, { label: string; color: string; dot: string }> = {
  completed:  { label: 'Completed',      color: 'text-emerald-700 bg-emerald-50 border-emerald-200',  dot: 'bg-emerald-500' },
  done:       { label: 'Completed',      color: 'text-emerald-700 bg-emerald-50 border-emerald-200',  dot: 'bg-emerald-500' },
  processing: { label: 'In progress',    color: 'text-amber-700 bg-amber-50 border-amber-200',        dot: 'bg-amber-500 animate-pulse' },
  running:    { label: 'In progress',    color: 'text-amber-700 bg-amber-50 border-amber-200',        dot: 'bg-amber-500 animate-pulse' },
  enriching:  { label: 'Enriching',      color: 'text-violet-700 bg-violet-50 border-violet-200',     dot: 'bg-violet-500 animate-pulse' },
  queued:     { label: 'Pending',        color: 'text-slate-700 bg-slate-50 border-slate-200',        dot: 'bg-slate-400' },
  pending:    { label: 'Pending',        color: 'text-slate-700 bg-slate-50 border-slate-200',        dot: 'bg-slate-400' },
  failed:     { label: 'Failed',         color: 'text-red-700 bg-red-50 border-red-200',              dot: 'bg-red-500' },
}

function StatusPill({ status }: { status: string }) {
  const s = STATUS_META[status] ?? { label: status, color: 'text-slate-600 bg-slate-50 border-slate-200', dot: 'bg-slate-400' }
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-semibold border ${s.color}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${s.dot}`} />
      {s.label}
    </span>
  )
}

// ── User avatar (for admin column) ────────────────────────────────────────────

function UserChip({ name, isCurrentUser }: { name: string; isCurrentUser: boolean }) {
  const initials = name
    .split(' ')
    .map(s => s[0] ?? '')
    .slice(0, 2)
    .join('')
    .toUpperCase() || '?'

  return (
    <div className="flex items-center gap-2">
      <div className="w-6 h-6 rounded-lg flex items-center justify-center text-white text-[10px] font-bold shrink-0"
        style={{ background: isCurrentUser ? 'linear-gradient(135deg, var(--brand), var(--accent))' : '#64748b' }}>
        {initials}
      </div>
      <span className="text-xs font-medium truncate max-w-[120px]" style={{ color: 'var(--ink)' }}>
        {name}
        {isCurrentUser && <span className="ml-1 ink-2">(you)</span>}
      </span>
    </div>
  )
}

// ── Page ─────────────────────────────────────────────────────────────────────

const PAGE_SIZE = 20

export default function RunsHistoryPage() {
  const nav              = useNavigate()
  const { user }         = useAuth()
  const { setActiveRun } = useRun()

  const isAdmin = user?.role === 'ADMIN'

  const [runs, setRuns]           = useState<AnalysisRun[]>([])
  const [total, setTotal]         = useState(0)
  const [page, setPage]           = useState(0)
  const [loading, setLoading]     = useState(false)

  // Admin only: map userId → display name
  const [userMap, setUserMap]     = useState<Record<string, string>>({})
  const [loadingUsers, setLoadingUsers] = useState(false)

  const [q, setQ]                       = useState('')
  const [statusFilter, setStatusFilter] = useState('ALL')

  // Inline rename
  const [editingId, setEditingId]   = useState<string | null>(null)
  const [editName, setEditName]     = useState('')
  const [savingEdit, setSavingEdit] = useState(false)

  // Delete modal
  const [pendingDelete, setPendingDelete] = useState<AnalysisRun | null>(null)
  const [deletingId, setDeletingId]       = useState<string | null>(null)

  // Load all workspace users (admin only) to display uploader names
  useEffect(() => {
    if (!isAdmin) return
    setLoadingUsers(true)
    listUsers()
      .then((users: BackendUser[]) => {
        const map: Record<string, string> = {}
        users.forEach(u => { map[u.id] = u.full_name || u.email })
        setUserMap(map)
      })
      .catch(() => {})
      .finally(() => setLoadingUsers(false))
  }, [isAdmin])

  function loadPage(p: number) {
    setLoading(true)
    listRuns({ limit: PAGE_SIZE, offset: p * PAGE_SIZE })
      .then(data => {
        setRuns(data.items)
        setTotal(data.total)
        setPage(p)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(() => { loadPage(0) }, [])

  // Operators see only their own runs; admins see everything
  const visibleRuns = isAdmin
    ? runs
    : runs.filter(r => r.created_by_user_id === user?.id)

  const filtered = visibleRuns.filter(r => {
    const matchQ = q === '' ||
      r.file_name.toLowerCase().includes(q.toLowerCase()) ||
      r.id.includes(q)
    const matchS = statusFilter === 'ALL' ||
      r.status === statusFilter ||
      (statusFilter === 'completed' && r.status === 'done')
    return matchQ && matchS
  })

  const totalPages = Math.ceil(total / PAGE_SIZE)

  function handleRowClick(r: AnalysisRun) {
    if (editingId === r.id) return
    setActiveRun({ id: r.id, name: r.file_name })
    nav(`/endpoints?run=${r.id}`)
  }

  function startEdit(r: AnalysisRun, e: React.MouseEvent) {
    e.stopPropagation()
    setEditingId(r.id)
    setEditName(r.file_name)
  }

  async function doSaveEdit() {
    if (!editingId || !editName.trim()) return
    setSavingEdit(true)
    try {
      const updated = await updateRun(editingId, { file_name: editName.trim() })
      setRuns(prev => prev.map(r => r.id === updated.id ? { ...r, file_name: updated.file_name } : r))
      setEditingId(null)
    } catch { /* keep editing on error */ }
    finally { setSavingEdit(false) }
  }

  function doCancelEdit() { setEditingId(null) }

  function handleDelete(r: AnalysisRun, e: React.MouseEvent) {
    e.stopPropagation()
    setPendingDelete(r)
  }

  async function confirmDelete() {
    if (!pendingDelete) return
    setDeletingId(pendingDelete.id)
    try {
      await deleteRun(pendingDelete.id)
      setRuns(prev => prev.filter(x => x.id !== pendingDelete.id))
      setTotal(prev => prev - 1)
      setPendingDelete(null)
    } catch { /* ignore */ }
    finally { setDeletingId(null) }
  }

  const uploaderName = (run: AnalysisRun): string => {
    if (!run.created_by_user_id) return '—'
    return userMap[run.created_by_user_id] || run.created_by_user_id.slice(0, 8) + '…'
  }

  return (
    <AppLayout>
      <div className="p-6 space-y-6">

        {/* Header */}
        <div className="flex items-end justify-between gap-4 flex-wrap">
          <div>
            <p className="text-xs font-semibold tracking-wider uppercase ink-2">Discovery</p>
            <h2 className="text-xl font-black mt-0.5" style={{ color: 'var(--ink)' }}>
              Analysis history
            </h2>
            <p className="text-sm ink-2 mt-1">
              {isAdmin ? (
                <span className="inline-flex items-center gap-1.5">
                  <Shield className="w-3.5 h-3.5" style={{ color: 'var(--brand)' }} />
                  Admin view · {total} HAR files · all users
                </span>
              ) : (
                <span className="inline-flex items-center gap-1.5">
                  <User className="w-3.5 h-3.5 ink-2" />
                  Your analyses · {visibleRuns.length} HAR files uploaded
                </span>
              )}
            </p>
          </div>
          <button onClick={() => nav('/analysis')} className="btn-primary">
            <Upload className="w-4 h-4" /> New analysis
          </button>
        </div>

        {/* Role badge */}
        {isAdmin && (
          <div className="flex items-center gap-2 px-4 py-2.5 rounded-xl w-fit"
            style={{ background: 'color-mix(in oklch, var(--brand) 8%, var(--card))', border: '1px solid color-mix(in oklch, var(--brand) 20%, var(--line))' }}>
            <Shield className="w-3.5 h-3.5 shrink-0" style={{ color: 'var(--brand)' }} />
            <span className="text-xs font-semibold" style={{ color: 'var(--brand)' }}>
              Administrator access — you can see analyses from all users
            </span>
          </div>
        )}

        {/* Filters + table */}
        <div className="card overflow-hidden">
          <div className="p-4 flex flex-wrap items-center gap-3" style={{ borderBottom: '1px solid var(--line)' }}>
            <div className="relative flex-1 min-w-[240px]">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 ink-2" />
              <input value={q} onChange={e => setQ(e.target.value)}
                className="input !pl-9"
                placeholder="Search by file name or ID…" />
            </div>
            <label className="flex items-center gap-2 px-3 py-2 rounded-xl text-sm cursor-pointer"
              style={{ border: '1px solid var(--line)', background: 'var(--card)' }}>
              <span className="text-xs font-medium ink-2">Status</span>
              <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
                className="bg-transparent outline-none text-sm font-medium" style={{ color: 'var(--ink)' }}>
                {['ALL', 'completed', 'processing', 'failed', 'queued'].map(s => (
                  <option key={s} value={s}>
                    {s === 'ALL' ? 'All' : STATUS_META[s]?.label ?? s}
                  </option>
                ))}
              </select>
            </label>
            <button onClick={() => loadPage(page)} className="btn-secondary !py-1.5 !px-3" title="Refresh">
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>
            <span className="ml-auto text-xs font-mono ink-2">
              {filtered.length} / {isAdmin ? total : visibleRuns.length}
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="aria-thead">
                <tr>
                  <th className="text-left px-4 py-2.5">HAR file</th>
                  <th className="text-left px-4 py-2.5">Status</th>
                  <th className="text-left px-4 py-2.5">Endpoints</th>
                  <th className="text-left px-4 py-2.5">Date</th>
                  {/* Uploader column — admins only */}
                  {isAdmin && (
                    <th className="text-left px-4 py-2.5">
                      <span className="inline-flex items-center gap-1.5">
                        <User className="w-3 h-3" /> Uploaded by
                      </span>
                    </th>
                  )}
                  <th className="text-left px-4 py-2.5">Actions</th>
                </tr>
              </thead>
              <tbody>
                {(loading || loadingUsers) && (
                  <tr>
                    <td colSpan={isAdmin ? 6 : 5} className="px-4 py-12 text-center">
                      <RefreshCw className="w-5 h-5 animate-spin mx-auto ink-2" />
                    </td>
                  </tr>
                )}

                {!loading && !loadingUsers && filtered.length === 0 && (
                  <tr>
                    <td colSpan={isAdmin ? 6 : 5} className="px-4 py-12 text-center">
                      <p className="text-sm ink-2">
                        {visibleRuns.length === 0
                          ? "You haven't uploaded a HAR file yet."
                          : 'No files match your search.'}
                      </p>
                      {visibleRuns.length === 0 && (
                        <button onClick={() => nav('/analysis')} className="btn-primary mt-4 mx-auto text-xs">
                          <Upload className="w-3.5 h-3.5" /> Upload a HAR
                        </button>
                      )}
                    </td>
                  </tr>
                )}

                {!loading && !loadingUsers && filtered.map(r => {
                  const isOwner = r.created_by_user_id === user?.id
                  return (
                    <tr key={r.id}
                      className="border-t cursor-pointer transition"
                      style={{ borderColor: 'var(--line)' }}
                      onMouseEnter={e => (e.currentTarget.style.background = 'color-mix(in oklch, var(--brand) 4%, var(--card))')}
                      onMouseLeave={e => (e.currentTarget.style.background = '')}
                      onClick={() => handleRowClick(r)}>

                      {/* File */}
                      <td className="px-4 py-3" onClick={e => editingId === r.id && e.stopPropagation()}>
                        <div className="flex items-center gap-2.5">
                          <div className="w-7 h-7 rounded-lg flex items-center justify-center shrink-0"
                            style={{ background: 'color-mix(in oklch, var(--brand) 10%, var(--card))', color: 'var(--brand)' }}>
                            <Sparkles className="w-3.5 h-3.5" />
                          </div>
                          <div className="min-w-0 flex-1">
                            {editingId === r.id ? (
                              <div className="flex items-center gap-1.5" onClick={e => e.stopPropagation()}>
                                <input
                                  autoFocus
                                  value={editName}
                                  onChange={e => setEditName(e.target.value)}
                                  onKeyDown={e => { if (e.key === 'Enter') doSaveEdit(); if (e.key === 'Escape') doCancelEdit() }}
                                  className="input !py-1 !px-2 text-xs font-mono w-40"
                                />
                                <button onClick={e => { e.stopPropagation(); doSaveEdit() }} disabled={savingEdit}
                                  className="btn-ghost !p-1 text-emerald-600 hover:text-emerald-700 disabled:opacity-40" title="Save">
                                  {savingEdit ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
                                </button>
                                <button onClick={e => { e.stopPropagation(); doCancelEdit() }} className="btn-ghost !p-1 hover:text-rose-500" title="Cancel">
                                  <X className="w-3.5 h-3.5" />
                                </button>
                              </div>
                            ) : (
                              <>
                                <p className="font-semibold truncate max-w-[200px]" style={{ color: 'var(--ink)' }}>
                                  {r.file_name}
                                </p>
                                <p className="text-[10px] font-mono ink-2 mt-0.5">{r.id.slice(0, 8)}…</p>
                              </>
                            )}
                          </div>
                        </div>
                      </td>

                      {/* Status */}
                      <td className="px-4 py-3">
                        <StatusPill status={r.status} />
                      </td>

                      {/* Endpoints */}
                      <td className="px-4 py-3">
                        <span className="font-mono font-bold text-sm" style={{ color: 'var(--ink)' }}>
                          {r.total_normalized_endpoints > 0
                            ? r.total_normalized_endpoints.toLocaleString()
                            : '—'}
                        </span>
                      </td>

                      {/* Date */}
                      <td className="px-4 py-3">
                        <p className="text-xs" style={{ color: 'var(--ink)' }}>
                          {new Date(r.created_at).toLocaleDateString('en-US', {
                            day: '2-digit', month: 'short', year: 'numeric',
                          })}
                        </p>
                        <p className="text-[10px] ink-2">
                          {new Date(r.created_at).toLocaleTimeString('en-US', {
                            hour: '2-digit', minute: '2-digit',
                          })}
                        </p>
                      </td>

                      {/* Uploader — admin only */}
                      {isAdmin && (
                        <td className="px-4 py-3" onClick={e => e.stopPropagation()}>
                          <UserChip
                            name={uploaderName(r)}
                            isCurrentUser={isOwner}
                          />
                        </td>
                      )}

                      {/* Actions */}
                      <td className="px-4 py-3" onClick={e => e.stopPropagation()}>
                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => { setActiveRun({ id: r.id, name: r.file_name }); nav(`/endpoints?run=${r.id}`) }}
                            className="btn-ghost !py-1 !px-2 text-xs" title="Explore endpoints">
                            <Database className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={() => { setActiveRun({ id: r.id, name: r.file_name }); nav(`/workflows?run=${r.id}`) }}
                            className="btn-ghost !py-1 !px-2 text-xs" title="View workflows">
                            <Network className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={() => { setActiveRun({ id: r.id, name: r.file_name }); nav(`/bulk?run=${r.id}`) }}
                            className="btn-ghost !py-1 !px-2 text-xs" title="Automate">
                            <Layers className="w-3.5 h-3.5" />
                          </button>

                          {/* Separator */}
                          <span className="w-px h-4 mx-0.5 shrink-0" style={{ background: 'var(--line)' }} />

                          <button
                            onClick={e => startEdit(r, e)}
                            disabled={editingId === r.id}
                            className="btn-ghost !py-1 !px-2 text-xs disabled:opacity-40"
                            title="Rename">
                            <Pencil className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={e => handleDelete(r, e)}
                            disabled={deletingId === r.id}
                            className="btn-ghost !py-1 !px-2 text-xs hover:text-red-500 disabled:opacity-40"
                            title="Delete this analysis">
                            {deletingId === r.id
                              ? <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                              : <Trash2 className="w-3.5 h-3.5" />
                            }
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          {/* Pagination — visible to admin only (operators see fewer rows, usually no need) */}
          {isAdmin && totalPages > 1 && (
            <div className="flex items-center justify-between px-5 py-3"
              style={{ borderTop: '1px solid var(--line)' }}>
              <p className="text-xs ink-2">
                Page {page + 1} / {totalPages} · {total} files
              </p>
              <div className="flex items-center gap-1">
                <button
                  disabled={page === 0}
                  onClick={() => loadPage(page - 1)}
                  className="btn-ghost !py-1.5 !px-2 disabled:opacity-30">
                  <ChevronLeft className="w-4 h-4" />
                </button>
                {Array.from({ length: Math.min(totalPages, 5) }, (_, i) => {
                  const p = page < 3 ? i : page - 2 + i
                  if (p >= totalPages) return null
                  return (
                    <button key={p} onClick={() => loadPage(p)}
                      className="w-8 h-8 rounded-lg text-xs font-bold transition"
                      style={{
                        background: p === page ? 'var(--brand)' : 'transparent',
                        color: p === page ? 'white' : 'var(--ink-2)',
                      }}>
                      {p + 1}
                    </button>
                  )
                })}
                <button
                  disabled={page >= totalPages - 1}
                  onClick={() => loadPage(page + 1)}
                  className="btn-ghost !py-1.5 !px-2 disabled:opacity-30">
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}
        </div>

      </div>

      {/* Delete confirmation modal */}
      {pendingDelete && (
        <DeleteModal
          run={pendingDelete}
          deleting={deletingId === pendingDelete.id}
          onConfirm={confirmDelete}
          onCancel={() => !deletingId && setPendingDelete(null)}
        />
      )}
    </AppLayout>
  )
}
