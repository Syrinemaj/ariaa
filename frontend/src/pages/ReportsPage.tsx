import { useState, useEffect } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area } from 'recharts'
import AppLayout from '../components/layout/AppLayout'
import { StatusBadge } from '../components/aria/Badges'
import { listAutomationRuns, getSummary, getDailyTrend, getAutomationReport, getAnalysisReport, GlobalSummary, AutomationExecutionReport, AnalysisRunReport, DailyTrendPoint } from '../lib/reportsApi'
import { listRuns } from '../lib/registryApi'
import { Wand2, FlaskConical, ChevronDown } from 'lucide-react'


type RunOption = { id: string; label: string }

function MiniStat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="card p-3">
      <p className="text-[10px] font-bold tracking-widest uppercase ink-2">{label}</p>
      <p className={`text-xl font-black mt-1 ${color ?? ''}`} style={!color ? { color: 'var(--ink)' } : {}}>{value}</p>
    </div>
  )
}

function RunSelector({ icon: Icon, options, value, onChange }: {
  icon: React.ElementType; options: RunOption[]
  value: string; onChange: (v: string) => void
}) {
  return (
    <div className="card overflow-hidden mb-4">
      <div className="p-4 lg:p-5">
        <p className="text-[10px] font-bold tracking-widest uppercase ink-2 mb-1.5">Run name</p>
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl grad-bg flex items-center justify-center flex-shrink-0">
            <Icon className="w-[18px] h-[18px] text-white" />
          </div>
          <div className="relative flex-1">
            <select value={value} onChange={e => onChange(e.target.value)} className="input pr-9 appearance-none cursor-pointer">
              {options.map(o => <option key={o.id} value={o.id}>{o.label}</option>)}
            </select>
            <ChevronDown className="w-4 h-4 absolute right-3 top-1/2 -translate-y-1/2 ink-2 pointer-events-none" />
          </div>
        </div>
      </div>
    </div>
  )
}

function GlobalTab({ summary, dailyTrend }: { summary: GlobalSummary | null; dailyTrend: DailyTrendPoint[] }) {
  const totalAutos  = summary?.total_automation_runs ?? 0
  const totalSteps  = summary?.total_steps ?? 0
  const successRate = summary ? summary.global_success_rate * 100 : 0
  const errorRate   = summary ? (1 - summary.global_success_rate) * 100 : 0
  const totalSuc    = summary?.total_success ?? 0
  const totalFail   = summary?.total_failed ?? 0

  const statusEntries = Object.entries(summary?.status_breakdown ?? {})
  const statusTotal = statusEntries.reduce((sum, [, count]) => sum + count, 0)

  const midIdx = Math.floor(dailyTrend.length / 2)
  const trendData = dailyTrend.map((d, i) => ({
    value: d.count,
    label: (i === 0 || i === midIdx || i === dailyTrend.length - 1)
      ? new Date(d.date).toLocaleDateString('en-US', { day: 'numeric', month: 'short' })
      : '',
  }))
  const peak = dailyTrend.reduce((max, d) => d.count > max.count ? d : max, { date: '', count: 0 })
  const peakLabel = peak.count > 0
    ? `peak: ${peak.count} on ${new Date(peak.date).toLocaleDateString('en-US', { day: 'numeric', month: 'long' })}`
    : 'no activity in this period'

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <MiniStat label="Total automations"      value={totalAutos.toLocaleString()} />
        <MiniStat label="Total steps executed"   value={totalSteps.toLocaleString()} />
        <MiniStat label="Success rate"           value={`${successRate.toFixed(1)}%`} color="text-emerald-600" />
        <MiniStat label="Error rate"             value={`${errorRate.toFixed(1)}%`}   color="text-rose-600" />
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="card pad">
          <p className="text-sm font-bold mb-1" style={{ color: 'var(--ink)' }}>Success vs failures</p>
          <p className="text-xs ink-2 mb-4">since the beginning · {totalSteps.toLocaleString()} steps</p>
          <p className="text-4xl font-black grad-text mb-1">{successRate.toFixed(1)}%</p>
          <p className="text-xs ink-2">of steps succeeded</p>
          <div className="mt-4 h-3 rounded-full overflow-hidden flex" style={{ background: 'var(--line)' }}>
            <div className="h-3 grad-bg" style={{ width: `${successRate}%` }} />
          </div>
          <div className="flex justify-between mt-1 text-xs ink-2"><span>{totalSuc.toLocaleString()} succeeded</span><span>{totalFail.toLocaleString()} failed</span></div>
        </div>
        <div className="card pad">
          <p className="text-sm font-bold mb-4" style={{ color: 'var(--ink)' }}>Automations by status</p>
          {statusEntries.length === 0 && <p className="text-xs ink-2">No automations yet.</p>}
          {statusEntries.map(([status, count]) => (
            <div key={status} className="mb-3">
              <div className="flex justify-between items-center text-xs mb-1">
                <StatusBadge s={status} />
                <span className="font-mono ink-2">{count.toLocaleString()}</span>
              </div>
              <div className="h-2 rounded-full overflow-hidden" style={{ background: 'var(--line)' }}>
                <div className="h-2 rounded-full grad-bg" style={{ width: `${statusTotal > 0 ? (count / statusTotal) * 100 : 0}%` }} />
              </div>
            </div>
          ))}
        </div>
      </div>
      <div className="card pad">
        <p className="text-sm font-bold mb-1" style={{ color: 'var(--ink)' }}>Automations · last 30 days</p>
        <p className="text-xs ink-2 mb-4">{peakLabel}</p>
        <ResponsiveContainer width="100%" height={200}>
          <AreaChart data={trendData}>
            <defs>
              <linearGradient id="grad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#dc2626" stopOpacity={0.15} />
                <stop offset="95%" stopColor="#dc2626" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="color-mix(in oklch, var(--line) 80%, transparent)" />
            <XAxis dataKey="label" tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
            <Tooltip contentStyle={{ borderRadius: 12, fontSize: 12, background: 'var(--card)', border: '1px solid var(--line)', color: 'var(--ink)' }} />
            <Area type="monotone" dataKey="value" stroke="#dc2626" strokeWidth={2} fill="url(#grad)" />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

function AutomationTab({ options, initialRunId }: { options: RunOption[]; initialRunId?: string }) {
  const [autoRunId, setAutoRunId] = useState(options[0]?.id ?? '')
  const [report, setReport] = useState<AutomationExecutionReport | null>(null)

  useEffect(() => {
    if (options.length === 0) return
    if (!autoRunId) {
      const target = initialRunId && options.some(o => o.id === initialRunId) ? initialRunId : options[0].id
      setAutoRunId(target)
    }
  }, [options])

  useEffect(() => {
    if (!autoRunId) return
    setReport(null)
    getAutomationReport(autoRunId).then(setReport).catch(() => {})
  }, [autoRunId])

  const successRate = report ? report.success_rate * 100 : 0
  const errorRate   = report ? report.error_rate * 100 : 0
  const duration    = report?.duration_seconds ?? 0
  const durationStr = duration > 0 ? `${Math.floor(duration / 60)}m ${Math.floor(duration % 60)}s` : '—'
  const throughput  = duration > 0 && report ? (report.total_steps / duration).toFixed(1) : '—'
  const logs = (report?.logs ?? []).slice(0, 8).map(l => ({
    t: '—',
    s: `${l.method.toLowerCase()}.${l.path.split('/').filter(Boolean).slice(-1)[0] ?? l.path}`,
    c: l.status_code != null ? String(l.status_code) : '—',
    m: l.error_message ?? (l.status === 'succeeded' ? 'success' : l.status),
    err: l.status === 'failed',
  }))

  return (
    <>
      <RunSelector icon={Wand2} options={options.length > 0 ? options : [{ id: '', label: 'Loading…' }]} value={autoRunId} onChange={setAutoRunId} />
      <div className="card pad">
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-5">
          <MiniStat label="Success rate" value={report ? `${successRate.toFixed(1)}%` : '—'} color="text-emerald-600" />
          <MiniStat label="Error rate"     value={report ? `${errorRate.toFixed(1)}%` : '—'}   color="text-rose-600" />
          <MiniStat label="Duration"       value={durationStr} />
          <MiniStat label="Steps"          value={report ? report.total_steps.toLocaleString() : '—'} />
          <MiniStat label="Throughput"     value={throughput !== '—' ? `${throughput}/s` : '—'} />
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_1.4fr] gap-5">
          <div>
            <p className="text-sm font-bold mb-1" style={{ color: 'var(--ink)' }}>Success vs failures</p>
            <p className="text-xs ink-2 mb-4">out of {report ? report.total_steps.toLocaleString() : '—'} steps executed</p>
            <p className="text-4xl font-black grad-text mb-1">{report ? `${successRate.toFixed(1)}%` : '—'}</p>
            <p className="text-xs ink-2">{report ? report.success_count.toLocaleString() : '—'} steps succeeded</p>
            <div className="mt-4 h-3 rounded-full overflow-hidden flex" style={{ background: 'var(--line)' }}>
              <div className="h-3 grad-bg" style={{ width: `${successRate}%` }} />
              <div className="h-3 bg-rose-400 flex-1" />
            </div>
          </div>
          <div>
            <p className="text-sm font-bold mb-3" style={{ color: 'var(--ink)' }}>Logs · {logs.length > 0 ? `${logs.length} most recent events` : 'no logs'}</p>
            <div className="rounded-xl overflow-hidden max-h-64 overflow-y-auto" style={{ border: '1px solid var(--line)' }}>
              <table className="w-full text-sm">
                <thead className="aria-thead sticky top-0">
                  <tr>{['Time', 'Step', 'Code', 'Message'].map(h => <th key={h} className="text-left px-3 py-2">{h}</th>)}</tr>
                </thead>
                <tbody className="font-mono text-xs">
                  {logs.length === 0 && (
                    <tr><td colSpan={4} className="px-3 py-6 text-center ink-2">No logs available</td></tr>
                  )}
                  {logs.map((l, i) => (
                    <tr key={i} className="border-t" style={{ borderColor: 'var(--line)' }}>
                      <td className="px-3 py-2 ink-2">{l.t}</td>
                      <td className="px-3 py-2" style={{ color: 'var(--ink)' }}>{l.s}</td>
                      <td className={`px-3 py-2 font-bold ${l.err ? 'text-rose-600' : 'text-emerald-600'}`}>{l.c}</td>
                      <td className="px-3 py-2 ink-2">{l.m}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </>
  )
}

function AnalysisTab({ options, initialRunId }: { options: RunOption[]; initialRunId?: string }) {
  const [runId, setRunId] = useState(options[0]?.id ?? '')
  const [report, setReport] = useState<AnalysisRunReport | null>(null)

  useEffect(() => {
    if (options.length === 0) return
    if (!runId) {
      const target = initialRunId && options.some(o => o.id === initialRunId) ? initialRunId : options[0].id
      setRunId(target)
    }
  }, [options])

  useEffect(() => {
    if (!runId) return
    setReport(null)
    getAnalysisReport(runId).then(setReport).catch(() => {})
  }, [runId])

  const avgRate = report ? (report.average_success_rate * 100).toFixed(1) : '—'

  return (
    <>
      <RunSelector icon={FlaskConical} options={options.length > 0 ? options : [{ id: '', label: 'Loading…' }]} value={runId} onChange={setRunId} />
      <div className="card pad">
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <MiniStat label="Total automations" value={report ? report.total_automation_runs.toLocaleString() : '—'} />
          <MiniStat label="Total steps"       value={report ? report.total_steps.toLocaleString() : '—'} />
          <MiniStat label="Success"           value={report ? report.total_success.toLocaleString() : '—'} color="text-emerald-600" />
          <MiniStat label="Failures"          value={report ? report.total_failed.toLocaleString() : '—'}  color="text-rose-600" />
          <MiniStat label="Average rate"      value={report ? `${avgRate}%` : '—'} />
        </div>
      </div>
    </>
  )
}

export default function ReportsPage() {
  const [searchParams] = useSearchParams()
  const nav = useNavigate()
  const [tab, setTab] = useState<'global' | 'automation' | 'analysis'>(() => {
    const t = searchParams.get('tab')
    if (t === 'automation' || t === 'analysis') return t
    return 'global'
  })
  const initialRunId = searchParams.get('run') ?? undefined
  const fromBulk = searchParams.has('tab') && searchParams.has('run')
  const [autoRunOptions, setAutoRunOptions] = useState<RunOption[]>([])
  const [runOptions, setRunOptions]         = useState<RunOption[]>([])
  const [summary, setSummary]               = useState<GlobalSummary | null>(null)
  const [dailyTrend, setDailyTrend]         = useState<DailyTrendPoint[]>([])

  const TABS = [
    { key: 'global',     label: "Overview" },
    { key: 'automation', label: 'Automation report' },
    { key: 'analysis',   label: "Analysis report" },
  ] as const

  // Fetch real run options for selectors + global summary
  useEffect(() => {
    getSummary().then(setSummary).catch(() => {})
    getDailyTrend(30).then(setDailyTrend).catch(() => {})

    listAutomationRuns({ limit: 50 })
      .then(data => {
        if (data.items.length > 0)
          setAutoRunOptions(data.items.map(r => ({ id: r.id, label: r.workflow_name })))
      })
      .catch(() => {})

    listRuns({ limit: 50 })
      .then(data => {
        if (data.items.length > 0)
          setRunOptions(data.items.map(r => ({ id: r.id, label: r.file_name })))
      })
      .catch(() => {})
  }, [])

  return (
    <AppLayout>
      <div className="p-6 space-y-6">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h2 className="text-xl font-black" style={{ color: 'var(--ink)' }}>Reports</h2>
            <p className="text-sm ink-2 mt-1">Aggregated metrics across all analyses and automations.</p>
          </div>
          {fromBulk && (
            <button onClick={() => nav(-1)} className="btn-ghost text-xs">
              ← Back
            </button>
          )}
        </div>

        {/* Context header when navigating from Bulk */}
        {fromBulk && initialRunId && tab === 'automation' && (
          <div className="card pad flex items-center gap-4"
            style={{ background: 'color-mix(in oklch, var(--brand) 5%, var(--card))', border: '1px solid color-mix(in oklch, var(--brand) 20%, var(--line))' }}>
            <div className="flex-1 min-w-0">
              <p className="text-[10px] font-bold tracking-widest uppercase" style={{ color: 'var(--brand)' }}>Execution report</p>
              <p className="text-sm font-semibold mt-0.5" style={{ color: 'var(--ink)' }}>
                {autoRunOptions.find(o => o.id === initialRunId)?.label ?? initialRunId.slice(0, 8)}
              </p>
            </div>
            <button onClick={() => nav('/bulk')} className="btn-secondary text-xs">Re-run</button>
          </div>
        )}

        <div className="flex gap-1 rounded-xl p-1 w-fit" style={{ background: 'color-mix(in oklch, var(--ink) 5%, var(--card))', border: '1px solid var(--line)' }}>
          {TABS.map(t => (
            <button key={t.key} onClick={() => setTab(t.key)}
              className="px-4 py-2 rounded-lg text-sm font-semibold transition"
              style={{
                background: tab === t.key ? 'var(--card)' : 'transparent',
                color: tab === t.key ? 'var(--ink)' : 'var(--ink-2)',
                boxShadow: tab === t.key ? '0 1px 3px rgba(0,0,0,0.08)' : 'none',
              }}>
              {t.label}
            </button>
          ))}
        </div>
        {tab === 'global'     && <GlobalTab summary={summary} dailyTrend={dailyTrend} />}
        {tab === 'automation' && <AutomationTab options={autoRunOptions} initialRunId={initialRunId} />}
        {tab === 'analysis'   && <AnalysisTab options={runOptions} initialRunId={initialRunId} />}
      </div>
    </AppLayout>
  )
}
