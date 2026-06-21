import { useState } from 'react'
import AppLayout from '../components/layout/AppLayout'
import { RefreshCw, Check, Shield } from 'lucide-react'

function Toggle({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <button onClick={() => onChange(!checked)} className="w-9 h-5 rounded-full relative flex-shrink-0 transition"
      style={{ background: checked ? 'linear-gradient(90deg, var(--brand), var(--accent))' : 'var(--line)' }}>
      <span className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform ${checked ? 'translate-x-4' : ''}`} />
    </button>
  )
}

function Section({ title, sub, children }: { title: string; sub: string; children: React.ReactNode }) {
  return (
    <div className="card pad">
      <div className="mb-4">
        <p className="text-sm font-bold" style={{ color: 'var(--ink)' }}>{title}</p>
        <p className="text-xs ink-2 mt-0.5 max-w-md">{sub}</p>
      </div>
      <div className="space-y-4">{children}</div>
    </div>
  )
}

function Field({ label, sub, mono, children }: { label: string; sub?: string; mono?: boolean; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[180px_1fr] gap-4 items-start">
      <div>
        <p className={`text-sm ${mono ? 'font-mono' : 'font-medium'}`} style={{ color: 'var(--ink)' }}>{label}</p>
        {sub && <p className="text-xs ink-2 mt-0.5">{sub}</p>}
      </div>
      <div className="min-w-0">{children}</div>
    </div>
  )
}

export default function SettingsPage() {
  const [baseUrl, setBaseUrl] = useState('http://localhost:8000')
  const [allowedDomains, setAllowedDomains] = useState('hr-api.northwind.io\npayroll.northwind.io\nstaging-api.northwind.io')
  const [batchSize, setBatchSize] = useState(100)
  const [dryDefault, setDryDefault] = useState(true)
  const [oauth, setOauth] = useState(true)
  const [authStrategy, setAuthStrategy] = useState('bearer')
  const [maskLogs, setMaskLogs] = useState(true)

  return (
    <AppLayout>
      <div className="p-6 space-y-6">
        <div className="flex items-end justify-between gap-4">
          <div>
            <h2 className="text-xl font-black" style={{ color: 'var(--ink)' }}>Settings</h2>
            <p className="text-sm ink-2 mt-1">Admin-only · workspace-wide configuration</p>
          </div>
          <div className="flex items-center gap-2">
            <button className="btn-secondary"><RefreshCw className="w-4 h-4" /> Discard</button>
            <button className="btn-primary"><Check className="w-4 h-4" /> Save changes</button>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <Section title="Connection" sub="Where the ARIA frontend talks to the FastAPI backend.">
            <Field label="API Base URL" mono>
              <input value={baseUrl} onChange={e => setBaseUrl(e.target.value)} className="input" />
            </Field>
            <Field label="Allowed target domains" mono sub="Bulk runs are only allowed to call these hosts.">
              <textarea rows={3} value={allowedDomains} onChange={e => setAllowedDomains(e.target.value)} className="input resize-none" />
            </Field>
            <Field label="Backend health" sub="Live ping check">
              <div className="flex items-center gap-2 px-3 py-2 rounded-xl" style={{ border: '1px solid var(--line)' }}>
                <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                <span className="text-sm font-mono" style={{ color: 'var(--ink)' }}>healthy · 38ms · v2.4.1</span>
              </div>
            </Field>
          </Section>

          <Section title="Execution defaults" sub="Applied to every new automation run unless overridden.">
            <Field label="Default batch size" sub="Used by Bulk → Execute">
              <div className="flex items-center gap-3">
                <input type="range" min="10" max="500" step="10" value={batchSize} onChange={e => setBatchSize(+e.target.value)}
                  className="flex-1 accent-[color:var(--brand)]" />
                <span className="font-mono text-sm w-12 text-right" style={{ color: 'var(--ink)' }}>{batchSize}</span>
              </div>
            </Field>
            <Field label="dry_run by default" mono sub="Recommended ON · prevents accidental writes">
              <Toggle checked={dryDefault} onChange={setDryDefault} />
            </Field>
            <Field label="OAuth client enabled" mono sub="Acquire tokens automatically for target APIs">
              <Toggle checked={oauth} onChange={setOauth} />
            </Field>
          </Section>

          <Section title="Authentication strategy" sub="How ARIA acquires credentials for target APIs at execution time.">
            <div className="grid grid-cols-3 gap-2">
              {[
                { v: 'bearer',   l: 'Bearer token', d: 'Static Authorization header' },
                { v: 'oauth_cc', l: 'OAuth client',  d: 'Client credentials flow' },
                { v: 'apikey',   l: 'API key',        d: 'Header or query param' },
              ].map(o => (
                <button key={o.v} onClick={() => setAuthStrategy(o.v)}
                  className="p-3 rounded-xl border text-left transition"
                  style={{
                    borderColor: authStrategy === o.v ? 'var(--brand)' : 'var(--line)',
                    background: authStrategy === o.v ? 'color-mix(in oklch, var(--brand) 6%, var(--card))' : 'var(--card)',
                  }}>
                  <p className="font-bold text-sm" style={{ color: authStrategy === o.v ? 'var(--brand)' : 'var(--ink)' }}>{o.l}</p>
                  <p className="text-xs ink-2 mt-0.5">{o.d}</p>
                </button>
              ))}
            </div>
          </Section>

          <Section title="Security & logging" sub="Frontend never sees secrets — these settings control what the backend masks before sending logs back.">
            <Field label="Mask sensitive log keys" sub="authorization, token, cookie, api-key, password, client_secret">
              <Toggle checked={maskLogs} onChange={setMaskLogs} />
            </Field>
            <div className="p-3 rounded-xl flex items-start gap-2" style={{ background: 'color-mix(in oklch, var(--brand) 6%, var(--card))', border: '1px solid color-mix(in oklch, var(--brand) 30%, var(--line))' }}>
              <Shield className="w-4 h-4 mt-0.5" style={{ color: 'var(--brand)' }} />
              <div className="text-xs">
                <p className="font-bold" style={{ color: 'var(--ink)' }}>No client secrets stored client-side.</p>
                <p className="ink-2 mt-0.5">All OAuth client secrets, bearer tokens, and API keys are held by the FastAPI backend (localStorage is never used for credentials).</p>
              </div>
            </div>
          </Section>
        </div>
      </div>
    </AppLayout>
  )
}
