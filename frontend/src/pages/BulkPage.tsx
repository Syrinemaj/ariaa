import { useState, useEffect, useRef } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useRun } from '../contexts/RunContext'
import { useToast } from '../contexts/ToastContext'
import AppLayout from '../components/layout/AppLayout'
import { StatusBadge } from '../components/aria/Badges'
import { listRuns, AnalysisRun, getWorkflows, BackendWorkflow } from '../lib/registryApi'
import {
  createPlan, CreatePlanResponse, validateToken, planFromWorkflow, recordApproval,
  ValidateTokenResponse,
} from '../lib/automationApi'
import {
  uploadDataFile, suggestMapping, validateBulk, dryRunBulk,
  executeBulk, getBulkJobProgress, getBulkReport, downloadRowErrorsCsv,
  DataFileUploadResult, MappingResult, ValidationResult,
  DryRunResult, BulkExecuteResult, BulkJobProgress, BulkReport,
} from '../lib/bulkApi'
import {
  Upload, Network, CheckCheck, Eye, Shield, Play, BarChart2,
  Check, ChevronLeft, ArrowRight, Layers, Inbox, BarChart3,
  FlaskConical, Folder, Download, Info, X, Plus,
  Lock, TriangleAlert, Loader2, Zap,
} from 'lucide-react'
import AutomationSimpleDrawer from '../components/automation/AutomationSimpleDrawer'

// ── Helpers ────────────────────────────────────────────────────────────────────

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

function Spinner({ className = 'w-5 h-5' }: { className?: string }) {
  return <Loader2 className={`${className} animate-spin`} style={{ color: 'var(--brand)' }} />
}

function ToggleBig({ label, hint, checked, onChange, disabled }: {
  label: string; hint: string; checked: boolean; onChange: (v: boolean) => void; disabled?: boolean
}) {
  return (
    <label className="flex items-start gap-3 p-3 rounded-xl border transition"
      style={{
        borderColor: checked && !disabled ? 'var(--brand)' : 'var(--line)',
        background: checked && !disabled ? 'color-mix(in oklch, var(--brand) 6%, var(--card))' : 'var(--card)',
        opacity: disabled ? 0.5 : 1, cursor: disabled ? 'not-allowed' : 'pointer',
      }}>
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
                {s && <span className="absolute right-2 top-1/2 -translate-y-1/2 pill text-[9px] bg-rose-50 text-rose-700 border-rose-200"><Lock className="w-2.5 h-2.5" />hidden</span>}
              </div>
              <button className="btn-ghost !p-1.5" onClick={() => setRows(rows.filter((_, j) => j !== i))}><X className="w-4 h-4" /></button>
            </div>
          )
        })}
        <button onClick={() => setRows([...rows, { k: '', v: '' }])} className="btn-ghost text-xs">
          <Plus className="w-3.5 h-3.5" /> Add
        </button>
      </div>
    </div>
  )
}

// ── Step constants ─────────────────────────────────────────────────────────────

const STEPS = [
  { key: 'upload', label: 'Upload', Icon: Upload },
  { key: 'mapping', label: 'Mapping', Icon: Network },
  { key: 'validate', label: 'Validation', Icon: CheckCheck },
  { key: 'dryrun', label: 'Dry-run', Icon: Eye },
  { key: 'approval', label: 'Approval', Icon: Shield },
  { key: 'execute', label: 'Execute', Icon: Play },
  { key: 'report', label: 'Report', Icon: BarChart2 },
]

// ── Step components ────────────────────────────────────────────────────────────

function StepUpload({
  uploadFile, setUploadFile, uploadResult, uploading, onNext, hasPlan,
}: {
  uploadFile: File | null
  setUploadFile: (f: File | null) => void
  uploadResult: DataFileUploadResult | null
  uploading: boolean
  onNext: () => void
  hasPlan: boolean
}) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-[1fr_1.2fr] gap-4">
      <div className="card pad">
        <p className="text-sm font-bold mb-1" style={{ color: 'var(--ink)' }}>Upload a CSV / Excel file</p>
        <p className="text-xs ink-2 mb-4">Accepted formats: .csv, .xlsx, .xls</p>

        <label className="rounded-2xl border-2 border-dashed p-8 text-center aria-hero flex flex-col items-center cursor-pointer hover:border-[var(--brand)] transition"
          style={{ borderColor: uploadFile ? 'var(--brand)' : 'var(--line)' }}>
          <div className="w-12 h-12 rounded-2xl grad-bg mx-auto flex items-center justify-center mb-3 text-white">
            <Folder className="w-6 h-6" />
          </div>
          {uploadFile
            ? <><p className="font-semibold" style={{ color: 'var(--ink)' }}>{uploadFile.name}</p>
              <p className="text-xs ink-2 mt-1">{(uploadFile.size / 1024).toFixed(0)} KB</p></>
            : <><p className="font-semibold" style={{ color: 'var(--ink)' }}>Drag and drop or click to choose</p>
              <p className="text-xs ink-2 mt-1">.csv · .xlsx · .xls</p></>
          }
          <input type="file" className="hidden" accept=".csv,.xlsx,.xls"
            onChange={e => setUploadFile(e.target.files?.[0] ?? null)} />
        </label>

        {uploadResult && (
          <div className="mt-4 grid grid-cols-2 gap-3">
            <div><p className="text-[10px] font-bold tracking-widest uppercase ink-2">File</p>
              <p className="text-sm font-semibold mt-1 truncate" style={{ color: 'var(--ink)' }}>{uploadResult.file_name}</p></div>
            <div><p className="text-[10px] font-bold tracking-widest uppercase ink-2">Rows</p>
              <p className="font-mono mt-1" style={{ color: 'var(--ink)' }}>{uploadResult.rows_count.toLocaleString()}</p></div>
            <div className="col-span-2"><p className="text-[10px] font-bold tracking-widest uppercase ink-2">Columns</p>
              <p className="font-mono text-xs mt-1 ink-2">{uploadResult.columns.join(', ')}</p></div>
          </div>
        )}

        {!hasPlan && (
          <div className="mt-4 p-3 rounded-xl flex items-start gap-2 text-xs" style={{ background: 'color-mix(in oklch, #f59e0b 10%, var(--card))', border: '1px solid color-mix(in oklch, #f59e0b 30%, var(--line))', color: '#92400e' }}>
            <TriangleAlert className="w-4 h-4 flex-shrink-0 mt-0.5" />
            First generate an automation plan above.
          </div>
        )}

        <div className="flex justify-end mt-4">
          <button className="btn-primary" onClick={onNext}
            disabled={!uploadFile || !hasPlan || uploading}>
            {uploading ? <><Spinner className="w-4 h-4" /> Uploading…</> : <>Upload & continue <ArrowRight className="w-4 h-4" /></>}
          </button>
        </div>
      </div>

      <div className="card pad">
        <div className="flex items-center justify-between mb-3">
          <div>
            <p className="text-sm font-bold" style={{ color: 'var(--ink)' }}>
              {uploadResult ? `Preview · ${uploadResult.columns.length} columns` : 'Preview'}
            </p>
            <p className="text-xs ink-2">{uploadResult ? `${uploadResult.rows_count} rows` : 'Upload a file to see the preview'}</p>
          </div>
          {uploadResult && <span className="pill bg-emerald-50 text-emerald-700 border-emerald-200">Uploaded ✓</span>}
        </div>
        {uploadResult && uploadResult.preview.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="aria-thead">
                <tr>
                  {uploadResult.columns.slice(0, 6).map(c => (
                    <th key={c} className="text-left px-2 py-2 truncate max-w-[100px]">{c}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {uploadResult.preview.slice(0, 8).map((row, i) => (
                  <tr key={i} className="border-t font-mono" style={{ borderColor: 'var(--line)' }}>
                    {uploadResult.columns.slice(0, 6).map(col => (
                      <td key={col} className="px-2 py-1.5 truncate max-w-[100px]" style={{ color: 'var(--ink)' }}>
                        {String(row[col] ?? '')}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="h-48 flex items-center justify-center ink-2 text-sm">
            <Folder className="w-8 h-8 opacity-30" />
          </div>
        )}
      </div>
    </div>
  )
}

function StepMapping({
  mapping, suggesting, onNext, onBack,
}: {
  mapping: MappingResult | null
  suggesting: boolean
  onNext: () => void
  onBack: () => void
}) {
  const KINDS: Record<string, string> = {
    exact: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    synonym: 'bg-sky-50 text-sky-700 border-sky-200',
    rules: 'bg-violet-50 text-violet-700 border-violet-200',
    missing: 'bg-rose-50 text-rose-700 border-rose-200',
  }

  const exactCount = mapping?.mappings.filter(m => m.target_field && m.source !== 'missing').length ?? 0
  const missingCount = mapping?.mappings.filter(m => !m.target_field).length ?? 0

  return (
    <div className="card pad">
      <div className="flex items-start justify-between mb-4 flex-wrap gap-3">
        <div>
          <p className="text-sm font-bold" style={{ color: 'var(--ink)' }}>Mapping suggestion</p>
          <p className="text-xs ink-2 mt-1">POST /bulk/mapping/suggest</p>
        </div>
        {mapping && (
          <div className="flex items-center gap-2">
            <span className="pill bg-emerald-50 text-emerald-700 border-emerald-200">{exactCount} mapped</span>
            {missingCount > 0 && <span className="pill bg-amber-50 text-amber-700 border-amber-200">{missingCount} missing</span>}
          </div>
        )}
      </div>

      {suggesting ? (
        <div className="flex flex-col items-center justify-center py-16 gap-3">
          <Spinner className="w-8 h-8" />
          <p className="text-sm ink-2">Analyzing mapping…</p>
        </div>
      ) : mapping ? (
        <div className="overflow-x-auto rounded-xl" style={{ border: '1px solid var(--line)' }}>
          <table className="w-full text-sm">
            <thead className="aria-thead">
              <tr>{['Source', '→', 'Target', 'Type', 'Confidence', 'Approved'].map(h => (
                <th key={h} className="text-left px-3 py-2.5">{h}</th>
              ))}</tr>
            </thead>
            <tbody>
              {mapping.mappings.map((m, i) => {
                const kind = !m.target_field ? 'missing' : m.source
                return (
                  <tr key={i} className="border-t" style={{ borderColor: 'var(--line)', background: !m.target_field ? 'color-mix(in oklch, #f43f5e 5%, var(--card))' : '' }}>
                    <td className="px-3 py-3 font-mono text-xs" style={{ color: 'var(--ink)' }}>{m.source_field}</td>
                    <td className="px-2 py-3 ink-2">→</td>
                    <td className="px-2 py-3 font-mono text-xs">
                      {m.target_field
                        ? <span style={{ color: 'var(--brand)' }}>{m.target_field}</span>
                        : <span className="text-rose-600 italic">— unmapped —</span>
                      }
                    </td>
                    <td className="px-2 py-3"><span className={`pill ${KINDS[kind] ?? ''}`}>{kind}</span></td>
                    <td className="px-2 py-3">
                      <div className="flex items-center gap-2 min-w-[120px]">
                        <div className="flex-1 h-1.5 rounded-full overflow-hidden" style={{ background: 'var(--line)' }}>
                          <div className="h-1.5 rounded-full grad-bg" style={{ width: `${m.confidence * 100}%` }} />
                        </div>
                        <span className={`font-mono text-xs ${m.confidence >= 0.9 ? 'text-emerald-600' : m.confidence >= 0.7 ? 'text-amber-600' : 'text-rose-600'}`}>
                          {m.confidence.toFixed(2)}
                        </span>
                      </div>
                    </td>
                    <td className="px-2 py-3 text-center">
                      {m.approved
                        ? <Check className="w-4 h-4 inline text-emerald-600" />
                        : <span className="text-xs ink-2 italic">—</span>
                      }
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center py-12 gap-2 ink-2">
          <Network className="w-8 h-8 opacity-30" />
          <p className="text-sm">Mapping not loaded</p>
        </div>
      )}

      <div className="flex items-center justify-between mt-5">
        <button onClick={onBack} className="btn-secondary"><ChevronLeft className="w-4 h-4" />Back</button>
        <button onClick={onNext} className="btn-primary" disabled={!mapping || suggesting}>
          Validate mapping <ArrowRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  )
}

function StepValidate({
  validation, validating, allowPartial, setAllowPartial, onNext, onBack,
}: {
  validation: ValidationResult | null
  validating: boolean
  allowPartial: boolean
  setAllowPartial: (v: boolean) => void
  onNext: () => void
  onBack: () => void
}) {
  const [filter, setFilter] = useState('ALL')
  const codes = validation
    ? ['ALL', ...Array.from(new Set(validation.errors.map(e => e.error_code))).slice(0, 4)]
    : ['ALL']
  const errors = (validation?.errors ?? []).filter(e => filter === 'ALL' || e.error_code === filter)

  return (
    <div className="space-y-4">
      {validating ? (
        <div className="card pad flex flex-col items-center justify-center py-16 gap-3">
          <Spinner className="w-8 h-8" />
          <p className="text-sm ink-2">Validating…</p>
        </div>
      ) : validation ? (
        <>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            {[
              { l: 'Total rows', v: validation.total_rows.toLocaleString(), c: '' },
              { l: 'Valid', v: validation.valid_rows.toLocaleString(), c: 'text-emerald-600' },
              { l: 'Invalid', v: validation.invalid_rows.toLocaleString(), c: 'text-rose-600' },
              { l: 'Ready', v: validation.ready_for_execution ? 'Yes' : 'No', c: '' },
              { l: 'Recommendation', v: `Skip ${validation.invalid_rows} · execute ${validation.valid_rows}`, c: 'text-sm' },
            ].map((s, i) => (
              <div key={i} className="card p-3">
                <p className="text-[10px] font-bold tracking-widest uppercase ink-2">{s.l}</p>
                <p className={`font-black mt-1 ${s.c || ''} ${i < 4 ? 'text-2xl' : 'text-sm'}`} style={!s.c ? { color: 'var(--ink)' } : {}}>{s.v}</p>
              </div>
            ))}
          </div>

          <div className="card pad">
            <div className="flex items-center justify-between gap-3 mb-3 flex-wrap">
              <div>
                <p className="text-sm font-bold" style={{ color: 'var(--ink)' }}>Validation errors</p>
                <p className="text-xs ink-2">POST /bulk/validate · {validation.errors.length} errors</p>
              </div>
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-xs ink-2">Filter:</span>
                {codes.slice(0, 5).map(c => (
                  <button key={c} onClick={() => setFilter(c)}
                    className="text-xs px-2.5 py-1 rounded-full border font-mono transition"
                    style={{ borderColor: filter === c ? 'var(--brand)' : 'var(--line)', color: filter === c ? 'var(--brand)' : 'var(--ink-2)' }}>
                    {c}
                  </button>
                ))}
              </div>
            </div>
            <div className="overflow-x-auto rounded-xl max-h-72 overflow-y-auto" style={{ border: '1px solid var(--line)' }}>
              <table className="w-full text-sm">
                <thead className="aria-thead sticky top-0">
                  <tr>{['Row', 'Field', 'Code', 'Message'].map(h => <th key={h} className="text-left px-3 py-2">{h}</th>)}</tr>
                </thead>
                <tbody>
                  {errors.map((e, i) => (
                    <tr key={i} className="border-t" style={{ borderColor: 'var(--line)' }}>
                      <td className="px-3 py-2 font-mono text-xs ink-2">#{e.row_index}</td>
                      <td className="px-3 py-2 font-mono text-xs" style={{ color: 'var(--ink)' }}>{e.field_name ?? '—'}</td>
                      <td className="px-3 py-2"><span className="pill bg-rose-50 text-rose-700 border-rose-200">{e.error_code}</span></td>
                      <td className="px-3 py-2 text-xs" style={{ color: 'var(--ink)' }}>{e.message}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {validation.invalid_rows > 0 && validation.can_execute_partial && (
            <div className="card pad flex items-center gap-3 flex-wrap">
              <Info className="w-5 h-5" style={{ color: 'var(--brand)' }} />
              <p className="text-sm flex-1 min-w-[280px]" style={{ color: 'var(--ink)' }}>
                {validation.invalid_rows} invalid rows can be skipped with{' '}
                <span className="font-mono font-semibold">allow_partial_execution</span>.
              </p>
              <label className="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" checked={allowPartial} onChange={e => setAllowPartial(e.target.checked)} />
                <span className="text-sm font-mono" style={{ color: 'var(--ink)' }}>allow_partial_execution</span>
              </label>
              <button className="btn-secondary text-xs"><Download className="w-3.5 h-3.5" />Export errors</button>
            </div>
          )}
        </>
      ) : (
        <div className="card pad flex flex-col items-center justify-center py-12 gap-2 ink-2">
          <CheckCheck className="w-8 h-8 opacity-30" />
          <p className="text-sm">Validation not run yet</p>
        </div>
      )}

      <div className="flex justify-between">
        <button onClick={onBack} className="btn-secondary"><ChevronLeft className="w-4 h-4" />Back</button>
        <button onClick={onNext} className="btn-primary" disabled={!validation || validating}>
          Run dry-run <ArrowRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  )
}

function StepDryRun({
  dryRunResult, dryRunning, planSteps, onNext, onBack,
}: {
  dryRunResult: DryRunResult | null
  dryRunning: boolean
  planSteps: Array<{ order: number; method: string; path: string }>
  onNext: () => void
  onBack: () => void
}) {
  const formatDuration = (secs: number) => {
    const m = Math.floor(secs / 60)
    const s = Math.floor(secs % 60)
    return m > 0 ? `${m} min ${s} s` : `${s} s`
  }

  return (
    <div className="card pad">
      {dryRunning ? (
        <div className="flex flex-col items-center justify-center py-16 gap-3">
          <Spinner className="w-8 h-8" />
          <p className="text-sm ink-2">Running dry-run simulation…</p>
          <p className="text-xs ink-2">No real request is sent.</p>
        </div>
      ) : dryRunResult ? (
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-6">
          <div>
            <p className="text-sm font-bold mb-1" style={{ color: 'var(--ink)' }}>Dry-run simulation</p>
            <p className="text-xs ink-2 mb-5">POST /bulk/dry-run · No real request.</p>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
              {[
                { l: 'Estimated API calls', v: dryRunResult.estimated_api_calls.toLocaleString(), s: `${dryRunResult.steps_count} steps × ${dryRunResult.valid_rows} rows` },
                { l: 'Estimated duration', v: formatDuration(dryRunResult.estimated_duration_seconds), s: 'estimate' },
                { l: 'Valid rows', v: dryRunResult.valid_rows.toLocaleString() },
                { l: 'Invalid rows', v: dryRunResult.invalid_rows.toLocaleString(), s: 'skipped' },
              ].map((s, i) => (
                <div key={i} className="p-3 rounded-xl" style={{ border: '1px solid var(--line)' }}>
                  <p className="text-[10px] font-bold tracking-widest uppercase ink-2">{s.l}</p>
                  <p className="text-lg font-black mt-1" style={{ color: 'var(--ink)' }}>{s.v}</p>
                  {s.s && <p className="text-xs ink-2 mt-0.5">{s.s}</p>}
                </div>
              ))}
            </div>
            <div className="mt-4 p-3 rounded-xl flex items-start gap-2 text-sm" style={{ background: 'color-mix(in oklch, var(--brand) 6%, var(--card))', border: '1px solid color-mix(in oklch, var(--brand) 30%, var(--line))' }}>
              <Check className="w-4 h-4 mt-0.5 text-emerald-600 flex-shrink-0" />
              <span style={{ color: 'var(--ink)' }}>{dryRunResult.recommendation}</span>
            </div>
          </div>
          <div className="flex flex-col" style={{ borderLeft: '1px solid var(--line)', paddingLeft: '1.5rem' }}>
            <p className="text-sm font-bold mb-3" style={{ color: 'var(--ink)' }}>Volume per step</p>
            <div className="space-y-2 flex-1">
              {planSteps.map(s => (
                <div key={s.order} className="flex items-center gap-2 text-sm">
                  <span className="w-5 h-5 rounded-md grad-bg text-white text-[10px] font-black flex items-center justify-center flex-shrink-0">{s.order + 1}</span>
                  <MethodBadge m={s.method} />
                  <span className="font-mono text-xs flex-1 truncate" style={{ color: 'var(--ink)' }}>{s.path.split('/').slice(-2).join('/')}</span>
                  <span className="font-mono text-xs ink-2">{dryRunResult.valid_rows}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center py-12 gap-2 ink-2">
          <Eye className="w-8 h-8 opacity-30" />
          <p className="text-sm">Dry-run not run yet</p>
        </div>
      )}

      <div className="flex justify-between mt-6 pt-5" style={{ borderTop: '1px solid var(--line)' }}>
        <button onClick={onBack} className="btn-secondary"><ChevronLeft className="w-4 h-4" />Back</button>
        <button onClick={onNext} className="btn-primary" disabled={!dryRunResult || dryRunning}>
          Request approval <ArrowRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  )
}

function StepApproval({
  dryRunResult, planSteps, approval, setApproval, onNext, onBack,
}: {
  dryRunResult: DryRunResult | null
  planSteps: Array<{ order: number; method: string; path: string }>
  approval: boolean
  setApproval: (v: boolean) => void
  onNext: () => void
  onBack: () => void
}) {
  const [confirmed, setConfirmed] = useState(false)

  const validRows = dryRunResult?.valid_rows ?? 0
  const invalidRows = dryRunResult?.invalid_rows ?? 0
  const totalCalls = dryRunResult?.estimated_api_calls ?? 0

  return (
    <div className="card pad">
      <p className="text-sm font-bold" style={{ color: 'var(--ink)' }}>Approval</p>
      <p className="text-xs ink-2 mt-1 mb-5">Required before any live execution. Kept for audit purposes.</p>
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_360px] gap-6">
        <div className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="card p-3">
              <p className="text-[10px] font-bold tracking-widest uppercase ink-2">Rows to execute</p>
              <p className="text-2xl font-black mt-0.5" style={{ color: 'var(--ink)' }}>{validRows.toLocaleString()}</p>
            </div>
            <div className="card p-3">
              <p className="text-[10px] font-bold tracking-widest uppercase ink-2">Skipped</p>
              <p className="text-2xl font-black mt-0.5" style={{ color: 'var(--ink)' }}>{invalidRows.toLocaleString()}</p>
            </div>
            <div className="card p-3">
              <p className="text-[10px] font-bold tracking-widest uppercase ink-2">Risk</p>
              <div className="mt-1.5"><SeverityBadge s="high" /></div>
            </div>
            <div className="card p-3">
              <p className="text-[10px] font-bold tracking-widest uppercase ink-2">HTTP methods</p>
              <div className="mt-1.5 flex gap-1.5 flex-wrap">
                {[...new Set(planSteps.map(s => s.method))].map(m => <MethodBadge key={m} m={m} />)}
              </div>
            </div>
          </div>

          {totalCalls > 0 && (
            <div className="p-4 rounded-xl flex items-start gap-3 text-sm" style={{ background: 'color-mix(in oklch, #f43f5e 8%, var(--card))', border: '1px solid color-mix(in oklch, #f43f5e 30%, var(--line))', color: '#9f1239' }}>
              <TriangleAlert className="w-5 h-5 mt-0.5 flex-shrink-0" />
              <div>
                <p className="font-bold">Live execution will make {totalCalls.toLocaleString()} calls</p>
                <p className="text-xs mt-0.5 opacity-80">This action is irreversible.</p>
              </div>
            </div>
          )}

          <div className="p-4 rounded-xl" style={{ border: '1px solid var(--line)' }}>
            <p className="text-[10px] font-bold tracking-widest uppercase ink-2 mb-2">Target endpoints</p>
            <div className="flex flex-wrap gap-2">
              {planSteps.map(s => (
                <div key={s.order} className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-xs" style={{ border: '1px solid var(--line)' }}>
                  <MethodBadge m={s.method} />
                  <span className="font-mono" style={{ color: 'var(--ink)' }}>{s.path}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div style={{ borderLeft: '1px solid var(--line)', paddingLeft: '1.5rem' }}>
          <p className="text-sm font-bold mb-3" style={{ color: 'var(--ink)' }}>Confirm</p>
          <label className="flex items-start gap-2 cursor-pointer mb-4">
            <input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} className="mt-0.5" />
            <span className="text-sm" style={{ color: 'var(--ink)' }}>I have reviewed the dry-run result and authorize execution.</span>
          </label>
          <button onClick={() => setApproval(true)} disabled={!confirmed}
            className={`w-full mt-4 ${approval ? 'btn-secondary' : 'btn-primary'}`}
            style={{ opacity: confirmed ? 1 : 0.6 }}>
            <Check className="w-4 h-4" /> {approval ? 'Approved ✓' : 'Approve run'}
          </button>
          {approval && (
            <p className="text-xs text-emerald-600 mt-2 text-center">Approval recorded</p>
          )}
        </div>
      </div>

      <div className="flex justify-between mt-6 pt-5" style={{ borderTop: '1px solid var(--line)' }}>
        <button onClick={onBack} className="btn-secondary"><ChevronLeft className="w-4 h-4" />Back</button>
        <button onClick={onNext} disabled={!approval} className="btn-primary" style={{ opacity: approval ? 1 : 0.6 }}>
          Proceed to execution <ArrowRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  )
}

function StepExecute({
  approval, dryRunResult,
  isSimulation, setIsSimulation,
  batchSize, setBatchSize,
  allowPartial, setAllowPartial,
  baseUrl, setBaseUrl,
  execHeaders, setExecHeaders,
  bulkJob, jobProgress, executing,
  tokenStatus, tokenMessage, onTestToken,
  onExecute, onNext, onBack,
}: {
  approval: boolean
  dryRunResult: DryRunResult | null
  isSimulation: boolean
  setIsSimulation: (v: boolean) => void
  batchSize: number
  setBatchSize: (v: number) => void
  allowPartial: boolean
  setAllowPartial: (v: boolean) => void
  baseUrl: string
  setBaseUrl: (v: string) => void
  execHeaders: HeaderRow[]
  setExecHeaders: (r: HeaderRow[]) => void
  bulkJob: BulkExecuteResult | null
  jobProgress: BulkJobProgress | null
  executing: boolean
  tokenStatus: 'idle' | 'testing' | 'valid' | 'error'
  tokenMessage: string
  onTestToken: () => void
  onExecute: () => void
  onNext: () => void
  onBack: () => void
}) {
  const canExecute = isSimulation || approval
  const progress = jobProgress ?? null
  const pct = progress?.progress_pct ?? 0
  const isDone = progress && ['done', 'failed', 'partial'].includes(progress.status)

  return (
    <div className="space-y-4">
      <div className="card pad">
        <div className="flex items-start justify-between gap-3 mb-4 flex-wrap">
          <div>
            <p className="text-sm font-bold" style={{ color: 'var(--ink)' }}>Configure execution</p>
            <p className="text-xs ink-2 mt-1">All the settings below will be applied.</p>
          </div>
          {isSimulation
            ? <span className="pill bg-sky-50 text-sky-700 border-sky-200">Simulation mode</span>
            : <span className="pill bg-rose-50 text-rose-700 border-rose-200 font-bold">Live execution</span>
          }
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <div className="space-y-4">
            <div>
              <p className="text-[10px] font-bold tracking-widest uppercase ink-2 mb-1.5">Target API URL</p>
              <div className="flex gap-2">
                <input value={baseUrl} onChange={e => setBaseUrl(e.target.value)} className="input !py-2 font-mono text-xs flex-1" />
                <button onClick={onTestToken} disabled={!baseUrl || tokenStatus === 'testing'}
                  className="btn-secondary shrink-0 !py-1.5 !px-3 text-xs whitespace-nowrap">
                  {tokenStatus === 'testing' ? <Spinner className="w-3.5 h-3.5" /> : 'Test'}
                </button>
              </div>
              {tokenStatus !== 'idle' && tokenStatus !== 'testing' && (
                <p className={`mt-1.5 text-xs flex items-center gap-1 ${tokenStatus === 'valid' ? 'text-emerald-600' : 'text-rose-600'}`}>
                  {tokenStatus === 'valid' ? <Check className="w-3 h-3" /> : <TriangleAlert className="w-3 h-3" />}
                  {tokenMessage}
                </p>
              )}
            </div>
            <KeyValueEditor label="Authentication headers" rows={execHeaders} setRows={setExecHeaders} />
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-[10px] font-bold tracking-widest uppercase ink-2">Rows per batch</span>
                <span className="font-mono text-xs" style={{ color: 'var(--ink)' }}>{batchSize}</span>
              </div>
              <input type="range" min="10" max="500" step="10" value={batchSize}
                onChange={e => setBatchSize(+e.target.value)} className="w-full" />
            </div>
          </div>
          <div className="space-y-3">
            <ToggleBig label="Simulation mode" hint="ARIA prepares the requests but does not send them" checked={isSimulation} onChange={setIsSimulation} />
            <ToggleBig label="Valid rows only" hint={`Execute only the ${dryRunResult?.valid_rows.toLocaleString() ?? '…'} valid rows`} checked={allowPartial} onChange={setAllowPartial} />
            {!isSimulation && approval && (
              <div className="p-3 rounded-xl flex items-start gap-2 text-xs" style={{ background: 'color-mix(in oklch, #f43f5e 8%, var(--card))', color: '#9f1239', border: '1px solid color-mix(in oklch, #f43f5e 30%, var(--line))' }}>
                <TriangleAlert className="w-4 h-4 mt-0.5 flex-shrink-0" />
                <span>You are about to execute <span className="font-bold">{(dryRunResult?.estimated_api_calls ?? 0).toLocaleString()} requests</span> against <span className="font-mono">{baseUrl}</span>. Irreversible.</span>
              </div>
            )}
          </div>
        </div>

        <div className="flex justify-end mt-5">
          <button onClick={onExecute} disabled={!canExecute || executing || !!bulkJob}
            className={isSimulation ? 'btn-primary' : 'btn-danger'}
            style={{ opacity: canExecute ? 1 : 0.6 }}>
            {executing && !bulkJob
              ? <><Spinner className="w-4 h-4" /> Starting…</>
              : bulkJob
                ? <><Check className="w-4 h-4" /> Started</>
                : <><Play className="w-4 h-4" /> {isSimulation ? 'Run simulation' : "Start execution"}</>
            }
          </button>
        </div>
      </div>

      {bulkJob && (
        <div className="card pad">
          <div className="flex items-start justify-between gap-3 flex-wrap mb-4">
            <div>
              <p className="text-sm font-bold" style={{ color: 'var(--ink)' }}>
                Job #{bulkJob.job_id.slice(0, 8)}…
              </p>
              <div className="flex items-center gap-2 flex-wrap mt-1">
                <StatusBadge s={progress?.status ?? 'queued'} />
                {isSimulation
                  ? <span className="pill bg-sky-50 text-sky-700 border-sky-200">Simulation</span>
                  : <span className="pill bg-rose-50 text-rose-700 border-rose-200">Live execution</span>
                }
              </div>
              <p className="mt-2 font-mono" style={{ color: 'var(--ink)' }}>
                <span className="text-2xl font-black">{progress ? (progress.completed + progress.failed).toLocaleString() : '—'}</span>
                <span className="text-sm ink-2"> / {progress ? progress.total.toLocaleString() : '—'} rows processed</span>
              </p>
            </div>
            <div className="grid grid-cols-3 gap-2 text-center">
              <div className="p-2.5 rounded-lg" style={{ background: 'color-mix(in oklch, #10b981 8%, var(--card))' }}>
                <p className="text-[10px] font-bold uppercase tracking-widest ink-2">Success</p>
                <p className="text-xl font-black text-emerald-600">{progress?.completed ?? '—'}</p>
              </div>
              <div className="p-2.5 rounded-lg" style={{ background: 'color-mix(in oklch, #f43f5e 8%, var(--card))' }}>
                <p className="text-[10px] font-bold uppercase tracking-widest ink-2">Failures</p>
                <p className="text-xl font-black text-rose-600">{progress?.failed ?? '—'}</p>
              </div>
              <div className="p-2.5 rounded-lg" style={{ background: 'color-mix(in oklch, var(--ink) 4%, var(--card))' }}>
                <p className="text-[10px] font-bold uppercase tracking-widest ink-2">Batches</p>
                <p className="text-xl font-black ink-2">{progress ? `${progress.batches_done}/${progress.batches}` : '—'}</p>
              </div>
            </div>
          </div>
          <div className="flex items-center justify-between text-xs ink-2 mb-2">
            <span>Overall progress</span>
            <span className="font-mono">{pct.toFixed(1)}%</span>
          </div>
          <div className="h-3 rounded-full overflow-hidden" style={{ background: 'var(--line)' }}>
            <div className="h-3 rounded-full grad-bg transition-all duration-500" style={{ width: `${pct}%` }} />
          </div>
          {!isDone && (
            <div className="flex items-center gap-2 mt-3">
              <Spinner className="w-4 h-4" />
              <span className="text-xs ink-2">Updating every 3s…</span>
            </div>
          )}
        </div>
      )}

      <div className="flex justify-between">
        <button onClick={onBack} className="btn-secondary"><ChevronLeft className="w-4 h-4" />Back</button>
        <button onClick={onNext} className="btn-primary" disabled={!isDone}>
          View report <ArrowRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  )
}

function StepReport({
  report, loadingReport, onBack, onViewFullReport,
}: {
  report: BulkReport | null
  loadingReport: boolean
  onBack: () => void
  onViewFullReport: (automationRunId: string) => void
}) {
  return (
    <div className="space-y-4">
      {loadingReport ? (
        <div className="card pad flex flex-col items-center justify-center py-16 gap-3">
          <Spinner className="w-8 h-8" />
          <p className="text-sm ink-2">Loading report…</p>
        </div>
      ) : report ? (
        <>
          <div className="card overflow-hidden">
            <div className="p-5 flex items-start justify-between gap-4 flex-wrap aria-hero">
              <div>
                <div className="flex items-center gap-2 flex-wrap mb-1">
                  <h3 className="font-black text-lg" style={{ color: 'var(--ink)' }}>Execution report</h3>
                  <StatusBadge s={report.status} />
                </div>
                <p className="text-sm ink-2">Automation run · {report.automation_run_id.slice(0, 12)}…</p>
              </div>
              <div className="grid grid-cols-2 gap-4 text-right">
                <div>
                  <p className="text-[10px] font-bold tracking-widest uppercase ink-2">Success</p>
                  <p className="text-2xl font-black text-emerald-600">{report.success_count}</p>
                </div>
                <div>
                  <p className="text-[10px] font-bold tracking-widest uppercase ink-2">Failures</p>
                  <p className="text-2xl font-black text-rose-600">{report.failed_count}</p>
                </div>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              { l: 'Success', v: report.success_count.toLocaleString(), c: 'text-emerald-600', s: `${((report.success_count / (report.success_count + report.failed_count)) * 100).toFixed(1)}%` },
              { l: 'Failures', v: report.failed_count.toLocaleString(), c: 'text-rose-600', s: 'to retry' },
              { l: 'Total batches', v: report.batch_summary.length.toLocaleString(), c: '', s: '' },
              { l: 'Status', v: report.status, c: report.status === 'done' ? 'text-emerald-600' : 'text-amber-600', s: '' },
            ].map((s, i) => (
              <div key={i} className="card p-3">
                <p className="text-[10px] font-bold tracking-widest uppercase ink-2">{s.l}</p>
                <p className={`text-2xl font-black mt-1 ${s.c}`} style={!s.c ? { color: 'var(--ink)' } : {}}>{s.v}</p>
                {s.s && <p className="text-xs ink-2 mt-0.5">{s.s}</p>}
              </div>
            ))}
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-[1.4fr_1fr] gap-4">
            <div className="card pad">
              <p className="text-sm font-bold mb-3" style={{ color: 'var(--ink)' }}>Batch summary</p>
              <div className="rounded-xl max-h-80 overflow-y-auto" style={{ border: '1px solid var(--line)' }}>
                <table className="w-full text-sm">
                  <thead className="aria-thead sticky top-0">
                    <tr>{['Batch', 'Rows', 'Success', 'Failures', 'Status'].map(h => <th key={h} className="text-left px-3 py-2">{h}</th>)}</tr>
                  </thead>
                  <tbody>
                    {report.batch_summary.map((b, i) => (
                      <tr key={i} className="border-t" style={{ borderColor: 'var(--line)' }}>
                        <td className="px-3 py-2 font-mono text-xs" style={{ color: 'var(--ink)' }}>Batch {b.batch_index + 1}</td>
                        <td className="px-3 py-2 font-mono text-xs ink-2">
                          {b.start_row != null ? `${b.start_row}–${b.end_row}` : '—'}
                        </td>
                        <td className="px-3 py-2 font-mono text-emerald-600 font-bold">{b.success_count}</td>
                        <td className="px-3 py-2 font-mono text-rose-600">{b.failed_count}</td>
                        <td className="px-3 py-2"><StatusBadge s={b.status} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            <div className="card pad">
              <div className="flex items-center justify-between mb-3">
                <div>
                  <p className="text-sm font-bold" style={{ color: 'var(--ink)' }}>Rows with errors</p>
                  <p className="text-xs ink-2">{report.row_errors.length} rows</p>
                </div>
                <button
                  onClick={() => report && downloadRowErrorsCsv(report.automation_run_id)}
                  className="btn-secondary text-xs">
                  <Download className="w-3.5 h-3.5" /> CSV
                </button>
              </div>
              <div className="rounded-xl max-h-80 overflow-y-auto" style={{ border: '1px solid var(--line)' }}>
                <table className="w-full text-sm">
                  <thead className="aria-thead sticky top-0">
                    <tr>{['Row', 'Code', 'Message'].map(h => <th key={h} className="text-left px-3 py-2">{h}</th>)}</tr>
                  </thead>
                  <tbody>
                    {report.row_errors.slice(0, 20).map((e, i) => (
                      <tr key={i} className="border-t" style={{ borderColor: 'var(--line)' }}>
                        <td className="px-3 py-2 font-mono text-xs ink-2">#{e.row_index}</td>
                        <td className="px-3 py-2"><span className="pill bg-rose-50 text-rose-700 border-rose-200">{e.error_code}</span></td>
                        <td className="px-3 py-2 text-xs truncate max-w-[200px]" style={{ color: 'var(--ink)' }}>{e.message}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </>
      ) : (
        <div className="card pad flex flex-col items-center justify-center py-12 gap-2 ink-2">
          <BarChart2 className="w-8 h-8 opacity-30" />
          <p className="text-sm">Report not available</p>
        </div>
      )}

      <div className="flex justify-between">
        <button onClick={onBack} className="btn-secondary"><ChevronLeft className="w-4 h-4" />Back</button>
        <div className="flex gap-2">
          {report && (
            <button onClick={() => onViewFullReport(report.automation_run_id)} className="btn-primary">
              <BarChart3 className="w-4 h-4" /> View full report
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function BulkPage() {
  const nav = useNavigate()
  const [searchParams] = useSearchParams()
  const { setActiveRun } = useRun()
  const { toast } = useToast()

  // Setup
  const [runs, setRuns] = useState<AnalysisRun[]>([])
  const [selectedRunId, setSelectedRunId] = useState('')
  const [planInstruction, setPlanInstruction] = useState('Create an employee with a permanent contract, open a payroll account, and issue a badge')

  // Job recovery — detect an interrupted bulk job from a previous session
  const [resumableJob, setResumableJob] = useState<{ jobId: string; workflowName: string } | null>(null)
  const [planResult, setPlanResult] = useState<CreatePlanResponse | null>(null)
  const [generatingPlan, setGeneratingPlan] = useState(false)

  // Steps
  const [step, setStep] = useState(0)
  const [apiError, setApiError] = useState('')

  // Step 0: Upload
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [uploadResult, setUploadResult] = useState<DataFileUploadResult | null>(null)
  const [uploading, setUploading] = useState(false)

  // Step 1: Mapping
  const [mappingResult, setMappingResult] = useState<MappingResult | null>(null)
  const [suggesting, setSuggesting] = useState(false)

  // Step 2: Validation
  const [validationResult, setValidationResult] = useState<ValidationResult | null>(null)
  const [validating, setValidating] = useState(false)
  const [allowPartial, setAllowPartial] = useState(true)

  // Step 3: Dry-run
  const [dryRunResult, setDryRunResult] = useState<DryRunResult | null>(null)
  const [dryRunning, setDryRunning] = useState(false)

  // Step 4: Approval
  const [approved, setApproved] = useState(false)

  // Step 5: Execute
  const [isSimulation, setIsSimulation] = useState(true)
  const [baseUrl, setBaseUrl] = useState('')
  const [execHeaders, setExecHeaders] = useState<HeaderRow[]>([
    { k: 'Authorization', v: '' },
  ])
  const [batchSize, setBatchSize] = useState(100)
  const [bulkJob, setBulkJob] = useState<BulkExecuteResult | null>(null)
  const [jobProgress, setJobProgress] = useState<BulkJobProgress | null>(null)
  const [executing, setExecuting] = useState(false)
  const pollingRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Token validation
  const [tokenStatus, setTokenStatus] = useState<'idle' | 'testing' | 'valid' | 'error'>('idle')
  const [tokenMessage, setTokenMessage] = useState('')

  // Workflow picker — plan generated without an LLM call, straight from a saved workflow
  const [loadingWorkflowPlan, setLoadingWorkflowPlan] = useState(false)
  const [workflows, setWorkflows] = useState<BackendWorkflow[]>([])
  const [workflowShortcutId, setWorkflowShortcutId] = useState('')

  // Step 6: Report
  const [bulkReport, setBulkReport] = useState<BulkReport | null>(null)
  const [loadingReport, setLoadingReport] = useState(false)

  // Automation Simple drawer
  const [showSimpleSheet, setShowSimpleSheet] = useState(false)

  const completed = new Set(Array.from({ length: step }, (_, i) => i))

  // Load analysis runs on mount — honour ?run= and ?workflow= query params
  useEffect(() => {
    const paramRun      = searchParams.get('run')
    const paramWorkflow = searchParams.get('workflow')

    listRuns({ limit: 50 }).then(data => {
      setRuns(data.items)
      const initial = data.items.find(r => r.id === paramRun) ?? data.items[0]
      if (initial) {
        setSelectedRunId(initial.id)
        setActiveRun({ id: initial.id, name: initial.file_name })
        // Preselect the workflow the picker below will load once it fetches this run's workflows.
        if (paramWorkflow) setWorkflowShortcutId(paramWorkflow)
      }
    }).catch(() => {})

    // Check for a recoverable bulk job from a previous session
    try {
      const saved = localStorage.getItem('aria_bulk_job')
      if (saved) setResumableJob(JSON.parse(saved) as { jobId: string; workflowName: string })
    } catch { /* ignore */ }
  }, [])

  // Reload the workflow picker whenever the analysis run changes — workflows
  // are scoped to the run they were detected/saved in.
  useEffect(() => {
    if (!selectedRunId) { setWorkflows([]); return }
    getWorkflows(selectedRunId).then(setWorkflows).catch(() => setWorkflows([]))
  }, [selectedRunId])

  // Cleanup polling on unmount
  useEffect(() => {
    return () => { if (pollingRef.current) clearTimeout(pollingRef.current) }
  }, [])

  async function handleWorkflowPlan() {
    if (!workflowShortcutId) return
    setLoadingWorkflowPlan(true)
    setApiError('')
    setPlanResult(null)
    // BUG-006: reset downstream wizard state so stale results from a prior plan
    // never pre-fill the new wizard steps
    setUploadResult(null)
    setMappingResult(null)
    setValidationResult(null)
    setDryRunResult(null)
    setStep(0)
    try {
      const result = await planFromWorkflow(workflowShortcutId)
      setPlanResult(result)
    } catch (e) {
      setApiError(e instanceof Error ? e.message : 'Error converting workflow')
    } finally {
      setLoadingWorkflowPlan(false)
    }
  }

  async function handleTestToken() {
    if (!baseUrl) return
    setTokenStatus('testing')
    setTokenMessage('')
    try {
      const authRow = execHeaders.find(h => h.k.toLowerCase() === 'authorization')
      const authValue = authRow?.v ?? ''
      let tokenType: 'bearer' | 'api_key' | 'basic' = 'bearer'
      let tokenValue = authValue
      if (authValue.toLowerCase().startsWith('bearer ')) {
        tokenType = 'bearer'
        tokenValue = authValue.slice(7).trim()
      } else if (authValue.toLowerCase().startsWith('basic ')) {
        tokenType = 'basic'
        tokenValue = authValue.slice(6).trim()
      } else if (!authValue.includes(' ') && authValue.length > 0) {
        tokenType = 'api_key'
      }
      const result: ValidateTokenResponse = await validateToken(baseUrl, tokenType, tokenValue)
      setTokenStatus(result.valid ? 'valid' : 'error')
      setTokenMessage(result.message)
    } catch (e) {
      setTokenStatus('error')
      setTokenMessage(e instanceof Error ? e.message : 'Network error')
    }
  }

  async function handleGeneratePlan() {
    if (!selectedRunId) return
    setGeneratingPlan(true)
    setApiError('')
    setPlanResult(null)
    // BUG-006: reset downstream wizard state to prevent stale results from a
    // previous plan leaking into the new wizard flow
    setUploadResult(null)
    setMappingResult(null)
    setValidationResult(null)
    setDryRunResult(null)
    setStep(0)
    try {
      const result = await createPlan(selectedRunId, planInstruction, 8)
      setPlanResult(result)
    } catch (e) {
      setApiError(e instanceof Error ? e.message : 'Error generating plan')
    } finally {
      setGeneratingPlan(false)
    }
  }

  async function handleUpload() {
    if (!uploadFile || !planResult) return
    setUploading(true)
    setApiError('')
    try {
      const result = await uploadDataFile(uploadFile, selectedRunId)
      setUploadResult(result)
      setStep(1)
      // Auto-trigger mapping with fresh result
      setSuggesting(true)
      try {
        const mapping = await suggestMapping(selectedRunId, result.data_file_id, planResult.plan)
        setMappingResult(mapping)
      } catch (e) {
        setApiError(e instanceof Error ? e.message : 'Mapping error')
      } finally {
        setSuggesting(false)
      }
    } catch (e) {
      setApiError(e instanceof Error ? e.message : 'Upload error')
    } finally {
      setUploading(false)
    }
  }

  async function handleGoValidation() {
    if (!uploadResult || !planResult) return
    setStep(2)
    if (validationResult) return
    setValidating(true)
    setApiError('')
    try {
      const result = await validateBulk(selectedRunId, uploadResult.data_file_id, planResult.plan)
      setValidationResult(result)
    } catch (e) {
      setApiError(e instanceof Error ? e.message : 'Validation error')
    } finally {
      setValidating(false)
    }
  }

  async function handleGoDryRun() {
    if (!uploadResult || !planResult) return
    setStep(3)
    if (dryRunResult) return
    setDryRunning(true)
    setApiError('')
    try {
      const result = await dryRunBulk(uploadResult.data_file_id, planResult.plan, allowPartial)
      setDryRunResult(result)
    } catch (e) {
      setApiError(e instanceof Error ? e.message : 'Dry-run error')
    } finally {
      setDryRunning(false)
    }
  }

  async function handleExecute() {
    if (!uploadResult || !planResult) return
    setExecuting(true)
    setApiError('')
    try {
      const headersObj = Object.fromEntries(execHeaders.filter(h => h.k).map(h => [h.k, h.v]))
      const result = await executeBulk(
        planResult.plan,
        uploadResult.data_file_id,
        baseUrl,
        headersObj,
        isSimulation,
        batchSize,
        allowPartial,
        approved,
      )
      setBulkJob(result)
      // Persist job for recovery across page reloads
      localStorage.setItem('aria_bulk_job', JSON.stringify({
        jobId: result.job_id,
        workflowName: planResult?.plan.workflow_name ?? 'Bulk run',
      }))

      // Persist approval record in DB when it's a real (non-simulation) run
      if (!isSimulation && approved) {
        try {
          await recordApproval(result.automation_run_id, 'Approved via BulkPage')
        } catch { /* non-blocking — execution already started */ }
      }

      // Poll for progress with exponential backoff using recursive setTimeout
      let pollInterval = 3000
      const MAX_POLL_MS = 45 * 60 * 1000  // 45 min hard limit
      const pollStartTime = Date.now()

      const schedulePoll = () => {
        pollingRef.current = setTimeout(async () => {
          // Hard timeout — stop polling and show actionable error
          if (Date.now() - pollStartTime > MAX_POLL_MS) {
            setExecuting(false)
            setApiError('The job appears stuck (45 min timeout). Check the worker logs or view the partial report.')
            return
          }

          try {
            const progress = await getBulkJobProgress(result.job_id)
            setJobProgress(progress)
            if (['done', 'failed', 'partial'].includes(progress.status)) {
              pollingRef.current = null
              setExecuting(false)
              localStorage.removeItem('aria_bulk_job')
              setResumableJob(null)
              const successRate = progress.total > 0
                ? `${progress.completed}/${progress.total} succeeded`
                : 'Completed'
              toast({
                type: progress.status === 'done' ? 'success' : 'warning',
                message: `Bulk run completed · ${successRate}`,
                action: { label: 'Report →', onClick: () => nav(`/reports?tab=automation&run=${progress.automation_run_id}`) },
              })
            } else {
              pollInterval = Math.min(pollInterval * 1.3, 15000)
              schedulePoll()
            }
          } catch {
            schedulePoll() // retry on transient network error
          }
        }, pollInterval)
      }
      schedulePoll()
    } catch (e) {
      setApiError(e instanceof Error ? e.message : "Execution error")
      setExecuting(false)
    }
  }

  async function handleGoReport() {
    setStep(6)
    if (bulkReport) return
    const runId = jobProgress?.automation_run_id ?? bulkJob?.automation_run_id
    if (!runId) return
    setLoadingReport(true)
    try {
      const report = await getBulkReport(runId)
      setBulkReport(report)
    } catch (e) {
      setApiError(e instanceof Error ? e.message : 'Error loading report')
    } finally {
      setLoadingReport(false)
    }
  }

  const planSteps = planResult?.plan.steps.map(s => ({
    order: s.order,
    method: s.method,
    path: s.path,
  })) ?? []

  return (
    <AppLayout>
      <div className="p-6 space-y-6">
        {/* Header */}
        <div className="flex items-end justify-between gap-4 flex-wrap">
          <div>
            <h2 className="text-xl font-black" style={{ color: 'var(--ink)' }}>Bulk Automation</h2>
            <p className="text-sm ink-2 mt-1">Large-scale processing mode · CSV / Excel · 1,200 rows or more.</p>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => nav('/approvals')} className="btn-secondary"><Inbox className="w-4 h-4" /> Approvals</button>
            <button onClick={() => nav('/reports')} className="btn-secondary"><BarChart3 className="w-4 h-4" /> Reports</button>
          </div>
        </div>

        {/* Resumable job banner */}
        {resumableJob && !bulkJob && (
          <div className="card pad flex items-center gap-4"
            style={{ background: 'color-mix(in oklch, #f59e0b 8%, var(--card))', border: '1px solid color-mix(in oklch, #f59e0b 30%, var(--line))' }}>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-bold" style={{ color: 'var(--ink)' }}>Interrupted job detected</p>
              <p className="text-xs ink-2 mt-0.5">{resumableJob.workflowName} · resume tracking from the current progress</p>
            </div>
            <button onClick={() => {
              setStep(5)
              setBulkJob({ job_id: resumableJob.jobId } as BulkExecuteResult)
            }} className="btn-primary text-xs whitespace-nowrap">
              Resume tracking →
            </button>
            <button onClick={() => {
              setResumableJob(null)
              localStorage.removeItem('aria_bulk_job')
            }} className="btn-ghost text-xs">Dismiss</button>
          </div>
        )}

        {/* Info banner */}
        <div className="card overflow-hidden">
          <div className="grid lg:grid-cols-[1fr_auto] items-stretch">
            <div className="p-5 flex items-start gap-4">
              <div className="w-10 h-10 rounded-xl grad-bg text-white flex items-center justify-center flex-shrink-0"><Layers className="w-5 h-5" /></div>
              <div>
                <p className="font-bold" style={{ color: 'var(--ink)' }}>Process a CSV/Excel file at scale</p>
                <p className="text-sm ink-2 mt-1 max-w-2xl">Run an API workflow on a large volume of data — e.g. create 1,200 hires from an HR export.</p>
              </div>
            </div>
            <div className="p-5 flex items-center" style={{ background: 'color-mix(in oklch, var(--brand) 4%, var(--card))', borderLeft: '1px solid var(--line)' }}>
              <button onClick={() => setShowSimpleSheet(true)} className="btn-secondary"><FlaskConical className="w-4 h-4" /> Simple Automation</button>
            </div>
          </div>
        </div>

        {/* Plan setup panel */}
        <div className="card pad">
          <div className="flex items-center gap-2 mb-4">
            <Zap className="w-5 h-5" style={{ color: 'var(--brand)' }} />
            <p className="font-bold" style={{ color: 'var(--ink)' }}>
              {planResult ? 'Active automation plan' : 'Configure the automation plan'}
            </p>
            {planResult && <span className="pill bg-emerald-50 text-emerald-700 border-emerald-200">Generated ✓</span>}
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-[180px_200px_1fr_auto] gap-3 items-end">
            <div>
              <p className="text-[10px] font-bold tracking-widest uppercase ink-2 mb-1.5">Analysis run</p>
              <select value={selectedRunId} onChange={e => setSelectedRunId(e.target.value)} className="input !py-2 text-xs">
                {runs.length === 0 && <option value="">Loading…</option>}
                {runs.map(r => (
                  <option key={r.id} value={r.id}>{r.file_name.slice(0, 30)} — {r.id.slice(0, 8)}</option>
                ))}
              </select>
            </div>
            <div>
              <p className="text-[10px] font-bold tracking-widest uppercase ink-2 mb-1.5">Existing workflow (optional)</p>
              <select value={workflowShortcutId} onChange={e => setWorkflowShortcutId(e.target.value)} className="input !py-2 text-xs">
                <option value="">— Write an instruction instead —</option>
                {workflows.map(w => (
                  <option key={w.id} value={w.id}>{w.name} · {w.steps.length} steps</option>
                ))}
              </select>
            </div>
            <div>
              <p className="text-[10px] font-bold tracking-widest uppercase ink-2 mb-1.5">Instruction</p>
              <input value={planInstruction} onChange={e => setPlanInstruction(e.target.value)}
                className="input !py-2 text-xs" placeholder="E.g.: Create an employee with a permanent contract…" />
            </div>
            <div className="flex gap-2">
              {workflowShortcutId && (
                <button onClick={handleWorkflowPlan} disabled={loadingWorkflowPlan || !!planResult}
                  className="btn-secondary whitespace-nowrap" title="Convert the selected workflow to a plan without an AI call">
                  {loadingWorkflowPlan ? <><Spinner className="w-4 h-4" /> Converting…</> : <><Layers className="w-4 h-4" /> Use this workflow</>}
                </button>
              )}
              <button onClick={handleGeneratePlan} disabled={!selectedRunId || generatingPlan} className="btn-primary whitespace-nowrap">
                {generatingPlan ? <><Spinner className="w-4 h-4" /> Generating…</> : <><Zap className="w-4 h-4" /> Generate plan</>}
              </button>
            </div>
          </div>
          {planResult && (
            <div className="mt-3 p-3 rounded-xl" style={{ background: 'color-mix(in oklch, var(--brand) 5%, var(--card))', border: '1px solid color-mix(in oklch, var(--brand) 25%, var(--line))' }}>
              <p className="text-xs font-semibold mb-2" style={{ color: 'var(--brand)' }}>
                {planResult.plan.workflow_name} · {planResult.plan.steps.length} steps
              </p>
              <div className="flex items-center gap-3 mb-2 flex-wrap">
                <div className="flex items-center gap-2 min-w-[140px]">
                  <span className="text-[10px] font-bold tracking-widest uppercase ink-2">AI confidence</span>
                  <div className="flex-1 h-1.5 rounded-full overflow-hidden" style={{ background: 'var(--line)', minWidth: 60 }}>
                    <div className="h-1.5 rounded-full grad-bg" style={{ width: `${planResult.plan.intent.confidence * 100}%` }} />
                  </div>
                  <span className={`font-mono text-xs ${planResult.plan.intent.confidence >= 0.9 ? 'text-emerald-600' : planResult.plan.intent.confidence >= 0.7 ? 'text-amber-600' : 'text-rose-600'}`}>
                    {planResult.plan.intent.confidence.toFixed(2)}
                  </span>
                </div>
                {planResult.plan.intent.business_domain && (
                  <span className="pill text-xs" style={{ border: '1px solid var(--line)', background: 'var(--card)' }}>
                    domain: {planResult.plan.intent.business_domain}
                  </span>
                )}
                {planResult.plan.intent.entities.map(entity => (
                  <span key={entity} className="pill text-xs" style={{ border: '1px solid var(--line)', background: 'var(--card)' }}>
                    {entity}
                  </span>
                ))}
              </div>
              <div className="flex flex-wrap gap-2">
                {planResult.plan.steps.map(s => (
                  <div key={s.order} className="flex items-center gap-1.5 text-xs px-2 py-1 rounded-lg" style={{ border: '1px solid var(--line)', background: 'var(--card)' }}>
                    <MethodBadge m={s.method} />
                    <span className="font-mono" style={{ color: 'var(--ink)' }}>{s.path.split('/').slice(-2).join('/')}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* API Error */}
        {apiError && (
          <div className="p-4 rounded-xl flex items-start gap-3 text-sm" style={{ background: 'color-mix(in oklch, #f43f5e 8%, var(--card))', border: '1px solid color-mix(in oklch, #f43f5e 30%, var(--line))', color: '#9f1239' }}>
            <TriangleAlert className="w-5 h-5 mt-0.5 flex-shrink-0" />
            <span className="flex-1">{apiError}</span>
            <button onClick={() => setApiError('')}><X className="w-4 h-4" /></button>
          </div>
        )}

        {/* Stepper */}
        <div className="card p-5">
          <div className="flex items-center w-full">
            {STEPS.map((s, i) => {
              const { Icon } = s
              const done = completed.has(i), isCurrent = step === i, reachable = i <= step
              return (
                <div key={s.key} className="flex items-center flex-1 min-w-0">
                  <button onClick={() => reachable && setStep(i)} disabled={!reachable}
                    className="flex flex-col items-center gap-1.5 shrink-0 transition"
                    style={{ opacity: reachable ? 1 : 0.4, cursor: reachable ? 'pointer' : 'not-allowed' }}>
                    <div className="w-10 h-10 rounded-xl flex items-center justify-center transition"
                      style={done ? { background: 'linear-gradient(135deg,var(--brand),var(--accent))', color: 'white' }
                        : isCurrent ? { border: '2px solid var(--brand)', color: 'var(--brand)', background: 'color-mix(in oklch, var(--brand) 8%, var(--card))' }
                          : { border: '1px solid var(--line)', color: 'var(--ink-2)' }}>
                      {done ? <Check className="w-5 h-5" /> : <Icon className="w-5 h-5" />}
                    </div>
                    <span className="text-xs font-medium" style={{ color: isCurrent ? 'var(--brand)' : done ? 'var(--ink)' : 'var(--ink-2)' }}>{s.label}</span>
                  </button>
                  {i < STEPS.length - 1 && (
                    <div className="flex-1 h-0.5 mx-2 rounded-full step-line" style={{ marginBottom: 18 }} data-done={i < step ? 'true' : undefined} />
                  )}
                </div>
              )
            })}
          </div>
        </div>

        {/* Step content */}
        {step === 0 && (
          <StepUpload
            uploadFile={uploadFile} setUploadFile={setUploadFile}
            uploadResult={uploadResult} uploading={uploading}
            onNext={handleUpload} hasPlan={!!planResult}
          />
        )}
        {step === 1 && (
          <StepMapping
            mapping={mappingResult} suggesting={suggesting}
            onNext={handleGoValidation} onBack={() => setStep(0)}
          />
        )}
        {step === 2 && (
          <StepValidate
            validation={validationResult} validating={validating}
            allowPartial={allowPartial} setAllowPartial={setAllowPartial}
            onNext={handleGoDryRun} onBack={() => setStep(1)}
          />
        )}
        {step === 3 && (
          <StepDryRun
            dryRunResult={dryRunResult} dryRunning={dryRunning}
            planSteps={planSteps}
            onNext={() => setStep(4)} onBack={() => setStep(2)}
          />
        )}
        {step === 4 && (
          <StepApproval
            dryRunResult={dryRunResult} planSteps={planSteps}
            approval={approved} setApproval={setApproved}
            onNext={() => setStep(5)} onBack={() => setStep(3)}
          />
        )}
        {step === 5 && (
          <StepExecute
            approval={approved} dryRunResult={dryRunResult}
            isSimulation={isSimulation} setIsSimulation={setIsSimulation}
            batchSize={batchSize} setBatchSize={setBatchSize}
            allowPartial={allowPartial} setAllowPartial={setAllowPartial}
            baseUrl={baseUrl} setBaseUrl={setBaseUrl}
            execHeaders={execHeaders} setExecHeaders={setExecHeaders}
            bulkJob={bulkJob} jobProgress={jobProgress} executing={executing}
            tokenStatus={tokenStatus} tokenMessage={tokenMessage} onTestToken={handleTestToken}
            onExecute={handleExecute} onNext={handleGoReport} onBack={() => setStep(4)}
          />
        )}
        {step === 6 && (
          <StepReport
            report={bulkReport} loadingReport={loadingReport}
            onBack={() => setStep(5)}
            onViewFullReport={(runId) => nav(`/reports?tab=automation&run=${runId}`)}
          />
        )}
      </div>

      <AutomationSimpleDrawer open={showSimpleSheet} onClose={() => setShowSimpleSheet(false)} />
    </AppLayout>
  )
}
