import { useCallback, useEffect, useState } from 'react'
import AppLayout from '../components/layout/AppLayout'
import { MethodBadge, SeverityBadge, StatusBadge } from '../components/aria/Badges'
import { Approval, Method, Risk } from '../lib/aria-data'
import { listApprovals, approveApproval, rejectApproval, BackendApproval } from '../lib/approvalsApi'
import { Filter, TriangleAlert, Check, X, CheckCheck } from 'lucide-react'

// Map backend approval → UI Approval shape
function mapApproval(ba: BackendApproval): Approval {
  return {
    id:          ba.id,
    run:         ba.automation_run_id,
    workflow:    ba.run?.workflow_name ?? 'Unknown workflow',
    rows:        ba.run?.total_steps ?? 0,
    invalid:     0,
    risk:        'medium' as Risk,
    requestedBy: ba.approved_by ?? 'system',
    requestedAt: new Date(ba.created_at).toLocaleDateString('en-US'),
    methods:     ['POST'] as Method[],
    targets:     [],
  }
}

export default function ApprovalsPage() {
  const [pending, setPending]   = useState<Approval[]>([])
  const [approved, setApproved] = useState<BackendApproval[]>([])
  const [loading, setLoading]   = useState(true)
  const [modal, setModal]       = useState<{ kind: 'approve' | 'reject'; a: Approval; idx: number } | null>(null)
  const [comment, setComment]   = useState('')

  const load = useCallback(() => {
    setLoading(true)
    return Promise.all([
      listApprovals('pending').then(data => setPending(data.map(mapApproval))).catch(() => setPending([])),
      listApprovals('approved').then(data => setApproved(data)).catch(() => setApproved([])),
    ]).finally(() => setLoading(false))
  }, [])

  // Load both queues on mount
  useEffect(() => { load() }, [load])

  const approve = async (id: string) => {
    try { await approveApproval(id, comment || undefined) } catch { /* silent */ }
    setModal(null)
    void load()
  }

  const reject = async (id: string) => {
    try { await rejectApproval(id, comment || 'Rejected') } catch { /* silent */ }
    setModal(null)
    void load()
  }

  const riskBg    = (r: string) => r === 'critical' ? 'color-mix(in oklch, #f43f5e 10%, var(--card))' : r === 'high' ? 'color-mix(in oklch, #f97316 10%, var(--card))' : 'color-mix(in oklch, #f59e0b 10%, var(--card))'
  const riskColor = (r: string) => r === 'critical' ? '#f43f5e' : r === 'high' ? '#ea580c' : '#d97706'

  return (
    <AppLayout>
      <div className="p-6 space-y-6">
        <div className="flex items-end justify-between gap-4">
          <div>
            <h2 className="text-xl font-black" style={{ color: 'var(--ink)' }}>Approvals queue</h2>
            <p className="text-sm ink-2 mt-1">{pending.length} bulk run{pending.length !== 1 ? 's' : ''} awaiting your decision</p>
          </div>
          <button className="btn-secondary"><Filter className="w-4 h-4" /> Filter</button>
        </div>

        {pending.length === 0 && (
          <div className="card pad text-center py-12">
            <div className="w-12 h-12 rounded-2xl bg-emerald-50 flex items-center justify-center mx-auto mb-4">
              <Check className="w-6 h-6 text-emerald-600" />
            </div>
            <p className="font-bold" style={{ color: 'var(--ink)' }}>Nothing to approve</p>
            <p className="text-sm ink-2 mt-1">Bulk runs awaiting approval will appear here as they&apos;re submitted.</p>
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {pending.map((a, idx) => (
            <div key={a.id} className="card overflow-hidden">
              <div className="px-5 py-3 flex items-center justify-between" style={{ background: riskBg(a.risk), borderBottom: '1px solid var(--line)' }}>
                <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-widest" style={{ color: riskColor(a.risk) }}>
                  <TriangleAlert className="w-3.5 h-3.5" />{a.risk} risk
                </div>
                <span className="text-xs ink-2">{a.requestedAt}</span>
              </div>
              <div className="p-5">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="font-black text-lg" style={{ color: 'var(--ink)' }}>{a.workflow}</p>
                    <p className="text-xs ink-2 mt-1">Run #{String(idx + 1).padStart(3, '0')} · requested by <span className="font-mono">{a.requestedBy}</span></p>
                  </div>
                  <SeverityBadge s={a.risk} />
                </div>

                <div className="grid grid-cols-3 gap-3 mt-4">
                  <div>
                    <p className="text-[10px] font-bold tracking-widest uppercase ink-2">Rows</p>
                    <p className="text-xl font-black mt-0.5" style={{ color: 'var(--ink)' }}>{a.rows.toLocaleString()}</p>
                  </div>
                  <div>
                    <p className="text-[10px] font-bold tracking-widest uppercase ink-2">Invalid</p>
                    <p className={`text-xl font-black mt-0.5 ${a.invalid ? 'text-rose-600' : ''}`} style={a.invalid ? {} : { color: 'var(--ink)' }}>{a.invalid}</p>
                  </div>
                  <div>
                    <p className="text-[10px] font-bold tracking-widest uppercase ink-2">Methods</p>
                    <div className="flex gap-1 mt-1.5">{a.methods.map(m => <MethodBadge key={m} m={m} />)}</div>
                  </div>
                </div>

                <div className="hr-soft my-4" />

                <p className="text-[10px] font-bold tracking-widest uppercase ink-2 mb-2">Target endpoints</p>
                <div className="flex flex-wrap gap-1.5">
                  {a.targets.length === 0
                    ? <span className="text-xs ink-2 font-mono">—</span>
                    : a.targets.map(t => (
                        <span key={t} className="font-mono text-[11px] px-2 py-0.5 rounded-lg ink-2" style={{ border: '1px solid var(--line)' }}>{t}</span>
                      ))
                  }
                </div>

                <div className="flex items-center gap-2 mt-5">
                  <button onClick={() => { setComment(''); setModal({ kind: 'reject', a, idx }) }} className="btn-secondary flex-1 justify-center"><X className="w-4 h-4" /> Reject</button>
                  <button onClick={() => { setComment('Reviewed dry-run. Looks good.'); setModal({ kind: 'approve', a, idx }) }} className="btn-primary flex-1 justify-center"><Check className="w-4 h-4" /> Approve</button>
                </div>
              </div>
            </div>
          ))}
        </div>

        <div>
          <div className="flex items-end justify-between gap-4">
            <div>
              <h2 className="text-xl font-black" style={{ color: 'var(--ink)' }}>Approved runs</h2>
              <p className="text-sm ink-2 mt-1">{approved.length} bulk run{approved.length !== 1 ? 's' : ''} cleared for execution</p>
            </div>
          </div>

          <div className="card overflow-hidden mt-4">
            {!loading && approved.length === 0 && (
              <div className="p-12 text-center">
                <div className="w-12 h-12 rounded-2xl flex items-center justify-center mx-auto mb-4"
                  style={{ background: 'color-mix(in oklch, var(--ink) 5%, var(--card))' }}>
                  <CheckCheck className="w-6 h-6 ink-2" />
                </div>
                <p className="font-bold" style={{ color: 'var(--ink)' }}>No approved runs yet</p>
                <p className="text-sm ink-2 mt-1">Runs you approve will show up here.</p>
              </div>
            )}

            {approved.length > 0 && (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="aria-thead">
                    <tr>
                      <th className="text-left px-4 py-2.5">Workflow</th>
                      <th className="text-left px-4 py-2.5">Run status</th>
                      <th className="text-left px-4 py-2.5">Steps</th>
                      <th className="text-left px-4 py-2.5">Approved by</th>
                      <th className="text-left px-4 py-2.5">Approved at</th>
                      <th className="text-left px-4 py-2.5">Comment</th>
                    </tr>
                  </thead>
                  <tbody>
                    {approved.map(a => (
                      <tr key={a.id} className="border-t" style={{ borderColor: 'var(--line)' }}>
                        <td className="px-4 py-3">
                          <p className="font-semibold" style={{ color: 'var(--ink)' }}>{a.run?.workflow_name ?? 'Unknown workflow'}</p>
                          <p className="text-[10px] font-mono ink-2 mt-0.5">{a.automation_run_id.slice(0, 8)}…</p>
                        </td>
                        <td className="px-4 py-3">
                          <StatusBadge s={a.run?.status ?? 'unknown'} />
                        </td>
                        <td className="px-4 py-3 font-mono text-xs" style={{ color: 'var(--ink)' }}>
                          {a.run ? `${a.run.success_count}/${a.run.total_steps} ok` : '—'}
                          {a.run && a.run.failed_count > 0 && <span className="text-rose-600"> · {a.run.failed_count} failed</span>}
                        </td>
                        <td className="px-4 py-3 font-mono text-xs" style={{ color: 'var(--ink)' }}>{a.approved_by ?? '—'}</td>
                        <td className="px-4 py-3 text-xs ink-2">{a.approved_at ? new Date(a.approved_at).toLocaleString('en-US') : '—'}</td>
                        <td className="px-4 py-3 text-xs ink-2 max-w-[240px] truncate" title={a.comment ?? ''}>{a.comment ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </div>

      {modal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/50" onClick={() => setModal(null)} />
          <div className="relative card pad w-full max-w-[460px] shadow-2xl">
            <h3 className="text-lg font-black mb-1" style={{ color: 'var(--ink)' }}>
              {modal.kind === 'approve' ? 'Approve bulk run?' : 'Reject bulk run?'}
            </h3>
            <p className="text-sm ink-2 mb-4">{modal.a.workflow} · Run #{String(modal.idx + 1).padStart(3, '0')}</p>
            <p className="text-sm mb-4" style={{ color: 'var(--ink)' }}>
              This will {modal.kind === 'approve' ? 'release' : 'block'} {modal.a.rows.toLocaleString()} rows targeting {modal.a.targets.length || '—'} endpoints.
            </p>
            <div>
              <p className="text-[10px] font-bold tracking-widest uppercase ink-2 mb-1.5">Comment</p>
              <textarea rows={3} value={comment} onChange={e => setComment(e.target.value)} className="input resize-none" placeholder="Optional reason…" />
            </div>
            <div className="flex gap-2 justify-end mt-4">
              <button onClick={() => setModal(null)} className="btn-secondary">Cancel</button>
              {modal.kind === 'approve'
                ? <button onClick={() => void approve(modal.a.id)} className="btn-primary"><Check className="w-4 h-4" /> Confirm approval</button>
                : <button onClick={() => void reject(modal.a.id)} className="btn-danger"><X className="w-4 h-4" /> Confirm rejection</button>}
            </div>
          </div>
        </div>
      )}
    </AppLayout>
  )
}
