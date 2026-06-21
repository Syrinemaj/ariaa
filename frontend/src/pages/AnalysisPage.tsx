import { useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import AppLayout from '../components/layout/AppLayout'
import { MethodBadge } from '../components/aria/Badges'
import { useHarAnalysis } from '../hooks/useHarAnalysis'
import { Upload, Play, RefreshCw, Sparkles, Search, ArrowRight, FileCode2, Lock, Unlock, Database, Check } from 'lucide-react'

export default function AnalysisPage() {
  const nav = useNavigate()
  const [filename, setFilename] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [query, setQuery] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)

  const {
    phase,
    result,
    endpoints,
    indexState,
    searchResults,
    searching,
    error,
    upload,
    triggerIndex,
    search,
  } = useHarAnalysis()

  const isLoading   = phase === 'uploading' || phase === 'processing'
  const showResults = phase === 'done' && result !== null
  const indexed     = indexState === 'done'

  function handleFileSelect(f: File) {
    setFile(f)
    setFilename(f.name)
  }

  return (
    <AppLayout>
      <div className="p-6 space-y-6">
        <div className="flex items-end justify-between gap-4 flex-wrap">
          <div>
            <h2 className="text-xl font-black" style={{ color: 'var(--ink)' }}>Analyse a HAR capture</h2>
            <p className="text-sm ink-2 mt-1">Upload a .har / .jmx / live capture to discover endpoints, infer schemas, and detect workflows.</p>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => nav('/rag')} className="btn-secondary"><Sparkles className="w-4 h-4" /> Endpoint Search</button>
            <button onClick={() => nav('/openapi')} className="btn-secondary"><FileCode2 className="w-4 h-4" /> View OpenAPI</button>
          </div>
        </div>

        {/* Upload zone */}
        <div className="card overflow-hidden">
          <div className="grid lg:grid-cols-[1.2fr_1fr]">
            <div className="p-6">
              <input ref={fileRef} type="file" accept=".har,.jmx" className="hidden"
                onChange={e => { const f = e.target.files?.[0]; if (f) handleFileSelect(f) }} />
              <div onClick={() => fileRef.current?.click()}
                onDragOver={e => e.preventDefault()}
                onDrop={e => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) handleFileSelect(f) }}
                className="cursor-pointer rounded-2xl border-2 border-dashed p-8 text-center transition"
                style={{ borderColor: 'var(--line)', background: 'color-mix(in oklch, var(--brand) 3%, var(--card))' }}
                onMouseEnter={e => (e.currentTarget.style.borderColor = 'var(--brand)')}
                onMouseLeave={e => (e.currentTarget.style.borderColor = 'var(--line)')}>
                <div className="w-14 h-14 rounded-2xl grad-bg mx-auto flex items-center justify-center mb-4 shadow-lg">
                  <Upload className="w-6 h-6 text-white" />
                </div>
                <p className="font-semibold" style={{ color: 'var(--ink)' }}>Drop your .har file here</p>
                <p className="text-xs ink-2 mt-1">or click to browse · max 50 MB · .har, .jmx, .json</p>
                {filename && (
                  <div className="mt-4 inline-flex items-center gap-2 px-3 py-1.5 rounded-xl text-xs font-mono"
                    style={{ background: 'var(--card)', border: '1px solid var(--line)', color: 'var(--ink)' }}>
                    {filename}
                  </div>
                )}
              </div>
              <div className="mt-4">
                <label className="block text-xs font-semibold uppercase tracking-wider mb-1.5 ink-2">
                  Nom du fichier HAR
                </label>
                <input
                  type="text"
                  value={filename}
                  onChange={e => setFilename(e.target.value)}
                  placeholder="ex: capture-prod-2026.har"
                  className="input w-full"
                />
              </div>
              {phase === 'error' && error && (
                <p className="mt-3 text-xs text-red-600">{error}</p>
              )}
              <div className="flex flex-wrap items-center gap-4 mt-4">
                <div className="flex-1" />
                <button
                  onClick={() => file && void upload(file, filename)}
                  disabled={isLoading || !file}
                  className="btn-primary">
                  {isLoading ? <><RefreshCw className="w-4 h-4 animate-spin" />Analyzing…</> : <><Play className="w-4 h-4" />Run analysis</>}
                </button>
              </div>
            </div>
            <div className="p-6" style={{ background: 'color-mix(in oklch, var(--ink) 3%, var(--card))', borderLeft: '1px solid var(--line)' }}>
              <p className="text-[10px] font-bold tracking-widest uppercase ink-2 mb-2">Endpoint</p>
              <p className="font-mono text-sm" style={{ color: 'var(--ink)' }}>POST /upload/har/analyze</p>
              <div className="hr-soft my-4" />
              <p className="text-xs ink-2 mb-3">Pipeline steps after upload:</p>
              <ol className="space-y-2">
                {['Cleaned HTTP transactions', 'Normalized endpoints', 'Schema inference', 'Persisted endpoints', 'Detected workflows'].map((s, i) => (
                  <li key={i} className="flex items-center gap-3 text-sm">
                    <span className="w-6 h-6 rounded-lg grad-bg text-white text-xs font-bold flex items-center justify-center">{i + 1}</span>
                    <span style={{ color: 'var(--ink)' }}>{s}</span>
                  </li>
                ))}
              </ol>
            </div>
          </div>
        </div>

        {isLoading && (
          <div className="card pad space-y-3">
            {[40, 100, 92].map((w, i) => <div key={i} className="skel" style={{ width: `${w}%`, height: i === 0 ? 18 : 12 }} />)}
          </div>
        )}

        {showResults && (
          <>
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              {[
                { l: 'Analyse',              v: result.run_id.slice(0, 8) },
                { l: 'Appels HTTP nettoyés', v: result.cleaned_api_calls.toLocaleString() },
                { l: 'Endpoints normalisés', v: result.normalized_endpoints.toString() },
                { l: 'Workflows détectés',   v: result.saved_workflows.toString() },
              ].map((c, i) => (
                <div key={i} className="card p-3">
                  <p className="text-[10px] font-bold tracking-widest uppercase ink-2">{c.l}</p>
                  <p className="text-lg font-black mt-1" style={{ color: 'var(--ink)' }}>{c.v}</p>
                </div>
              ))}
            </div>

            {/* Endpoints preview */}
            <div className="card overflow-hidden">
              <div className="flex items-center justify-between px-5 pt-5 pb-3">
                <div>
                  <p className="text-sm font-bold" style={{ color: 'var(--ink)' }}>Detected endpoints</p>
                  <p className="text-xs ink-2">{result.normalized_endpoints} endpoints</p>
                </div>
                <button onClick={() => nav('/endpoints')} className="btn-ghost text-xs">Open catalog <ArrowRight className="w-3.5 h-3.5" /></button>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="aria-thead">
                    <tr>{['Method', 'Path', 'Canonical key', 'Domain · action', 'Auth', 'Statuses'].map(h => <th key={h} className="text-left px-3 py-2.5">{h}</th>)}</tr>
                  </thead>
                  <tbody>
                    {endpoints.slice(0, 8).map((e, i) => (
                      <tr key={e.id ?? i} className="border-t" style={{ borderColor: 'var(--line)' }}>
                        <td className="px-3 py-2.5"><MethodBadge m={e.method} /></td>
                        <td className="px-3 py-2.5 font-mono text-xs" style={{ color: 'var(--ink)' }}>{e.path}</td>
                        <td className="px-3 py-2.5 font-mono text-xs ink-2">{e.canonical_key}</td>
                        <td className="px-3 py-2.5 text-xs"><span className="font-semibold" style={{ color: 'var(--ink)' }}>{e.business_domain ?? '—'}</span><span className="ink-2"> · {e.business_action ?? '—'}</span></td>
                        <td className="px-3 py-2.5">{e.auth_required ? <Lock className="w-3.5 h-3.5 text-amber-500" /> : <Unlock className="w-3.5 h-3.5 text-emerald-500" />}</td>
                        <td className="px-3 py-2.5 font-mono text-xs ink-2">{e.status_codes.join(' · ')}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* RAG strip */}
            <div className="grid grid-cols-1 lg:grid-cols-[1fr_1.4fr] gap-4">
              <div className="card pad flex flex-col gap-4">
                <div>
                  <p className="text-sm font-bold" style={{ color: 'var(--ink)' }}>RAG indexing</p>
                  <p className="text-xs ink-2 mt-1">Embed {result.normalized_endpoints} endpoints to enable natural-language search.</p>
                </div>
                <div className="flex items-center gap-3">
                  <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${indexed ? 'bg-emerald-50 text-emerald-600' : ''}`}
                    style={indexed ? {} : { background: 'color-mix(in oklch, var(--ink) 6%, var(--card))', color: 'var(--ink-2)' }}>
                    {indexState === 'indexing'
                      ? <RefreshCw className="w-5 h-5 animate-spin" />
                      : indexed
                        ? <Check className="w-5 h-5" />
                        : <Database className="w-5 h-5" />}
                  </div>
                  <div>
                    <p className="text-sm font-semibold" style={{ color: 'var(--ink)' }}>{indexed ? 'Indexed' : 'Not indexed'}</p>
                    <p className="text-xs font-mono ink-2">{indexed ? `${result.saved_endpoints} vecteurs` : '—'}</p>
                  </div>
                  <div className="flex-1" />
                  <button
                    onClick={() => void triggerIndex()}
                    disabled={indexState === 'indexing'}
                    className={indexed ? 'btn-secondary' : 'btn-primary'}>
                    {indexed ? <><RefreshCw className="w-3.5 h-3.5" /> Re-index</> : <><Sparkles className="w-3.5 h-3.5" /> Index for AI</>}
                  </button>
                </div>
                <p className="font-mono text-xs ink-2">POST /rag/index/{result.run_id}</p>
              </div>
              <div className="card pad">
                <p className="text-sm font-bold mb-1" style={{ color: 'var(--ink)' }}>Recherche d&apos;endpoint rapide</p>
                <p className="text-xs ink-2 mb-3">Trouvez un endpoint en langage naturel.</p>
                <div className="flex items-center gap-2">
                  <div className="relative flex-1">
                    <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 ink-2" />
                    <input
                      value={query}
                      onChange={e => setQuery(e.target.value)}
                      onKeyDown={e => e.key === 'Enter' && void search(query)}
                      className="input !pl-9"
                      placeholder="find users endpoints"
                    />
                  </div>
                  <button
                    onClick={() => void search(query)}
                    disabled={searching}
                    className="btn-primary">
                    {searching ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
                  </button>
                </div>
                <div className="mt-3 space-y-2">
                  {(searchResults.length > 0 ? searchResults : endpoints.slice(3, 6).map(e => ({ method: e.method, path: e.path, score: 0, endpoint: e }))).map((r, i) => (
                    <div key={i} className="flex items-center gap-3 p-2.5 rounded-xl" style={{ border: '1px solid var(--line)' }}>
                      <MethodBadge m={r.method} />
                      <span className="font-mono text-xs flex-1 truncate" style={{ color: 'var(--ink)' }}>{r.path}</span>
                      <span className="font-mono text-xs ink-2">{r.score > 0 ? r.score.toFixed(2) : ''}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </AppLayout>
  )
}
