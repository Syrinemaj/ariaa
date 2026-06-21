import { NavLink } from 'react-router-dom'
import { useState } from 'react'
import {
  Home, Upload, Package, Network, FileCode2, Sparkles,
  Wand2, Layers, Inbox, BarChart2, Settings2, Users,
  LogOut, ChevronLeft, ChevronRight,
} from 'lucide-react'
import { useAuth } from '../../contexts/AuthContext'

const NAV = [
  { path:'/dashboard',  label:'Dashboard',       icon:Home,      badge:null },
  { path:'/analysis',   label:'Analyse HAR',     icon:Upload,    badge:null },
  { path:'/endpoints',  label:'Endpoints',       icon:Package,   badge:null },
  { path:'/workflows',  label:'Workflows',       icon:Network,   badge:null },
  { path:'/openapi',    label:'OpenAPI',         icon:FileCode2, badge:null },
  { path:'/rag',        label:'Endpoint Search', icon:Sparkles,  badge:null },
  { path:'/automation', label:'Automation',      icon:Wand2,     badge:null },
  { path:'/bulk',       label:'Bulk',            icon:Layers,    badge:1 },
  { path:'/approvals',  label:'Approvals',       icon:Inbox,     badge:3 },
  { path:'/reports',    label:'Reports',         icon:BarChart2, badge:null },
  { path:'/settings',   label:'Settings',        icon:Settings2, badge:null },
  { path:'/users',      label:'Users',           icon:Users,     badge:null },
]

export default function Sidebar() {
  const { user, logout } = useAuth()
  const [collapsed, setCollapsed] = useState(false)

  const initials = user?.name
    ? user.name.split(' ').map((s: string) => s[0]).slice(0, 2).join('').toUpperCase()
    : 'U'

  return (
    <aside
      className="h-screen sticky top-0 flex flex-col shrink-0 transition-all duration-200"
      style={{
        width: collapsed ? 72 : 248,
        background: 'var(--card)',
        borderRight: '1px solid var(--line)',
      }}
    >
      {/* Logo */}
      <div
        className="px-4 py-4 flex items-center justify-between min-h-[60px]"
        style={{ borderBottom: '1px solid var(--line)' }}
      >
        {!collapsed && (
          <div className="flex items-center gap-2.5 select-none">
            <div
              className="w-8 h-8 rounded-xl flex items-center justify-center"
              style={{ background: 'linear-gradient(135deg, var(--brand), var(--accent))' }}
            >
              <svg viewBox="0 0 32 32" width={16} height={16}>
                <path d="M9 22 L16 10 L23 22" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M12.5 17.5 L19.5 17.5" stroke="white" strokeWidth="2.5" strokeLinecap="round" />
                <circle cx="16" cy="10" r="1.8" fill="white" />
              </svg>
            </div>
            <div className="flex flex-col leading-none">
              <span className="text-[17px] font-black tracking-tight grad-text">aria</span>
              <span
                className="text-[9px] font-mono tracking-[0.2em] uppercase mt-0.5"
                style={{ color: 'var(--ink-2)' }}
              >
                api.reverse.intel
              </span>
            </div>
          </div>
        )}

        {collapsed && (
          <div
            className="w-8 h-8 rounded-xl mx-auto flex items-center justify-center"
            style={{ background: 'linear-gradient(135deg, var(--brand), var(--accent))' }}
          >
            <svg viewBox="0 0 32 32" width={16} height={16}>
              <path d="M9 22 L16 10 L23 22" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
              <path d="M12.5 17.5 L19.5 17.5" stroke="white" strokeWidth="2.5" strokeLinecap="round" />
              <circle cx="16" cy="10" r="1.8" fill="white" />
            </svg>
          </div>
        )}

        {!collapsed && (
          <button
            onClick={() => setCollapsed(true)}
            className="p-1.5 rounded-lg transition hover:opacity-70"
            style={{ color: 'var(--ink-2)' }}
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto px-2 py-3 space-y-0.5">
        {!collapsed && (
          <p
            className="text-[10px] font-bold tracking-widest uppercase px-3 py-1.5"
            style={{ color: 'var(--ink-2)' }}
          >
            Workspace
          </p>
        )}

        {NAV.map(item => {
          const Icon = item.icon
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
              <Icon className="w-[18px] h-[18px] shrink-0" />
              {!collapsed && <span className="flex-1 truncate">{item.label}</span>}
              {!collapsed && item.badge != null && (
                <span
                  className="text-[10px] font-bold px-1.5 py-0.5 rounded-md"
                  style={{
                    background: 'color-mix(in oklch, #f59e0b 18%, transparent)',
                    color: '#92400e',
                  }}
                >
                  {item.badge}
                </span>
              )}
            </NavLink>
          )
        })}
      </nav>

      <div className="h-px mx-3" style={{ background: 'var(--line)' }} />

      {/* Footer */}
      <div className="p-2">
        <div
          className={`flex items-center gap-3 p-2 rounded-xl transition ${collapsed ? 'justify-center' : ''}`}
          onMouseEnter={e => { e.currentTarget.style.background = 'color-mix(in oklch, var(--ink) 4%, var(--card))' }}
          onMouseLeave={e => { e.currentTarget.style.background = '' }}
        >
          <div
            className="w-9 h-9 rounded-xl shrink-0 flex items-center justify-center text-white text-sm font-bold"
            style={{ background: 'linear-gradient(135deg, var(--brand), var(--accent))' }}
          >
            {initials}
          </div>

          {!collapsed && (
            <>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold truncate" style={{ color: 'var(--ink)' }}>
                  {user?.name ?? 'User'}
                </p>
                <p className="text-xs" style={{ color: 'var(--ink-2)' }}>Admin</p>
              </div>
              <button
                onClick={logout}
                className="p-1.5 rounded-lg transition hover:opacity-70"
                style={{ color: 'var(--ink-2)' }}
                title="Sign out"
              >
                <LogOut className="w-4 h-4" />
              </button>
            </>
          )}
        </div>

        {collapsed && (
          <button
            onClick={() => setCollapsed(false)}
            className="w-full mt-1 p-1.5 rounded-lg transition flex justify-center hover:opacity-70"
            style={{ color: 'var(--ink-2)' }}
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        )}
      </div>
    </aside>
  )
}
