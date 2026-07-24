import { useEffect, useState } from 'react'
import AppLayout from '../components/layout/AppLayout'
import { listUsers, activateUser, deactivateUser, updateUserRole, createUser, BackendUser } from '../lib/usersApi'
import { ApiError } from '../lib/api'
import { Search, Plus, X, ArrowRight, Clock, CheckCircle2, XCircle, RefreshCw } from 'lucide-react'

// ── Backend roles ─────────────────────────────────────────────────────────────

type BackendRole = 'ADMIN' | 'OPERATOR' | 'VIEWER'

const ROLE_INFO: Record<BackendRole, { label: string; swatch: string; description: string }> = {
  ADMIN:    { label: 'Admin',      swatch: '#8b5cf6', description: 'Accès total, gestion des utilisateurs' },
  OPERATOR: { label: 'Opérateur', swatch: '#6366f1', description: 'Exécutions bulk et automatisations'   },
  VIEWER:   { label: 'Lecteur',   swatch: '#64748b', description: 'Lecture seule'                        },
}

type UserStatus = 'active' | 'pending' | 'rejected'

interface MappedUser {
  id:     string
  name:   string
  email:  string
  role:   BackendRole
  status: UserStatus
}

function mapUser(bu: BackendUser): MappedUser {
  let status: UserStatus
  if (bu.is_active)          status = 'active'
  else if (!bu.last_login_at) status = 'pending'   // jamais connecté → en attente d'approbation
  else                        status = 'rejected'   // déjà connecté, puis désactivé
  return {
    id:     bu.id,
    name:   bu.full_name,
    email:  bu.email,
    role:   ((bu.role ?? 'OPERATOR').toUpperCase() as BackendRole),
    status,
  }
}

// ── Status badge ──────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: UserStatus }) {
  if (status === 'active')
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
        <CheckCircle2 className="w-3 h-3" /> Actif
      </span>
    )
  if (status === 'pending')
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200">
        <Clock className="w-3 h-3" /> En attente
      </span>
    )
  return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-50 text-rose-700 border border-rose-200">
      <XCircle className="w-3 h-3" /> Désactivé
    </span>
  )
}

// ── Create user form state ────────────────────────────────────────────────────

interface InviteForm {
  full_name: string
  email:     string
  password:  string
  role:      BackendRole
}

const EMPTY_FORM: InviteForm = { full_name: '', email: '', password: '', role: 'OPERATOR' }

// ── Page ──────────────────────────────────────────────────────────────────────

export default function UsersPage() {
  const [users, setUsers]             = useState<MappedUser[]>([])
  const [loading, setLoading]         = useState(true)
  const [q, setQ]                     = useState('')
  const [inviteOpen, setInviteOpen]   = useState(false)
  const [inviteForm, setInviteForm]   = useState<InviteForm>(EMPTY_FORM)
  const [inviteLoading, setInviteLoading] = useState(false)
  const [inviteError, setInviteError] = useState('')
  const [savingRole, setSavingRole]   = useState<string | null>(null)

  // ── Data loading ────────────────────────────────────────────────────────────

  const load = () => {
    setLoading(true)
    listUsers()
      .then(data => setUsers(data.map(mapUser)))
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  // ── Filtering ───────────────────────────────────────────────────────────────

  const filtered      = users.filter(u => (u.name + u.email).toLowerCase().includes(q.toLowerCase()))
  const pendingCount  = users.filter(u => u.status === 'pending').length

  // ── Role change ─────────────────────────────────────────────────────────────

  const handleRoleChange = async (userId: string, role: BackendRole) => {
    setUsers(prev => prev.map(u => u.id === userId ? { ...u, role } : u))
    setSavingRole(userId)
    try {
      await updateUserRole(userId, role)
    } catch {
      load()
    } finally {
      setSavingRole(null)
    }
  }

  // ── Approve / Reject / Reactivate / Deactivate ─────────────────────────────

  const handleActivate = async (userId: string, activate: boolean) => {
    setUsers(prev => prev.map(u =>
      u.id === userId ? { ...u, status: activate ? 'active' : 'rejected' } : u
    ))
    try {
      if (activate) await activateUser(userId)
      else          await deactivateUser(userId)
    } catch {
      load()
    }
  }

  // ── Create user (modal) ─────────────────────────────────────────────────────

  const openInvite = () => {
    setInviteForm(EMPTY_FORM)
    setInviteError('')
    setInviteOpen(true)
  }

  const handleCreate = async () => {
    if (!inviteForm.full_name.trim()) { setInviteError('Le nom est requis.'); return }
    if (!inviteForm.email.includes('@')) { setInviteError('Email invalide.'); return }
    if (inviteForm.password.length < 8) { setInviteError('Mot de passe min. 8 caractères.'); return }
    setInviteLoading(true)
    setInviteError('')
    try {
      await createUser({
        email:     inviteForm.email.trim().toLowerCase(),
        password:  inviteForm.password,
        full_name: inviteForm.full_name.trim(),
        role:      inviteForm.role,
      })
      setInviteOpen(false)
      load()
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.status === 409) setInviteError('Cet email est déjà enregistré.')
        else if (err.status === 422) setInviteError('Données invalides. Vérifiez les champs.')
        else setInviteError('Erreur lors de la création. Réessayez.')
      } else {
        setInviteError('Erreur réseau.')
      }
    } finally {
      setInviteLoading(false)
    }
  }

  // ── Helpers ─────────────────────────────────────────────────────────────────

  const initials = (name: string) =>
    name.split(' ').map(s => s[0]).slice(0, 2).join('').toUpperCase()

  const field = (key: keyof InviteForm, value: string) =>
    setInviteForm(prev => ({ ...prev, [key]: value }))

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <AppLayout>
      <div className="p-6 space-y-6">

        {/* Header */}
        <div className="flex items-end justify-between gap-4 flex-wrap">
          <div>
            <h2 className="text-xl font-black" style={{ color: 'var(--ink)' }}>Utilisateurs</h2>
            <p className="text-sm mt-1" style={{ color: 'var(--ink-2)' }}>
              {users.length} membres ·{' '}
              {pendingCount > 0
                ? <span className="font-semibold text-amber-600">{pendingCount} en attente d'approbation</span>
                : <span>0 en attente</span>}
            </p>
          </div>
          <button onClick={openInvite} className="btn-primary flex items-center gap-2">
            <Plus className="w-4 h-4" /> Créer un utilisateur
          </button>
        </div>

        {/* Compteurs par rôle */}
        <div className="grid grid-cols-3 gap-3">
          {(Object.entries(ROLE_INFO) as [BackendRole, typeof ROLE_INFO[BackendRole]][]).map(([k, v]) => (
            <div key={k} className="card p-3 flex items-center gap-3">
              <div className="w-9 h-9 rounded-xl flex items-center justify-center text-white font-bold text-sm flex-shrink-0"
                style={{ background: v.swatch }}>
                {v.label[0]}
              </div>
              <div>
                <p className="text-[10px] font-bold tracking-widest uppercase" style={{ color: 'var(--ink-2)' }}>{v.label}</p>
                <p className="text-xl font-black" style={{ color: 'var(--ink)' }}>
                  {users.filter(u => u.role === k && u.status === 'active').length}
                </p>
              </div>
            </div>
          ))}
        </div>

        {/* Tableau */}
        <div className="card overflow-hidden">
          <div className="p-4 flex flex-wrap items-center gap-3" style={{ borderBottom: '1px solid var(--line)' }}>
            <div className="relative flex-1 min-w-[200px]">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--ink-2)' }} />
              <input
                value={q}
                onChange={e => setQ(e.target.value)}
                className="input !pl-9"
                placeholder="Rechercher par nom ou email…"
              />
            </div>
            <span className="text-xs font-mono" style={{ color: 'var(--ink-2)' }}>
              {filtered.length} / {users.length}
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="aria-thead">
                <tr>
                  <th className="text-left px-4 py-2.5">Membre</th>
                  <th className="text-left px-4 py-2.5">Email</th>
                  <th className="text-left px-4 py-2.5">Rôle</th>
                  <th className="text-left px-4 py-2.5">Statut</th>
                  <th className="text-right px-4 py-2.5">Actions</th>
                </tr>
              </thead>
              <tbody>
                {loading && (
                  <tr><td colSpan={5} className="px-4 py-8 text-center text-sm" style={{ color: 'var(--ink-2)' }}>
                    Chargement…
                  </td></tr>
                )}
                {!loading && filtered.length === 0 && (
                  <tr><td colSpan={5} className="px-4 py-8 text-center text-sm" style={{ color: 'var(--ink-2)' }}>
                    Aucun utilisateur trouvé.
                  </td></tr>
                )}
                {filtered.map(u => {
                  const info    = ROLE_INFO[u.role] ?? ROLE_INFO.OPERATOR
                  const isSaving = savingRole === u.id
                  return (
                    <tr
                      key={u.id}
                      className="border-t transition"
                      style={{ borderColor: 'var(--line)' }}
                      onMouseEnter={e => (e.currentTarget.style.background = 'color-mix(in oklch, var(--brand) 3%, var(--card))')}
                      onMouseLeave={e => (e.currentTarget.style.background = '')}
                    >
                      {/* Membre */}
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-3">
                          <div className="w-9 h-9 rounded-xl flex items-center justify-center text-white font-bold text-sm flex-shrink-0"
                            style={{ background: info.swatch }}>
                            {initials(u.name)}
                          </div>
                          <div>
                            <p className="font-semibold" style={{ color: 'var(--ink)' }}>{u.name}</p>
                            <p className="text-xs" style={{ color: 'var(--ink-2)' }}>{info.description}</p>
                          </div>
                        </div>
                      </td>

                      {/* Email */}
                      <td className="px-4 py-3 font-mono text-xs" style={{ color: 'var(--ink-2)' }}>
                        {u.email}
                      </td>

                      {/* Rôle */}
                      <td className="px-4 py-3">
                        <div className="relative inline-flex items-center">
                          <select
                            value={u.role}
                            onChange={e => void handleRoleChange(u.id, e.target.value as BackendRole)}
                            disabled={isSaving}
                            className="input !py-1 !w-auto text-xs font-medium disabled:opacity-50 pr-8"
                          >
                            {(Object.entries(ROLE_INFO) as [BackendRole, typeof ROLE_INFO[BackendRole]][]).map(([k, v]) => (
                              <option key={k} value={k}>{v.label}</option>
                            ))}
                          </select>
                          {isSaving && (
                            <svg className="animate-spin h-3 w-3 absolute right-2 pointer-events-none" style={{ color: 'var(--ink-2)' }} fill="none" viewBox="0 0 24 24">
                              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                            </svg>
                          )}
                        </div>
                      </td>

                      {/* Statut */}
                      <td className="px-4 py-3">
                        <StatusBadge status={u.status} />
                      </td>

                      {/* Actions */}
                      <td className="px-4 py-3 text-right">
                        {u.status === 'active' ? (
                          <button
                            onClick={() => void handleActivate(u.id, false)}
                            className="text-xs px-2.5 py-1 rounded-lg font-semibold transition"
                            style={{ background: '#f8fafc', border: '1px solid #e2e8f0', color: '#64748b' }}
                            onMouseEnter={e => (e.currentTarget.style.background = '#f1f5f9')}
                            onMouseLeave={e => (e.currentTarget.style.background = '#f8fafc')}
                          >
                            Désactiver
                          </button>
                        ) : u.status === 'pending' ? (
                          <div className="flex justify-end gap-1.5">
                            <button
                              onClick={() => void handleActivate(u.id, true)}
                              className="text-xs px-2.5 py-1 rounded-lg font-semibold transition"
                              style={{ background: '#f0fdf4', border: '1px solid #bbf7d0', color: '#15803d' }}
                              onMouseEnter={e => (e.currentTarget.style.background = '#dcfce7')}
                              onMouseLeave={e => (e.currentTarget.style.background = '#f0fdf4')}
                            >
                              ✓ Approuver
                            </button>
                            <button
                              onClick={() => void handleActivate(u.id, false)}
                              className="text-xs px-2.5 py-1 rounded-lg font-semibold transition"
                              style={{ background: '#fff1f2', border: '1px solid #fecdd3', color: '#be123c' }}
                              onMouseEnter={e => (e.currentTarget.style.background = '#ffe4e6')}
                              onMouseLeave={e => (e.currentTarget.style.background = '#fff1f2')}
                            >
                              ✗ Rejeter
                            </button>
                          </div>
                        ) : (
                          /* rejected / deactivated → réactiver */
                          <button
                            onClick={() => void handleActivate(u.id, true)}
                            className="inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-lg font-semibold transition"
                            style={{ background: '#eff6ff', border: '1px solid #bfdbfe', color: '#1d4ed8' }}
                            onMouseEnter={e => (e.currentTarget.style.background = '#dbeafe')}
                            onMouseLeave={e => (e.currentTarget.style.background = '#eff6ff')}
                          >
                            <RefreshCw className="w-3 h-3" /> Réactiver
                          </button>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* ── Modal Créer un utilisateur ────────────────────────────────────────── */}
      {inviteOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/50" onClick={() => !inviteLoading && setInviteOpen(false)} />
          <div className="relative card pad w-full max-w-[460px] shadow-2xl space-y-4">
            {/* Header */}
            <div className="flex items-start justify-between">
              <div>
                <h3 className="text-lg font-black" style={{ color: 'var(--ink)' }}>Créer un utilisateur</h3>
                <p className="text-sm mt-0.5" style={{ color: 'var(--ink-2)' }}>
                  Le compte est actif immédiatement.
                </p>
              </div>
              <button onClick={() => !inviteLoading && setInviteOpen(false)} className="btn-ghost !p-1.5">
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Error */}
            {inviteError && (
              <div className="rounded-xl px-4 py-3 text-sm font-medium"
                style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)', color: '#ef4444' }}>
                {inviteError}
              </div>
            )}

            {/* Fields */}
            <div>
              <p className="text-[10px] font-bold tracking-widest uppercase mb-1.5" style={{ color: 'var(--ink-2)' }}>Nom complet</p>
              <input
                type="text"
                className="input"
                placeholder="Prénom Nom"
                value={inviteForm.full_name}
                onChange={e => field('full_name', e.target.value)}
                disabled={inviteLoading}
              />
            </div>
            <div>
              <p className="text-[10px] font-bold tracking-widest uppercase mb-1.5" style={{ color: 'var(--ink-2)' }}>Email</p>
              <input
                type="email"
                className="input"
                placeholder="utilisateur@societe.com"
                value={inviteForm.email}
                onChange={e => field('email', e.target.value)}
                disabled={inviteLoading}
              />
            </div>
            <div>
              <p className="text-[10px] font-bold tracking-widest uppercase mb-1.5" style={{ color: 'var(--ink-2)' }}>Mot de passe (min. 8 car.)</p>
              <input
                type="password"
                className="input"
                placeholder="••••••••••••"
                value={inviteForm.password}
                onChange={e => field('password', e.target.value)}
                disabled={inviteLoading}
              />
            </div>
            <div>
              <p className="text-[10px] font-bold tracking-widest uppercase mb-1.5" style={{ color: 'var(--ink-2)' }}>Rôle</p>
              <select
                className="input"
                value={inviteForm.role}
                onChange={e => field('role', e.target.value as BackendRole)}
                disabled={inviteLoading}
              >
                {(Object.entries(ROLE_INFO) as [BackendRole, typeof ROLE_INFO[BackendRole]][]).map(([k, v]) => (
                  <option key={k} value={k}>{v.label}</option>
                ))}
              </select>
            </div>

            {/* Actions */}
            <div className="flex gap-2 justify-end pt-1">
              <button
                onClick={() => !inviteLoading && setInviteOpen(false)}
                className="btn-secondary"
                disabled={inviteLoading}
              >
                Annuler
              </button>
              <button
                onClick={handleCreate}
                className="btn-primary flex items-center gap-2"
                disabled={inviteLoading}
              >
                {inviteLoading ? (
                  <svg className="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                  </svg>
                ) : <ArrowRight className="w-4 h-4" />}
                Créer
              </button>
            </div>
          </div>
        </div>
      )}
    </AppLayout>
  )
}
