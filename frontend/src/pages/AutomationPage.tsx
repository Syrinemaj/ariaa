import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppLayout from '../components/layout/AppLayout'
import { StatusBadge } from '../components/aria/Badges'
import { listRuns, AnalysisRun } from '../lib/registryApi'
import {
  createPlan, executePlan,
  BackendPlanStep, CreatePlanResponse, ExecutePlanResponse,
} from '../lib/automationApi'
import { ApiError } from '../lib/api'
import { Connection } from '../lib/connectionsApi'
import { listApprovals } from '../lib/approvalsApi'
import ConnectionPicker from '../components/automation/ConnectionPicker'
import {
  FlaskConical, Layers, Sparkles, Play, Lock, Unlock, ChevronDown, TriangleAlert,
  AlertCircle, X, ShieldCheck, RefreshCw, CheckCircle2,
} from 'lucide-react'

// Non-interactive status tile — replaces the old self-check "Approved" toggle
// in the slot next to "Simulation mode". An operator ticking their own
// "Approved" box never meant anything real: governance decides server-side
// regardless of what the client sends (app/api/automation.py), so the old
// toggle was purely decorative and could mislead someone into thinking they
// had authorized their own risky action. This only ever displays real state.
function StatusTile({ icon, label, hint, tone }: { icon: React.ReactNode; label: string; hint: string; tone: 'muted' | 'pending' | 'approved' }) {
  const palette = tone === 'pending'
    ? { border: '#f59e0b', bg: 'color-mix(in oklch, #f59e0b 6%, var(--card))', color: '#92400e' }
    : tone === 'approved'
      ? { border: '#10b981', bg: 'color-mix(in oklch, #10b981 6%, var(--card))', color: '#047857' }
      : { border: 'var(--line)', bg: 'var(--card)', color: 'var(--ink-2)' }
  return (
    <div className="flex items-start gap-3 p-3 rounded-xl border" style={{ borderColor: palette.border, background: palette.bg }}>
      <div className="flex-shrink-0 mt-0.5" style={{ color: palette.color }}>{icon}</div>
      <div>
        <p className="text-sm font-semibold" style={{ color: 'var(--ink)' }}>{label}</p>
        <p className="text-xs" style={{ color: palette.color }}>{hint}</p>
      </div>
    </div>
  )
}

function MethodBadge({ m }: { m: string }) {
  const cls: Record<string, string> = { GET:'bg-emerald-50 text-emerald-700 border-emerald-200', POST:'bg-indigo-50 text-indigo-700 border-indigo-200', PUT:'bg-amber-50 text-amber-700 border-amber-200', PATCH:'bg-violet-50 text-violet-700 border-violet-200', DELETE:'bg-rose-50 text-rose-700 border-rose-200' }
  return <span className={`pill ${cls[m] ?? 'bg-slate-50 text-slate-600 border-slate-200'}`}>{m}</span>
}
function SeverityBadge({ s }: { s: string }) {
  const cls: Record<string, string> = { low:'bg-emerald-50 text-emerald-700 border-emerald-200', medium:'bg-amber-50 text-amber-700 border-amber-200', high:'bg-orange-50 text-orange-700 border-orange-200', critical:'bg-rose-50 text-rose-700 border-rose-200' }
  return <span className={`pill ${cls[s] ?? 'bg-slate-50 text-slate-600 border-slate-200'}`}>{s}</span>
}

function ToggleBig({ label, hint, checked, onChange, disabled }: { label: string; hint: string; checked: boolean; onChange: (v: boolean) => void; disabled?: boolean }) {
  return (
    <label className="flex items-start gap-3 p-3 rounded-xl border transition cursor-pointer"
      style={{ borderColor: checked && !disabled ? 'var(--brand)' : 'var(--line)', background: checked && !disabled ? 'color-mix(in oklch, var(--brand) 6%, var(--card))' : 'var(--card)', opacity: disabled ? 0.5 : 1, cursor: disabled ? 'not-allowed' : 'pointer' }}>
      <button onClick={() => !disabled && onChange(!checked)} className="w-9 h-5 rounded-full relative flex-shrink-0 mt-0.5 transition"
        style={{ background: checked ? 'linear-gradient(90deg, var(--brand), var(--accent))' : 'var(--line)' }}>
        <span className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform ${checked ? 'translate-x-4' : ''}`} />
      </button>
      <div>
        <p className="text-sm font-semibold" style={{ color: 'var(--ink)' }}>{label}</p>
        <p className="text-xs ink-2">{hint}</p>
      </div>
    </label>
  )
}

function PlanStep({ step }: { step: BackendPlanStep }) {
  const [open, setOpen] = useState(false)
  return (
    <li className="relative pl-10">
      <div className="absolute left-1 top-1 w-7 h-7 rounded-full grad-bg text-white text-xs font-black flex items-center justify-center ring-4" style={{ '--tw-ring-color': 'var(--card)' } as React.CSSProperties}>
        {step.order}
      </div>
      <div className="card pad !p-4">
        <div className="flex flex-wrap items-center gap-3">
          <MethodBadge m={step.method} />
          <span className="font-mono text-xs flex-1 min-w-0 truncate" style={{ color: 'var(--ink)' }}>{step.path}</span>
          <SeverityBadge s={step.risk_level} />
          {step.auth_required ? <Lock className="w-3.5 h-3.5 text-amber-500" /> : <Unlock className="w-3.5 h-3.5 text-emerald-500" />}
        </div>
        <p className="mt-2 text-sm" style={{ color: 'var(--ink)' }}>{step.action ?? '—'}</p>
        <div className="mt-1 flex items-center gap-2 text-xs ink-2 flex-wrap">
          <span>Domain: <span className="font-semibold" style={{ color: 'var(--ink)' }}>{step.business_domain ?? '—'}</span></span>
          {step.depends_on.length > 0 && <span>· Depends on step {step.depends_on.join(', ')}</span>}
        </div>
        <button onClick={() => setOpen(o => !o)} className="mt-2 text-xs ink-2 inline-flex items-center gap-1 hover:opacity-80">
          <ChevronDown className={`w-3.5 h-3.5 transition-transform ${open ? 'rotate-180' : ''}`} />
          {open ? 'Hide schemas' : 'View request/response schemas'}
        </button>
        {open && (
          <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
            {(['Request schema', 'Response schema'] as const).map(t => (
              <div key={t}>
                <p className="text-[10px] font-bold tracking-widest uppercase ink-2 mb-1.5">{t}</p>
                <pre className="rounded-xl p-3 text-xs font-mono overflow-auto max-h-[180px]"
                  style={{ background: 'color-mix(in oklch, var(--ink) 4%, var(--card))', color: 'var(--ink)', border: '1px solid var(--line)' }}>
                  {JSON.stringify(t === 'Request schema' ? (step.request_schema ?? {}) : (step.response_schema ?? {}), null, 2)}
                </pre>
              </div>
            ))}
          </div>
        )}
      </div>
    </li>
  )
}

type ScoreLevel = 'low' | 'medium' | 'good'
const ACTION_WORDS = [
  'créer','creer','create','mettre','update','envoyer','send','récupérer','recuperer',
  'fetch','supprimer','delete','lister','list','ouvrir','ajouter','add','générer','generer',
  'activer','désactiver','modifier','authenticate','login','calculer','calculate',
  'valider','validate','archiver','archive','importer','import','exporter','export',
  'synchroniser','notifier','notify','démarrer','arrêter','déclencher','trigger',
]
const ENTITY_WORDS = [
  'employé','employee','contrat','contract','utilisateur','user','compte','account',
  'salaire','salary','email','fichier','file','client','customer','commande','order',
  'facture','invoice','manager','département','department','rôle','role','accès','access',
  'token','rapport','report','paiement','payment','profil','profile','équipe','team',
  'cotisation','bulletin','fiche','notification','identifiant','credential',
]

function validateInstruction(v: string): string {
  const t = v.trim()
  const lower = t.toLowerCase()
  if (t.length < 10) return `Too short — ${t.length}/10 characters minimum.`
  if (t.length > 500) return `Too long — ${t.length}/500 characters maximum.`
  if (!ACTION_WORDS.some(w => lower.includes(w)))
    return 'Add an action verb: create, send, retrieve, update, delete…'
  if (!ENTITY_WORDS.some(w => lower.includes(w)) && t.split(/\s+/).length < 5)
    return 'Specify the object: employee, contract, account, email, user…'
  return ''
}

function scoreInstruction(v: string): { level: ScoreLevel; hint: string } {
  const t = v.trim()
  const lower = t.toLowerCase()
  const words = t.split(/\s+/)
  if (t.length < 10) return { level: 'low', hint: `${t.length}/10 min` }
  const hasAction = ACTION_WORDS.some(w => lower.includes(w))
  const hasEntity = ENTITY_WORDS.some(w => lower.includes(w))
  const isDetailed = words.length >= 7 && t.length >= 50
  if (!hasAction) return { level: 'low', hint: 'Missing action verb' }
  if (!hasEntity) return { level: 'medium', hint: 'Specify the object (employee, contract…)' }
  if (isDetailed) return { level: 'good', hint: 'Detailed instruction ✓' }
  return { level: 'medium', hint: 'Add more details for better results' }
}

export default function AutomationPage() {
  const nav = useNavigate()

  const [runs, setRuns]                       = useState<AnalysisRun[]>([])
  const [selectedRunId, setSelectedRunId]     = useState('')
  const [instruction, setInstruction]         = useState('')
  const [searchLevel, setSearchLevel]         = useState<'precise' | 'balanced' | 'wide'>('balanced')
  const [generating, setGenerating]           = useState(false)
  const [executing, setExecuting]             = useState(false)
  const [planResult, setPlanResult]           = useState<CreatePlanResponse | null>(null)
  const [executionResult, setExecutionResult] = useState<ExecutePlanResponse | null>(null)
  const [apiError, setApiError]               = useState('')
  const [dryRun, setDryRun]                   = useState(true)
  // 'pending' = an approval request was sent and we're polling for the
  // admin's decision (see startPolling below). 'approved' = the admin said
  // yes — the tile turns green and waits for the operator to click
  // "Execute for real" themselves; it does NOT auto-execute, by design (the
  // operator gets a deliberate last look before the real call goes out).
  const [approvalStatus, setApprovalStatus]   = useState<'idle' | 'pending' | 'approved'>('idle')
  const [pendingRunId, setPendingRunId]       = useState<string | null>(null)
  const [resultModal, setResultModal]         = useState<{ kind: 'success' | 'failure'; result: ExecutePlanResponse } | null>(null)
  const [connectionId, setConnectionId]       = useState('')
  const [selectedConnection, setSelectedConnection] = useState<Connection | undefined>(undefined)
  const [inputRows, setInputRows] = useState('')
  const [planError, setPlanError]               = useState('')
  const [planSuggestion, setPlanSuggestion]     = useState('')
  const pollRef = useRef<number | null>(null)

  const topK = searchLevel === 'precise' ? 5 : searchLevel === 'wide' ? 12 : 8
  const canExecute = !!planResult && !!connectionId && approvalStatus !== 'pending'
  const steps = planResult?.plan.steps ?? []
  const instructionError = validateInstruction(instruction)
  const instructionScore = scoreInstruction(instruction)
  const SCORE_COLORS: Record<ScoreLevel, string> = { low: '#f43f5e', medium: '#f59e0b', good: '#22c55e' }
  const SCORE_LEVELS: Record<ScoreLevel, number> = { low: 0, medium: 1, good: 2 }

  useEffect(() => {
    listRuns({ limit: 50 }).then(data => {
      setRuns(data.items)
      if (data.items.length > 0) setSelectedRunId(data.items[0].id)
    }).catch(() => {})
  }, [])

  useEffect(() => () => stopPolling(), []) // eslint-disable-line react-hooks/exhaustive-deps

  function stopPolling() {
    if (pollRef.current !== null) {
      window.clearInterval(pollRef.current)
      pollRef.current = null
    }
  }

  async function handleGeneratePlan() {
    if (!selectedRunId || instructionError) return
    setGenerating(true)
    setApiError('')
    setPlanError('')
    setPlanSuggestion('')
    setPlanResult(null)
    setExecutionResult(null)
    try {
      const result = await createPlan(selectedRunId, instruction, topK)
      setPlanResult(result)
    } catch (e) {
      if (e instanceof ApiError && e.body) {
        const d = (e.body as { detail?: { code?: string; message?: string; suggestion?: string } }).detail
        if (d && typeof d === 'object') {
          setPlanError(d.message ?? 'Invalid instruction or no matching endpoint.')
          setPlanSuggestion(d.suggestion ?? '')
          return
        }
      }
      setApiError(e instanceof Error ? e.message : 'Error generating the plan')
    } finally {
      setGenerating(false)
    }
  }

  // Fires the exact same /automation/execute call every time — on the first
  // click AND on every poll tick while waiting for admin approval. The
  // backend (app/api/automation.py) is what makes this safe to repeat: it
  // looks up any existing "pending_approval" run for this same plan+user
  // before creating a new one, so retrying is really "check whether the
  // admin has decided yet", not "submit a new request every time".
  // approval_granted is always sent as true — the server ignores it and
  // decides for itself via governance policy either way, so the client no
  // longer pretends to make that call itself.
  // forceDryRun lets a caller override the current toggle instead of reading
  // it — needed by "Send for approval" below, which must send dry_run=false
  // even if the Simulation mode toggle is still on (the operator just ran a
  // simulation and is now asking to turn that into a real request, without
  // first having to flip the toggle themselves).
  async function callExecute(forceDryRun?: boolean): Promise<ExecutePlanResponse> {
    if (!planResult) throw new Error('No plan')
    let parsedRows: Record<string, unknown>[] = []
    try {
      const parsed = JSON.parse(inputRows) as unknown
      parsedRows = Array.isArray(parsed) ? parsed as Record<string, unknown>[] : [parsed as Record<string, unknown>]
    } catch { parsedRows = [] }
    return executePlan(planResult.plan, parsedRows, connectionId, forceDryRun ?? dryRun, true)
  }

  function onExecutionSettled(result: ExecutePlanResponse) {
    stopPolling()
    setApprovalStatus('idle')
    setPendingRunId(null)
    setExecutionResult(result)
    setResultModal({ kind: result.failed_count > 0 ? 'failure' : 'success', result })
  }

  // Polls the Approvals queue (read-only — GET /approvals?status=...), not
  // /automation/execute: that endpoint EXECUTES for real the moment it sees
  // an approved run, which is exactly what we don't want here. The operator
  // decides when to actually pull the trigger, after seeing the tile turn
  // green — this only ever checks the decision, never acts on it.
  // runId is taken as a parameter rather than read from the pendingRunId
  // state to avoid a stale-closure bug: this function is called right after
  // setPendingRunId(), and the interval's closure would otherwise capture
  // whatever pendingRunId was at render time (still null), not the value
  // just set.
  function startPolling(runId: string) {
    stopPolling()
    pollRef.current = window.setInterval(async () => {
      try {
        const [approved, rejected] = await Promise.all([listApprovals('approved'), listApprovals('rejected')])
        const rejection = rejected.find(a => a.automation_run_id === runId)
        if (rejection) {
          stopPolling()
          setApprovalStatus('idle')
          setPendingRunId(null)
          setApiError(`Your request was rejected${rejection.comment ? `: ${rejection.comment}` : '.'}`)
          return
        }
        if (approved.some(a => a.automation_run_id === runId)) {
          stopPolling()
          setApprovalStatus('approved') // tile turns green; operator clicks Execute for real themselves
        }
      } catch {
        // transient fetch error — just try again next tick
      }
    }, 8000)
  }

  async function runExecution(forceDryRun?: boolean) {
    if (!planResult || !connectionId) return
    if (forceDryRun === false) setDryRun(false) // reflect reality in the toggle too
    setExecuting(true)
    setApiError('')
    try {
      const result = await callExecute(forceDryRun)
      onExecutionSettled(result)
    } catch (e) {
      const detail = e instanceof ApiError && e.body && typeof e.body.detail === 'object'
        ? e.body.detail as { code?: string; message?: string; automation_run_id?: string } : undefined
      if (detail?.code === 'APPROVAL_PENDING') {
        const runId = detail.automation_run_id ?? null
        setApprovalStatus('pending')
        setPendingRunId(runId)
        if (runId) startPolling(runId)
        return
      }
      setApiError(e instanceof Error ? e.message : "Error during execution")
    } finally {
      setExecuting(false)
    }
  }

  const handleExecute = () => runExecution()
  // Follow-up action shown after a successful simulation: turns that exact
  // same plan/input into a real request without the operator having to
  // manually flip "Simulation mode" off first.
  const handleSendForApproval = () => runExecution(false)

  return (
    <AppLayout>
      <div className="p-6 space-y-6">
        <div>
          <h2 className="text-xl font-black" style={{ color: 'var(--ink)' }}>Simple Automation</h2>
          <p className="text-sm ink-2 mt-1">Test mode · a single action or a few manual rows.</p>
        </div>

        <div className="card overflow-hidden">
          <div className="grid lg:grid-cols-[1fr_auto] items-stretch">
            <div className="p-5 flex items-start gap-4">
              <div className="w-10 h-10 rounded-xl grad-bg text-white flex items-center justify-center flex-shrink-0"><FlaskConical className="w-5 h-5" /></div>
              <div>
                <p className="font-bold" style={{ color: 'var(--ink)' }}>Test a workflow on a single action</p>
                <p className="text-sm ink-2 mt-1 max-w-xl">Use this mode to run an API workflow on one or a few JSON rows. For a CSV/Excel file, switch to <span className="font-semibold">Bulk Automation</span> mode.</p>
              </div>
            </div>
            <div className="p-5 flex items-center" style={{ background: 'color-mix(in oklch, var(--brand) 4%, var(--card))', borderLeft: '1px solid var(--line)' }}>
              <button onClick={() => nav('/bulk')} className="btn-secondary"><Layers className="w-4 h-4" /> Switch to Bulk Automation</button>
            </div>
          </div>
        </div>

        {planError && (
          <div className="p-3 rounded-xl flex items-start gap-2 text-xs" style={{ background: 'color-mix(in oklch, #f59e0b 8%, var(--card))', color: '#92400e', border: '1px solid color-mix(in oklch, #f59e0b 30%, var(--line))' }}>
            <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0 text-amber-500" />
            <div>
              <p className="font-semibold">{planError}</p>
              {planSuggestion && <p className="mt-1 opacity-80">{planSuggestion}</p>}
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="card pad">
            <p className="text-sm font-bold mb-1" style={{ color: 'var(--ink)' }}>Generate a plan</p>
            <p className="text-xs ink-2 mb-4">Pick an existing workflow to run it as-is, or describe the action for AI plan generation.</p>
            <div className="space-y-3">
              {runs.length > 0 && (
                <div>
                  <p className="text-[10px] font-bold tracking-widest uppercase ink-2 mb-1.5">Analysis run</p>
                  <select value={selectedRunId} onChange={e => setSelectedRunId(e.target.value)}
                    className="input !py-1.5 text-xs font-mono w-full">
                    {runs.map(r => <option key={r.id} value={r.id}>{r.file_name}</option>)}
                  </select>
                </div>
              )}
              <div>
                <p className="text-[10px] font-bold tracking-widest uppercase ink-2 mb-1.5">Instruction</p>
                <textarea
                  value={instruction}
                  onChange={e => { setInstruction(e.target.value); setPlanError(''); setPlanSuggestion('') }}
                  rows={3}
                  className="input resize-none"
                  placeholder="Describe the action to automate…"
                />
                {instruction.trim().length > 0 && (
                  <div className="mt-2 flex items-center gap-2">
                    <div className="flex gap-0.5 flex-1">
                      {(['low', 'medium', 'good'] as ScoreLevel[]).map(lvl => (
                        <div key={lvl} className="h-1 flex-1 rounded-full transition-all"
                          style={{ background: SCORE_LEVELS[instructionScore.level] >= SCORE_LEVELS[lvl] ? SCORE_COLORS[instructionScore.level] : 'var(--line)' }} />
                      ))}
                    </div>
                    <span className="text-xs ink-2 whitespace-nowrap">{instructionScore.hint}</span>
                    <span className="text-[11px] font-mono whitespace-nowrap"
                      style={{ color: instruction.length > 450 ? '#f43f5e' : 'var(--ink-2)' }}>
                      {instruction.length}/500
                    </span>
                  </div>
                )}
                {instruction.trim().length > 0 && instructionError && (
                  <p className="mt-1 text-xs" style={{ color: '#f43f5e' }}>{instructionError}</p>
                )}
              </div>
              <div>
                <p className="text-[10px] font-bold tracking-widest uppercase ink-2 mb-1.5">Search level</p>
                <div className="grid grid-cols-3 gap-2">
                  {([['precise', 'Precise', '5 endpoints'], ['balanced', 'Balanced', '8 endpoints · recommended'], ['wide', 'Wide', '12 endpoints']] as const).map(([v, l, d]) => (
                    <button key={v} onClick={() => setSearchLevel(v)}
                      className="text-left p-2.5 rounded-xl border transition"
                      style={{ borderColor: searchLevel === v ? 'var(--brand)' : 'var(--line)', background: searchLevel === v ? 'color-mix(in oklch, var(--brand) 6%, var(--card))' : 'var(--card)' }}>
                      <p className="text-sm font-bold" style={{ color: searchLevel === v ? 'var(--brand)' : 'var(--ink)' }}>{l}</p>
                      <p className="text-[11px] ink-2 mt-0.5">{d}</p>
                    </button>
                  ))}
                </div>
              </div>
              <div className="flex justify-end">
                <button onClick={handleGeneratePlan} disabled={!selectedRunId || generating || !!instructionError} className="btn-primary"
                  style={{ opacity: !selectedRunId || generating || !!instructionError ? 0.6 : 1 }}>
                  <Sparkles className="w-4 h-4" /> {generating ? 'Generating…' : 'Generate plan'}
                </button>
              </div>
            </div>
           
          </div>

          <div className="card pad">
            <div className="flex items-start justify-between mb-1">
              <p className="text-sm font-bold" style={{ color: 'var(--ink)' }}>Execute</p>
              {dryRun ? <span className="pill bg-sky-50 text-sky-700 border-sky-200">Simulation</span>
                : <span className="pill bg-rose-50 text-rose-700 border-rose-200 font-bold">Live execution</span>}
            </div>
            <p className="text-xs ink-2 mb-4">The instruction will be sent to the target API if you disable simulation.</p>
            <div className="space-y-3">
              <ConnectionPicker value={connectionId} onChange={setConnectionId} onSelectConnection={setSelectedConnection} />
              {planResult && planResult.required_input_fields.length > 0 && (
                <div className="p-3 rounded-xl" style={{ background: 'color-mix(in oklch, var(--brand) 4%, var(--card))', border: '1px solid var(--line)' }}>
                  <p className="text-[10px] font-bold tracking-widest uppercase ink-2 mb-2">Fields your input JSON needs</p>
                  {/* Grouped by the step that first needs them — a field a
                      later step gets for free from an earlier step's
                      response (e.g. employee_id after "Create Employee")
                      never appears here. See app/automation/payload_mapper.py
                      ::required_input_fields() for how this is computed. */}
                  {Array.from(new Set(planResult.required_input_fields.map(f => f.first_needed_at_step))).map(stepOrder => (
                    <div key={stepOrder} className="flex items-start gap-2 mb-1.5 last:mb-0">
                      <span className="text-[10px] font-mono ink-2 mt-0.5 flex-shrink-0">Step {stepOrder}</span>
                      <div className="flex flex-wrap gap-1">
                        {planResult.required_input_fields.filter(f => f.first_needed_at_step === stepOrder).map(f => (
                          <span key={f.field} className="px-1.5 py-0.5 rounded text-[11px] font-mono"
                            style={{ background: 'color-mix(in oklch, var(--ink) 5%, var(--card))', color: 'var(--ink)', border: '1px solid var(--line)' }}>
                            {f.field} <span className="ink-2">({f.type})</span>
                          </span>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
              <div>
                <p className="text-[10px] font-bold tracking-widest uppercase ink-2 mb-1.5">Input data (JSON) · optional</p>
                <textarea value={inputRows} onChange={e => setInputRows(e.target.value)} rows={4} className="input resize-none font-mono text-xs"
                  placeholder='[{ "field": "value" }]' />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <ToggleBig label="Simulation mode" hint="ARIA prepares the requests without sending them" checked={dryRun}
                  onChange={v => { setDryRun(v); if (v) { stopPolling(); setApprovalStatus('idle'); setPendingRunId(null) } }} />
                {approvalStatus === 'pending' ? (
                  <StatusTile icon={<RefreshCw className="w-4 h-4 animate-spin" />} tone="pending"
                    label="Pending admin approval"
                    hint={`Waiting for a decision — checking automatically${pendingRunId ? ` (run ${pendingRunId.slice(0, 8)}…)` : ''}`} />
                ) : approvalStatus === 'approved' ? (
                  <StatusTile icon={<CheckCircle2 className="w-4 h-4" />} tone="approved"
                    label="Approved"
                    hint="An admin approved this request — click Execute for real to run it" />
                ) : (
                  <StatusTile icon={<ShieldCheck className="w-4 h-4" />} tone="muted"
                    label="Approval"
                    hint={dryRun ? 'Not required in simulation' : "Requested automatically from an admin if your org's policy requires it"} />
                )}
              </div>
              {!dryRun && (
                <div className="p-3 rounded-xl flex items-start gap-2 text-xs" style={{ background: 'color-mix(in oklch, #f43f5e 8%, var(--card))', color: '#9f1239', border: '1px solid color-mix(in oklch, #f43f5e 30%, var(--line))' }}>
                  <TriangleAlert className="w-4 h-4 mt-0.5 flex-shrink-0" />
                  <span>Live execution will send POST/PUT requests to <span className="font-mono">{selectedConnection?.base_url ?? 'the selected connection'}</span>. This cannot be undone.</span>
                </div>
              )}
              <div className="flex justify-end">
                <button onClick={handleExecute} disabled={!canExecute || executing}
                  className={dryRun ? 'btn-primary' : 'btn-danger'} style={{ opacity: canExecute && !executing ? 1 : 0.6 }}>
                  <Play className="w-4 h-4" />
                  {approvalStatus === 'pending' ? 'Waiting for approval…' : executing ? 'Executing…' : dryRun ? 'Run simulation' : 'Execute for real'}
                </button>
              </div>
            </div>
          </div>
        </div>

        {planResult && (
          <div className="card pad">
            <div className="flex items-start justify-between gap-4 flex-wrap mb-4">
              <div>
                <div className="flex items-center gap-2 flex-wrap mb-1">
                  <h3 className="font-black text-lg" style={{ color: 'var(--ink)' }}>{planResult.plan.workflow_name}</h3>
                  {planResult.plan.requires_approval && <span className="pill bg-amber-50 text-amber-700 border-amber-200">Approval required</span>}
                  {planResult.plan.dry_run_default && <span className="pill bg-sky-50 text-sky-700 border-sky-200">Simulation by default</span>}
                </div>
                <p className="text-sm ink-2">Type: <span className="font-semibold" style={{ color: 'var(--ink)' }}>Simple Automation</span> · {steps.length} steps</p>
              </div>
              <div className="text-right">
                <p className="text-[10px] font-bold tracking-widest uppercase ink-2">Estimated</p>
                <p className="font-mono text-sm" style={{ color: 'var(--ink)' }}>~ {steps.length} calls</p>
              </div>
            </div>

            {planResult.validation.issues.length > 0 && (
              <div className="mb-4 p-3 rounded-xl space-y-1 text-xs" style={{ background: 'color-mix(in oklch, #f59e0b 8%, var(--card))', border: '1px solid color-mix(in oklch, #f59e0b 30%, var(--line))' }}>
                {planResult.validation.issues.map((issue, i) => (
                  <p key={i} style={{ color: issue.level === 'error' ? '#9f1239' : '#92400e' }}>
                    <span className="font-bold uppercase">{issue.level}</span> {issue.step_order != null ? `[step ${issue.step_order}] ` : ''}{issue.message}
                  </p>
                ))}
              </div>
            )}

            <div className="relative">
              <div className="absolute left-4 top-2 bottom-2 w-0.5 rounded-full grad-bg" />
              <ol className="space-y-3">{steps.map(s => <PlanStep key={s.order} step={s} />)}</ol>
            </div>
          </div>
        )}

        {executionResult && (
          <div className="card pad">
            <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
              <div>
                <p className="text-sm font-bold" style={{ color: 'var(--ink)' }}>Result — Simple Automation</p>
                <div className="flex items-center gap-2 flex-wrap mt-1">
                  {/* Backend only ever returns status="success" | "partial_failure" | "failed"
                      (app/automation/models.py::AutomationExecutionResult) — never "completed".
                      Comparing against 'completed' always failed, so a partial_failure run
                      (the common case: at least one real step error) fell through to the
                      'running' default forever, even once the call had long finished. */}
                  <StatusBadge s={executionResult.status === 'success' ? 'completed' : 'failed'} />
                  {executionResult.dry_run && <span className="pill bg-sky-50 text-sky-700 border-sky-200">Simulation</span>}
                </div>
              </div>
              <div className="grid grid-cols-3 gap-4 text-center">
                <div><p className="text-xs ink-2">Success</p><p className="text-xl font-black text-emerald-600">{executionResult.success_count}</p></div>
                <div><p className="text-xs ink-2">Failures</p><p className="text-xl font-black text-rose-600">{executionResult.failed_count}</p></div>
                <div><p className="text-xs ink-2">Total</p><p className="text-xl font-black" style={{ color: 'var(--ink)' }}>{executionResult.total_steps}</p></div>
              </div>
            </div>
            <div className="overflow-hidden rounded-xl" style={{ border: '1px solid var(--line)' }}>
              <table className="w-full text-sm">
                <thead className="aria-thead"><tr>{['Step', 'Method', 'Path', 'Status', 'Code', 'Risk'].map(h => <th key={h} className="text-left px-3 py-2">{h}</th>)}</tr></thead>
                <tbody>
                  {/* Real per-step outcomes from the backend (executionResult.result.results)
                      — this used to iterate the PLAN's steps instead and hardcode every row
                      as "completed" / 201, regardless of what actually happened. Risk level
                      isn't on the execution result, so it's looked up from the plan by
                      step_order purely for display. */}
                  {executionResult.result.results.map(r => {
                    const planStep = steps.find(s => s.order === r.step_order)
                    const ok = r.status === 'success' || r.status === 'dry_run'
                    return (
                      <tr key={r.step_order} className="border-t align-top" style={{ borderColor: 'var(--line)' }}>
                        <td className="px-3 py-2 font-mono text-xs ink-2">{r.step_order}</td>
                        <td className="px-3 py-2"><MethodBadge m={r.method} /></td>
                        <td className="px-3 py-2 font-mono text-xs" style={{ color: 'var(--ink)' }}>
                          {r.path}
                          {!ok && r.error_message && (
                            <p className="mt-1 text-xs font-sans" style={{ color: '#e11d48' }}>{r.error_message}</p>
                          )}
                        </td>
                        <td className="px-3 py-2"><StatusBadge s={ok ? 'completed' : 'failed'} /></td>
                        <td className="px-3 py-2 text-right font-mono text-xs font-bold" style={{ color: ok ? '#059669' : '#e11d48' }}>
                          {r.status_code ?? '—'}
                        </td>
                        <td className="px-3 py-2">{planStep && <SeverityBadge s={planStep.risk_level} />}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            {executionResult.dry_run && approvalStatus === 'idle' && (
              <div className="flex items-center justify-between gap-3 mt-4 p-3 rounded-xl" style={{ background: 'color-mix(in oklch, var(--brand) 4%, var(--card))', border: '1px solid var(--line)' }}>
                <p className="text-xs ink-2">Simulation looks good? Turn it into a real request — sent to an admin for approval if your org's policy requires it.</p>
                <button onClick={handleSendForApproval} disabled={executing} className="btn-primary flex-shrink-0" style={{ opacity: executing ? 0.6 : 1 }}>
                  <ShieldCheck className="w-4 h-4" /> Send for approval
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Execution blocked/error — popup instead of an inline banner */}
      {apiError && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/50" onClick={() => setApiError('')} />
          <div className="relative card pad w-full max-w-[480px] shadow-2xl space-y-4">
            <div className="flex items-start gap-3">
              <div className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
                style={{ background: 'rgba(244,63,94,0.1)', color: '#f43f5e' }}>
                <TriangleAlert className="w-5 h-5" />
              </div>
              <div className="flex-1 min-w-0">
                <h3 className="text-lg font-black" style={{ color: 'var(--ink)' }}>
                  {apiError.toLowerCase().includes('governance policy')
                    ? 'Blocked by governance policy'
                    : apiError.toLowerCase().includes('rejected')
                      ? 'Request rejected'
                      : apiError.toLowerCase().includes('approval')
                        ? 'Approval required'
                        : 'Execution error'}
                </h3>
                <p className="text-sm ink-2 mt-1.5 whitespace-pre-wrap">{apiError}</p>
              </div>
              <button onClick={() => setApiError('')} className="btn-ghost !p-1.5 flex-shrink-0"><X className="w-4 h-4" /></button>
            </div>
            <div className="flex justify-end pt-1">
              <button onClick={() => setApiError('')} className="btn-primary">Close</button>
            </div>
          </div>
        </div>
      )}

      {/* Execution outcome — success or failure, shown once a real (or
          simulated) run actually settles, including after an admin approves
          a pending request and the auto-poll gets the real result back. */}
      {resultModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/50" onClick={() => setResultModal(null)} />
          <div className="relative card pad w-full max-w-[480px] shadow-2xl space-y-4">
            <div className="flex items-start gap-3">
              <div className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
                style={resultModal.kind === 'success'
                  ? { background: 'rgba(16,185,129,0.1)', color: '#059669' }
                  : { background: 'rgba(244,63,94,0.1)', color: '#f43f5e' }}>
                {resultModal.kind === 'success' ? <CheckCircle2 className="w-5 h-5" /> : <TriangleAlert className="w-5 h-5" />}
              </div>
              <div className="flex-1 min-w-0">
                <h3 className="text-lg font-black" style={{ color: 'var(--ink)' }}>
                  {resultModal.kind === 'success' ? 'Execution succeeded' : 'Execution failed'}
                  {resultModal.result.dry_run && ' (simulation)'}
                </h3>
                <p className="text-sm ink-2 mt-1.5">
                  {resultModal.result.success_count}/{resultModal.result.total_steps} step(s) succeeded.
                </p>
                {resultModal.kind === 'failure' && (
                  <div className="mt-2 space-y-1">
                    {resultModal.result.result.results.filter(r => r.status === 'failed').map(r => (
                      <p key={r.step_order} className="text-xs" style={{ color: '#e11d48' }}>
                        Step {r.step_order} ({r.method} {r.path}): {r.error_message ?? `HTTP ${r.status_code ?? '—'}`}
                      </p>
                    ))}
                  </div>
                )}
              </div>
              <button onClick={() => setResultModal(null)} className="btn-ghost !p-1.5 flex-shrink-0"><X className="w-4 h-4" /></button>
            </div>
            <div className="flex justify-end gap-2 pt-1">
              <button onClick={() => setResultModal(null)} className="btn-secondary">Close</button>
              {resultModal.kind === 'success' && resultModal.result.dry_run && (
                <button onClick={() => { setResultModal(null); handleSendForApproval() }} className="btn-primary">
                  <ShieldCheck className="w-4 h-4" /> Send for approval
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </AppLayout>
  )
}
