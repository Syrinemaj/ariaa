import { useEffect, useState } from 'react'
import AppLayout from '../components/layout/AppLayout'
import { useToast } from '../contexts/ToastContext'
import {
  getPolicy, updatePolicy, listForbiddenRules, createForbiddenRule, deleteForbiddenRule,
  GovernancePolicy, ForbiddenEndpointRule, EnvironmentPolicyMode,
} from '../lib/governanceApi'
import { ApiError } from '../lib/api'
import { Shield, Save, Loader2, Plus, Trash2 } from 'lucide-react'

const ENVS: Array<'test' | 'preprod' | 'prod'> = ['test', 'preprod', 'prod']
const ENV_LABEL: Record<string, string> = { test: 'Test', preprod: 'Preprod', prod: 'Prod' }

const MODES: { value: EnvironmentPolicyMode; label: string; hint: string }[] = [
  { value: 'full_access', label: 'Full access', hint: 'No restriction' },
  { value: 'writes_require_approval', label: 'Writes need approval', hint: 'Reads run freely; writes need an admin' },
  { value: 'read_only', label: 'Read-only', hint: 'Any write step is blocked' },
  { value: 'forbidden', label: 'Forbidden', hint: 'Nothing may run here' },
]

const METHODS = ['', 'GET', 'POST', 'PUT', 'PATCH', 'DELETE']

export default function GovernancePage() {
  const { toast } = useToast()
  const [policy, setPolicy] = useState<GovernancePolicy | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  const [low, setLow] = useState(1)
  const [high, setHigh] = useState(10)
  const [envPolicies, setEnvPolicies] = useState<Record<string, EnvironmentPolicyMode>>({})

  const [rules, setRules] = useState<ForbiddenEndpointRule[]>([])
  const [rulesLoading, setRulesLoading] = useState(true)
  const [newMethod, setNewMethod] = useState('')
  const [newPattern, setNewPattern] = useState('')
  const [ruleError, setRuleError] = useState('')
  const [addingRule, setAddingRule] = useState(false)
  const [deletingRuleId, setDeletingRuleId] = useState<string | null>(null)

  const load = () => {
    setLoading(true)
    getPolicy()
      .then(p => {
        setPolicy(p)
        setLow(p.risk_threshold_low)
        setHigh(p.risk_threshold_high)
        setEnvPolicies(p.environment_policies)
      })
      .catch(() => {})
      .finally(() => setLoading(false))

    setRulesLoading(true)
    listForbiddenRules()
      .then(r => setRules(r.rules))
      .catch(() => {})
      .finally(() => setRulesLoading(false))
  }

  useEffect(() => { load() }, [])

  async function handleSave() {
    setSaving(true)
    try {
      const updated = await updatePolicy({
        risk_threshold_low: low,
        risk_threshold_high: high,
        environment_policies: envPolicies as Record<'test' | 'preprod' | 'prod', EnvironmentPolicyMode>,
      })
      setPolicy(updated)
      toast({ type: 'success', message: 'Governance policy saved.' })
    } catch (e) {
      toast({ type: 'error', message: e instanceof ApiError ? e.message : 'Could not save policy.' })
    } finally {
      setSaving(false)
    }
  }

  async function handleAddRule() {
    setRuleError('')
    if (!newPattern.trim()) {
      setRuleError('Path pattern is required (e.g. /employees/*).')
      return
    }
    setAddingRule(true)
    try {
      const rule = await createForbiddenRule({ method: newMethod || undefined, path_pattern: newPattern.trim() })
      setRules(r => [rule, ...r])
      setNewMethod('')
      setNewPattern('')
      toast({ type: 'success', message: 'Forbidden rule added.' })
    } catch (e) {
      setRuleError(e instanceof ApiError ? e.message : 'Could not add rule.')
    } finally {
      setAddingRule(false)
    }
  }

  async function handleDeleteRule(id: string) {
    setDeletingRuleId(id)
    try {
      await deleteForbiddenRule(id)
      setRules(r => r.filter(x => x.id !== id))
    } catch (e) {
      toast({ type: 'error', message: e instanceof ApiError ? e.message : 'Could not delete rule.' })
    } finally {
      setDeletingRuleId(null)
    }
  }

  const unsaved = policy && (low !== policy.risk_threshold_low || high !== policy.risk_threshold_high
    || JSON.stringify(envPolicies) !== JSON.stringify(policy.environment_policies))

  return (
    <AppLayout>
      <div className="p-6 space-y-6 max-w-[900px]">
        <div>
          <h2 className="text-xl font-black flex items-center gap-2" style={{ color: 'var(--ink)' }}>
            <Shield className="w-5 h-5" style={{ color: 'var(--brand)' }} /> Governance
          </h2>
          <p className="text-sm mt-1 ink-2">
            Limits enforced automatically on every automation plan, server-side, before execution. Admin approval can never override a block.
          </p>
        </div>

        {/* ── Risk thresholds ─────────────────────────────────────────────── */}
        <div className="card pad space-y-4">
          <div>
            <p className="text-sm font-bold" style={{ color: 'var(--ink)' }}>Risk thresholds</p>
            <p className="text-xs ink-2 mt-1">
              Plan risk score = highest-risk step (low=1, medium=5, high=10). Below the low threshold, operators execute directly.
              Between the two, admin approval is required. Above the high threshold, execution is blocked outright.
            </p>
          </div>
          {loading ? (
            <p className="text-sm ink-2 flex items-center gap-2"><Loader2 className="w-4 h-4 animate-spin" /> Loading…</p>
          ) : (
            <div className="grid grid-cols-2 gap-4 max-w-[400px]">
              <div>
                <p className="text-[10px] font-bold tracking-widest uppercase mb-1.5" style={{ color: 'var(--ink-2)' }}>Low threshold</p>
                <input type="number" min={0} className="input" value={low} onChange={e => setLow(Number(e.target.value))} />
              </div>
              <div>
                <p className="text-[10px] font-bold tracking-widest uppercase mb-1.5" style={{ color: 'var(--ink-2)' }}>High threshold</p>
                <input type="number" min={0} className="input" value={high} onChange={e => setHigh(Number(e.target.value))} />
              </div>
            </div>
          )}
        </div>

        {/* ── Environment policies ────────────────────────────────────────── */}
        <div className="card pad space-y-4">
          <div>
            <p className="text-sm font-bold" style={{ color: 'var(--ink)' }}>Per-environment access</p>
            <p className="text-xs ink-2 mt-1">Set by each connection's environment — independent of risk score.</p>
          </div>
          {!loading && (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {ENVS.map(env => (
                <div key={env}>
                  <p className="text-[10px] font-bold tracking-widest uppercase mb-1.5" style={{ color: 'var(--ink-2)' }}>{ENV_LABEL[env]}</p>
                  <select
                    className="input text-xs"
                    value={envPolicies[env] ?? 'full_access'}
                    onChange={e => setEnvPolicies(p => ({ ...p, [env]: e.target.value as EnvironmentPolicyMode }))}
                  >
                    {MODES.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
                  </select>
                  <p className="text-[11px] mt-1 ink-2">{MODES.find(m => m.value === envPolicies[env])?.hint}</p>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="flex justify-end">
          <button onClick={handleSave} disabled={saving || loading || !unsaved} className="btn-primary" style={{ opacity: unsaved ? 1 : 0.5 }}>
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />} Save policy
          </button>
        </div>

        {/* ── Forbidden endpoint rules ─────────────────────────────────────── */}
        <div className="card overflow-hidden">
          <div className="p-4" style={{ borderBottom: '1px solid var(--line)' }}>
            <p className="text-sm font-bold" style={{ color: 'var(--ink)' }}>Forbidden endpoints</p>
            <p className="text-xs ink-2 mt-1">Method + path pattern (wildcards allowed, e.g. DELETE /employees/*). A matching call is rejected before approval.</p>
          </div>
          <div className="p-4 flex flex-wrap items-end gap-2" style={{ borderBottom: '1px solid var(--line)' }}>
            <div>
              <p className="text-[10px] font-bold tracking-widest uppercase mb-1.5" style={{ color: 'var(--ink-2)' }}>Method</p>
              <select className="input !w-auto text-xs" value={newMethod} onChange={e => setNewMethod(e.target.value)}>
                {METHODS.map(m => <option key={m} value={m}>{m || 'Any'}</option>)}
              </select>
            </div>
            <div className="flex-1 min-w-[220px]">
              <p className="text-[10px] font-bold tracking-widest uppercase mb-1.5" style={{ color: 'var(--ink-2)' }}>Path pattern</p>
              <input className="input font-mono text-xs" value={newPattern} onChange={e => setNewPattern(e.target.value)} placeholder="/employees/*" autoComplete="off" />
            </div>
            <button onClick={handleAddRule} disabled={addingRule} className="btn-secondary">
              {addingRule ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />} Add rule
            </button>
          </div>
          {ruleError && (
            <div className="px-4 py-2 text-sm font-medium" style={{ color: '#ef4444' }}>{ruleError}</div>
          )}
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="aria-thead">
                <tr>
                  {['Method', 'Path pattern', ''].map(h => <th key={h} className="text-left px-4 py-2.5">{h}</th>)}
                </tr>
              </thead>
              <tbody>
                {rulesLoading && (
                  <tr><td colSpan={3} className="px-4 py-8 text-center text-sm ink-2">Loading…</td></tr>
                )}
                {!rulesLoading && rules.length === 0 && (
                  <tr><td colSpan={3} className="px-4 py-8 text-center text-sm ink-2">No forbidden rule yet.</td></tr>
                )}
                {rules.map(r => (
                  <tr key={r.id} className="border-t" style={{ borderColor: 'var(--line)' }}>
                    <td className="px-4 py-2.5">
                      <span className="pill bg-rose-50 text-rose-700 border-rose-200 font-mono text-xs">{r.method ?? 'ANY'}</span>
                    </td>
                    <td className="px-4 py-2.5 font-mono text-xs" style={{ color: 'var(--ink)' }}>{r.path_pattern}</td>
                    <td className="px-4 py-2.5 text-right">
                      <button onClick={() => handleDeleteRule(r.id)} disabled={deletingRuleId === r.id} className="btn-ghost !p-1.5" title="Delete rule">
                        {deletingRuleId === r.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </AppLayout>
  )
}
