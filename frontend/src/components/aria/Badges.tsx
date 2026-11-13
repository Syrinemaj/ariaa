import type { Risk, Role } from '../../lib/aria-data'
import { ROLES } from '../../lib/aria-data'

const METHOD_SWATCH: Record<string, string> = {
  GET:    '#10b981',
  POST:   '#6366f1',
  PUT:    '#f59e0b',
  PATCH:  '#8b5cf6',
  DELETE: '#f43f5e',
}
const RISK_CLS: Record<Risk, string> = {
  low:      'bg-emerald-50 text-emerald-700 border-emerald-200',
  medium:   'bg-amber-50 text-amber-700 border-amber-200',
  high:     'bg-orange-50 text-orange-700 border-orange-200',
  critical: 'bg-rose-50 text-rose-700 border-rose-200',
}
const STATUS_CLS: Record<string, string> = {
  completed:        'bg-emerald-50 text-emerald-700 border-emerald-200',
  running:          'bg-blue-50 text-blue-700 border-blue-200',
  pending:          'bg-slate-50 text-slate-600 border-slate-200',
  failed:           'bg-rose-50 text-rose-700 border-rose-200',
  parsing:          'bg-amber-50 text-amber-700 border-amber-200',
  active:           'bg-emerald-50 text-emerald-700 border-emerald-200',
  approved:         'bg-emerald-50 text-emerald-700 border-emerald-200',
  rejected:         'bg-rose-50 text-rose-700 border-rose-200',
  cancelling:       'bg-amber-50 text-amber-700 border-amber-200',
  cancelled:        'bg-slate-50 text-slate-600 border-slate-200',
  // AutomationRun statuses (app/models/automation.py) — distinct vocabulary
  // from the bulk-job statuses above (completed/cancelled/...), surfaced on
  // the Reports page's status breakdown and run picker.
  success:          'bg-emerald-50 text-emerald-700 border-emerald-200',
  done:             'bg-emerald-50 text-emerald-700 border-emerald-200',
  partial_success:  'bg-amber-50 text-amber-700 border-amber-200',
  partial_failure:  'bg-amber-50 text-amber-700 border-amber-200',
  partial:          'bg-amber-50 text-amber-700 border-amber-200',
  queued:           'bg-slate-50 text-slate-600 border-slate-200',
}
const STATUS_DOT: Record<string, string> = {
  completed:        'bg-emerald-500',
  running:          'bg-blue-500 animate-pulse',
  pending:          'bg-slate-400',
  failed:           'bg-rose-500',
  parsing:          'bg-amber-500',
  active:           'bg-emerald-500',
  approved:         'bg-emerald-500',
  rejected:         'bg-rose-500',
  cancelling:       'bg-amber-500 animate-pulse',
  cancelled:        'bg-slate-400',
  success:          'bg-emerald-500',
  done:             'bg-emerald-500',
  partial_success:  'bg-amber-500',
  partial_failure:  'bg-amber-500',
  partial:          'bg-amber-500',
  queued:           'bg-slate-400',
}

export function MethodBadge({ m }: { m: string }) {
  const swatch = METHOD_SWATCH[m] ?? '#64748b'
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-mono font-bold border"
      style={{ color: swatch, background: `${swatch}18`, borderColor: `${swatch}40` }}>
      {m}
    </span>
  )
}

export function SeverityBadge({ s }: { s: Risk }) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${RISK_CLS[s]}`}>
      {s}
    </span>
  )
}

export function StatusBadge({ s }: { s: string }) {
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium border ${STATUS_CLS[s] ?? 'bg-slate-50 text-slate-600 border-slate-200'}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${STATUS_DOT[s] ?? 'bg-slate-400'}`} />
      {s}
    </span>
  )
}

export function RoleBadge({ role }: { role: Role }) {
  const info = ROLES[role]
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border"
      style={{ color: info.swatch, background: `${info.swatch}18`, borderColor: `${info.swatch}40` }}>
      {info.label}
    </span>
  )
}
