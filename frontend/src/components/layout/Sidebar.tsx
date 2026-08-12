import { NavLink } from 'react-router-dom'
import { useState, useEffect } from 'react'
import {
  Home, Upload, Package, Network, FileCode2, Sparkles,
  Layers, Inbox, BarChart2, Users,
  LogOut, ChevronLeft, ChevronRight, Zap, History, FlaskConical, ClipboardList,
} from 'lucide-react'
import { useAuth } from '../../contexts/AuthContext'
import { useRun } from '../../contexts/RunContext'
import { listAutomationRuns } from '../../lib/reportsApi'

// ── Role labels ───────────────────────────────────────────────────────────────
const ROLE_LABELS: Record<string, string> = {
  ADMIN:    'Admin',
  OPERATOR: 'Operator',
}

// ── Nav definition ────────────────────────────────────────────────────────────
// roles: undefined = visible to all; otherwise restricted to listed roles

type NavItem = {
  path: string
  label: string
  icon: React.ComponentType<{ className?: string }>
  dynamic?: string
  roles?: string[]
}

type NavGroup = { label: string; items: NavItem[] }

const NAV_GROUPS: NavGroup[] = [
  {
    label: 'Main',
    items: [
      { path: '/dashboard', label: 'Dashboard',   icon: Home },
      { path: '/analysis',  label: 'Analyze HAR', icon: Upload,  roles: ['ADMIN', 'OPERATOR'] },
      { path: '/runs',      label: 'History',   icon: History },
    ],
  },
  {
    label: 'Catalogs',
    items: [
      { path: '/endpoints', label: 'Endpoints',      icon: Package },
      { path: '/workflows', label: 'Workflows',      icon: Network,   roles: ['ADMIN', 'OPERATOR'] },
      { path: '/openapi',   label: 'OpenAPI',         icon: FileCode2, roles: ['ADMIN', 'OPERATOR'] },
      { path: '/rag',       label: 'Endpoint Search', icon: Sparkles,  roles: ['ADMIN', 'OPERATOR'] },
    ],
  },
  {
    label: 'Automation',
    items: [
      { path: '/automation',      label: 'Simple Automation', icon: FlaskConical,  roles: ['ADMIN', 'OPERATOR'] },
      { path: '/automation-list', label: 'Automations',       icon: ClipboardList, roles: ['ADMIN', 'OPERATOR'] },
      { path: '/bulk',            label: 'Bulk execution',    icon: Layers,        roles: ['ADMIN', 'OPERATOR'], dynamic: 'bulk' },
      { path: '/approvals',       label: 'Approvals',         icon: Inbox,         roles: ['ADMIN'], dynamic: 'approvals' },
      { path: '/reports',         label: 'Reports',           icon: BarChart2 },
    ],
  },
  {
    label: 'Admin',
    items: [
      { path: '/users',    label: 'Users', icon: Users,     roles: ['ADMIN'] },
    ],
  },
]

export default function Sidebar() {
  const { user, logout } = useAuth()
  const { activeRun, setActiveRun } = useRun()
  const [collapsed, setCollapsed]     = useState(false)
  const [runningJobs, setRunningJobs] = useState(0)

  const role     = (user?.role ?? 'OPERATOR').toUpperCase()
  const initials = user?.name
    ? user.name.split(' ').map((s: string) => s[0]).slice(0, 2).join('').toUpperCase()
    : 'U'

  // Poll for running automation jobs to show badge
  useEffect(() => {
    const check = () => {
      listAutomationRuns({ status: 'running', limit: 10 })
        .then(data => setRunningJobs(data.items.length))
        .catch(() => {})
    }
    check()
    const id = setInterval(check, 30_000)
    return () => clearInterval(id)
  }, [])

  function getBadge(dynamic?: string): number | null {
    if (dynamic === 'bulk') return runningJobs > 0 ? runningJobs : null
    return null
  }

  function isVisible(item: NavItem): boolean {
    if (!item.roles) return true
    return item.roles.includes(role)
  }

  return (
    <aside
      className="h-screen sticky top-0 flex flex-col shrink-0 transition-all duration-200"
      style={{ width: collapsed ? 72 : 248, background: 'var(--card)', borderRight: '1px solid var(--line)' }}
    >
      {/* Logo */}
      <div className="px-4 py-4 flex items-center justify-between min-h-[60px]" style={{ borderBottom: '1px solid var(--line)' }}>
        {!collapsed && (
          <div className="flex items-center gap-2.5 select-none">
            <img src="/sopra.png" alt="Sopra" className="w-7 h-7 object-contain shrink-0" />
            <div className="flex flex-col leading-none">
              <span className="text-[17px] font-black tracking-tight" style={{ color: 'var(--ink)' }}>aria</span>
              <span className="text-[9px] font-mono tracking-[0.2em] uppercase mt-0.5" style={{ color: 'var(--ink-2)' }}>api.reverse.intel</span>
            </div>
          </div>
        )}
        {collapsed && (
          <img src="/sopra.png" alt="Sopra" className="w-7 h-7 object-contain mx-auto" />
        )}
        {!collapsed && (
          <button onClick={() => setCollapsed(true)} className="p-1.5 rounded-lg transition hover:opacity-70" style={{ color: 'var(--ink-2)' }}>
            <ChevronLeft className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto px-2 py-3 space-y-3">
        {NAV_GROUPS.map(group => {
          const visibleItems = group.items.filter(isVisible)
          if (visibleItems.length === 0) return null
          return (
            <div key={group.label}>
              {!collapsed && (
                <p className="text-[10px] font-bold tracking-widest uppercase px-3 py-1" style={{ color: 'var(--ink-2)' }}>
                  {group.label}
                </p>
              )}
              <div className="space-y-0.5">
                {visibleItems.map(item => {
                  const Icon = item.icon
                  const badge = getBadge(item.dynamic)
                  return (
                    <NavLink
                      key={item.path}
                      to={item.path}
                      className={({ isActive }) =>
                        `flex items-center gap-3 px-3 py-2 rounded-xl text-sm font-medium transition ${collapsed ? 'justify-center' : ''}` +
                        (isActive ? ' nav-active' : '')
                      }
                      style={({ isActive }) => isActive ? {} : { color: 'var(--ink-2)' }}
                      onMouseEnter={e => {
                        const el = e.currentTarget
                        if (!el.classList.contains('nav-active')) {
                          el.style.background = 'color-mix(in oklch, var(--ink) 4%, var(--card))'
                          el.style.color = 'var(--ink)'
                        }
                      }}
                      onMouseLeave={e => {
                        const el = e.currentTarget
                        if (!el.classList.contains('nav-active')) {
                          el.style.background = ''
                          el.style.color = 'var(--ink-2)'
                        }
                      }}
                    >
                      <div className="relative shrink-0">
                        <Icon className="w-[18px] h-[18px]" />
                        {collapsed && badge != null && (
                          <span className="absolute -top-1 -right-1 w-3.5 h-3.5 rounded-full flex items-center justify-center text-[9px] font-bold text-white"
                            style={{ background: '#f59e0b' }}>
                            {badge > 9 ? '9+' : badge}
                          </span>
                        )}
                      </div>
                      {!collapsed && <span className="flex-1 truncate">{item.label}</span>}
                      {!collapsed && badge != null && (
                        <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-md animate-pulse"
                          style={{ background: 'color-mix(in oklch, #f59e0b 18%, transparent)', color: '#92400e' }}>
                          {badge}
                        </span>
                      )}
                    </NavLink>
                  )
                })}
              </div>
            </div>
          )
        })}
      </nav>

      {/* Active run context */}
      {!collapsed && activeRun && (
        <div className="mx-2 mb-1 px-3 py-2 rounded-xl flex items-center justify-between gap-2"
          style={{ background: 'color-mix(in oklch, var(--brand) 8%, var(--card))', border: '1px solid color-mix(in oklch, var(--brand) 20%, transparent)' }}>
          <div className="min-w-0">
            <p className="text-[9px] font-bold tracking-widest uppercase" style={{ color: 'var(--brand)' }}>Active run</p>
            <p className="text-xs font-mono truncate mt-0.5" style={{ color: 'var(--ink)' }}>{activeRun.name}</p>
          </div>
          <button onClick={() => setActiveRun(null)} className="shrink-0 text-xs opacity-50 hover:opacity-100 transition-opacity" style={{ color: 'var(--ink-2)' }}>
            <Zap className="w-3 h-3" />
          </button>
        </div>
      )}

      <div className="h-px mx-3" style={{ background: 'var(--line)' }} />

      {/* Footer — user card */}
      <div className="p-2">
        <div className={`flex items-center gap-3 p-2 rounded-xl transition ${collapsed ? 'justify-center' : ''}`}
          onMouseEnter={e => { e.currentTarget.style.background = 'color-mix(in oklch, var(--ink) 4%, var(--card))' }}
          onMouseLeave={e => { e.currentTarget.style.background = '' }}>
          <div className="w-9 h-9 rounded-xl shrink-0 flex items-center justify-center text-white text-sm font-bold"
            style={{ background: 'linear-gradient(135deg, var(--brand), var(--accent))' }}>
            {initials}
          </div>
          {!collapsed && (
            <>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold truncate" style={{ color: 'var(--ink)' }}>{user?.name ?? 'User'}</p>
                <p className="text-xs" style={{ color: 'var(--ink-2)' }}>{ROLE_LABELS[role] ?? role}</p>
              </div>
              <button onClick={logout} className="p-1.5 rounded-lg transition hover:opacity-70" style={{ color: 'var(--ink-2)' }} title="Log out">
                <LogOut className="w-4 h-4" />
              </button>
            </>
          )}
        </div>
        {collapsed && (
          <button onClick={() => setCollapsed(false)}
            className="w-full mt-1 p-1.5 rounded-lg transition flex justify-center hover:opacity-70"
            style={{ color: 'var(--ink-2)' }}>
            <ChevronRight className="w-4 h-4" />
          </button>
        )}
      </div>
    </aside>
  )
}
