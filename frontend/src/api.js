const baseUrl = (import.meta.env?.VITE_API_BASE_URL || '/backend-api').replace(/\/$/, '')

export async function apiRequest(path, options = {}) {
  let response
  try {
    response = await fetch(`${baseUrl}${path}`, {
      ...options,
      credentials: 'include',
      headers: { ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...options.headers },
    })
  } catch {
    throw new Error('Cannot reach RouteSense. Check that the backend is running and try again.')
  }
  const raw = await response.text()
  let data
  try { data = raw ? JSON.parse(raw) : null } catch { throw new Error(`The service returned an invalid response (HTTP ${response.status}). Check the backend connection.`) }
  if (!response.ok) {
    const detail = data?.error || data?.detail
    const details = detail?.details
    const validation = Array.isArray(details) ? details.map(item => item.message || item.msg).join(' ') : ''
    const message = typeof detail === 'string' ? detail : detail?.message || (Array.isArray(detail) ? detail.map(item => item.msg).join(' ') : response.status >= 500 ? `RouteSense is temporarily unavailable (HTTP ${response.status}). Check that the backend is running.` : `Request failed (HTTP ${response.status}).`)
    const requestId = data?.error?.request_id || response.headers.get('X-Request-ID')
    const error = new Error(`${message}${validation ? ` ${validation}` : ''}${requestId ? ` (Request ID: ${requestId})` : ''}`)
    error.status = response.status
    error.payload = data
    if (response.status === 401 && !['/api/auth/login', '/api/auth/signup', '/api/auth/me'].includes(path)) {
      window.dispatchEvent(new Event('routesense:unauthorized'))
    }
    throw error
  }
  return data
}

const post = (path, body) => apiRequest(path, { method: 'POST', ...(body ? { body: JSON.stringify(body) } : {}) })
export const api = {
  health: () => apiRequest('/health'),
  signup: (body) => post('/api/auth/signup', body),
  login: (body) => post('/api/auth/login', body),
  me: () => apiRequest('/api/auth/me'),
  logout: () => post('/api/auth/logout'),
  extract: (body) => post('/api/v1/itineraries/extract', body),
  generate: (body) => post('/api/v1/itineraries/generate', body),
  list: () => apiRequest('/api/v1/itineraries'),
  get: (id) => apiRequest(`/api/v1/itineraries/${encodeURIComponent(id)}`),
  remove: (id) => apiRequest(`/api/v1/itineraries/${encodeURIComponent(id)}`, { method: 'DELETE' }),
}
