import { useLocation } from 'react-router-dom'
import { useTheme } from '../../contexts/ThemeContext'
import { useAuth } from '../../contexts/AuthContext'
import {
  Sun, Moon, Bell, Home, Upload, Package, Network,
  FileCode2, Sparkles, Wand2, Layers, Inbox, BarChart2,
  Settings2, Users, ChevronRight,
} from 'lucide-react'

const PAGES: Record<string, { label: string; icon: React.ElementType; section: string }> = {
  '/dashboard':  { label:'Dashboard',       icon:Home,      section:'Overview' },
  '/analysis':   { label:'Analyse HAR',     icon:Upload,    section:'Discovery' },
  '/endpoints':  { label:'Endpoints',       icon:Package,   section:'Discovery' },
  '/workflows':  { label:'Workflows',       icon:Network,   section:'Discovery' },
  '/openapi':    { label:'OpenAPI',         icon:FileCode2, section:'Discovery' },
  '/rag':        { label:'Endpoint Search', icon:Sparkles,  section:'Discovery' },
  '/automation': { label:'Automation',      icon:Wand2,     section:'Execution' },
  '/bulk':       { label:'Automation Bulk', icon:Layers,    section:'Execution' },
  '/approvals':  { label:'Approvals',       icon:Inbox,     section:'Execution' },
  '/reports':    { label:'Reports',         icon:BarChart2, section:'Analytics' },
  '/settings':   { label:'Settings',        icon:Settings2, section:'Admin' },
  '/users':      { label:'Users',           icon:Users,     section:'Admin' },
}

export default function Topbar() {
  const { pathname } = useLocation()
  const { theme, toggleTheme } = useTheme()
  const { user } = useAuth()
  const isDark = theme === 'dark'

  const page = PAGES[pathname]
  const Icon = page?.icon ?? Home
  const initials = user?.name
    ? user.name.split(' ').map((s: string) => s[0]).slice(0, 2).join('').toUpperCase()
    : 'U'

  // Aria1 CSS variables are defined on :root / html.dark in index.css
  const borderStyle = { borderBottom: '1px solid var(--line)' }
  const cardBg = { background: 'var(--card)' }
  const iconBtnStyle = {
    ...cardBg,
    border: '1px solid var(--line)',
    color: 'var(--ink-2)',
  }

  return (
    <header
      className="sticky top-0 z-10 flex items-center justify-between gap-4 px-6 h-[60px] backdrop-blur-md"
      style={{
        ...borderStyle,
        background: 'color-mix(in oklch, var(--card) 80%, transparent)',
      }}
    >
      {/* Left — breadcrumb */}
      <div className="flex items-center gap-2 min-w-0">
        <div className="flex items-center justify-center w-7 h-7 rounded-lg"
          style={{ background: 'color-mix(in oklch, var(--brand) 12%, transparent)' }}>
          <Icon className="w-4 h-4" style={{ color: 'var(--brand)' }} />
        </div>

        {page?.section && (
          <>
            <span className="text-xs font-medium hidden sm:inline" style={{ color: 'var(--ink-2)' }}>
              {page.section}
            </span>
            <ChevronRight className="w-3 h-3 hidden sm:inline" style={{ color: 'var(--line)' }} />
          </>
        )}

        <h1 className="text-sm font-bold truncate" style={{ color: 'var(--ink)' }}>
          {page?.label ?? 'ARIA'}
        </h1>
      </div>

      {/* Right */}
      <div className="flex items-center gap-1.5">


        {/* Dark mode toggle */}
        <button
          onClick={toggleTheme}
          title={isDark ? 'Light mode' : 'Dark mode'}
          className="p-2 rounded-xl transition hover:opacity-80"
          style={iconBtnStyle}
        >
          {isDark
            ? <Sun className="w-4 h-4" style={{ color: 'var(--ink-2)' }} />
            : <Moon className="w-4 h-4" style={{ color: 'var(--ink-2)' }} />}
        </button>

        {/* Notifications */}
        <button
          className="relative p-2 rounded-xl transition hover:opacity-80"
          style={iconBtnStyle}
        >
          <Bell className="w-4 h-4" />
          <span className="absolute top-1.5 right-1.5 w-1.5 h-1.5 rounded-full bg-rose-500" />
        </button>

        {/* Divider */}
        <div className="w-px h-6 mx-1" style={{ background: 'var(--line)' }} />

        {/* User */}
        <div className="flex items-center gap-2 pl-1">
          <div
            className="w-8 h-8 rounded-xl flex items-center justify-center text-white text-xs font-bold cursor-pointer"
            style={{ background: 'linear-gradient(135deg, var(--brand), var(--accent))' }}
          >
            {initials}
          </div>
          <div className="hidden lg:block">
            <p className="text-xs font-semibold leading-none" style={{ color: 'var(--ink)' }}>
              {user?.name ?? 'User'}
            </p>
            <p className="text-[10px] mt-0.5" style={{ color: 'var(--ink-2)' }}>Admin</p>
          </div>
        </div>
      </div>
    </header>
  )
}
