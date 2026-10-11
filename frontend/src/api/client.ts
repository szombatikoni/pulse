import { clearToken, getToken } from '../auth/token'

// Közös fetch-burok a backendhez. Minden útvonal az /api előtag alatt van; ha
// van token, az `Authorization: Bearer` fejlécben megy.
export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

/** Lejárt vagy érvénytelen munkamenet: kijelentkeztetés, és vissza a
 * belépőoldalra, ahonnan belépés után ide térünk vissza. */
function handleExpiredSession(): void {
  clearToken()
  const next = window.location.pathname + window.location.search
  window.location.replace(`/login?expired=1&next=${encodeURIComponent(next)}`)
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const token = getToken()
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (token) headers.Authorization = `Bearer ${token}`

  const response = await fetch(`/api${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  })

  // 401 tokennel = a munkamenet lejárt vagy a fiókot letiltották. (A belépésnél
  // még nincs token, ott a 401 hibás e-mailt vagy jelszót jelent.)
  if (response.status === 401 && token) {
    handleExpiredSession()
  }
  if (!response.ok) {
    throw new ApiError(response.status, `${response.status} ${response.statusText}`)
  }
  return (await response.json()) as T
}

export const apiGet = <T>(path: string) => request<T>('GET', path)
export const apiPost = <T>(path: string, body: unknown) => request<T>('POST', path, body)
