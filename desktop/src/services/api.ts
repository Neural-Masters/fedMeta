const API_BASE = 'http://localhost:8000'
const AUTH_TOKEN_KEY = 'fedmeta_access_token'

export function getAccessToken(): string | null {
  return localStorage.getItem(AUTH_TOKEN_KEY)
}

export function setAccessToken(token: string): void {
  localStorage.setItem(AUTH_TOKEN_KEY, token)
}

export function clearAccessToken(): void {
  localStorage.removeItem(AUTH_TOKEN_KEY)
}

export function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers)
  const token = getAccessToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (init.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  return fetch(`${API_BASE}${path}`, { ...init, headers })
}

export { API_BASE }
