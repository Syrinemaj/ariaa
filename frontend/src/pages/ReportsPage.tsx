import { useState, useEffect, useMemo } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area } from 'recharts'
import AppLayout from '../components/layout/AppLayout'
import { StatusBadge } from '../components/aria/Badges'
import {
  listAutomationRuns, getSummary, getDailyTrend, getKpiTrends, getAutomationReport, getAnalysisReport,
  GlobalSummary, AutomationExecutionReport, AnalysisRunReport, DailyTrendPoint, KpiTrends, AutomationRun,
} from '../lib/reportsApi'
import { listRuns } from '../lib/registryApi'
import { FlaskConical, ChevronDown, TriangleAlert, CheckCircle2, Search, Download, ChevronLeft, ChevronRight, ArrowRight, X } from 'lucide-react'


type RunOption = { id: string; label: string }

const ATTENTION_STATUSES = new Set(['failed', 'partial_success'])
const LOGS_PAGE_SIZE = 8

function timeAgo(iso: string | null): string {
  if (!iso) return '—'
  const diffMs = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diffMs / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins} min ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days < 7) return days === 1 ? 'yesterday' : `${days}d ago`
  return new Date(iso).toLocaleDateString('en-US', { day: 'numeric', month: 'short' })
}

function successRateOf(run: AutomationRun): number {
  // Clamped: a run whose AutomationRun record was reused across an
  // approval-retry (see app/bulk_execution/service.py) keeps its original
  // total_steps instead of the recomputed rows×steps count, so success_count
  // can legitimately exceed it — shown as 100%, not a nonsensical >100%.
  return run.total_steps > 0 ? Math.min(100, (run.success_count / run.total_steps) * 100) : 0
}

// Defangs a leading =/+/-/@ (Excel/Sheets formula injection) before writing a
// CSV cell — this is client-generated from already-fetched report data, not
// server output, so the safety has to live here too.
function csvCell(value: string): string {
  const needsGuard = /^[=+\-@]/.test(value)
  const escaped = (needsGuard ? `'${value}` : value).replace(/"/g, '""')
  return `"${escaped}"`
}

function downloadCsv(filename: string, rows: string[][]) {
  const csv = rows.map(r => r.map(csvCell).join(',')).join('\r\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

function MiniStat({ label, value, color, delta }: { label: string; value: string; color?: string; delta?: { value: number; goodDirection: 'up' | 'down' } }) {
  const deltaUp = delta ? delta.value >= 0 : null
  const isGood = delta ? (delta.goodDirection === 'up' ? deltaUp : !deltaUp) : null
  return (
    <div className="card p-3">
      <p className="text-[10px] font-bold tracking-widest uppercase ink-2">{label}</p>
      <p className={`text-xl font-black mt-1 ${color ?? ''}`} style={!color ? { color: 'var(--ink)' } : {}}>{value}</p>
      {delta && Math.abs(delta.value) >= 0.05 && (
        <p className={`text-[11px] font-bold mt-0.5 ${isGood ? 'text-emerald-600' : 'text-rose-600'}`}>
          {deltaUp ? '▲' : '▼'} {Math.abs(delta.value).toFixed(1)}{delta.goodDirection === 'up' && Math.abs(delta.value) < 1 ? '' : ''} vs previous period
        </p>
      )}
    </div>
  )
}

// Per-browser "I've seen this" — not a shared/synced preference, so
// localStorage is the right place for it (same pattern as aria_theme
// elsewhere). Stores run ids, not a blanket flag, so dismissing today's
// 3 problem runs doesn't silence tomorrow's new failure — a NEW run id
// not in this set still shows the banner.
const DISMISS_KEY = 'aria_reports_attention_dismissed'

function loadDismissed(): Set<string> {
  try { return new Set(JSON.parse(localStorage.getItem(DISMISS_KEY) ?? '[]')) } catch { return new Set() }
}
function saveDismissed(ids: Set<string>) {
  try { localStorage.setItem(DISMISS_KEY, JSON.stringify([...ids])) } catch { /* ignore */ }
}

function HealthBanner({ attentionRuns, onFilterStatus }: { attentionRuns: AutomationRun[]; onFilterStatus: (s: string) => void }) {
  const [dismissed, setDismissed] = useState<Set<string>>(() => loadDismissed())
  const visible = attentionRuns.filter(r => !dismissed.has(r.id))

  if (attentionRuns.length === 0) {
    return (
      <div className="card pad flex items-center gap-4" style={{ background: 'color-mix(in oklch, #10b981 6%, var(--card))', border: '1px solid color-mix(in oklch, #10b981 25%, var(--line))' }}>
        <div className="w-10 h-10 rounded-xl bg-white flex items-center justify-center flex-shrink-0 text-emerald-600 shadow-sm"><CheckCircle2 className="w-5 h-5" /></div>
        <p className="text-sm font-bold text-emerald-700">All recent automations are healthy — nothing needs attention.</p>
      </div>
    )
  }

  // Everything currently flagged has already been marked as read — no new
  // issue since then, so stay quiet rather than re-show a stale warning.
  if (visible.length === 0) return null

  function markAsRead() {
    const next = new Set(dismissed)
    attentionRuns.forEach(r => next.add(r.id))
    setDismissed(next)
    saveDismissed(next)
  }

  const latest = visible[0]
  return (
    <div className="card pad flex items-center gap-4 flex-wrap" style={{ background: 'color-mix(in oklch, #f59e0b 6%, var(--card))', border: '1px solid color-mix(in oklch, #f59e0b 25%, var(--line))' }}>
      <div className="w-10 h-10 rounded-xl bg-white flex items-center justify-center flex-shrink-0 shadow-sm" style={{ color: '#b45309' }}><TriangleAlert className="w-5 h-5" /></div>
      <div className="flex-1 min-w-[240px]">
        <p className="text-[13px] font-black" style={{ color: '#b45309' }}>{visible.length} run{visible.length > 1 ? 's' : ''} need{visible.length === 1 ? 's' : ''} attention</p>
        <p className="text-[13px] mt-0.5 ink-2">Most recent: "{latest.workflow_name}" finished {latest.status} with {latest.failed_count} failed step(s), {timeAgo(latest.created_at)}.</p>
      </div>
      <button onClick={() => onFilterStatus(latest.status)} className="text-[13px] font-bold whitespace-nowrap" style={{ color: 'var(--brand)' }}>View all →</button>
      <button onClick={markAsRead} aria-label="Mark as read — hide this until a new run needs attention"
        className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 hover:bg-black/5 transition" style={{ color: '#b45309' }}>
        <X className="w-4 h-4" />
      </button>
    </div>
  )
}

function RunRow({ run, onClick }: { run: AutomationRun; onClick: () => void }) {
  return (
    <button onClick={onClick} className="w-full flex items-center gap-3 px-4 py-2.5 text-left hover:bg-[color-mix(in_oklch,var(--ink)_3%,var(--card))] transition">
      <StatusBadge s={run.status} />
      <span className="flex-1 min-w-0 text-[13px] font-semibold truncate" style={{ color: 'var(--ink)' }}>{run.workflow_name}</span>
      <span className="text-xs ink-2 flex-shrink-0">{successRateOf(run).toFixed(0)}% success</span>
      <span className="text-[11px] ink-2 flex-shrink-0 w-20 text-right">{timeAgo(run.created_at)}</span>
    </button>
  )
}

function GlobalTab({
  summary, dailyTrend, kpiTrends, trendWindowDays, setTrendWindowDays, attentionRuns, onFilterStatus, onViewRun,
}: {
  summary: GlobalSummary | null
  dailyTrend: DailyTrendPoint[]
  kpiTrends: KpiTrends | null
  trendWindowDays: 7 | 30 | 90
  setTrendWindowDays: (d: 7 | 30 | 90) => void
  attentionRuns: AutomationRun[]
  onFilterStatus: (s: string) => void
  onViewRun: (id: string) => void
}) {
  const totalAutos  = summary?.total_automation_runs ?? 0
  const totalSteps  = summary?.total_steps ?? 0
  const successRate = summary ? summary.global_success_rate * 100 : 0
  const errorRate   = summary ? (1 - summary.global_success_rate) * 100 : 0
  const totalSuc    = summary?.total_success ?? 0
  const totalFail   = summary?.total_failed ?? 0

  const statusEntries = Object.entries(summary?.status_breakdown ?? {})
  const statusTotal = statusEntries.reduce((sum, [, count]) => sum + count, 0)
  const STATUS_COLOR: Record<string, string> = {
    done: '#059669', success: '#059669', partial_success: '#b45309', partial_failure: '#b45309',
    failed: '#e11d48', rejected: '#e11d48', running: 'var(--ink-2)', queued: 'var(--ink-2)', cancelled: 'var(--ink-2)',
  }

  const runsDelta = kpiTrends ? kpiTrends.automation_runs.current - kpiTrends.automation_runs.previous : undefined
  const successRateDeltaPts = kpiTrends ? (kpiTrends.global_success_rate.current - kpiTrends.global_success_rate.previous) * 100 : undefined

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
      <HealthBanner attentionRuns={attentionRuns} onFilterStatus={onFilterStatus} />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <MiniStat label="Total automations" value={totalAutos.toLocaleString()}
          delta={runsDelta !== undefined ? { value: runsDelta, goodDirection: 'up' } : undefined} />
        <MiniStat label="Total steps executed" value={totalSteps.toLocaleString()} />
        <MiniStat label="Success rate" value={`${successRate.toFixed(1)}%`} color="text-emerald-600"
          delta={successRateDeltaPts !== undefined ? { value: successRateDeltaPts, goodDirection: 'up' } : undefined} />
        <MiniStat label="Error rate" value={`${errorRate.toFixed(1)}%`} color="text-rose-600"
          delta={successRateDeltaPts !== undefined ? { value: -successRateDeltaPts, goodDirection: 'down' } : undefined} />
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
          <div className="flex items-center justify-between mb-1">
            <p className="text-sm font-bold" style={{ color: 'var(--ink)' }}>Automations by status</p>
          </div>
          <p className="text-[11px] ink-2 mb-3">Click a status to filter the run list</p>
          {statusEntries.length === 0 && <p className="text-xs ink-2">No automations yet.</p>}
          {statusEntries.map(([status, count]) => (
            <button key={status} onClick={() => onFilterStatus(status)} className="block w-full text-left mb-3 last:mb-0 -mx-2 px-2 py-1 rounded-lg hover:bg-[color-mix(in_oklch,var(--ink)_3%,var(--card))] transition">
              <div className="flex justify-between items-center text-xs mb-1">
                <StatusBadge s={status} />
                <span className="font-mono ink-2">{count.toLocaleString()}</span>
              </div>
              <div className="h-2 rounded-full overflow-hidden" style={{ background: 'var(--line)' }}>
                <div className="h-2 rounded-full" style={{ width: `${statusTotal > 0 ? (count / statusTotal) * 100 : 0}%`, background: STATUS_COLOR[status] ?? 'var(--ink-2)' }} />
              </div>
            </button>
          ))}
        </div>
      </div>

      <div className="card pad">
        <div className="flex items-start justify-between gap-3 flex-wrap mb-1">
          <div>
            <p className="text-sm font-bold" style={{ color: 'var(--ink)' }}>Automations over time</p>
            <p className="text-xs ink-2 mt-0.5">{peakLabel}</p>
          </div>
          <div className="flex gap-1 rounded-lg p-0.5" style={{ background: 'color-mix(in oklch, var(--ink) 5%, var(--card))', border: '1px solid var(--line)' }}>
            {([7, 30, 90] as const).map(d => (
              <button key={d} onClick={() => setTrendWindowDays(d)}
                className="px-3 py-1.5 rounded-md text-xs font-bold transition"
                style={{
                  background: trendWindowDays === d ? 'var(--card)' : 'transparent',
                  color: trendWindowDays === d ? 'var(--ink)' : 'var(--ink-2)',
                  boxShadow: trendWindowDays === d ? '0 1px 2px rgba(0,0,0,0.08)' : 'none',
                }}>
                {d}d
              </button>
            ))}
          </div>
        </div>
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

      <div className="card pad">
        <p className="text-sm font-bold mb-3" style={{ color: 'var(--ink)' }}>Needs attention</p>
        {attentionRuns.length === 0 ? (
          <p className="text-xs ink-2">Nothing to review — every recent run succeeded.</p>
        ) : (
          <div className="rounded-xl overflow-hidden" style={{ border: '1px solid var(--line)' }}>
            {attentionRuns.map((run, i) => (
              <div key={run.id} className="flex items-center gap-3 px-4 py-3" style={i > 0 ? { borderTop: '1px solid var(--line)' } : undefined}>
                <StatusBadge s={run.status} />
                <div className="flex-1 min-w-0">
                  <p className="text-[13px] font-bold truncate" style={{ color: 'var(--ink)' }}>{run.workflow_name}</p>
                  <p className="text-xs ink-2 mt-0.5">{run.failed_count.toLocaleString()} failed step{run.failed_count === 1 ? '' : 's'} · {timeAgo(run.created_at)}</p>
                </div>
                <button onClick={() => onViewRun(run.id)} className="text-xs font-bold flex items-center gap-1 flex-shrink-0" style={{ color: 'var(--brand)' }}>
                  View report <ArrowRight className="w-3 h-3" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function AutomationTab({
  autoRuns, analysisOptions, initialRunId, statusFilter, onClearFilter,
}: {
  autoRuns: AutomationRun[]
  analysisOptions: RunOption[]
  initialRunId?: string
  statusFilter: string | null
  onClearFilter: () => void
}) {
  const [autoRunId, setAutoRunId] = useState('')
  const [report, setReport] = useState<AutomationExecutionReport | null>(null)
  const [search, setSearch] = useState('')
  const [logsPage, setLogsPage] = useState(0)

  // Analysis report, folded in here instead of its own tab: picking an
  // analysis run scopes the run list below to the automations it produced,
  // with that analysis's own aggregate stats shown above the scope picker.
  const [analysisId, setAnalysisId] = useState('')
  const [analysisReport, setAnalysisReport] = useState<AnalysisRunReport | null>(null)
  const [scopedRuns, setScopedRuns] = useState<AutomationRun[] | null>(null)

  useEffect(() => {
    if (!analysisId) { setScopedRuns(null); setAnalysisReport(null); return }
    setAnalysisReport(null)
    listAutomationRuns({ analysisRunId: analysisId, limit: 50 }).then(d => setScopedRuns(d.items)).catch(() => {})
    getAnalysisReport(analysisId).then(setAnalysisReport).catch(() => {})
  }, [analysisId])

  const sourceRuns = scopedRuns ?? autoRuns

  useEffect(() => {
    if (sourceRuns.length === 0) return
    if (initialRunId && sourceRuns.some(r => r.id === initialRunId)) { setAutoRunId(initialRunId); return }
    if (!autoRunId || !sourceRuns.some(r => r.id === autoRunId)) setAutoRunId(sourceRuns[0].id)
  }, [sourceRuns, initialRunId])

  useEffect(() => {
    if (!autoRunId) return
    setReport(null)
    setLogsPage(0)
    getAutomationReport(autoRunId).then(setReport).catch(() => {})
  }, [autoRunId])

  const filteredRuns = useMemo(() => {
    let list = sourceRuns
    if (statusFilter) list = list.filter(r => r.status === statusFilter)
    if (search.trim()) {
      const q = search.trim().toLowerCase()
      list = list.filter(r => r.workflow_name.toLowerCase().includes(q))
    }
    return list
  }, [sourceRuns, statusFilter, search])

  const successRate = report ? report.success_rate * 100 : 0
  const errorRate   = report ? report.error_rate * 100 : 0
  const duration    = report?.duration_seconds ?? 0
  const durationStr = duration > 0 ? `${Math.floor(duration / 60)}m ${Math.floor(duration % 60)}s` : '—'
  const throughput  = duration > 0 && report ? (report.total_steps / duration).toFixed(1) : '—'

  const allLogs = report?.logs ?? []
  const totalPages = Math.max(1, Math.ceil(allLogs.length / LOGS_PAGE_SIZE))
  const pageLogs = allLogs.slice(logsPage * LOGS_PAGE_SIZE, (logsPage + 1) * LOGS_PAGE_SIZE)

  function exportLogsCsv() {
    if (!report) return
    const rows: string[][] = [['time', 'step', 'code', 'message']]
    for (const l of allLogs) {
      const step = `${l.method.toLowerCase()}.${l.path.split('/').filter(Boolean).slice(-1)[0] ?? l.path}`
      const msg = l.error_message ?? (l.status === 'succeeded' ? 'success' : l.status)
      rows.push([l.created_at ?? '', step, l.status_code != null ? String(l.status_code) : '', msg])
    }
    downloadCsv(`automation_${report.automation_run_id.slice(0, 8)}_logs.csv`, rows)
  }

  return (
    <>
      <div className="card overflow-hidden mb-4">
        <div className="p-4 lg:p-5">
          <p className="text-[10px] font-bold tracking-widest uppercase ink-2 mb-1.5">Scope to analysis (optional)</p>
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl grad-bg flex items-center justify-center flex-shrink-0">
              <FlaskConical className="w-[18px] h-[18px] text-white" />
            </div>
            <div className="relative flex-1">
              <select value={analysisId} onChange={e => setAnalysisId(e.target.value)} className="input pr-9 appearance-none cursor-pointer">
                <option value="">All analyses</option>
                {analysisOptions.map(o => <option key={o.id} value={o.id}>{o.label}</option>)}
              </select>
              <ChevronDown className="w-4 h-4 absolute right-3 top-1/2 -translate-y-1/2 ink-2 pointer-events-none" />
            </div>
          </div>
          {analysisId && (
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mt-4 pt-4" style={{ borderTop: '1px solid var(--line)' }}>
              <MiniStat label="Total automations" value={analysisReport ? analysisReport.total_automation_runs.toLocaleString() : '—'} />
              <MiniStat label="Total steps"       value={analysisReport ? analysisReport.total_steps.toLocaleString() : '—'} />
              <MiniStat label="Success"           value={analysisReport ? analysisReport.total_success.toLocaleString() : '—'} color="text-emerald-600" />
              <MiniStat label="Failures"          value={analysisReport ? analysisReport.total_failed.toLocaleString() : '—'}  color="text-rose-600" />
              <MiniStat label="Average rate"      value={analysisReport ? `${(analysisReport.average_success_rate * 100).toFixed(1)}%` : '—'} />
            </div>
          )}
        </div>
      </div>

      <div className="card overflow-hidden mb-4">
        <div className="p-4 lg:p-5">
          <div className="flex items-center justify-between mb-1.5">
            <p className="text-[10px] font-bold tracking-widest uppercase ink-2">Run</p>
            {statusFilter && (
              <button onClick={onClearFilter} className="text-[11px] font-bold flex items-center gap-1" style={{ color: 'var(--brand)' }}>
                Filtered: {statusFilter} · clear ×
              </button>
            )}
          </div>
          <div className="rounded-xl overflow-hidden" style={{ border: '1px solid var(--line)' }}>
            <div className="flex items-center gap-2 px-3 py-2.5" style={{ borderBottom: '1px solid var(--line)' }}>
              <Search className="w-4 h-4 ink-2 flex-shrink-0" />
              <input
                type="text" value={search} onChange={e => setSearch(e.target.value)}
                placeholder="Search automation runs…" aria-label="Search automation runs"
                className="flex-1 text-sm bg-transparent outline-none border-none" style={{ color: 'var(--ink)' }}
              />
              <span className="text-[11px] font-bold ink-2 flex-shrink-0">{filteredRuns.length} run{filteredRuns.length !== 1 ? 's' : ''}</span>
            </div>
            <div className="max-h-44 overflow-y-auto">
              {filteredRuns.length === 0 && <p className="text-xs ink-2 px-4 py-4">No runs match.</p>}
              {filteredRuns.slice(0, 50).map(run => (
                <div key={run.id} style={run.id !== filteredRuns[0]?.id ? { borderTop: '1px solid var(--line)' } : undefined}
                  className={run.id === autoRunId ? 'bg-[color-mix(in_oklch,var(--brand)_6%,var(--card))]' : ''}>
                  <RunRow run={run} onClick={() => setAutoRunId(run.id)} />
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

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
            <div className="flex items-center justify-between mb-3">
              <p className="text-sm font-bold" style={{ color: 'var(--ink)' }}>Logs · {allLogs.length > 0 ? `${allLogs.length} events` : 'no logs'}</p>
              {allLogs.length > 0 && (
                <button onClick={exportLogsCsv} className="btn-secondary !py-1.5 !text-xs">
                  <Download className="w-3.5 h-3.5" /> Export CSV
                </button>
              )}
            </div>
            <div className="rounded-xl overflow-hidden" style={{ border: '1px solid var(--line)' }}>
              <table className="w-full text-sm">
                <thead className="aria-thead">
                  <tr>{['Time', 'Step', 'Code', 'Message'].map(h => <th key={h} className="text-left px-3 py-2">{h}</th>)}</tr>
                </thead>
                <tbody className="font-mono text-xs">
                  {pageLogs.length === 0 && (
                    <tr><td colSpan={4} className="px-3 py-6 text-center ink-2">No logs available</td></tr>
                  )}
                  {pageLogs.map((l, i) => {
                    const err = l.status === 'failed'
                    const step = `${l.method.toLowerCase()}.${l.path.split('/').filter(Boolean).slice(-1)[0] ?? l.path}`
                    const time = l.created_at ? new Date(l.created_at).toLocaleTimeString('en-US', { hour12: false }) : '—'
                    return (
                      <tr key={i} className="border-t" style={{ borderColor: 'var(--line)' }}>
                        <td className="px-3 py-2 ink-2 whitespace-nowrap">{time}</td>
                        <td className="px-3 py-2" style={{ color: 'var(--ink)' }}>{step}</td>
                        <td className={`px-3 py-2 font-bold ${err ? 'text-rose-600' : 'text-emerald-600'}`}>{l.status_code ?? '—'}</td>
                        <td className="px-3 py-2 ink-2">{l.error_message ?? (l.status === 'succeeded' ? 'success' : l.status)}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            {allLogs.length > LOGS_PAGE_SIZE && (
              <div className="flex items-center justify-between mt-2 text-xs">
                <span className="ink-2">Page {logsPage + 1} of {totalPages}</span>
                <div className="flex gap-1.5">
                  <button onClick={() => setLogsPage(p => Math.max(0, p - 1))} disabled={logsPage === 0}
                    className="btn-secondary !py-1 !px-2.5 !text-xs" style={{ opacity: logsPage === 0 ? 0.5 : 1 }}>
                    <ChevronLeft className="w-3.5 h-3.5" /> Prev
                  </button>
                  <button onClick={() => setLogsPage(p => Math.min(totalPages - 1, p + 1))} disabled={logsPage >= totalPages - 1}
                    className="btn-secondary !py-1 !px-2.5 !text-xs" style={{ opacity: logsPage >= totalPages - 1 ? 0.5 : 1 }}>
                    Next <ChevronRight className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  )
}

export default function ReportsPage() {
  const [searchParams] = useSearchParams()
  const nav = useNavigate()
  const [tab, setTab] = useState<'global' | 'automation'>(() => {
    const t = searchParams.get('tab')
    // 'analysis' no longer exists as its own tab — folded into Automation
    // report (the "Scope to analysis" picker there). Old links/bookmarks
    // with ?tab=analysis still land somewhere sensible.
    if (t === 'automation' || t === 'analysis') return 'automation'
    return 'global'
  })
  const [jumpToRunId, setJumpToRunId] = useState<string | undefined>(searchParams.get('run') ?? undefined)
  const [statusFilter, setStatusFilter] = useState<string | null>(null)
  const fromBulk = searchParams.has('tab') && searchParams.has('run')
  const [autoRuns, setAutoRuns] = useState<AutomationRun[]>([])
  const [runOptions, setRunOptions]         = useState<RunOption[]>([])
  const [summary, setSummary]               = useState<GlobalSummary | null>(null)
  const [dailyTrend, setDailyTrend]         = useState<DailyTrendPoint[]>([])
  const [trendWindowDays, setTrendWindowDays] = useState<7 | 30 | 90>(30)
  const [kpiTrends, setKpiTrends]           = useState<KpiTrends | null>(null)

  const TABS = [
    { key: 'global',     label: "Overview" },
    { key: 'automation', label: 'Automation report' },
  ] as const

  // Fetch real run options for selectors + global summary
  useEffect(() => {
    getSummary().then(setSummary).catch(() => {})

    listAutomationRuns({ limit: 50 })
      .then(data => setAutoRuns(data.items))
      .catch(() => {})

    listRuns({ limit: 50 })
      .then(data => {
        if (data.items.length > 0)
          setRunOptions(data.items.map(r => ({ id: r.id, label: r.file_name })))
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    getDailyTrend(trendWindowDays).then(setDailyTrend).catch(() => {})
    getKpiTrends(trendWindowDays).then(setKpiTrends).catch(() => {})
  }, [trendWindowDays])

  const attentionRuns = useMemo(() => (
    autoRuns
      .filter(r => ATTENTION_STATUSES.has(r.status))
      .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
      .slice(0, 3)
  ), [autoRuns])

  const autoRunOptions = useMemo(() => autoRuns.map(r => ({ id: r.id, label: r.workflow_name })), [autoRuns])

  function handleFilterStatus(status: string) {
    setStatusFilter(status)
    setTab('automation')
  }

  function handleViewRun(runId: string) {
    setJumpToRunId(runId)
    setStatusFilter(null)
    setTab('automation')
  }

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
        {fromBulk && jumpToRunId && tab === 'automation' && (
          <div className="card pad flex items-center gap-4"
            style={{ background: 'color-mix(in oklch, var(--brand) 5%, var(--card))', border: '1px solid color-mix(in oklch, var(--brand) 20%, var(--line))' }}>
            <div className="flex-1 min-w-0">
              <p className="text-[10px] font-bold tracking-widest uppercase" style={{ color: 'var(--brand)' }}>Execution report</p>
              <p className="text-sm font-semibold mt-0.5" style={{ color: 'var(--ink)' }}>
                {autoRunOptions.find(o => o.id === jumpToRunId)?.label ?? jumpToRunId.slice(0, 8)}
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
        {tab === 'global' && (
          <GlobalTab
            summary={summary} dailyTrend={dailyTrend} kpiTrends={kpiTrends}
            trendWindowDays={trendWindowDays} setTrendWindowDays={setTrendWindowDays}
            attentionRuns={attentionRuns} onFilterStatus={handleFilterStatus} onViewRun={handleViewRun}
          />
        )}
        {tab === 'automation' && (
          <AutomationTab
            autoRuns={autoRuns} analysisOptions={runOptions} initialRunId={jumpToRunId} statusFilter={statusFilter}
            onClearFilter={() => setStatusFilter(null)}
          />
        )}
      </div>
    </AppLayout>
  )
}
