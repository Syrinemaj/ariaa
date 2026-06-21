import { useEffect, useState } from 'react'
import AppLayout from '../components/layout/AppLayout'
import { StatusBadge } from '../components/aria/Badges'
import { ROLES, User, Role } from '../lib/aria-data'
import { listUsers, activateUser, deactivateUser, BackendUser } from '../lib/usersApi'
import { Search, Download, Plus, X, ArrowRight } from 'lucide-react'

// Extend User with backend id (User from aria-data has no id field)
type UserWithId = User & { id: string }

function mapUser(bu: BackendUser): UserWithId {
  return {
    id:     bu.id,
    name:   bu.full_name,
    email:  bu.email,
    role:   bu.role as Role,
    status: bu.is_active ? 'active' : 'rejected',
  }
}

export default function UsersPage() {
  const [users, setUsers]       = useState<UserWithId[]>([])
  const [q, setQ]               = useState('')
  const [inviteOpen, setInviteOpen] = useState(false)

  // Load users on mount
  useEffect(() => {
    listUsers()
      .then(data => setUsers(data.map(mapUser)))
      .catch(() => {})
  }, [])

  const filtered = users.filter(u => (u.name + u.email).toLowerCase().includes(q.toLowerCase()))

  // Role change — local only (no backend endpoint)
  const setUserRole = (email: string, role: Role) =>
    setUsers(users.map(u => u.email === email ? { ...u, role } : u))

  // Activate / deactivate — calls real API, optimistic update
  const setUserStatus = async (userId: string, activate: boolean) => {
    // Optimistic update
    setUsers(prev => prev.map(u => u.id === userId ? { ...u, status: activate ? 'active' : 'rejected' } : u))
    try {
      if (activate) await activateUser(userId)
      else await deactivateUser(userId)
    } catch {
      // Revert on failure
      setUsers(prev => prev.map(u => u.id === userId ? { ...u, status: activate ? 'rejected' : 'active' } : u))
    }
  }

  return (
    <AppLayout>
      <div className="p-6 space-y-6">
        <div className="flex items-end justify-between gap-4 flex-wrap">
          <div>
            <h2 className="text-xl font-black" style={{ color: 'var(--ink)' }}>Users</h2>
            <p className="text-sm ink-2 mt-1">
              {users.length} workspace members · {users.filter(u => u.status === 'pending').length} awaiting approval
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button className="btn-secondary"><Download className="w-4 h-4" /> Export</button>
            <button onClick={() => setInviteOpen(true)} className="btn-primary"><Plus className="w-4 h-4" /> Invite</button>
          </div>
        </div>

        {/* Role summary */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {(Object.entries(ROLES) as [Role, typeof ROLES[Role]][]).slice(0, 4).map(([k, v]) => (
            <div key={k} className="card p-3 flex items-center gap-3">
              <div className="w-9 h-9 rounded-xl flex items-center justify-center text-white font-bold text-sm" style={{ background: v.swatch }}>
                {v.label[0]}
              </div>
              <div>
                <p className="text-[10px] font-bold tracking-widest uppercase ink-2">{v.label}</p>
                <p className="text-xl font-black" style={{ color: 'var(--ink)' }}>{users.filter(u => u.role === k).length}</p>
              </div>
            </div>
          ))}
        </div>

        {/* Table */}
        <div className="card overflow-hidden">
          <div className="p-4 flex flex-wrap items-center gap-3" style={{ borderBottom: '1px solid var(--line)' }}>
            <div className="relative flex-1 min-w-[200px]">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 ink-2" />
              <input value={q} onChange={e => setQ(e.target.value)} className="input !pl-9" placeholder="Search by name or email…" />
            </div>
            <span className="text-xs font-mono ink-2">{filtered.length} / {users.length}</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="aria-thead">
                <tr>
                  {['Member', 'Email', 'Role', 'Status', ''].map((h, i) => (
                    <th key={i} className={`text-left px-4 py-2.5 ${i === 4 ? 'text-right' : ''}`}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.length === 0 && (
                  <tr><td colSpan={5} className="px-4 py-8 text-center ink-2 text-sm">No users found.</td></tr>
                )}
                {filtered.map(u => {
                  const initials = u.name.split(' ').map(s => s[0]).slice(0, 2).join('')
                  return (
                    <tr key={u.email} className="border-t transition" style={{ borderColor: 'var(--line)' }}
                      onMouseEnter={e => (e.currentTarget.style.background = 'color-mix(in oklch, var(--brand) 3%, var(--card))')}
                      onMouseLeave={e => (e.currentTarget.style.background = '')}>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-3">
                          <div className="w-9 h-9 rounded-xl flex items-center justify-center text-white font-bold text-sm" style={{ background: ROLES[u.role]?.swatch ?? '#64748b' }}>
                            {initials}
                          </div>
                          <div>
                            <p className="font-semibold" style={{ color: 'var(--ink)' }}>{u.name}</p>
                            <p className="text-xs ink-2">joined 12 May 2026</p>
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-3 font-mono text-xs ink-2">{u.email}</td>
                      <td className="px-4 py-3">
                        <select value={u.role} onChange={e => setUserRole(u.email, e.target.value as Role)}
                          className="input !py-1 !w-auto text-xs font-medium">
                          {(Object.entries(ROLES) as [Role, typeof ROLES[Role]][]).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
                        </select>
                      </td>
                      <td className="px-4 py-3"><StatusBadge s={u.status} /></td>
                      <td className="px-4 py-3 text-right">
                        {u.status !== 'active' ? (
                          <div className="flex justify-end gap-1.5">
                            <button onClick={() => void setUserStatus(u.id, true)} className="text-xs px-2.5 py-1 rounded-lg text-emerald-700 bg-emerald-50 border border-emerald-200 font-semibold hover:bg-emerald-100 transition">Approve</button>
                            <button onClick={() => void setUserStatus(u.id, false)} className="text-xs px-2.5 py-1 rounded-lg text-rose-700 bg-rose-50 border border-rose-200 font-semibold hover:bg-rose-100 transition">Reject</button>
                          </div>
                        ) : (
                          <button onClick={() => void setUserStatus(u.id, false)} className="text-xs px-2.5 py-1 rounded-lg text-slate-500 bg-slate-50 border border-slate-200 font-semibold hover:bg-slate-100 transition">Deactivate</button>
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

      {/* Invite modal */}
      {inviteOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/50" onClick={() => setInviteOpen(false)} />
          <div className="relative card pad w-full max-w-[460px] shadow-2xl">
            <div className="flex items-start justify-between mb-4">
              <div>
                <h3 className="text-lg font-black" style={{ color: 'var(--ink)' }}>Invite teammates</h3>
                <p className="text-sm ink-2 mt-1">They&apos;ll receive an email to set their password.</p>
              </div>
              <button onClick={() => setInviteOpen(false)} className="btn-ghost !p-1.5"><X className="w-4 h-4" /></button>
            </div>
            <div className="space-y-3">
              <div>
                <p className="text-[10px] font-bold tracking-widest uppercase ink-2 mb-1.5">Emails · comma separated</p>
                <textarea rows={3} className="input resize-none" placeholder="alex@team.com, jordan@team.com" />
              </div>
              <div>
                <p className="text-[10px] font-bold tracking-widest uppercase ink-2 mb-1.5">Assign role</p>
                <select className="input">
                  {(Object.entries(ROLES) as [Role, typeof ROLES[Role]][]).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
                </select>
              </div>
            </div>
            <div className="flex gap-2 justify-end mt-5">
              <button onClick={() => setInviteOpen(false)} className="btn-secondary">Cancel</button>
              <button onClick={() => setInviteOpen(false)} className="btn-primary"><ArrowRight className="w-4 h-4" /> Send invitations</button>
            </div>
          </div>
        </div>
      )}
    </AppLayout>
  )
}
