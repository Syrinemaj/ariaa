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
  const token = localStorage.getItem('access_token')
  return token ? { Authorization: `Bearer ${token}` } : {}
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
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    localStorage.removeItem('aria_auth_user')
    window.location.href = '/login'
    throw new ApiError(401, 'Unauthorized')
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({})) as Record<string, unknown>
    const detail = body.detail
    const message = typeof detail === 'string' ? detail : `HTTP ${res.status}`
    throw new ApiError(res.status, message, body)
  }

  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

async function requestBlob(path: string): Promise<Blob> {
  const res = await fetch(`${BASE}${path}`, { headers: authHeaders() })
  if (res.status === 401 && !window.location.pathname.startsWith('/login')) {
    localStorage.removeItem('access_token')
    window.location.href = '/login'
    throw new ApiError(401, 'Unauthorized')
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({})) as Record<string, unknown>
    const detail = body.detail
    const message = typeof detail === 'string' ? detail : `HTTP ${res.status}`
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
