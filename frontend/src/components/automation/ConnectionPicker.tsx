import { useEffect, useState } from 'react'
import { Loader2, CheckCircle2, XCircle } from 'lucide-react'
import { listConnections, testConnection, Connection } from '../../lib/connectionsApi'
import { ApiError } from '../../lib/api'

interface Props {
  value: string
  onChange: (connectionId: string) => void
  onSelectConnection?: (connection: Connection | undefined) => void
  disabled?: boolean
}

const ENV_LABEL: Record<string, string> = { test: 'Test', preprod: 'Preprod', prod: 'Prod' }

export default function ConnectionPicker({ value, onChange, onSelectConnection, disabled }: Props) {
  const [connections, setConnections] = useState<Connection[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [testState, setTestState] = useState<'idle' | 'testing' | 'ok' | 'fail'>('idle')
  const [testMessage, setTestMessage] = useState('')

  useEffect(() => {
    listConnections()
      .then(res => {
        setConnections(res.connections)
        if (!value && res.connections.length > 0) {
          onChange(res.connections[0].id)
          onSelectConnection?.(res.connections[0])
        } else {
          onSelectConnection?.(res.connections.find(c => c.id === value))
        }
      })
      .catch(e => setError(e instanceof Error ? e.message : 'Failed to load connections'))
      .finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function handleTest() {
    if (!value) return
    setTestState('testing')
    setTestMessage('')
    try {
      const result = await testConnection(value)
      setTestState(result.success ? 'ok' : 'fail')
      setTestMessage(result.message)
    } catch (e) {
      setTestState('fail')
      setTestMessage(e instanceof ApiError ? e.message : 'Test failed')
    }
  }

  const selected = connections.find(c => c.id === value)

  return (
    <div>
      <p className="text-[10px] font-bold tracking-widest uppercase mb-1.5" style={{ color: 'var(--ink-2)' }}>
        Connection
      </p>
      {loading ? (
        <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--ink-2)' }}>
          <Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading connections…
        </div>
      ) : connections.length === 0 ? (
        <p className="text-xs" style={{ color: 'var(--ink-2)' }}>
          No connection available. Ask an admin to create one and assign it to you under Connections.
        </p>
      ) : (
        <div className="flex gap-2">
          <select
            className="input !py-2 text-xs flex-1"
            value={value}
            disabled={disabled}
            onChange={e => {
              onChange(e.target.value)
              onSelectConnection?.(connections.find(c => c.id === e.target.value))
              setTestState('idle')
              setTestMessage('')
            }}
          >
            {connections.map(c => (
              <option key={c.id} value={c.id}>
                {c.name} — {ENV_LABEL[c.environment] ?? c.environment} ({c.base_url})
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={handleTest}
            disabled={!value || testState === 'testing' || disabled}
            className="btn-secondary shrink-0 !py-1.5 !px-3 text-xs whitespace-nowrap"
          >
            {testState === 'testing' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : 'Test'}
          </button>
        </div>
      )}
      {error && <p className="text-xs mt-1 text-rose-600">{error}</p>}
      {testState === 'ok' && (
        <p className="text-xs mt-1 flex items-center gap-1 text-emerald-600">
          <CheckCircle2 className="w-3.5 h-3.5" /> {testMessage}
        </p>
      )}
      {testState === 'fail' && (
        <p className="text-xs mt-1 flex items-center gap-1 text-rose-600">
          <XCircle className="w-3.5 h-3.5" /> {testMessage}
        </p>
      )}
      {selected && (
        <p className="text-[11px] mt-1" style={{ color: 'var(--ink-2)' }}>
          Auth: {selected.auth_type.replace(/_/g, ' ')} · Environment: {ENV_LABEL[selected.environment] ?? selected.environment}
        </p>
      )}
    </div>
  )
}
