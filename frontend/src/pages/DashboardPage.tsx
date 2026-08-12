import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { BarChart, Bar, AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'
import AppLayout from '../components/layout/AppLayout'
import { useAuth } from '../contexts/AuthContext'
import { StatusBadge } from '../components/aria/Badges'
import { RecentRun, RecentAutomation, RunStatus } from '../lib/aria-data'
import { listRuns } from '../lib/registryApi'
import { listAutomationRuns, getSummary, getKpiTrends, getDailyTrend, GlobalSummary, KpiTrends, DailyTrendPoint } from '../lib/reportsApi'
import { getRunEndpoints, RunEndpoint } from '../lib/analysisApi'
import { FlaskConical, Package, Wand2, CheckCheck, TriangleAlert, Shield, ArrowRight, Upload, Layers, TrendingUp, TrendingDown } from 'lucide-react'

function mapRunStatus(s: string): RunStatus {
  const m: Record<string, RunStatus> = {
    done: 'completed', completed: 'completed',
    processing: 'running', running: 'running',
    queued: 'pending', pending: 'pending',
    failed: 'failed', parsing: 'parsing',
  }
  return m[s] ?? 'pending'
}

// Relative change vs the previous window, or null when there's nothing to compare against.
function deltaPct(current: number, previous: number): number | null {
  if (previous === 0) return current > 0 ? null : 0
  return Math.round(((current - previous) / previous) * 1000) / 10
}

function TrendBadge({ current, previous }: { current: number; previous: number }) {
  const pct = deltaPct(current, previous)
  if (pct === null) {
    return previous === 0 && current > 0
      ? <span className="text-[11px] font-bold" style={{ color: 'var(--brand)' }}>New</span>
      : null
  }
  const flat = pct === 0
  const up = pct > 0
  const color = flat ? 'var(--ink-2)' : up ? '#10b981' : '#f43f5e'
  return (
    <span className="inline-flex items-center gap-0.5 text-[11px] font-bold" style={{ color }}>
      {!flat && (up ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />)}
      {up ? '+' : ''}{pct}%
    </span>
  )
}

const ANALYSIS_PAGE_SIZE = 5
const AUTOMATION_PAGE_SIZE = 5

function Pager({ page, totalPages, onChange }: { page: number; totalPages: number; onChange: (page: number) => void }) {
  if (totalPages <= 1) return null
  return (
    <div className="flex items-center justify-between px-4 py-2.5" style={{ borderTop: '1px solid var(--line)' }}>
      <button
        onClick={() => onChange(page - 1)}
        disabled={page <= 1}
        className="text-xs font-semibold px-2.5 py-1.5 rounded-lg transition disabled:opacity-40 disabled:cursor-not-allowed hover:opacity-70"
        style={{ color: 'var(--ink-2)' }}
      >
        ← Prev
      </button>
      <span className="text-xs ink-2">Page {page} / {totalPages}</span>
      <button
        onClick={() => onChange(page + 1)}
        disabled={page >= totalPages}
        className="text-xs font-semibold px-2.5 py-1.5 rounded-lg transition disabled:opacity-40 disabled:cursor-not-allowed hover:opacity-70"
        style={{ color: 'var(--ink-2)' }}
      >
        Next →
      </button>
    </div>
  )
}

function StatCard({ label, value, icon: Icon, sub, alert, trend }: {
  label: string; value: string; icon: React.ElementType
  sub?: string; alert?: boolean; trend?: { current: number; previous: number }
}) {
  return (
    <div className="card pad flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div className="w-10 h-10 rounded-xl flex items-center justify-center"
          style={{ background: alert ? 'color-mix(in oklch, #f43f5e 12%, var(--card))' : 'color-mix(in oklch, var(--brand) 12%, var(--card))', color: alert ? '#f43f5e' : 'var(--brand)' }}>
          <Icon className="w-5 h-5" />
        </div>
        {trend && <TrendBadge current={trend.current} previous={trend.previous} />}
      </div>
      <div>
        <p className="text-2xl font-black" style={{ color: 'var(--ink)' }}>{value}</p>
        <p className="text-xs ink-2 mt-0.5">{label}</p>
        {sub && <p className="text-[11px] ink-2 mt-0.5">{sub}</p>}
      </div>
    </div>
  )
}

export default function DashboardPage() {
  const nav = useNavigate()
  const { user } = useAuth()
  const firstName = user?.name?.split(' ')[0] || user?.email || 'there'
  const today = new Date().toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' })

  const [recentRuns, setRecentRuns]           = useState<RecentRun[]>([])
  const [recentAutos, setRecentAutos]         = useState<RecentAutomation[]>([])
  const [summary, setSummary]                 = useState<GlobalSummary | null>(null)
  const [totalAnalysisRuns, setTotalAnalysisRuns] = useState<number | null>(null)
  const [latestEndpoints, setLatestEndpoints] = useState<RunEndpoint[]>([])
  const [kpiTrends, setKpiTrends]             = useState<KpiTrends | null>(null)
  const [dailyTrend, setDailyTrend]           = useState<DailyTrendPoint[]>([])

  // Both tables paginate independently — 1-based to match the UI/backend "page" param.
  const [runsPage, setRunsPage]               = useState(1)
  const [runsTotalPages, setRunsTotalPages]   = useState(1)
  const [autosPage, setAutosPage]             = useState(1)
  const [autosTotalPages, setAutosTotalPages] = useState(1)

  useEffect(() => {
    getSummary().then(setSummary).catch(() => {})
    getKpiTrends(7).then(setKpiTrends).catch(() => {})
    getDailyTrend(30).then(setDailyTrend).catch(() => {})

    // Seed the charts from the single most-recent run — independent of the
    // "Recent analysis runs" table's own pagination below.
    listRuns({ limit: 1 }).then(data => {
      if (data.items.length > 0) {
        getRunEndpoints(data.items[0].id)
          .then(eps => setLatestEndpoints(eps.endpoints))
          .catch(() => {})
      }
    }).catch(() => {})
  }, [])

  useEffect(() => {
    listRuns({ limit: ANALYSIS_PAGE_SIZE, offset: (runsPage - 1) * ANALYSIS_PAGE_SIZE }).then(data => {
      setTotalAnalysisRuns(data.total)
      setRunsTotalPages(Math.max(1, Math.ceil(data.total / ANALYSIS_PAGE_SIZE)))
      setRecentRuns(data.items.map((r) => ({
        id: r.id,
        name: r.file_name,
        source: 'HAR',
        status: mapRunStatus(r.status),
        endpoints: r.total_normalized_endpoints,
        created: new Date(r.created_at).toLocaleDateString(),
        duration: '—',
      })))
    }).catch(() => {})
  }, [runsPage])

  useEffect(() => {
    listAutomationRuns({ limit: AUTOMATION_PAGE_SIZE, page: autosPage }).then(data => {
      setAutosTotalPages(data.total_pages)
      setRecentAutos(data.items.map(r => ({
        id: r.id,
        workflow: r.workflow_name,
        rows: r.total_steps,
        success: r.success_count,
        failed: r.failed_count,
        status: mapRunStatus(r.status),
        started: new Date(r.created_at).toLocaleDateString(),
        dryRun: r.dry_run,
      })))
    }).catch(() => {})
  }, [autosPage])

  const kpis = [
    { label: 'Analysis runs',        value: totalAnalysisRuns != null ? totalAnalysisRuns.toLocaleString() : '—', icon: FlaskConical, sub: 'vs previous 7 days', trend: kpiTrends?.analysis_runs },
    { label: 'Endpoints catalogued', value: recentRuns.length > 0 ? recentRuns.reduce((s, r) => s + r.endpoints, 0).toLocaleString() : '—', icon: Package, sub: 'vs previous 7 days', trend: kpiTrends?.endpoints_catalogued },
    { label: 'Automation runs',      value: summary ? summary.total_automation_runs.toLocaleString() : '—', icon: Wand2, sub: summary?.status_breakdown?.['running'] ? `${summary.status_breakdown['running']} in progress` : 'vs previous 7 days', trend: kpiTrends?.automation_runs },
    { label: 'Global success rate',  value: summary ? `${(summary.global_success_rate * 100).toFixed(1)}%` : '—', icon: CheckCheck, sub: 'vs previous 7 days', trend: kpiTrends ? { current: kpiTrends.global_success_rate.current * 100, previous: kpiTrends.global_success_rate.previous * 100 } : undefined },
  ]

  const totalFailed = summary?.total_failed ?? 0
  const alerts = [
    { label: 'Failed runs', value: totalFailed > 0 ? totalFailed.toLocaleString() : '0', icon: TriangleAlert, sub: totalFailed > 0 ? 'view reports' : 'no errors', alert: totalFailed > 0 },
    { label: 'Current role',         value: 'Admin',  icon: Shield, sub: 'Active permissions' },
  ]

  // Real chart data from latest run endpoints
  const methodData = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE']
    .map(m => ({ method: m, count: latestEndpoints.filter(e => e.method === m).length }))
    .filter(d => d.count > 0)

  const domainMap = latestEndpoints.reduce((acc, e) => {
    const d = e.business_domain ?? 'Other'
    acc[d] = (acc[d] ?? 0) + 1
    return acc
  }, {} as Record<string, number>)
  const domainData = Object.entries(domainMap)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)
    .map(([domain, count]) => ({ domain, count }))

  const hasAnyData = totalAnalysisRuns != null && totalAnalysisRuns > 0

  return (
    <AppLayout>
      <div className="p-6 space-y-6">
        {/* Greeting */}
        <div className="flex items-end justify-between gap-4 flex-wrap">
          <div>
            <p className="text-xs font-semibold tracking-wider uppercase ink-2">{today}</p>
            <h1 className="text-2xl font-black mt-0.5" style={{ color: 'var(--ink)' }}>
              Good morning, <span className="grad-text">{firstName}</span>
            </h1>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => nav('/analysis')} className="btn-secondary"><Upload className="w-4 h-4" /> Upload HAR</button>
            <button onClick={() => nav('/bulk')} className="btn-primary"><Layers className="w-4 h-4" /> Open bulk run</button>
          </div>
        </div>

        {/* Empty state — first time */}
        {!hasAnyData && totalAnalysisRuns === 0 && (
          <div className="card pad text-center py-16 space-y-4">
            <div className="w-16 h-16 rounded-2xl grad-bg mx-auto flex items-center justify-center">
              <Upload className="w-7 h-7 text-white" />
            </div>
            <div>
              <p className="text-lg font-black" style={{ color: 'var(--ink)' }}>Welcome to ARIA</p>
              <p className="text-sm ink-2 mt-1">Start by analyzing a HAR file to discover your endpoints, infer schemas, and detect workflows.</p>
            </div>
            <div className="flex items-center justify-center gap-6 text-sm ink-2 pt-2">
              {['① Upload a HAR', '② Explore your APIs', '③ Automate in bulk'].map((step, i) => (
                <div key={i} className="flex items-center gap-1.5">
                  <span className="w-5 h-5 rounded-full grad-bg text-white text-[10px] font-bold flex items-center justify-center">{i + 1}</span>
                  <span>{step.slice(2)}</span>
                </div>
              ))}
            </div>
            <button onClick={() => nav('/analysis')} className="btn-primary mx-auto">
              <Upload className="w-4 h-4" /> Analyze my first HAR
            </button>
          </div>
        )}

        {/* KPIs — only when we have data */}
        {hasAnyData && (
          <>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {kpis.map((k, i) => <StatCard key={i} {...k} />)}
            </div>

            {/* Charts — données réelles depuis le run le plus récent */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              <div className="lg:col-span-2 card pad">
                <p className="text-sm font-bold" style={{ color: 'var(--ink)' }}>HTTP method distribution</p>
                <p className="text-xs ink-2 mt-0.5 mb-4">Most recent run · {latestEndpoints.length} endpoints</p>
                {methodData.length === 0 ? (
                  <div className="flex items-center justify-center h-[180px] ink-2 text-sm">Loading…</div>
                ) : (
                  <ResponsiveContainer width="100%" height={180}>
                    <BarChart data={methodData} barGap={4}>
                      <CartesianGrid strokeDasharray="3 3" stroke="color-mix(in oklch, var(--line) 80%, transparent)" />
                      <XAxis dataKey="method" tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
                      <YAxis tick={{ fontSize: 11 }} axisLine={false} tickLine={false} allowDecimals={false} />
                      <Tooltip contentStyle={{ borderRadius: 12, fontSize: 12, background: 'var(--card)', border: '1px solid var(--line)', color: 'var(--ink)' }} />
                      <Bar dataKey="count" name="Endpoints" fill="#dc2626" radius={[6, 6, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </div>
              <div className="card pad">
                <p className="text-sm font-bold" style={{ color: 'var(--ink)' }}>Top business domains</p>
                <p className="text-xs ink-2 mt-0.5 mb-5">Most recent run</p>
                {domainData.length === 0 ? (
                  <div className="flex items-center justify-center h-[120px] ink-2 text-sm">No data</div>
                ) : (
                  <div className="space-y-3">
                    {domainData.map(({ domain, count }) => {
                      const pct = Math.round((count / latestEndpoints.length) * 100)
                      return (
                        <div key={domain}>
                          <div className="flex justify-between text-xs mb-1.5">
                            <span className="font-semibold capitalize" style={{ color: 'var(--ink)' }}>{domain}</span>
                            <span className="font-mono ink-2">{count} eps</span>
                          </div>
                          <div className="h-2 rounded-full" style={{ background: 'var(--line)' }}>
                            <div className="h-2 rounded-full grad-bg" style={{ width: `${pct}%` }} />
                          </div>
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>
            </div>

            {/* Historical trend — real automation-run counts per day */}
            <div className="card pad">
              <p className="text-sm font-bold" style={{ color: 'var(--ink)' }}>Automation runs — last 30 days</p>
              <p className="text-xs ink-2 mt-0.5 mb-4">{dailyTrend.reduce((s, d) => s + d.count, 0).toLocaleString()} runs total</p>
              {dailyTrend.length === 0 ? (
                <div className="flex items-center justify-center h-[160px] ink-2 text-sm">Loading…</div>
              ) : (
                <ResponsiveContainer width="100%" height={160}>
                  <AreaChart data={dailyTrend}>
                    <defs>
                      <linearGradient id="dashTrendGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#dc2626" stopOpacity={0.25} />
                        <stop offset="95%" stopColor="#dc2626" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="color-mix(in oklch, var(--line) 80%, transparent)" />
                    <XAxis dataKey="date" tick={{ fontSize: 11 }} axisLine={false} tickLine={false} minTickGap={24}
                      tickFormatter={d => new Date(d).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })} />
                    <YAxis tick={{ fontSize: 11 }} axisLine={false} tickLine={false} allowDecimals={false} width={28} />
                    <Tooltip contentStyle={{ borderRadius: 12, fontSize: 12, background: 'var(--card)', border: '1px solid var(--line)', color: 'var(--ink)' }}
                      labelFormatter={d => new Date(d).toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })} />
                    <Area type="monotone" dataKey="count" name="Runs" stroke="#dc2626" strokeWidth={2} fill="url(#dashTrendGrad)" />
                  </AreaChart>
                </ResponsiveContainer>
              )}
            </div>

            {/* Alerts */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {alerts.map((a, i) => <StatCard key={i} {...a} />)}
            </div>
          </>
        )}

        {/* Tables — always visible */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="card overflow-hidden">
            <div className="flex items-center justify-between px-5 pt-5 pb-3">
              <div>
                <p className="text-sm font-bold" style={{ color: 'var(--ink)' }}>Recent analysis runs</p>
                <p className="text-xs ink-2">From HAR / JMX / Live captures</p>
              </div>
              <button onClick={() => nav('/analysis')} className="btn-ghost text-xs">View all <ArrowRight className="w-3.5 h-3.5" /></button>
            </div>
            <table className="w-full text-sm">
              <thead className="aria-thead">
                <tr>{['Run', 'Source', 'Status', 'Endpoints'].map(h => <th key={h} className="text-left px-4 py-2.5">{h}</th>)}</tr>
              </thead>
              <tbody>
                {recentRuns.length === 0 && (
                  <tr>
                    <td colSpan={4} className="px-4 py-10 text-center">
                      <p className="text-sm ink-2">No analyses yet</p>
                      <button onClick={() => nav('/analysis')} className="btn-primary mt-3 mx-auto text-xs">
                        <Upload className="w-3.5 h-3.5" /> Analyze a HAR
                      </button>
                    </td>
                  </tr>
                )}
                {recentRuns.map((r, i) => (
                  <tr key={r.id} className="border-t cursor-pointer transition" style={{ borderColor: 'var(--line)' }}
                    onMouseEnter={e => (e.currentTarget.style.background = 'color-mix(in oklch, var(--brand) 4%, var(--card))')}
                    onMouseLeave={e => (e.currentTarget.style.background = '')}
                    onClick={() => nav(`/endpoints?run=${r.id}`)}>
                    <td className="px-4 py-2.5">
                      <p className="font-semibold" style={{ color: 'var(--ink)' }}>Analysis #{String((runsPage - 1) * ANALYSIS_PAGE_SIZE + i + 1).padStart(3, '0')}</p>
                      <p className="text-xs ink-2 truncate max-w-[160px]">{r.name}</p>
                    </td>
                    <td className="px-4 py-2.5"><span className="pill" style={{ background: 'color-mix(in oklch, var(--ink) 4%, var(--card))', borderColor: 'var(--line)', color: 'var(--ink-2)' }}>{r.source}</span></td>
                    <td className="px-4 py-2.5"><StatusBadge s={r.status} /></td>
                    <td className="px-4 py-2.5 font-mono text-sm font-bold text-right" style={{ color: 'var(--ink)' }}>{r.endpoints}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Pager page={runsPage} totalPages={runsTotalPages} onChange={setRunsPage} />
          </div>

          <div className="card overflow-hidden">
            <div className="flex items-center justify-between px-5 pt-5 pb-3">
              <div>
                <p className="text-sm font-bold" style={{ color: 'var(--ink)' }}>Recent automation runs</p>
                <p className="text-xs ink-2">Including dry-runs and approved executions</p>
              </div>
              <button onClick={() => nav('/reports')} className="btn-ghost text-xs">View all <ArrowRight className="w-3.5 h-3.5" /></button>
            </div>
            <table className="w-full text-sm">
              <thead className="aria-thead">
                <tr>{['Run', 'Workflow', 'Status', 'Success'].map(h => <th key={h} className="text-left px-4 py-2.5">{h}</th>)}</tr>
              </thead>
              <tbody>
                {recentAutos.length === 0 && (
                  <tr>
                    <td colSpan={4} className="px-4 py-10 text-center">
                      <p className="text-sm ink-2">No runs yet</p>
                      <button onClick={() => nav('/bulk')} className="btn-primary mt-3 mx-auto text-xs">
                        <Layers className="w-3.5 h-3.5" /> Run a bulk
                      </button>
                    </td>
                  </tr>
                )}
                {recentAutos.map((r, i) => (
                  <tr key={r.id} className="border-t cursor-pointer transition" style={{ borderColor: 'var(--line)' }}
                    onMouseEnter={e => (e.currentTarget.style.background = 'color-mix(in oklch, var(--brand) 4%, var(--card))')}
                    onMouseLeave={e => (e.currentTarget.style.background = '')}
                    onClick={() => nav(`/reports?tab=automation&run=${r.id}`)}>
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-2">
                        <p className="font-semibold" style={{ color: 'var(--ink)' }}>#{String((autosPage - 1) * AUTOMATION_PAGE_SIZE + i + 1).padStart(3, '0')}</p>
                        {r.dryRun && <span className="pill bg-sky-50 text-sky-700 border-sky-200">Sim</span>}
                      </div>
                    </td>
                    <td className="px-4 py-2.5 text-sm ink-2 truncate max-w-[140px]">{r.workflow}</td>
                    <td className="px-4 py-2.5"><StatusBadge s={r.status} /></td>
                    <td className="px-4 py-2.5 font-mono text-sm text-right font-bold" style={{ color: 'var(--ink)' }}>
                      {r.success.toLocaleString()}<span className="ink-2 font-normal text-xs">/{r.rows.toLocaleString()}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Pager page={autosPage} totalPages={autosTotalPages} onChange={setAutosPage} />
          </div>
        </div>
      </div>
    </AppLayout>
  )
}
