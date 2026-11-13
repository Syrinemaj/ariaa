import { useEffect, useState } from 'react'
import AppLayout from '../components/layout/AppLayout'
import { useToast } from '../contexts/ToastContext'
import {
  listConnections, createConnection, updateConnection, rotateConnectionSecret,
  revokeConnection, reactivateConnection, deleteConnection, testConnection, assignOperator, unassignOperator,
  getConnection, Connection,
} from '../lib/connectionsApi'
import { listUsers, BackendUser } from '../lib/usersApi'
import { ApiError } from '../lib/api'
import {
  Plug, Plus, X, ArrowRight, RefreshCw, Ban, CheckCircle2, XCircle,
  Loader2, KeyRound, Users2, Pencil, Trash2, TriangleAlert,
} from 'lucide-react'

const ENVIRONMENTS = [
  { value: 'test', label: 'Test' },
  { value: 'preprod', label: 'Preprod' },
  { value: 'prod', label: 'Prod' },
]

const AUTH_TYPES = [
  { value: 'api_key', label: 'API key' },
  { value: 'service_account', label: 'Service account' },
  { value: 'oauth_client_credentials', label: 'OAuth client credentials' },
]

interface FormState {
  name: string
  base_url: string
  environment: string
  auth_type: string
  secret: string
}

const EMPTY_FORM: FormState = { name: '', base_url: '', environment: 'test', auth_type: 'api_key', secret: '' }

export default function ConnectionsPage() {
  const { toast } = useToast()
  const [connections, setConnections] = useState<Connection[]>([])
  const [loading, setLoading] = useState(true)
  const [users, setUsers] = useState<BackendUser[]>([])

  const [testingId, setTestingId] = useState<string | null>(null)
  const [togglingId, setTogglingId] = useState<string | null>(null)

  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<Connection | null>(null)
  const [form, setForm] = useState<FormState>(EMPTY_FORM)
  const [formError, setFormError] = useState('')
  const [formLoading, setFormLoading] = useState(false)

  const [rotateFor, setRotateFor] = useState<Connection | null>(null)
  const [rotateSecret, setRotateSecret] = useState('')
  const [rotateError, setRotateError] = useState('')
  const [rotateLoading, setRotateLoading] = useState(false)

  const [operatorsFor, setOperatorsFor] = useState<Connection | null>(null)
  const [operatorIds, setOperatorIds] = useState<string[]>([])
  const [addOperatorId, setAddOperatorId] = useState('')
  const [operatorsLoading, setOperatorsLoading] = useState(false)

  const [deleteFor, setDeleteFor] = useState<Connection | null>(null)
  const [deleteLoading, setDeleteLoading] = useState(false)

  const load = () => {
    setLoading(true)
    listConnections()
      .then(res => setConnections(res.connections))
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    load()
    listUsers().then(setUsers).catch(() => {})
  }, [])

  function field<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm(f => ({ ...f, [key]: value }))
  }

  function openCreate() {
    setEditing(null)
    setForm(EMPTY_FORM)
    setFormError('')
    setFormOpen(true)
  }

  function openEdit(c: Connection) {
    setEditing(c)
    setForm({ name: c.name, base_url: c.base_url, environment: c.environment, auth_type: c.auth_type, secret: '' })
    setFormError('')
    setFormOpen(true)
  }

  async function handleSubmit() {
    setFormError('')
    if (!form.name.trim() || !form.base_url.trim() || (!editing && !form.secret.trim())) {
      setFormError('Name, base URL' + (editing ? '' : ' and secret') + ' are required.')
      return
    }
    setFormLoading(true)
    try {
      if (editing) {
        await updateConnection(editing.id, {
          name: form.name.trim(),
          base_url: form.base_url.trim(),
          environment: form.environment,
          auth_type: form.auth_type,
        })
        toast({ type: 'success', message: `Connection "${form.name}" updated.` })
      } else {
        await createConnection({
          name: form.name.trim(),
          base_url: form.base_url.trim(),
          environment: form.environment,
          auth_type: form.auth_type,
          secret: form.secret,
        })
        toast({ type: 'success', message: `Connection "${form.name}" created.` })
      }
      setFormOpen(false)
      load()
    } catch (e) {
      setFormError(e instanceof ApiError ? e.message : 'Something went wrong.')
    } finally {
      setFormLoading(false)
    }
  }

  async function handleTest(c: Connection) {
    setTestingId(c.id)
    try {
      const result = await testConnection(c.id)
      toast({ type: result.success ? 'success' : 'error', message: `${c.name}: ${result.message}` })
    } catch (e) {
      toast({ type: 'error', message: e instanceof ApiError ? e.message : 'Test failed.' })
    } finally {
      setTestingId(null)
    }
  }

  async function handleToggleStatus(c: Connection) {
    setTogglingId(c.id)
    try {
      if (c.status === 'active') {
        await revokeConnection(c.id)
        toast({ type: 'success', message: `"${c.name}" revoked.` })
      } else {
        await reactivateConnection(c.id)
        toast({ type: 'success', message: `"${c.name}" reactivated.` })
      }
      load()
    } catch (e) {
      toast({ type: 'error', message: e instanceof ApiError ? e.message : 'Action failed.' })
    } finally {
      setTogglingId(null)
    }
  }

  async function handleDeleteConnection() {
    if (!deleteFor) return
    setDeleteLoading(true)
    try {
      await deleteConnection(deleteFor.id)
      toast({ type: 'success', message: `"${deleteFor.name}" deleted.` })
      setDeleteFor(null)
      load()
    } catch (e) {
      toast({ type: 'error', message: e instanceof ApiError ? e.message : 'Delete failed.' })
    } finally {
      setDeleteLoading(false)
    }
  }

  function openRotate(c: Connection) {
    setRotateFor(c)
    setRotateSecret('')
    setRotateError('')
  }

  async function handleRotate() {
    if (!rotateFor) return
    if (!rotateSecret.trim()) {
      setRotateError('New secret is required.')
      return
    }
    setRotateLoading(true)
    setRotateError('')
    try {
      await rotateConnectionSecret(rotateFor.id, rotateSecret)
      toast({ type: 'success', message: `Secret rotated for "${rotateFor.name}".` })
      setRotateFor(null)
      load()
    } catch (e) {
      setRotateError(e instanceof ApiError ? e.message : 'Rotation failed.')
    } finally {
      setRotateLoading(false)
    }
  }

  async function openOperators(c: Connection) {
    setOperatorsFor(c)
    setAddOperatorId('')
    setOperatorsLoading(true)
    try {
      const full = await getConnection(c.id)
      setOperatorIds(full.operator_ids ?? [])
    } catch {
      setOperatorIds([])
    } finally {
      setOperatorsLoading(false)
    }
  }

  async function handleAddOperator() {
    if (!operatorsFor || !addOperatorId) return
    try {
      await assignOperator(operatorsFor.id, addOperatorId)
      setOperatorIds(ids => [...ids, addOperatorId])
      setAddOperatorId('')
    } catch (e) {
      toast({ type: 'error', message: e instanceof ApiError ? e.message : 'Could not assign operator.' })
    }
  }

  async function handleRemoveOperator(userId: string) {
    if (!operatorsFor) return
    try {
      await unassignOperator(operatorsFor.id, userId)
      setOperatorIds(ids => ids.filter(id => id !== userId))
    } catch (e) {
      toast({ type: 'error', message: e instanceof ApiError ? e.message : 'Could not remove operator.' })
    }
  }

  const operatorsOnly = users.filter(u => (u.role ?? '').toUpperCase() === 'OPERATOR')
  const userById = (id: string) => users.find(u => u.id === id)
  const assignableOperators = operatorsOnly.filter(u => !operatorIds.includes(u.id))

  return (
    <AppLayout>
      <div className="p-6 space-y-6">
        <div className="flex items-end justify-between gap-4 flex-wrap">
          <div>
            <h2 className="text-xl font-black flex items-center gap-2" style={{ color: 'var(--ink)' }}>
              <Plug className="w-5 h-5" style={{ color: 'var(--brand)' }} /> Connections
            </h2>
            <p className="text-sm mt-1 ink-2">
              How ARIA authenticates to target systems at execution time. Secrets are write-only — never shown again after creation.
            </p>
          </div>
          <button onClick={openCreate} className="btn-primary">
            <Plus className="w-4 h-4" /> New connection
          </button>
        </div>

        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="aria-thead">
                <tr>
                  {['Name', 'Base URL', 'Environment', 'Auth type', 'Status', 'Operators', 'Actions'].map(h => (
                    <th key={h} className="text-left px-4 py-2.5">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {loading && (
                  <tr><td colSpan={7} className="px-4 py-10 text-center text-sm ink-2">Loading…</td></tr>
                )}
                {!loading && connections.length === 0 && (
                  <tr><td colSpan={7} className="px-4 py-10 text-center text-sm ink-2">No connections yet. Create one to let operators run automations.</td></tr>
                )}
                {connections.map(c => (
                  <tr key={c.id} className="border-t" style={{ borderColor: 'var(--line)' }}>
                    <td className="px-4 py-2.5 font-semibold" style={{ color: 'var(--ink)' }}>{c.name}</td>
                    <td className="px-4 py-2.5 text-xs font-mono ink-2">{c.base_url}</td>
                    <td className="px-4 py-2.5 text-xs capitalize ink-2">{c.environment}</td>
                    <td className="px-4 py-2.5 text-xs ink-2">{c.auth_type.replace(/_/g, ' ')}</td>
                    <td className="px-4 py-2.5">
                      {c.status === 'active' ? (
                        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                          <CheckCircle2 className="w-3 h-3" /> Active
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-50 text-rose-700 border border-rose-200">
                          <XCircle className="w-3 h-3" /> Revoked
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2.5">
                      <button onClick={() => openOperators(c)} className="text-xs font-semibold flex items-center gap-1 hover:opacity-70" style={{ color: 'var(--brand)' }}>
                        <Users2 className="w-3.5 h-3.5" /> Manage
                      </button>
                    </td>
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-2 flex-wrap">
                        <button onClick={() => handleTest(c)} disabled={testingId === c.id} className="btn-secondary !py-1 !px-2.5 text-xs">
                          {testingId === c.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : 'Test'}
                        </button>
                        <button onClick={() => openEdit(c)} className="btn-ghost !p-1.5" title="Edit">
                          <Pencil className="w-3.5 h-3.5" />
                        </button>
                        <button onClick={() => openRotate(c)} className="btn-ghost !p-1.5" title="Rotate secret">
                          <KeyRound className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={() => handleToggleStatus(c)}
                          disabled={togglingId === c.id}
                          className="btn-ghost !p-1.5"
                          title={c.status === 'active' ? 'Revoke' : 'Reactivate'}
                        >
                          {togglingId === c.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : c.status === 'active' ? <Ban className="w-3.5 h-3.5" /> : <RefreshCw className="w-3.5 h-3.5" />}
                        </button>
                        <button
                          onClick={() => setDeleteFor(c)}
                          className="btn-ghost !p-1.5 hover:text-rose-600 hover:border-rose-200"
                          title="Delete connection"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* ── Create / edit connection modal ──────────────────────────────────── */}
      {formOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/50" onClick={() => !formLoading && setFormOpen(false)} />
          <div className="relative card pad w-full max-w-[480px] shadow-2xl space-y-4">
            <div className="flex items-start justify-between">
              <h3 className="text-lg font-black" style={{ color: 'var(--ink)' }}>{editing ? 'Edit connection' : 'New connection'}</h3>
              <button onClick={() => !formLoading && setFormOpen(false)} className="btn-ghost !p-1.5"><X className="w-4 h-4" /></button>
            </div>
            {formError && (
              <div className="rounded-xl px-4 py-3 text-sm font-medium" style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)', color: '#ef4444' }}>
                {formError}
              </div>
            )}
            <div>
              <p className="text-[10px] font-bold tracking-widest uppercase mb-1.5" style={{ color: 'var(--ink-2)' }}>Name</p>
              <input className="input" name="connection-name" value={form.name} onChange={e => field('name', e.target.value)} disabled={formLoading} placeholder="HR System — Prod" autoComplete="off" />
            </div>
            <div>
              <p className="text-[10px] font-bold tracking-widest uppercase mb-1.5" style={{ color: 'var(--ink-2)' }}>Base URL</p>
              <input className="input font-mono text-xs" name="connection-base-url" value={form.base_url} onChange={e => field('base_url', e.target.value)} disabled={formLoading} placeholder="https://hr-api.company.com" autoComplete="off" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <p className="text-[10px] font-bold tracking-widest uppercase mb-1.5" style={{ color: 'var(--ink-2)' }}>Environment</p>
                <select className="input" value={form.environment} onChange={e => field('environment', e.target.value)} disabled={formLoading}>
                  {ENVIRONMENTS.map(e => <option key={e.value} value={e.value}>{e.label}</option>)}
                </select>
              </div>
              <div>
                <p className="text-[10px] font-bold tracking-widest uppercase mb-1.5" style={{ color: 'var(--ink-2)' }}>Auth type</p>
                <select className="input" value={form.auth_type} onChange={e => field('auth_type', e.target.value)} disabled={formLoading}>
                  {AUTH_TYPES.map(a => <option key={a.value} value={a.value}>{a.label}</option>)}
                </select>
              </div>
            </div>
            {!editing && (
              <div>
                <p className="text-[10px] font-bold tracking-widest uppercase mb-1.5" style={{ color: 'var(--ink-2)' }}>Secret</p>
                <input type="password" className="input font-mono text-xs" name="connection-secret" value={form.secret} onChange={e => field('secret', e.target.value)} disabled={formLoading} placeholder="••••••••••••" autoComplete="new-password" />
                <p className="text-[11px] mt-1 ink-2">Encrypted at rest. Never shown again — use "Rotate secret" to change it later.</p>
              </div>
            )}
            <div className="flex gap-2 justify-end pt-1">
              <button onClick={() => !formLoading && setFormOpen(false)} className="btn-secondary" disabled={formLoading}>Cancel</button>
              <button onClick={handleSubmit} className="btn-primary flex items-center gap-2" disabled={formLoading}>
                {formLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <ArrowRight className="w-4 h-4" />}
                {editing ? 'Save' : 'Create'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Rotate secret modal ─────────────────────────────────────────────── */}
      {rotateFor && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/50" onClick={() => !rotateLoading && setRotateFor(null)} />
          <div className="relative card pad w-full max-w-[420px] shadow-2xl space-y-4">
            <div className="flex items-start justify-between">
              <h3 className="text-lg font-black" style={{ color: 'var(--ink)' }}>Rotate secret</h3>
              <button onClick={() => !rotateLoading && setRotateFor(null)} className="btn-ghost !p-1.5"><X className="w-4 h-4" /></button>
            </div>
            <p className="text-sm ink-2">New secret for "{rotateFor.name}". The old one stops working immediately.</p>
            {rotateError && (
              <div className="rounded-xl px-4 py-3 text-sm font-medium" style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)', color: '#ef4444' }}>
                {rotateError}
              </div>
            )}
            <input type="password" className="input font-mono text-xs" name="connection-rotate-secret" value={rotateSecret} onChange={e => setRotateSecret(e.target.value)} disabled={rotateLoading} placeholder="New secret" autoComplete="new-password" />
            <div className="flex gap-2 justify-end pt-1">
              <button onClick={() => !rotateLoading && setRotateFor(null)} className="btn-secondary" disabled={rotateLoading}>Cancel</button>
              <button onClick={handleRotate} className="btn-primary flex items-center gap-2" disabled={rotateLoading}>
                {rotateLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <KeyRound className="w-4 h-4" />} Rotate
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Manage operators modal ──────────────────────────────────────────── */}
      {operatorsFor && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/50" onClick={() => setOperatorsFor(null)} />
          <div className="relative card pad w-full max-w-[460px] shadow-2xl space-y-4">
            <div className="flex items-start justify-between">
              <div>
                <h3 className="text-lg font-black" style={{ color: 'var(--ink)' }}>Operators</h3>
                <p className="text-sm mt-0.5 ink-2">Who can use "{operatorsFor.name}". Admins can always use any connection.</p>
              </div>
              <button onClick={() => setOperatorsFor(null)} className="btn-ghost !p-1.5"><X className="w-4 h-4" /></button>
            </div>
            {operatorsLoading ? (
              <p className="text-sm ink-2 flex items-center gap-2"><Loader2 className="w-4 h-4 animate-spin" /> Loading…</p>
            ) : (
              <>
                <div className="space-y-2 max-h-[220px] overflow-y-auto">
                  {operatorIds.length === 0 && <p className="text-sm ink-2">No operator assigned yet.</p>}
                  {operatorIds.map(id => {
                    const u = userById(id)
                    return (
                      <div key={id} className="flex items-center justify-between px-3 py-2 rounded-xl" style={{ border: '1px solid var(--line)' }}>
                        <div>
                          <p className="text-sm font-semibold" style={{ color: 'var(--ink)' }}>{u?.full_name ?? id}</p>
                          {u && <p className="text-[11px] ink-2">{u.email}</p>}
                        </div>
                        <button onClick={() => handleRemoveOperator(id)} className="btn-ghost !p-1.5"><X className="w-3.5 h-3.5" /></button>
                      </div>
                    )
                  })}
                </div>
                <div className="flex gap-2">
                  <select className="input flex-1" value={addOperatorId} onChange={e => setAddOperatorId(e.target.value)}>
                    <option value="">Select an operator…</option>
                    {assignableOperators.map(u => <option key={u.id} value={u.id}>{u.full_name} ({u.email})</option>)}
                  </select>
                  <button onClick={handleAddOperator} disabled={!addOperatorId} className="btn-secondary shrink-0">
                    <Plus className="w-4 h-4" /> Add
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* ── Delete connection confirmation ──────────────────────────────────── */}
      {deleteFor && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/50" onClick={() => !deleteLoading && setDeleteFor(null)} />
          <div className="relative card pad w-full max-w-[420px] shadow-2xl space-y-4">
            <div className="flex items-start gap-3">
              <div className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
                style={{ background: 'rgba(239,68,68,0.1)', color: '#ef4444' }}>
                <TriangleAlert className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-lg font-black" style={{ color: 'var(--ink)' }}>Delete "{deleteFor.name}"?</h3>
                <p className="text-sm ink-2 mt-1">
                  This permanently removes the connection and its operator assignments. Past executions that used it
                  are kept in reports, just without a live link back to it. This cannot be undone.
                </p>
              </div>
            </div>
            <div className="flex gap-2 justify-end pt-1">
              <button onClick={() => setDeleteFor(null)} className="btn-secondary" disabled={deleteLoading}>Cancel</button>
              <button onClick={handleDeleteConnection} className="btn-danger flex items-center gap-2" disabled={deleteLoading}>
                {deleteLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />} Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </AppLayout>
  )
}
