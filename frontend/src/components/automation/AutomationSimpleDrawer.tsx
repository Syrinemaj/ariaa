import { useEffect, useState } from 'react'
import { StatusBadge } from '../aria/Badges'
import { listRuns, AnalysisRun } from '../../lib/registryApi'
import {
  createPlan, executePlan,
  BackendPlanStep, CreatePlanResponse, ExecutePlanResponse,
} from '../../lib/automationApi'
import { ApiError } from '../../lib/api'
import {
  X, FlaskConical, Sparkles, Play, Lock, Unlock,
  ChevronDown, Plus, TriangleAlert, AlertCircle,
} from 'lucide-react'

// ── Local helpers (same patterns as AutomationPage) ────────────────────────────

function MethodBadge({ m }: { m: string }) {
  const cls: Record<string, string> = {
    GET: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    POST: 'bg-indigo-50 text-indigo-700 border-indigo-200',
    PUT: 'bg-amber-50 text-amber-700 border-amber-200',
    PATCH: 'bg-violet-50 text-violet-700 border-violet-200',
    DELETE: 'bg-rose-50 text-rose-700 border-rose-200',
  }
  return <span className={`pill ${cls[m] ?? 'bg-slate-50 text-slate-600 border-slate-200'}`}>{m}</span>
}

function SeverityBadge({ s }: { s: string }) {
  const cls: Record<string, string> = {
    low: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    medium: 'bg-amber-50 text-amber-700 border-amber-200',
    high: 'bg-orange-50 text-orange-700 border-orange-200',
    critical: 'bg-rose-50 text-rose-700 border-rose-200',
  }
  return <span className={`pill ${cls[s] ?? 'bg-slate-50 text-slate-600 border-slate-200'}`}>{s}</span>
}

function ToggleBig({ label, hint, checked, onChange, disabled }: {
  label: string; hint: string; checked: boolean; onChange: (v: boolean) => void; disabled?: boolean
}) {
  return (
    <label className="flex items-start gap-3 p-3 rounded-xl border transition cursor-pointer"
      style={{
        borderColor: checked && !disabled ? 'var(--brand)' : 'var(--line)',
        background: checked && !disabled ? 'color-mix(in oklch, var(--brand) 6%, var(--card))' : 'var(--card)',
        opacity: disabled ? 0.5 : 1,
        cursor: disabled ? 'not-allowed' : 'pointer',
      }}>
      <button onClick={() => !disabled && onChange(!checked)}
        className="w-9 h-5 rounded-full relative flex-shrink-0 mt-0.5 transition"
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

type HeaderRow = { k: string; v: string }
function KeyValueEditor({ label, rows, setRows }: { label: string; rows: HeaderRow[]; setRows: (r: HeaderRow[]) => void }) {
  const SENSITIVE = ['authorization', 'token', 'cookie', 'api-key', 'password', 'secret']
  return (
    <div>
      <p className="text-[10px] font-bold tracking-widest uppercase ink-2 mb-1.5">{label}</p>
      <div className="space-y-2">
        {rows.map((h, i) => {
          const s = SENSITIVE.some(k => h.k.toLowerCase().includes(k))
          return (
            <div key={i} className="grid grid-cols-[1fr_2fr_auto] gap-2">
              <input value={h.k} className="input !py-1.5 font-mono text-xs"
                onChange={e => setRows(rows.map((x, j) => j === i ? { ...x, k: e.target.value } : x))} />
              <div className="relative">
                <input type={s ? 'password' : 'text'} value={h.v} className="input !py-1.5 font-mono text-xs"
                  onChange={e => setRows(rows.map((x, j) => j === i ? { ...x, v: e.target.value } : x))} />
                {s && (
                  <span className="absolute right-2 top-1/2 -translate-y-1/2 pill text-[9px] bg-rose-50 text-rose-700 border-rose-200">
                    <Lock className="w-2.5 h-2.5" />masqué
                  </span>
                )}
              </div>
              <button className="btn-ghost !p-1.5" onClick={() => setRows(rows.filter((_, j) => j !== i))}>
                <X className="w-4 h-4" />
              </button>
            </div>
          )
        })}
        <button onClick={() => setRows([...rows, { k: '', v: '' }])} className="btn-ghost text-xs">
          <Plus className="w-3.5 h-3.5" /> Ajouter
        </button>
      </div>
    </div>
  )
}

function PlanStep({ step }: { step: BackendPlanStep }) {
  const [open, setOpen] = useState(false)
  return (
    <li className="relative pl-10">
      <div className="absolute left-1 top-1 w-7 h-7 rounded-full grad-bg text-white text-xs font-black flex items-center justify-center ring-4"
        style={{ '--tw-ring-color': 'var(--card)' } as React.CSSProperties}>
        {step.order}
      </div>
      <div className="card pad !p-4">
        <div className="flex flex-wrap items-center gap-3">
          <MethodBadge m={step.method} />
          <span className="font-mono text-xs flex-1 min-w-0 truncate" style={{ color: 'var(--ink)' }}>{step.path}</span>
          <SeverityBadge s={step.risk_level} />
          {step.auth_required
            ? <Lock className="w-3.5 h-3.5 text-amber-500" />
            : <Unlock className="w-3.5 h-3.5 text-emerald-500" />}
        </div>
        <p className="mt-2 text-sm" style={{ color: 'var(--ink)' }}>{step.action ?? '—'}</p>
        <div className="mt-1 flex items-center gap-2 text-xs ink-2 flex-wrap">
          <span>Domaine : <span className="font-semibold" style={{ color: 'var(--ink)' }}>{step.business_domain ?? '—'}</span></span>
          {step.depends_on.length > 0 && <span>· Dépend de l&apos;étape {step.depends_on.join(', ')}</span>}
        </div>
        <button onClick={() => setOpen(o => !o)} className="mt-2 text-xs ink-2 inline-flex items-center gap-1 hover:opacity-80">
          <ChevronDown className={`w-3.5 h-3.5 transition-transform ${open ? 'rotate-180' : ''}`} />
          {open ? 'Masquer les schémas' : 'Voir request/response schemas'}
        </button>
        {open && (
          <div className="mt-3 grid grid-cols-1 gap-3">
            {(['Request schema', 'Response schema'] as const).map(t => (
              <div key={t}>
                <p className="text-[10px] font-bold tracking-widest uppercase ink-2 mb-1.5">{t}</p>
                <pre className="rounded-xl p-3 text-xs font-mono overflow-auto max-h-[140px]"
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

// ── Instruction helpers ────────────────────────────────────────────────────────

const INSTRUCTION_EXAMPLES = [
  'Créer un employé Bob Martin avec contrat CDI et envoyer un email de bienvenue',
  'Ouvrir un compte paie et calculer le salaire du mois de janvier',
  'Récupérer la liste des employés actifs du département Engineering',
  'Mettre à jour le poste et le salaire d\'un employé existant',
  'Créer un utilisateur avec rôle OPERATOR et activer son accès',
]

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
  if (t.length < 10) return `Trop court — ${t.length}/10 caractères minimum.`
  if (t.length > 500) return `Trop long — ${t.length}/500 caractères maximum.`
  if (!ACTION_WORDS.some(w => lower.includes(w)))
    return 'Ajoutez un verbe d\'action : créer, envoyer, récupérer, mettre à jour, supprimer…'
  if (!ENTITY_WORDS.some(w => lower.includes(w)) && t.split(/\s+/).length < 5)
    return 'Précisez l\'objet : employé, contrat, compte, email, utilisateur…'
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
  if (!hasAction) return { level: 'low', hint: 'Verbe d\'action manquant' }
  if (!hasEntity) return { level: 'medium', hint: 'Précisez l\'objet (employé, contrat…)' }
  if (isDetailed) return { level: 'good', hint: 'Instruction détaillée ✓' }
  return { level: 'medium', hint: 'Ajoutez des détails pour de meilleurs résultats' }
}

// ── Main drawer component ──────────────────────────────────────────────────────

interface Props {
  open: boolean
  onClose: () => void
}

export default function AutomationSimpleDrawer({ open, onClose }: Props) {
  const [runs, setRuns]                       = useState<AnalysisRun[]>([])
  const [selectedRunId, setSelectedRunId]     = useState('')
  const [instruction, setInstruction]         = useState('Créer un employé nommé Bob avec contrat CDI, ouvrir un compte paie et envoyer un email de bienvenue')
  const [searchLevel, setSearchLevel]         = useState<'precise' | 'balanced' | 'wide'>('balanced')
  const [generating, setGenerating]           = useState(false)
  const [executing, setExecuting]             = useState(false)
  const [planResult, setPlanResult]           = useState<CreatePlanResponse | null>(null)
  const [executionResult, setExecutionResult] = useState<ExecutePlanResponse | null>(null)
  const [apiError, setApiError]               = useState('')
  const [dryRun, setDryRun]                   = useState(true)
  const [approved, setApproved]               = useState(false)
  const [baseUrl, setBaseUrl]                 = useState('https://hr-api.northwind.io')
  const [headers, setHeaders]                 = useState<HeaderRow[]>([
    { k: 'Authorization', v: 'Bearer eyJhbGciOiJIUzI1NiJ9.payload.sign' },
    { k: 'X-Tenant', v: 'northwind' },
  ])
  const [inputRows, setInputRows] = useState('[\n  { "firstName":"Bob", "lastName":"Hartman", "email":"bob@northwind.io",\n    "department":"Engineering", "contract_type":"CDI", "salary_eur":68000 }\n]')
  const [planError, setPlanError]               = useState('')
  const [planSuggestion, setPlanSuggestion]     = useState('')
  const [instructionFocused, setInstructionFocused] = useState(false)

  const topK = searchLevel === 'precise' ? 5 : searchLevel === 'wide' ? 12 : 8
  const canExecute = !!planResult && (dryRun || approved)
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

  // Close on Escape
  useEffect(() => {
    if (!open) return
    const handle = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handle)
    return () => window.removeEventListener('keydown', handle)
  }, [open, onClose])

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
      if (e instanceof ApiError && e.status === 400 && e.body) {
        const d = (e.body as { detail?: { code?: string; message?: string; suggestion?: string } }).detail
        if (d && typeof d === 'object') {
          setPlanError(d.message ?? 'Instruction invalide ou aucun endpoint correspondant.')
          setPlanSuggestion(d.suggestion ?? '')
          return
        }
      }
      setApiError(e instanceof Error ? e.message : 'Erreur lors de la génération du plan')
    } finally {
      setGenerating(false)
    }
  }

  async function handleExecute() {
    if (!planResult || !canExecute) return
    setExecuting(true)
    setApiError('')
    try {
      const headersObj = Object.fromEntries(headers.filter(h => h.k).map(h => [h.k, h.v]))
      let parsedRows: Record<string, unknown>[] = []
      try {
        const parsed = JSON.parse(inputRows) as unknown
        parsedRows = Array.isArray(parsed) ? parsed as Record<string, unknown>[] : [parsed as Record<string, unknown>]
      } catch { parsedRows = [] }
      const result = await executePlan(planResult.plan, parsedRows, baseUrl, headersObj, dryRun, approved)
      setExecutionResult(result)
    } catch (e) {
      setApiError(e instanceof Error ? e.message : "Erreur lors de l'exécution")
    } finally {
      setExecuting(false)
    }
  }

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 transition-opacity duration-300"
        style={{
          background: 'rgba(0,0,0,0.45)',
          opacity: open ? 1 : 0,
          pointerEvents: open ? 'auto' : 'none',
        }}
        onClick={onClose}
      />

      {/* Drawer panel */}
      <div
        className="fixed inset-y-0 right-0 z-50 flex flex-col transition-transform duration-300 ease-in-out"
        style={{
          width: 640,
          background: 'var(--card)',
          borderLeft: '1px solid var(--line)',
          boxShadow: '-8px 0 40px rgba(0,0,0,0.15)',
          transform: open ? 'translateX(0)' : 'translateX(100%)',
        }}
      >
        {/* Drawer header */}
        <div className="flex items-center justify-between gap-4 px-5 py-4 flex-shrink-0"
          style={{ borderBottom: '1px solid var(--line)' }}>
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg grad-bg text-white flex items-center justify-center flex-shrink-0">
              <FlaskConical className="w-4 h-4" />
            </div>
            <div>
              <p className="font-black text-sm" style={{ color: 'var(--ink)' }}>Automation Simple</p>
              <p className="text-[11px] ink-2">Test sur une seule ligne JSON</p>
            </div>
          </div>
          <button onClick={onClose} className="btn-ghost !p-2" title="Fermer (Échap)">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Scrollable content */}
        <div className="flex-1 overflow-y-auto p-5 space-y-5">

          {apiError && (
            <div className="p-3 rounded-xl flex items-start gap-2 text-xs"
              style={{ background: 'color-mix(in oklch, #f43f5e 8%, var(--card))', color: '#9f1239', border: '1px solid color-mix(in oklch, #f43f5e 30%, var(--line))' }}>
              <TriangleAlert className="w-4 h-4 mt-0.5 flex-shrink-0" />
              <span>{apiError}</span>
            </div>
          )}

          {planError && (
            <div className="p-3 rounded-xl flex items-start gap-2 text-xs"
              style={{ background: 'color-mix(in oklch, #f59e0b 8%, var(--card))', color: '#92400e', border: '1px solid color-mix(in oklch, #f59e0b 30%, var(--line))' }}>
              <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0 text-amber-500" />
              <div>
                <p className="font-semibold">{planError}</p>
                {planSuggestion && <p className="mt-1 opacity-80">{planSuggestion}</p>}
              </div>
            </div>
          )}

          {/* Plan generation card */}
          <div className="card pad">
            <p className="text-sm font-bold mb-1" style={{ color: 'var(--ink)' }}>Générer un plan</p>
            <p className="text-xs ink-2 mb-4">Décrivez l&apos;action à effectuer.</p>
            <div className="space-y-3">
              {runs.length > 0 && (
                <div>
                  <p className="text-[10px] font-bold tracking-widest uppercase ink-2 mb-1.5">Run d&apos;analyse</p>
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
                  onFocus={() => setInstructionFocused(true)}
                  onBlur={() => setInstructionFocused(false)}
                  rows={3}
                  className="input resize-none"
                  placeholder="Décrivez l'action à automatiser…"
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
                {(instructionFocused || instruction.trim().length === 0) && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    <span className="text-xs ink-2 self-center">Exemples :</span>
                    {INSTRUCTION_EXAMPLES.map(ex => (
                      <button key={ex} type="button"
                        onMouseDown={e => { e.preventDefault(); setInstruction(ex); setPlanError(''); setPlanSuggestion('') }}
                        className="text-xs px-2.5 py-1 rounded-full border transition hover:opacity-80"
                        style={{ borderColor: 'var(--brand)', color: 'var(--brand)', background: 'color-mix(in oklch, var(--brand) 6%, var(--card))' }}>
                        {ex.length > 38 ? ex.slice(0, 38) + '…' : ex}
                      </button>
                    ))}
                  </div>
                )}
              </div>
              <div>
                <p className="text-[10px] font-bold tracking-widest uppercase ink-2 mb-1.5">Niveau de recherche</p>
                <div className="grid grid-cols-3 gap-2">
                  {([['precise', 'Précis', '5 endpoints'], ['balanced', 'Équilibré', '8 · recommandé'], ['wide', 'Large', '12 endpoints']] as const).map(([v, l, d]) => (
                    <button key={v} onClick={() => setSearchLevel(v)}
                      className="text-left p-2.5 rounded-xl border transition"
                      style={{
                        borderColor: searchLevel === v ? 'var(--brand)' : 'var(--line)',
                        background: searchLevel === v ? 'color-mix(in oklch, var(--brand) 6%, var(--card))' : 'var(--card)',
                      }}>
                      <p className="text-sm font-bold" style={{ color: searchLevel === v ? 'var(--brand)' : 'var(--ink)' }}>{l}</p>
                      <p className="text-[11px] ink-2 mt-0.5">{d}</p>
                    </button>
                  ))}
                </div>
              </div>
              <div className="flex justify-end">
                <button onClick={handleGeneratePlan} disabled={!selectedRunId || generating || !!instructionError} className="btn-primary"
                  style={{ opacity: !selectedRunId || generating || !!instructionError ? 0.6 : 1 }}>
                  <Sparkles className="w-4 h-4" /> {generating ? 'Génération…' : 'Générer le plan'}
                </button>
              </div>
            </div>
          </div>

          {/* Execution card */}
          <div className="card pad">
            <div className="flex items-start justify-between mb-1">
              <p className="text-sm font-bold" style={{ color: 'var(--ink)' }}>Exécuter</p>
              {dryRun
                ? <span className="pill bg-sky-50 text-sky-700 border-sky-200">Simulation</span>
                : <span className="pill bg-rose-50 text-rose-700 border-rose-200 font-bold">Exécution réelle</span>
              }
            </div>
            <p className="text-xs ink-2 mb-4">L&apos;instruction sera envoyée à l&apos;API cible si vous désactivez la simulation.</p>
            <div className="space-y-3">
              <div>
                <p className="text-[10px] font-bold tracking-widest uppercase ink-2 mb-1.5">URL de l&apos;API cible</p>
                <input value={baseUrl} onChange={e => setBaseUrl(e.target.value)}
                  className="input !py-2 font-mono text-xs" placeholder="https://hr-api.company.com" />
              </div>
              <KeyValueEditor label="En-têtes d'authentification" rows={headers} setRows={setHeaders} />
              <div>
                <p className="text-[10px] font-bold tracking-widest uppercase ink-2 mb-1.5">Données d&apos;entrée (JSON) · optionnel</p>
                <textarea value={inputRows} onChange={e => setInputRows(e.target.value)}
                  rows={4} className="input resize-none font-mono text-xs" />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <ToggleBig label="Mode simulation" hint="ARIA prépare les requêtes sans les envoyer"
                  checked={dryRun} onChange={v => { setDryRun(v); if (v) setApproved(false) }} />
                <ToggleBig label="Approuvé" hint={dryRun ? 'Non nécessaire en simulation' : "Requis pour l'exécution réelle"}
                  disabled={dryRun} checked={approved} onChange={setApproved} />
              </div>
              {!dryRun && (
                <div className="p-3 rounded-xl flex items-start gap-2 text-xs"
                  style={{ background: 'color-mix(in oklch, #f43f5e 8%, var(--card))', color: '#9f1239', border: '1px solid color-mix(in oklch, #f43f5e 30%, var(--line))' }}>
                  <TriangleAlert className="w-4 h-4 mt-0.5 flex-shrink-0" />
                  <span>L&apos;exécution réelle enverra des requêtes à <span className="font-mono">{baseUrl}</span>. Ceci ne peut pas être annulé.</span>
                </div>
              )}
              <div className="flex justify-end">
                <button onClick={handleExecute} disabled={!canExecute || executing}
                  className={dryRun ? 'btn-primary' : 'btn-danger'}
                  style={{ opacity: canExecute && !executing ? 1 : 0.6 }}>
                  <Play className="w-4 h-4" /> {executing ? 'Exécution…' : dryRun ? 'Lancer la simulation' : 'Exécuter pour de vrai'}
                </button>
              </div>
            </div>
          </div>

          {/* Plan steps */}
          {planResult && (
            <div className="card pad">
              <div className="flex items-start justify-between gap-4 flex-wrap mb-4">
                <div>
                  <div className="flex items-center gap-2 flex-wrap mb-1">
                    <h3 className="font-black text-base" style={{ color: 'var(--ink)' }}>{planResult.plan.workflow_name}</h3>
                    {planResult.plan.requires_approval && (
                      <span className="pill bg-amber-50 text-amber-700 border-amber-200">Approbation requise</span>
                    )}
                    {planResult.plan.dry_run_default && (
                      <span className="pill bg-sky-50 text-sky-700 border-sky-200">Simulation par défaut</span>
                    )}
                  </div>
                  <p className="text-sm ink-2">Automation Simple · {steps.length} étapes</p>
                </div>
              </div>

              {planResult.validation.issues.length > 0 && (
                <div className="mb-4 p-3 rounded-xl space-y-1 text-xs"
                  style={{ background: 'color-mix(in oklch, #f59e0b 8%, var(--card))', border: '1px solid color-mix(in oklch, #f59e0b 30%, var(--line))' }}>
                  {planResult.validation.issues.map((issue, i) => (
                    <p key={i} style={{ color: issue.level === 'error' ? '#9f1239' : '#92400e' }}>
                      <span className="font-bold uppercase">{issue.level}</span>{' '}
                      {issue.step_order != null ? `[étape ${issue.step_order}] ` : ''}{issue.message}
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

          {/* Execution result */}
          {executionResult && (
            <div className="card pad">
              <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
                <div>
                  <p className="text-sm font-bold" style={{ color: 'var(--ink)' }}>Résultat — Automation simple</p>
                  <div className="flex items-center gap-2 flex-wrap mt-1">
                    <StatusBadge s={executionResult.status === 'completed' ? 'completed' : executionResult.status === 'failed' ? 'failed' : 'running'} />
                    {executionResult.dry_run && <span className="pill bg-sky-50 text-sky-700 border-sky-200">Simulation</span>}
                  </div>
                </div>
                <div className="grid grid-cols-3 gap-4 text-center">
                  <div><p className="text-xs ink-2">Succès</p><p className="text-xl font-black text-emerald-600">{executionResult.success_count}</p></div>
                  <div><p className="text-xs ink-2">Échecs</p><p className="text-xl font-black text-rose-600">{executionResult.failed_count}</p></div>
                  <div><p className="text-xs ink-2">Total</p><p className="text-xl font-black" style={{ color: 'var(--ink)' }}>{executionResult.total_steps}</p></div>
                </div>
              </div>
              <div className="overflow-hidden rounded-xl" style={{ border: '1px solid var(--line)' }}>
                <table className="w-full text-sm">
                  <thead className="aria-thead">
                    <tr>{['Étape', 'Méthode', 'Path', 'Code', 'Risk'].map(h => (
                      <th key={h} className="text-left px-3 py-2">{h}</th>
                    ))}</tr>
                  </thead>
                  <tbody>
                    {steps.map(s => (
                      <tr key={s.order} className="border-t" style={{ borderColor: 'var(--line)' }}>
                        <td className="px-3 py-2 font-mono text-xs ink-2">{s.order}</td>
                        <td className="px-3 py-2"><MethodBadge m={s.method} /></td>
                        <td className="px-3 py-2 font-mono text-xs" style={{ color: 'var(--ink)' }}>{s.path}</td>
                        <td className="px-3 py-2 font-mono text-xs text-emerald-600 font-bold">{s.method === 'POST' ? '201' : '200'}</td>
                        <td className="px-3 py-2"><SeverityBadge s={s.risk_level} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

        </div>
      </div>
    </>
  )
}
