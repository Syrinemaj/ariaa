const BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? ''

export class ApiError extends Error {
  body?: Record<string, unknown>
  constructor(
    public readonly status: number,
    message: string,
    body?: Record<string, unknown>,
  ) {
    super(message)
    this.name = 'ApiError'
    this.body = body
  }
}

function authHeaders(): Record<string, string> {
  // sessionStorage, not localStorage: isolated per browser tab, so two tabs
  // can hold two different logged-in users at once (localStorage is shared
  // across every tab of the same origin — logging in as a second user in
  // one tab silently overwrote the token every other tab was reading,
  // making a tab "become" whichever user logged in most recently on any
  // refresh). Trade-off: opening a brand-new tab (not a duplicate of an
  // existing one) starts logged out — see AuthContext.tsx.
  const token = sessionStorage.getItem('access_token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

// FastAPI error bodies are usually `{detail: "a string"}`, but some routes
// (governance blocks, instruction-unclear, etc.) send a structured
// `{detail: {code, message, reasons?, suggestion?}}` instead. Extracting the
// real message here means every caller gets it via `ApiError.message`
// automatically, instead of each call site re-parsing `e.body` — most
// didn't, and silently showed "HTTP 403" instead of the actual reason.
function errorMessageFromDetail(detail: unknown, status: number): string {
  if (typeof detail === 'string') return detail
  if (detail && typeof detail === 'object') {
    const d = detail as { message?: string; reasons?: string[]; suggestion?: string }
    if (d.message) {
      const extra = [
        ...(Array.isArray(d.reasons) ? d.reasons : []),
        ...(d.suggestion ? [d.suggestion] : []),
      ]
      return extra.length > 0 ? `${d.message} ${extra.join(' ')}` : d.message
    }
  }
  return `HTTP ${status}`
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const isFormData = init.body instanceof FormData
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
      ...authHeaders(),
      ...(init.headers as Record<string, string> | undefined ?? {}),
    },
  })

  // Token expired — clear auth and redirect to login (skip on login page itself)
  if (res.status === 401 && !window.location.pathname.startsWith('/login')) {
    sessionStorage.removeItem('access_token')
    sessionStorage.removeItem('refresh_token')
    sessionStorage.removeItem('aria_auth_user')
    window.location.href = '/login'
    throw new ApiError(401, 'Unauthorized')
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({})) as Record<string, unknown>
    const detail = body.detail
    const message = errorMessageFromDetail(detail, res.status)
    throw new ApiError(res.status, message, body)
  }

  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

async function requestBlob(path: string): Promise<Blob> {
  const res = await fetch(`${BASE}${path}`, { headers: authHeaders() })
  if (res.status === 401 && !window.location.pathname.startsWith('/login')) {
    sessionStorage.removeItem('access_token')
    window.location.href = '/login'
    throw new ApiError(401, 'Unauthorized')
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({})) as Record<string, unknown>
    const detail = body.detail
    const message = errorMessageFromDetail(detail, res.status)
    throw new ApiError(res.status, message, body)
  }
  return res.blob()
}

export const api = {
  get:   <T>(path: string) => request<T>(path),
  post:  <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: 'POST',
      body: body instanceof FormData ? body : body !== undefined ? JSON.stringify(body) : undefined,
    }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: 'PATCH',
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }),
  del:   <T>(path: string) => request<T>(path, { method: 'DELETE' }),
  blob:  (path: string) => requestBlob(path),
}
