import { useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { useTheme } from '../../contexts/ThemeContext'
import { useAuth } from '../../contexts/AuthContext'
import {
  Sun, Moon, Bell, Home, Upload, Package, Network,
  FileCode2, Sparkles, Wand2, Layers, Inbox, BarChart2,
  Users, ChevronRight,
} from 'lucide-react'
import {
  AriaNotification,
  getNotifications,
  getUnreadNotificationCount,
  markAllNotificationsRead,
  markNotificationRead,
} from '../../lib/notificationsApi'

const NOTIFICATIONS_POLL_MS = 15000

// BULK_EXECUTION_STARTED / APPROVAL_REQUIRED are team-wide notices (shown
// with the operator/admin's name); the other three are personal completion
// notices sent only to whoever launched the run.
const TEAM_NOTICE_ACTIONS = new Set(['BULK_EXECUTION_STARTED', 'APPROVAL_REQUIRED'])

const NOTIFICATION_COPY: Record<string, { verb: string; dotColor: string }> = {
  BULK_EXECUTION_STARTED:   { verb: 'launched a bulk run',            dotColor: 'var(--brand)' },
  APPROVAL_REQUIRED:        { verb: 'needs approval to run',          dotColor: '#f59e0b' },
  BULK_EXECUTION_COMPLETED: { verb: 'Your bulk run finished successfully', dotColor: '#22c55e' },
  BULK_EXECUTION_PARTIAL:   { verb: 'Your bulk run finished with some errors', dotColor: '#f59e0b' },
  BULK_EXECUTION_FAILED:    { verb: 'Your bulk run failed',           dotColor: '#ef4444' },
}

function formatRelativeTime(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime()
  const diffMin = Math.floor(diffMs / 60000)
  if (diffMin < 1) return "just now"
  if (diffMin < 60) return `${diffMin} min ago`
  const diffH = Math.floor(diffMin / 60)
  if (diffH < 24) return `${diffH} h ago`
  return `${Math.floor(diffH / 24)} d ago`
}

const PAGES: Record<string, { label: string; icon: React.ElementType; section: string }> = {
  '/dashboard':  { label:'Dashboard',       icon:Home,      section:'Overview' },
  '/analysis':   { label:'HAR Analysis',     icon:Upload,    section:'Discovery' },
  '/endpoints':  { label:'Endpoints',       icon:Package,   section:'Discovery' },
  '/workflows':  { label:'Workflows',       icon:Network,   section:'Discovery' },
  '/openapi':    { label:'OpenAPI',         icon:FileCode2, section:'Discovery' },
  '/rag':        { label:'Endpoint Search', icon:Sparkles,  section:'Discovery' },
  '/automation': { label:'Automation',      icon:Wand2,     section:'Execution' },
  '/bulk':       { label:'Bulk Automation', icon:Layers,    section:'Execution' },
  '/approvals':  { label:'Approvals',       icon:Inbox,     section:'Execution' },
  '/reports':    { label:'Reports',         icon:BarChart2, section:'Analytics' },
  '/users':      { label:'Users',           icon:Users,     section:'Admin' },
}

export default function Topbar() {
  const { pathname } = useLocation()
  const { theme, toggleTheme } = useTheme()
  const { user } = useAuth()
  const isDark = theme === 'dark'
  const canSeeNotifications = !!user

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

  // ── Notifications ──────────────────────────────────────────────────────────
  // Admins see team-wide notices when an operator in their org launches a bulk
  // run; every launcher (admin or operator) gets a personal notice when their
  // own run finishes. The backend scopes GET /notifications per role.
  const [notifPanelOpen, setNotifPanelOpen] = useState(false)
  const [notifications, setNotifications] = useState<AriaNotification[]>([])
  const [unreadCount, setUnreadCount] = useState(0)
  const notifPanelRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!canSeeNotifications) return
    let cancelled = false
    const pollUnread = () => {
      getUnreadNotificationCount()
        .then(({ count }) => { if (!cancelled) setUnreadCount(count) })
        .catch(() => {})
    }
    pollUnread()
    const id = setInterval(pollUnread, NOTIFICATIONS_POLL_MS)
    return () => { cancelled = true; clearInterval(id) }
  }, [canSeeNotifications])

  useEffect(() => {
    const onClickOutside = (e: MouseEvent) => {
      if (notifPanelRef.current && !notifPanelRef.current.contains(e.target as Node)) {
        setNotifPanelOpen(false)
      }
    }
    document.addEventListener('mousedown', onClickOutside)
    return () => document.removeEventListener('mousedown', onClickOutside)
  }, [])

  const toggleNotifPanel = () => {
    const next = !notifPanelOpen
    setNotifPanelOpen(next)
    if (next) {
      getNotifications().then(setNotifications).catch(() => {})
    }
  }

  const handleNotificationClick = (n: AriaNotification) => {
    if (n.is_read) return
    setNotifications(prev => prev.map(x => x.id === n.id ? { ...x, is_read: true } : x))
    setUnreadCount(prev => Math.max(0, prev - 1))
    markNotificationRead(n.id).catch(() => {})
  }

  const handleMarkAllRead = () => {
    setNotifications(prev => prev.map(x => ({ ...x, is_read: true })))
    setUnreadCount(0)
    markAllNotificationsRead().catch(() => {})
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
        {canSeeNotifications && (
          <div className="relative" ref={notifPanelRef}>
            <button
              onClick={toggleNotifPanel}
              title="Notifications"
              className="relative p-2 rounded-xl transition hover:opacity-80"
              style={iconBtnStyle}
            >
              <Bell className="w-4 h-4" />
              {unreadCount > 0 && (
                <span className="absolute top-1.5 right-1.5 w-1.5 h-1.5 rounded-full bg-rose-500" />
              )}
            </button>

            {notifPanelOpen && (
              <div
                className="absolute right-0 mt-2 w-80 max-h-96 overflow-y-auto rounded-xl shadow-lg z-20"
                style={{ ...cardBg, border: '1px solid var(--line)' }}
              >
                <div
                  className="flex items-center justify-between px-3 py-2"
                  style={{ borderBottom: '1px solid var(--line)' }}
                >
                  <span className="text-xs font-semibold" style={{ color: 'var(--ink)' }}>
                    Notifications
                  </span>
                  {unreadCount > 0 && (
                    <button
                      onClick={handleMarkAllRead}
                      className="text-[10px] font-medium hover:underline"
                      style={{ color: 'var(--brand)' }}
                    >
                      Mark all as read
                    </button>
                  )}
                </div>

                {notifications.length === 0 ? (
                  <p className="px-3 py-6 text-center text-xs" style={{ color: 'var(--ink-2)' }}>
                    No notifications
                  </p>
                ) : (
                  notifications.map(n => {
                    const copy = NOTIFICATION_COPY[n.action] ?? NOTIFICATION_COPY.BULK_EXECUTION_STARTED
                    const isTeamNotice = TEAM_NOTICE_ACTIONS.has(n.action)
                    return (
                      <button
                        key={n.id}
                        onClick={() => handleNotificationClick(n)}
                        className="w-full text-left px-3 py-2.5 transition hover:opacity-80"
                        style={{
                          borderBottom: '1px solid var(--line)',
                          background: n.is_read ? 'transparent' : 'color-mix(in oklch, var(--brand) 8%, transparent)',
                        }}
                      >
                        <p className="text-xs flex items-start gap-1.5" style={{ color: 'var(--ink)' }}>
                          <span
                            className="mt-1 w-1.5 h-1.5 rounded-full shrink-0"
                            style={{ background: copy.dotColor }}
                          />
                          <span>
                            {isTeamNotice && <span className="font-semibold">{n.operator_name}</span>}{' '}
                            {copy.verb}
                            {n.har_file_name && (
                              <> {isTeamNotice ? 'on' : '—'} <span className="font-semibold">{n.har_file_name}</span></>
                            )}
                          </span>
                        </p>
                        <p className="text-[10px] mt-0.5 pl-3" style={{ color: 'var(--ink-2)' }}>
                          {formatRelativeTime(n.created_at)}
                        </p>
                      </button>
                    )
                  })
                )}
              </div>
            )}
          </div>
        )}

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
