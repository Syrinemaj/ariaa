import { useEffect, useState } from 'react'
import AppLayout from '../components/layout/AppLayout'
import { listAuditLogs, AuditLogEntry } from '../lib/reportsApi'
import { actionColor, formatAction } from '../lib/auditFormat'
import { ScrollText, Search, RefreshCw } from 'lucide-react'

const PAGE_SIZE = 25

const RESOURCE_TYPES = ['user', 'team', 'workflow', 'analysis_run', 'automation_run']

export default function AuditLogPage() {
  const [logs, setLogs] = useState<AuditLogEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)

  const [actionFilter, setActionFilter] = useState('')
  const [resourceFilter, setResourceFilter] = useState('')

  const load = () => {
    setLoading(true)
    listAuditLogs({
      page,
      page_size: PAGE_SIZE,
      action: actionFilter.trim() || undefined,
      resource_type: resourceFilter || undefined,
    })
      .then(data => {
        setLogs(data.items)
        setTotal(data.total)
        setTotalPages(data.total_pages)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [page, actionFilter, resourceFilter])

  const formatDate = (iso: string | null) => {
    if (!iso) return '—'
    const d = new Date(iso)
    return d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
  }

  return (
    <AppLayout>
      <div className="p-6 space-y-6">
        <div className="flex items-end justify-between gap-4 flex-wrap">
          <div>
            <h2 className="text-xl font-black flex items-center gap-2" style={{ color: 'var(--ink)' }}>
              <ScrollText className="w-5 h-5" style={{ color: 'var(--brand)' }} /> Audit log
            </h2>
            <p className="text-sm mt-1 ink-2">Who did what, when, and on which resource — {total.toLocaleString()} entries.</p>
          </div>
          <button onClick={load} className="btn-secondary">
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} /> Refresh
          </button>
        </div>

        <div className="card overflow-hidden">
          <div className="p-4 flex flex-wrap items-center gap-3" style={{ borderBottom: '1px solid var(--line)' }}>
            <div className="relative flex-1 min-w-[220px]">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--ink-2)' }} />
              <input
                value={actionFilter}
                onChange={e => { setPage(1); setActionFilter(e.target.value) }}
                className="input !pl-9"
                placeholder="Filter by exact action, e.g. USER_DELETED…"
                autoComplete="off"
              />
            </div>
            <select
              value={resourceFilter}
              onChange={e => { setPage(1); setResourceFilter(e.target.value) }}
              className="input !w-auto"
            >
              <option value="">All resource types</option>
              {RESOURCE_TYPES.map(rt => <option key={rt} value={rt}>{rt}</option>)}
            </select>
            <span className="text-xs font-mono ink-2 ml-auto">{logs.length} / {total}</span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="aria-thead">
                <tr>
                  {['When', 'Who', 'Action', 'Resource', 'Details'].map(h => (
                    <th key={h} className="text-left px-4 py-2.5">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {loading && (
                  <tr><td colSpan={5} className="px-4 py-10 text-center text-sm ink-2">Loading…</td></tr>
                )}
                {!loading && logs.length === 0 && (
                  <tr><td colSpan={5} className="px-4 py-10 text-center text-sm ink-2">No audit entries match these filters.</td></tr>
                )}
                {logs.map(log => (
                  <tr key={log.id} className="border-t" style={{ borderColor: 'var(--line)' }}>
                    <td className="px-4 py-2.5 text-xs whitespace-nowrap" style={{ color: 'var(--ink)' }}>
                      {formatDate(log.created_at)}
                    </td>
                    <td className="px-4 py-2.5">
                      {log.user_email ? (
                        <>
                          <p className="text-xs font-semibold" style={{ color: 'var(--ink)' }}>{log.user_name || log.user_email}</p>
                          <p className="text-[11px] ink-2">{log.user_email}</p>
                        </>
                      ) : (
                        <span className="text-xs ink-2 italic">System / unknown</span>
                      )}
                    </td>
                    <td className="px-4 py-2.5">
                      <span className="text-xs font-bold font-mono capitalize" style={{ color: actionColor(log.action) }}>
                        {formatAction(log.action)}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-xs font-mono ink-2">
                      {log.resource_type ? (
                        <>
                          {log.resource_type}
                          {log.resource_id && <span className="ink-2"> · {log.resource_id.slice(0, 8)}…</span>}
                        </>
                      ) : '—'}
                    </td>
                    <td className="px-4 py-2.5 text-xs font-mono ink-2 max-w-[260px] truncate" title={JSON.stringify(log.metadata)}>
                      {log.metadata && Object.keys(log.metadata).length > 0
                        ? Object.entries(log.metadata).map(([k, v]) => `${k}: ${v}`).join(' · ')
                        : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <div className="flex items-center justify-between px-4 py-2.5" style={{ borderTop: '1px solid var(--line)' }}>
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="text-xs font-semibold px-2.5 py-1.5 rounded-lg transition disabled:opacity-40 disabled:cursor-not-allowed hover:opacity-70"
                style={{ color: 'var(--ink-2)' }}
              >
                ← Prev
              </button>
              <span className="text-xs ink-2">Page {page} / {totalPages}</span>
              <button
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="text-xs font-semibold px-2.5 py-1.5 rounded-lg transition disabled:opacity-40 disabled:cursor-not-allowed hover:opacity-70"
                style={{ color: 'var(--ink-2)' }}
              >
                Next →
              </button>
            </div>
          )}
        </div>
      </div>
    </AppLayout>
  )
}
