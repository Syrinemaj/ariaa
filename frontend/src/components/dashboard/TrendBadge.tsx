import { TrendingUp, TrendingDown } from 'lucide-react'

// Relative change vs the previous window, or null when there's nothing to compare against.
function deltaPct(current: number, previous: number): number | null {
  if (previous === 0) return current > 0 ? null : 0
  return Math.round(((current - previous) / previous) * 1000) / 10
}

export default function TrendBadge({ current, previous }: { current: number; previous: number }) {
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
