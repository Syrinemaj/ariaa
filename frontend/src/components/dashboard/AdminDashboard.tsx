import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppLayout from '../layout/AppLayout'
import TrendBadge from './TrendBadge'
import { StatusBadge } from '../aria/Badges'
import { useAuth } from '../../contexts/AuthContext'
import { RunStatus } from '../../lib/aria-data'
import { listRuns, AnalysisRun } from '../../lib/registryApi'
import { listAutomationRuns, getSummary, getKpiTrends, listAuditLogs, GlobalSummary, KpiTrends, AutomationRun, AuditLogEntry } from '../../lib/reportsApi'
import { getRunEndpoints, RunEndpoint } from '../../lib/analysisApi'
import { listApprovals } from '../../lib/approvalsApi'
import { actionColor, formatAction } from '../../lib/auditFormat'
import { Clock, CheckCheck, BellRing, ArrowRight, Layers } from 'lucide-react'

const RECENT_HAR_LIMIT = 3
const AUDIT_LIMIT = 5
const EXECUTIONS_LIMIT = 4

function mapRunStatus(s: string): RunStatus {
  const m: Record<string, RunStatus> = {
    done: 'completed', completed: 'completed',
    processing: 'running', running: 'running',
    queued: 'pending', pending: 'pending',
    failed: 'failed', parsing: 'parsing',
  }
  return m[s] ?? 'pending'
}

function timeAgo(iso: string | null): string {
  if (!iso) return '—'
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.round(mins / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.round(hours / 24)}d ago`
}

function auditResource(log: AuditLogEntry): string | null {
  const name = log.metadata?.name ?? log.metadata?.file_name ?? log.metadata?.email
  if (typeof name === 'string' && name) return name
  if (log.resource_type) return log.resource_type.replace(/_/g, ' ')
  return null
}

function PanelHeader({ title, sub, onViewAll }: { title: string; sub?: string; onViewAll: () => void }) {
  return (
    <div className="flex items-start justify-between gap-3 mb-3">
      <div>
        <p className="text-sm font-bold" style={{ color: 'var(--ink)' }}>{title}</p>
        {sub && <p className="text-xs ink-2 mt-0.5">{sub}</p>}
      </div>
      <button onClick={onViewAll} className="btn-ghost text-xs shrink-0">View all <ArrowRight className="w-3.5 h-3.5" /></button>
    </div>
  )
}

function SectionLabel({ children }: { children: string }) {
  return <p className="text-[11px] font-extrabold tracking-wider uppercase ink-2 mb-2.5">{children}</p>
}

function EmptyRow({ children }: { children: string }) {
  return <p className="text-sm ink-2 text-center py-8">{children}</p>
}

const rowHover = {
  onMouseEnter: (e: React.MouseEvent<HTMLElement>) => { e.currentTarget.style.background = 'color-mix(in oklch, var(--brand) 4%, var(--card))' },
  onMouseLeave: (e: React.MouseEvent<HTMLElement>) => { e.currentTarget.style.background = '' },
}

export default function AdminDashboard() {
  const nav = useNavigate()
  const { user } = useAuth()
  const firstName = user?.name?.split(' ')[0] || user?.email || 'there'
  const today = new Date().toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' })

  const [kpiTrends, setKpiTrends]               = useState<KpiTrends | null>(null)
  const [summary, setSummary]                   = useState<GlobalSummary | null>(null)
  const [inProgress, setInProgress]             = useState<number | null>(null)
  const [pendingApprovals, setPendingApprovals] = useState<number | null>(null)
  const [recentHarRuns, setRecentHarRuns]       = useState<AnalysisRun[] | null>(null)
  const [auditLogs, setAuditLogs]               = useState<AuditLogEntry[] | null>(null)
  const [executions, setExecutions]             = useState<AutomationRun[] | null>(null)
  const [latestEndpoints, setLatestEndpoints]   = useState<RunEndpoint[]>([])

  useEffect(() => {
    getKpiTrends(7).then(setKpiTrends).catch(() => {})
    getSummary().then(setSummary).catch(() => {})
    listApprovals('pending').then(a => setPendingApprovals(a.length)).catch(() => {})

    // Ingestion goes queued → processing → completed | failed; both early states count as "still running".
    Promise.all([listRuns({ status: 'queued', limit: 1 }), listRuns({ status: 'processing', limit: 1 })])
      .then(([q, p]) => setInProgress(q.total + p.total))
      .catch(() => {})

    listRuns({ limit: RECENT_HAR_LIMIT }).then(d => setRecentHarRuns(d.items)).catch(() => setRecentHarRuns([]))
    listAuditLogs({ page: 1, page_size: AUDIT_LIMIT }).then(d => setAuditLogs(d.items)).catch(() => setAuditLogs([]))
    listAutomationRuns({ limit: EXECUTIONS_LIMIT, page: 1 }).then(d => setExecutions(d.items)).catch(() => setExecutions([]))

    listRuns({ limit: 1, status: 'completed' }).then(data => {
      if (data.items.length > 0) {
        getRunEndpoints(data.items[0].id).then(eps => setLatestEndpoints(eps.endpoints)).catch(() => {})
      }
    }).catch(() => {})
  }, [])

  const domainMap = latestEndpoints.reduce((acc, e) => {
    const d = e.business_domain ?? 'Other'
    acc[d] = (acc[d] ?? 0) + 1
    return acc
  }, {} as Record<string, number>)
  const domainData = Object.entries(domainMap).sort((a, b) => b[1] - a[1]).slice(0, 3)
  const topDomainCount = domainData[0]?.[1] ?? 1

  const approvalsAlert = (pendingApprovals ?? 0) > 0

  return (
    <AppLayout>
      <div className="p-6 space-y-6 max-w-[1180px]">
        {/* Greeting */}
        <div className="flex items-end justify-between gap-4 flex-wrap">
          <div>
            <p className="text-sm ink-2">{today}</p>
            <h1 className="text-2xl font-black mt-0.5" style={{ color: 'var(--ink)' }}>
              Good morning, <span className="grad-text">{firstName}</span>
            </h1>
          </div>
          <button onClick={() => nav('/bulk')} className="btn-primary"><Layers className="w-4 h-4" /> Open bulk run</button>
        </div>

        {/* Row 1 — needs your attention */}
        <div>
          <SectionLabel>Needs your attention</SectionLabel>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <button onClick={() => nav('/runs')} className="card pad text-left flex flex-col gap-3">
              <div className="w-10 h-10 rounded-xl flex items-center justify-center"
                style={{ background: 'color-mix(in oklch, var(--brand) 12%, var(--card))', color: 'var(--brand)' }}>
                <Clock className="w-5 h-5" />
              </div>
              <div>
                <p className="text-2xl font-black" style={{ color: 'var(--ink)' }}>{kpiTrends ? kpiTrends.analysis_runs.current.toLocaleString() : '—'}</p>
                <p className="text-xs ink-2 mt-0.5">HAR runs (7d)</p>
                {inProgress != null && inProgress > 0 && (
                  <p className="text-[11px] font-bold mt-1" style={{ color: 'var(--brand)' }}>{inProgress} still processing</p>
                )}
              </div>
            </button>

            <button onClick={() => nav('/reports')} className="card pad text-left flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <div className="w-10 h-10 rounded-xl flex items-center justify-center"
                  style={{ background: 'color-mix(in oklch, #10b981 12%, var(--card))', color: '#10b981' }}>
                  <CheckCheck className="w-5 h-5" />
                </div>
                {kpiTrends && (
                  <TrendBadge current={kpiTrends.global_success_rate.current * 100} previous={kpiTrends.global_success_rate.previous * 100} />
                )}
              </div>
              <div>
                <p className="text-2xl font-black" style={{ color: 'var(--ink)' }}>{summary ? `${(summary.global_success_rate * 100).toFixed(1)}%` : '—'}</p>
                <p className="text-xs ink-2 mt-0.5">Automation success rate</p>
              </div>
            </button>

            <button onClick={() => nav('/approvals')} className="card pad text-left flex flex-col gap-3"
              style={approvalsAlert ? { borderColor: 'color-mix(in oklch, #f59e0b 40%, var(--line))', background: 'color-mix(in oklch, #f59e0b 5%, var(--card))' } : undefined}>
              <div className="w-10 h-10 rounded-xl flex items-center justify-center"
                style={{ background: 'color-mix(in oklch, #f59e0b 14%, var(--card))', color: '#b45309' }}>
                <BellRing className="w-5 h-5" />
              </div>
              <div>
                <p className="text-2xl font-black" style={{ color: 'var(--ink)' }}>{pendingApprovals != null ? pendingApprovals.toLocaleString() : '—'}</p>
                <p className="text-xs ink-2 mt-0.5">Pending approvals</p>
                <p className="text-[11px] font-bold mt-1" style={{ color: approvalsAlert ? '#b45309' : 'var(--ink-2)' }}>
                  {approvalsAlert ? 'Action required' : 'Nothing waiting'}
                </p>
              </div>
            </button>
          </div>
        </div>

        {/* Row 2 — recent HAR analyses + audit log */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="card pad">
            <PanelHeader title="Recent HAR analyses" onViewAll={() => nav('/runs')} />
            {recentHarRuns === null && <EmptyRow>Loading…</EmptyRow>}
            {recentHarRuns?.length === 0 && <EmptyRow>No analyses yet</EmptyRow>}
            <div className="flex flex-col gap-px">
              {recentHarRuns?.map(r => (
                <button key={r.id} onClick={() => nav('/runs')} {...rowHover}
                  className="flex items-center gap-2.5 px-1.5 py-2 rounded-lg text-left transition">
                  <span className="flex-1 min-w-0 truncate font-mono text-[12.5px] font-semibold" style={{ color: 'var(--ink)' }}>{r.file_name}</span>
                  <StatusBadge s={mapRunStatus(r.status)} />
                  <span className="text-[11px] ink-2 shrink-0">{timeAgo(r.created_at)}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="card pad">
            <PanelHeader title="Audit log" sub="Latest actions across all users" onViewAll={() => nav('/audit-log')} />
            {auditLogs === null && <EmptyRow>Loading…</EmptyRow>}
            {auditLogs?.length === 0 && <EmptyRow>No activity recorded yet</EmptyRow>}
            <div className="flex flex-col gap-px">
              {auditLogs?.map(log => {
                const resource = auditResource(log)
                return (
                  <button key={log.id} onClick={() => nav('/audit-log')} {...rowHover}
                    className="flex items-center gap-2.5 px-1.5 py-2 rounded-lg text-left transition">
                    <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: actionColor(log.action) }} />
                    <span className="flex-1 min-w-0 truncate text-[12.5px]" style={{ color: 'var(--ink)' }}>
                      <b className="font-bold">{log.user_name || log.user_email || 'System'}</b>
                      {' '}<span className="font-mono font-semibold" style={{ color: actionColor(log.action) }}>{formatAction(log.action)}</span>
                      {resource && <span className="ink-2"> · {resource}</span>}
                    </span>
                    <span className="text-[11px] ink-2 shrink-0">{timeAgo(log.created_at)}</span>
                  </button>
                )
              })}
            </div>
          </div>
        </div>

        {/* Row 3 — results */}
        <div>
          <SectionLabel>Results</SectionLabel>
          <div className="grid grid-cols-1 lg:grid-cols-[0.85fr_1.15fr] gap-4">
            <div className="card pad">
              <p className="text-sm font-bold" style={{ color: 'var(--ink)' }}>Endpoints discovered</p>
              <div className="flex items-center gap-2 mt-0.5">
                <p className="text-xs ink-2">Catalogued in the last 7 days</p>
                {kpiTrends && <TrendBadge current={kpiTrends.endpoints_catalogued.current} previous={kpiTrends.endpoints_catalogued.previous} />}
              </div>
              <p className="text-[34px] font-black mt-3" style={{ color: 'var(--ink)' }}>
                {kpiTrends ? kpiTrends.endpoints_catalogued.current.toLocaleString() : '—'}
              </p>
              {domainData.length > 0 && (
                <div className="mt-3 space-y-2.5">
                  <p className="text-[11px] ink-2">Top domains — most recent run</p>
                  {domainData.map(([domain, count]) => (
                    <div key={domain}>
                      <div className="flex justify-between text-xs mb-1">
                        <span className="font-semibold capitalize" style={{ color: 'var(--ink)' }}>{domain}</span>
                        <span className="font-mono ink-2">{count}</span>
                      </div>
                      <div className="h-1.5 rounded-full" style={{ background: 'var(--line)' }}>
                        <div className="h-1.5 rounded-full grad-bg" style={{ width: `${Math.round((count / topDomainCount) * 100)}%` }} />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="card overflow-hidden">
              <div className="px-5 pt-5">
                <PanelHeader title="Recent executions" onViewAll={() => nav('/reports')} />
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="aria-thead">
                    <tr>
                      <th className="text-left px-4 py-2.5">Workflow</th>
                      <th className="text-left px-4 py-2.5">Status</th>
                      <th className="text-right px-4 py-2.5">Success</th>
                    </tr>
                  </thead>
                  <tbody>
                    {executions === null && (
                      <tr><td colSpan={3} className="px-4 py-8 text-center text-sm ink-2">Loading…</td></tr>
                    )}
                    {executions?.length === 0 && (
                      <tr><td colSpan={3} className="px-4 py-8 text-center text-sm ink-2">No executions yet</td></tr>
                    )}
                    {executions?.map(r => (
                      <tr key={r.id} className="border-t cursor-pointer transition" style={{ borderColor: 'var(--line)' }}
                        {...rowHover}
                        onClick={() => nav(`/reports?tab=automation&run=${r.id}`)}>
                        <td className="px-4 py-2.5 truncate max-w-[220px]" style={{ color: 'var(--ink)' }}>{r.workflow_name}</td>
                        <td className="px-4 py-2.5"><StatusBadge s={mapRunStatus(r.status)} /></td>
                        <td className="px-4 py-2.5 font-mono text-right font-bold" style={{ color: 'var(--ink)' }}>
                          {r.success_count.toLocaleString()}<span className="ink-2 font-normal text-xs">/{r.total_steps.toLocaleString()}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      </div>
    </AppLayout>
  )
}
