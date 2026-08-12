import { useEffect, useState } from 'react'
import AppLayout from '../components/layout/AppLayout'
import { listUsers, activateUser, deactivateUser, updateUserRole, createUser, BackendUser } from '../lib/usersApi'
import { listTeams, createTeam, renameTeam, deleteTeam, getTeam, addTeamMember, removeTeamMember, Team, TeamDetail } from '../lib/teamsApi'
import { ApiError } from '../lib/api'
import { Search, Plus, X, ArrowRight, Clock, CheckCircle2, XCircle, RefreshCw, Users, Pencil, Trash2, UserPlus } from 'lucide-react'

// ── Backend roles ─────────────────────────────────────────────────────────────

type BackendRole = 'ADMIN' | 'OPERATOR'

const ROLE_INFO: Record<BackendRole, { label: string; swatch: string; description: string }> = {
  ADMIN:    { label: 'Admin',    swatch: '#8b5cf6', description: 'Full access, user management' },
  OPERATOR: { label: 'Operator', swatch: '#6366f1', description: 'Bulk executions and automations' },
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
        <CheckCircle2 className="w-3 h-3" /> Active
      </span>
    )
  if (status === 'pending')
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200">
        <Clock className="w-3 h-3" /> Pending
      </span>
    )
  return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-50 text-rose-700 border border-rose-200">
      <XCircle className="w-3 h-3" /> Deactivated
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

  // ── Teams state ─────────────────────────────────────────────────────────────

  const [teams, setTeams]                 = useState<Team[]>([])
  const [createTeamOpen, setCreateTeamOpen] = useState(false)
  const [newTeamName, setNewTeamName]     = useState('')
  const [createTeamError, setCreateTeamError] = useState('')
  const [createTeamLoading, setCreateTeamLoading] = useState(false)
  const [manageTeam, setManageTeam]       = useState<TeamDetail | null>(null)
  const [manageError, setManageError]     = useState('')
  const [addMemberUserId, setAddMemberUserId] = useState('')
  const [renameValue, setRenameValue]     = useState('')

  // ── Data loading ────────────────────────────────────────────────────────────

  const load = () => {
    setLoading(true)
    listUsers()
      .then(data => setUsers(data.map(mapUser)))
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  const loadTeams = () => {
    listTeams().then(setTeams).catch(() => {})
  }

  useEffect(() => { load(); loadTeams() }, [])

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
    if (!inviteForm.full_name.trim()) { setInviteError('Name is required.'); return }
    if (!inviteForm.email.includes('@')) { setInviteError('Invalid email.'); return }
    if (inviteForm.password.length < 8) { setInviteError('Password must be at least 8 characters.'); return }
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
        if (err.status === 409) setInviteError('This email is already registered.')
        else if (err.status === 422) setInviteError('Invalid data. Please check the fields.')
        else setInviteError('Error creating user. Please try again.')
      } else {
        setInviteError('Network error.')
      }
    } finally {
      setInviteLoading(false)
    }
  }

  // ── Teams (create / manage members) ────────────────────────────────────────

  const openCreateTeam = () => {
    setNewTeamName('')
    setCreateTeamError('')
    setCreateTeamOpen(true)
  }

  const handleCreateTeam = async () => {
    if (!newTeamName.trim()) { setCreateTeamError('Team name is required.'); return }
    setCreateTeamLoading(true)
    setCreateTeamError('')
    try {
      await createTeam(newTeamName.trim())
      setCreateTeamOpen(false)
      loadTeams()
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 409) setCreateTeamError('A team with this name already exists.')
      else setCreateTeamError('Error creating team. Please try again.')
    } finally {
      setCreateTeamLoading(false)
    }
  }

  const openManageTeam = (team: Team) => {
    setManageError('')
    setAddMemberUserId('')
    setRenameValue(team.name)
    getTeam(team.id).then(setManageTeam).catch(() => setManageError('Could not load team.'))
  }

  const closeManageTeam = () => setManageTeam(null)

  const refreshManageTeam = (teamId: string) => {
    getTeam(teamId).then(setManageTeam).catch(() => {})
    loadTeams()
  }

  const handleRenameTeam = async () => {
    if (!manageTeam || !renameValue.trim() || renameValue.trim() === manageTeam.name) return
    try {
      await renameTeam(manageTeam.id, renameValue.trim())
      refreshManageTeam(manageTeam.id)
    } catch (err: unknown) {
      setManageError(err instanceof ApiError && err.status === 409
        ? 'A team with this name already exists.'
        : 'Error renaming team.')
    }
  }

  const handleDeleteTeam = async (teamId: string) => {
    try {
      await deleteTeam(teamId)
      if (manageTeam?.id === teamId) closeManageTeam()
      loadTeams()
    } catch {
      setManageError('Error deleting team.')
    }
  }

  const handleAddMember = async () => {
    if (!manageTeam || !addMemberUserId) return
    try {
      await addTeamMember(manageTeam.id, addMemberUserId)
      setAddMemberUserId('')
      refreshManageTeam(manageTeam.id)
    } catch {
      setManageError('Error adding member.')
    }
  }

  const handleRemoveMember = async (userId: string) => {
    if (!manageTeam) return
    try {
      await removeTeamMember(manageTeam.id, userId)
      refreshManageTeam(manageTeam.id)
    } catch {
      setManageError('Error removing member.')
    }
  }

  // ── Assign a user to a team, directly from the users table ────────────────

  const [assignOpenFor, setAssignOpenFor] = useState<string | null>(null)
  const [assigning, setAssigning] = useState<string | null>(null)

  const userTeams = (userId: string) => teams.filter(t => t.member_user_ids.includes(userId))

  const handleAssignTeam = async (userId: string, teamId: string) => {
    setAssigning(userId)
    try {
      await addTeamMember(teamId, userId)
      loadTeams()
    } catch {
      // ignore — e.g. already a member
    } finally {
      setAssigning(null)
      setAssignOpenFor(null)
    }
  }

  const handleUnassignTeam = async (userId: string, teamId: string) => {
    setAssigning(userId)
    try {
      await removeTeamMember(teamId, userId)
      loadTeams()
    } finally {
      setAssigning(null)
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
            <h2 className="text-xl font-black" style={{ color: 'var(--ink)' }}>Users</h2>
            <p className="text-sm mt-1" style={{ color: 'var(--ink-2)' }}>
              {users.length} members ·{' '}
              {pendingCount > 0
                ? <span className="font-semibold text-amber-600">{pendingCount} pending approval</span>
                : <span>0 pending</span>}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={openCreateTeam} className="btn-secondary flex items-center gap-2">
              <Plus className="w-4 h-4" /> Create team
            </button>
            <button onClick={openInvite} className="btn-primary flex items-center gap-2">
              <Plus className="w-4 h-4" /> Create user
            </button>
          </div>
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

        {/* Teams */}
        <div className="card pad">
          <div className="mb-4">
            <h3 className="text-sm font-black flex items-center gap-2" style={{ color: 'var(--ink)' }}>
              <Users className="w-4 h-4" style={{ color: 'var(--brand)' }} /> Teams
            </h3>
            <p className="text-xs mt-0.5" style={{ color: 'var(--ink-2)' }}>{teams.length} teams</p>
          </div>
          {teams.length === 0 ? (
            <p className="text-sm py-4 text-center" style={{ color: 'var(--ink-2)' }}>No teams yet.</p>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {teams.map(t => (
                <button
                  key={t.id}
                  onClick={() => openManageTeam(t)}
                  className="text-left rounded-xl p-3 transition flex items-center justify-between gap-2"
                  style={{ border: '1px solid var(--line)', background: 'var(--card)' }}
                  onMouseEnter={e => (e.currentTarget.style.background = 'color-mix(in oklch, var(--brand) 4%, var(--card))')}
                  onMouseLeave={e => (e.currentTarget.style.background = 'var(--card)')}
                >
                  <div className="min-w-0">
                    <p className="font-semibold text-sm truncate" style={{ color: 'var(--ink)' }}>{t.name}</p>
                    <p className="text-xs mt-0.5" style={{ color: 'var(--ink-2)' }}>{t.member_count} member{t.member_count === 1 ? '' : 's'}</p>
                  </div>
                  <Pencil className="w-3.5 h-3.5 flex-shrink-0" style={{ color: 'var(--ink-2)' }} />
                </button>
              ))}
            </div>
          )}
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
                placeholder="Search by name or email…"
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
                  <th className="text-left px-4 py-2.5">Member</th>
                  <th className="text-left px-4 py-2.5">Email</th>
                  <th className="text-left px-4 py-2.5">Role</th>
                  <th className="text-left px-4 py-2.5">Team</th>
                  <th className="text-left px-4 py-2.5">Status</th>
                  <th className="text-right px-4 py-2.5">Actions</th>
                </tr>
              </thead>
              <tbody>
                {loading && (
                  <tr><td colSpan={6} className="px-4 py-8 text-center text-sm" style={{ color: 'var(--ink-2)' }}>
                    Loading…
                  </td></tr>
                )}
                {!loading && filtered.length === 0 && (
                  <tr><td colSpan={6} className="px-4 py-8 text-center text-sm" style={{ color: 'var(--ink-2)' }}>
                    No users found.
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

                      {/* Team */}
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-1.5 flex-wrap relative">
                          {userTeams(u.id).map(t => (
                            <span key={t.id} className="inline-flex items-center gap-1 pl-2 pr-1 py-0.5 rounded-full text-[11px] font-semibold"
                              style={{ background: 'color-mix(in oklch, var(--brand) 10%, var(--card))', color: 'var(--brand)', border: '1px solid color-mix(in oklch, var(--brand) 25%, transparent)' }}>
                              {t.name}
                              <button
                                onClick={() => void handleUnassignTeam(u.id, t.id)}
                                disabled={assigning === u.id}
                                className="hover:opacity-70 disabled:opacity-40"
                              >
                                <X className="w-2.5 h-2.5" />
                              </button>
                            </span>
                          ))}
                          <button
                            onClick={() => setAssignOpenFor(assignOpenFor === u.id ? null : u.id)}
                            disabled={assigning === u.id}
                            className="w-5 h-5 rounded-full flex items-center justify-center transition disabled:opacity-40"
                            style={{ border: '1px dashed var(--line)', color: 'var(--ink-2)' }}
                          >
                            <Plus className="w-3 h-3" />
                          </button>

                          {assignOpenFor === u.id && (
                            <>
                              <div className="fixed inset-0 z-10" onClick={() => setAssignOpenFor(null)} />
                              <div className="absolute top-full left-0 mt-1 z-20 rounded-xl shadow-lg py-1 min-w-[160px]"
                                style={{ background: 'var(--card)', border: '1px solid var(--line)' }}>
                                {teams.filter(t => !t.member_user_ids.includes(u.id)).length === 0 ? (
                                  <p className="px-3 py-2 text-xs" style={{ color: 'var(--ink-2)' }}>No teams to assign</p>
                                ) : (
                                  teams.filter(t => !t.member_user_ids.includes(u.id)).map(t => (
                                    <button
                                      key={t.id}
                                      onClick={() => void handleAssignTeam(u.id, t.id)}
                                      className="block w-full text-left px-3 py-1.5 text-xs font-medium transition"
                                      style={{ color: 'var(--ink)' }}
                                      onMouseEnter={e => (e.currentTarget.style.background = 'color-mix(in oklch, var(--brand) 6%, var(--card))')}
                                      onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                                    >
                                      {t.name}
                                    </button>
                                  ))
                                )}
                              </div>
                            </>
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
                            Deactivate
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
                              ✓ Approve
                            </button>
                            <button
                              onClick={() => void handleActivate(u.id, false)}
                              className="text-xs px-2.5 py-1 rounded-lg font-semibold transition"
                              style={{ background: '#fff1f2', border: '1px solid #fecdd3', color: '#be123c' }}
                              onMouseEnter={e => (e.currentTarget.style.background = '#ffe4e6')}
                              onMouseLeave={e => (e.currentTarget.style.background = '#fff1f2')}
                            >
                              ✗ Reject
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
                            <RefreshCw className="w-3 h-3" /> Reactivate
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
                <h3 className="text-lg font-black" style={{ color: 'var(--ink)' }}>Create user</h3>
                <p className="text-sm mt-0.5" style={{ color: 'var(--ink-2)' }}>
                  The account is active immediately.
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
              <p className="text-[10px] font-bold tracking-widest uppercase mb-1.5" style={{ color: 'var(--ink-2)' }}>Full name</p>
              <input
                type="text"
                className="input"
                placeholder="First Last"
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
                placeholder="user@company.com"
                value={inviteForm.email}
                onChange={e => field('email', e.target.value)}
                disabled={inviteLoading}
              />
            </div>
            <div>
              <p className="text-[10px] font-bold tracking-widest uppercase mb-1.5" style={{ color: 'var(--ink-2)' }}>Password (min. 8 chars.)</p>
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
              <p className="text-[10px] font-bold tracking-widest uppercase mb-1.5" style={{ color: 'var(--ink-2)' }}>Role</p>
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
                Cancel
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
                Create
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Modal Créer une équipe ────────────────────────────────────────────── */}
      {createTeamOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/50" onClick={() => !createTeamLoading && setCreateTeamOpen(false)} />
          <div className="relative card pad w-full max-w-[420px] shadow-2xl space-y-4">
            <div className="flex items-start justify-between">
              <h3 className="text-lg font-black" style={{ color: 'var(--ink)' }}>Create team</h3>
              <button onClick={() => !createTeamLoading && setCreateTeamOpen(false)} className="btn-ghost !p-1.5">
                <X className="w-4 h-4" />
              </button>
            </div>

            {createTeamError && (
              <div className="rounded-xl px-4 py-3 text-sm font-medium"
                style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)', color: '#ef4444' }}>
                {createTeamError}
              </div>
            )}

            <div>
              <p className="text-[10px] font-bold tracking-widest uppercase mb-1.5" style={{ color: 'var(--ink-2)' }}>Team name</p>
              <input
                type="text"
                className="input"
                placeholder="e.g. Backend, QA, Integrations"
                value={newTeamName}
                onChange={e => setNewTeamName(e.target.value)}
                disabled={createTeamLoading}
              />
            </div>

            <div className="flex gap-2 justify-end pt-1">
              <button onClick={() => !createTeamLoading && setCreateTeamOpen(false)} className="btn-secondary" disabled={createTeamLoading}>
                Cancel
              </button>
              <button onClick={handleCreateTeam} className="btn-primary flex items-center gap-2" disabled={createTeamLoading}>
                {createTeamLoading ? (
                  <svg className="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                  </svg>
                ) : <ArrowRight className="w-4 h-4" />}
                Create
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Modal Gérer une équipe ─────────────────────────────────────────────── */}
      {manageTeam && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/50" onClick={closeManageTeam} />
          <div className="relative card pad w-full max-w-[480px] shadow-2xl space-y-4">
            <div className="flex items-start justify-between gap-2">
              <div className="flex-1 flex items-center gap-2">
                <input
                  type="text"
                  className="input !py-1.5 text-sm font-black flex-1"
                  value={renameValue}
                  onChange={e => setRenameValue(e.target.value)}
                  onBlur={handleRenameTeam}
                  onKeyDown={e => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur() }}
                />
              </div>
              <button onClick={closeManageTeam} className="btn-ghost !p-1.5">
                <X className="w-4 h-4" />
              </button>
            </div>

            {manageError && (
              <div className="rounded-xl px-4 py-3 text-sm font-medium"
                style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)', color: '#ef4444' }}>
                {manageError}
              </div>
            )}

            {/* Add member */}
            <div className="flex gap-2">
              <select
                className="input flex-1"
                value={addMemberUserId}
                onChange={e => setAddMemberUserId(e.target.value)}
              >
                <option value="">Add a member…</option>
                {users
                  .filter(u => !manageTeam.members.some(m => m.id === u.id))
                  .map(u => <option key={u.id} value={u.id}>{u.name} ({u.email})</option>)}
              </select>
              <button onClick={handleAddMember} disabled={!addMemberUserId} className="btn-secondary !px-3 disabled:opacity-50">
                <UserPlus className="w-4 h-4" />
              </button>
            </div>

            {/* Members list */}
            <div className="space-y-1.5 max-h-[280px] overflow-y-auto">
              {manageTeam.members.length === 0 && (
                <p className="text-sm text-center py-4" style={{ color: 'var(--ink-2)' }}>No members yet.</p>
              )}
              {manageTeam.members.map(m => (
                <div key={m.id} className="flex items-center justify-between gap-2 rounded-xl px-3 py-2"
                  style={{ background: 'color-mix(in oklch, var(--ink) 3%, var(--card))' }}>
                  <div className="min-w-0">
                    <p className="text-sm font-semibold truncate" style={{ color: 'var(--ink)' }}>{m.full_name}</p>
                    <p className="text-xs truncate" style={{ color: 'var(--ink-2)' }}>{m.email}</p>
                  </div>
                  <button onClick={() => handleRemoveMember(m.id)} className="btn-ghost !p-1.5 flex-shrink-0">
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))}
            </div>

            <div className="pt-1 flex justify-end" style={{ borderTop: '1px solid var(--line)' }}>
              <button
                onClick={() => handleDeleteTeam(manageTeam.id)}
                className="text-xs px-2.5 py-1.5 rounded-lg font-semibold transition inline-flex items-center gap-1.5 mt-3"
                style={{ background: '#fff1f2', border: '1px solid #fecdd3', color: '#be123c' }}
              >
                <Trash2 className="w-3.5 h-3.5" /> Delete team
              </button>
            </div>
          </div>
        </div>
      )}
    </AppLayout>
  )
}
