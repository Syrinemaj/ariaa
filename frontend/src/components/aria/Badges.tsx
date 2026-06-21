import type { Risk, Role } from '../../lib/aria-data'
import { ROLES } from '../../lib/aria-data'

const METHOD_CLS: Record<string, string> = {
  GET:    'bg-emerald-50 text-emerald-700 border-emerald-200',
  POST:   'bg-indigo-50 text-indigo-700 border-indigo-200',
  PUT:    'bg-amber-50 text-amber-700 border-amber-200',
  PATCH:  'bg-violet-50 text-violet-700 border-violet-200',
  DELETE: 'bg-rose-50 text-rose-700 border-rose-200',
}
const RISK_CLS: Record<Risk, string> = {
  low:      'bg-emerald-50 text-emerald-700 border-emerald-200',
  medium:   'bg-amber-50 text-amber-700 border-amber-200',
  high:     'bg-orange-50 text-orange-700 border-orange-200',
  critical: 'bg-rose-50 text-rose-700 border-rose-200',
}
const STATUS_CLS: Record<string, string> = {
  completed: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  running:   'bg-blue-50 text-blue-700 border-blue-200',
  pending:   'bg-slate-50 text-slate-600 border-slate-200',
  failed:    'bg-rose-50 text-rose-700 border-rose-200',
  parsing:   'bg-amber-50 text-amber-700 border-amber-200',
  active:    'bg-emerald-50 text-emerald-700 border-emerald-200',
  rejected:  'bg-rose-50 text-rose-700 border-rose-200',
}
const STATUS_DOT: Record<string, string> = {
  completed: 'bg-emerald-500',
  running:   'bg-blue-500 animate-pulse',
  pending:   'bg-slate-400',
  failed:    'bg-rose-500',
  parsing:   'bg-amber-500',
  active:    'bg-emerald-500',
  rejected:  'bg-rose-500',
}

export function MethodBadge({ m }: { m: string }) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-xs font-mono font-bold border ${METHOD_CLS[m] ?? 'bg-slate-50 text-slate-600 border-slate-200'}`}>
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
