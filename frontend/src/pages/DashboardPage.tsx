import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'
import AppLayout from '../components/layout/AppLayout'
import { StatusBadge } from '../components/aria/Badges'
import { SUCCESS_TIMELINE, STATUS_BREAKDOWN, RecentRun, RecentAutomation, RunStatus } from '../lib/aria-data'
import { listRuns } from '../lib/registryApi'
import { listAutomationRuns, getSummary, GlobalSummary } from '../lib/reportsApi'
import { FlaskConical, Package, Wand2, CheckCheck, TriangleAlert, Database, Shield, ArrowRight, Upload, Layers } from 'lucide-react'

function mapRunStatus(s: string): RunStatus {
  const m: Record<string, RunStatus> = {
    done: 'completed', completed: 'completed',
    processing: 'running', running: 'running',
    queued: 'pending', pending: 'pending',
    failed: 'failed', parsing: 'parsing',
  }
  return m[s] ?? 'pending'
}

function StatCard({ label, value, icon: Icon, trend, trendUp, sub, alert }: {
  label: string; value: string; icon: React.ElementType
  trend?: string; trendUp?: boolean; sub?: string; alert?: boolean
}) {
  return (
    <div className="card pad flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div className="w-10 h-10 rounded-xl flex items-center justify-center"
          style={{ background: alert ? 'color-mix(in oklch, #f43f5e 12%, var(--card))' : 'color-mix(in oklch, var(--brand) 12%, var(--card))', color: alert ? '#f43f5e' : 'var(--brand)' }}>
          <Icon className="w-5 h-5" />
        </div>
        {trend && <span className={`text-xs font-semibold ${trendUp ? 'text-emerald-600' : 'text-rose-600'}`}>{trend}</span>}
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
  const today = new Date().toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' })

  // Real data state — start empty, fill from API
  const [recentRuns, setRecentRuns] = useState<RecentRun[]>([])
  const [recentAutos, setRecentAutos] = useState<RecentAutomation[]>([])
  const [summary, setSummary] = useState<GlobalSummary | null>(null)
  const [totalAnalysisRuns, setTotalAnalysisRuns] = useState<number | null>(null)

  useEffect(() => {
    // Load global summary (KPIs + alerts)
    getSummary().then(setSummary).catch(() => {})

    // Load recent analysis runs
    listRuns({ limit: 5 }).then(data => {
      setTotalAnalysisRuns(data.total)
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

    // Load recent automation runs — backend returns { items: [...] }
    listAutomationRuns({ limit: 5 }).then(data => {
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
  }, [])

  const runningCount = summary?.status_breakdown?.['running'] ?? 0
  const kpis = [
    { label: 'Analysis runs',        value: totalAnalysisRuns != null ? totalAnalysisRuns.toLocaleString() : '—', icon: FlaskConical, trend: '+8 this week', trendUp: true, sub: '5 in last 24h' },
    { label: 'Endpoints catalogued', value: recentRuns.length > 0 ? recentRuns.reduce((s, r) => s + r.endpoints, 0).toLocaleString() : '—', icon: Package, trend: '+22', trendUp: true, sub: 'across latest runs' },
    { label: 'Automation runs',      value: summary ? summary.total_automation_runs.toLocaleString() : '—', icon: Wand2, trend: '+218 today', trendUp: true, sub: runningCount > 0 ? `${runningCount} en cours` : 'aucun en cours' },
    { label: 'Global success rate',  value: summary ? `${(summary.global_success_rate * 100).toFixed(1)}%` : '—', icon: CheckCheck, trend: '+0.6pp', trendUp: true, sub: '30-day rolling' },
  ]
  const alerts = [
    { label: 'Failed executions', value: summary ? summary.total_failed.toLocaleString() : '—', icon: TriangleAlert, trend: summary ? `${summary.total_failed} au total` : '', alert: true },
    { label: 'Index endpoints',   value: 'Synced', icon: Database, sub: '312 endpoints · 4 min ago' },
    { label: 'Current role',      value: 'Admin',  icon: Shield,   sub: 'Permissions resolved' },
  ]

  return (
    <AppLayout>
      <div className="p-6 space-y-6">
        {/* Greeting */}
        <div className="flex items-end justify-between gap-4 flex-wrap">
          <div>
            <p className="text-xs font-semibold tracking-wider uppercase ink-2">{today}</p>
            <h1 className="text-2xl font-black mt-0.5" style={{ color: 'var(--ink)' }}>
              Good morning, <span className="grad-text">Aria</span>
            </h1>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => nav('/analysis')} className="btn-secondary"><Upload className="w-4 h-4" /> Upload HAR</button>
            <button onClick={() => nav('/bulk')} className="btn-primary"><Layers className="w-4 h-4" /> Open bulk run</button>
          </div>
        </div>

        {/* Hero strip */}
        <div className="card overflow-hidden">
          <div className="p-5 flex items-center justify-between gap-4 flex-wrap aria-hero">
            <div className="space-y-2 max-w-xl">
              <span className="pill" style={{ background: 'var(--card)', borderColor: 'var(--line)', color: 'var(--ink-2)' }}>
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                Automation Bulk #001 en cours d&apos;exécution
              </span>
              <p className="text-xl font-black" style={{ color: 'var(--ink)' }}>
                <span className="grad-text">1,200 employee onboardings</span> in progress
              </p>
              <p className="text-sm ink-2">Batch 6 of 12 · 524 / 1,178 rows succeeded · 7 failed · est. 4 min remaining</p>
              <div className="w-full h-2 rounded-full" style={{ background: 'var(--line)' }}>
                <div className="h-2 rounded-full grad-bg" style={{ width: '44%' }} />
              </div>
            </div>
          </div>
        </div>

        {/* KPIs */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {kpis.map((k, i) => <StatCard key={i} {...k} />)}
        </div>

        {/* Charts */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="lg:col-span-2 card pad">
            <p className="text-sm font-bold" style={{ color: 'var(--ink)' }}>Volume d&apos;exécution · 7 derniers jours</p>
            <p className="text-xs ink-2 mt-0.5 mb-4">Étapes réussies vs échouées</p>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={SUCCESS_TIMELINE} barGap={2}>
                <CartesianGrid strokeDasharray="3 3" stroke="color-mix(in oklch, var(--line) 80%, transparent)" />
                <XAxis dataKey="day" tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={{ borderRadius: 12, fontSize: 12, background: 'var(--card)', border: '1px solid var(--line)', color: 'var(--ink)' }} />
                <Bar dataKey="success" name="Succès" fill="oklch(0.585 0.205 277)" radius={[4, 4, 0, 0]} />
                <Bar dataKey="failed" name="Échecs" fill="#f87171" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="card pad">
            <p className="text-sm font-bold" style={{ color: 'var(--ink)' }}>Codes HTTP</p>
            <p className="text-xs ink-2 mt-0.5 mb-5">7 derniers jours · 4 410 requêtes</p>
            <div className="space-y-4">
              {STATUS_BREAKDOWN.map(s => (
                <div key={s.label}>
                  <div className="flex justify-between text-xs mb-1.5">
                    <span className="font-semibold" style={{ color: 'var(--ink)' }}>{s.label}</span>
                    <span className="font-mono ink-2">{s.value.toLocaleString()}</span>
                  </div>
                  <div className="h-2 rounded-full" style={{ background: 'var(--line)' }}>
                    <div className="h-2 rounded-full grad-bg" style={{ width: `${s.pct}%` }} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Alert strip */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {alerts.map((a, i) => <StatCard key={i} {...a} />)}
        </div>

        {/* Tables — wired to real API */}
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
                  <tr><td colSpan={4} className="px-4 py-8 text-center ink-2 text-sm">No runs yet</td></tr>
                )}
                {recentRuns.map((r, i) => (
                  <tr key={r.id} className="border-t cursor-pointer transition" style={{ borderColor: 'var(--line)' }}
                    onMouseEnter={e => (e.currentTarget.style.background = 'color-mix(in oklch, var(--brand) 4%, var(--card))')}
                    onMouseLeave={e => (e.currentTarget.style.background = '')}
                    onClick={() => nav('/endpoints')}>
                    <td className="px-4 py-2.5">
                      <p className="font-semibold" style={{ color: 'var(--ink)' }}>Analyse #{String(i + 1).padStart(3, '0')}</p>
                      <p className="text-xs ink-2 truncate max-w-[160px]">{r.name}</p>
                    </td>
                    <td className="px-4 py-2.5"><span className="pill" style={{ background: 'color-mix(in oklch, var(--ink) 4%, var(--card))', borderColor: 'var(--line)', color: 'var(--ink-2)' }}>{r.source}</span></td>
                    <td className="px-4 py-2.5"><StatusBadge s={r.status} /></td>
                    <td className="px-4 py-2.5 font-mono text-sm font-bold text-right" style={{ color: 'var(--ink)' }}>{r.endpoints}</td>
                  </tr>
                ))}
              </tbody>
            </table>
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
                  <tr><td colSpan={4} className="px-4 py-8 text-center ink-2 text-sm">No runs yet</td></tr>
                )}
                {recentAutos.map((r, i) => (
                  <tr key={r.id} className="border-t cursor-pointer transition" style={{ borderColor: 'var(--line)' }}
                    onMouseEnter={e => (e.currentTarget.style.background = 'color-mix(in oklch, var(--brand) 4%, var(--card))')}
                    onMouseLeave={e => (e.currentTarget.style.background = '')}
                    onClick={() => nav('/bulk')}>
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-2">
                        <p className="font-semibold" style={{ color: 'var(--ink)' }}>#{String(i + 1).padStart(3, '0')}</p>
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
          </div>
        </div>
      </div>
    </AppLayout>
  )
}
