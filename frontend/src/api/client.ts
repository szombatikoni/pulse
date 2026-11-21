import { clearToken, getToken } from '../auth/token'

// Közös fetch-burok a backendhez. Minden útvonal az /api előtag alatt van; ha
// van token, az `Authorization: Bearer` fejlécben megy.
export class ApiError extends Error {
  readonly status: number
  /** A szerver hibaleírása (FastAPI: `detail`), ha volt; pl. érvénytelen
   * mérésnél `{ code, component }`, amiből a felület a saját nyelvén ír. */
  readonly detail: unknown

  constructor(status: number, message: string, detail?: unknown) {
    super(message)
    this.status = status
    this.detail = detail
  }
}

/** Lejárt vagy érvénytelen munkamenet: kijelentkeztetés, és vissza a
 * belépőoldalra, ahonnan belépés után ide térünk vissza. Az oldal újratöltődik,
 * így az előző felhasználó adatai nem maradnak a memóriában. */
export function expireSession(): void {
  clearToken()
  const next = window.location.pathname + window.location.search
  window.location.replace(`/login?expired=1&next=${encodeURIComponent(next)}`)
}

/** Újrabelépés helyben (M3, A8 D3): a bejelentkezett oldalak kerete beállít egy
 * kezelőt, amely megnyitja az újrabelépő ablakot, és akkor teljesül, amikor
 * ugyanaz a felhasználó újra belépett. Ha nincs kezelő (pl. az első betöltésnél,
 * még a keret előtt), marad a régi viselkedés: vissza a belépőoldalra. */
type ReloginHandler = () => Promise<void>
let reloginHandler: ReloginHandler | null = null

/** A kezelő beállítása; a visszaadott függvény törli (a keret lebontásakor). */
export function setReloginHandler(handler: ReloginHandler): () => void {
  reloginHandler = handler
  return () => {
    if (reloginHandler === handler) reloginHandler = null
  }
}

// A belépés 401-e hibás e-mailt vagy jelszót jelent, nem lejárt munkamenetet
// (az újrabelépő ablakban a régi token még a tárolóban van).
const LOGIN_PATH = '/auth/login'

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  tokenOverride?: string,
): Promise<T> {
  const token = tokenOverride ?? getToken()
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
  if (response.status === 401 && token && path !== LOGIN_PATH && tokenOverride === undefined) {
    if (getToken() !== token && getToken() !== null) {
      // Közben új token lett (újrabelépés): a lekérdezés egyszer újrapróbálható vele.
      if (method === 'GET') return request<T>(method, path, body)
    } else if (reloginHandler === null) {
      expireSession()
    } else {
      // Az ablak megnyílik (többszöri 401-re is csak egy). A lekérdezés megvárja az
      // újrabelépést, és utána az új tokennel fut le: így nem kerül hibaállapotba, és
      // a hibát mutató oldalrész nem cseréli le a félig kitöltött űrlapot. A mentést
      // nem ismételjük meg magától: a felhasználó belépés után újra megnyomja (D3).
      const relogin = reloginHandler()
      if (method === 'GET') {
        await relogin
        return request<T>(method, path, body)
      }
    }
  }
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: unknown } | null
    throw new ApiError(response.status, `${response.status} ${response.statusText}`, body?.detail)
  }
  return (await response.json()) as T
}

export const apiGet = <T>(path: string) => request<T>('GET', path)
export const apiPost = <T>(path: string, body: unknown) => request<T>('POST', path, body)
/** Lekérés egy megadott tokennel (az újrabelépés ellenőrzéséhez, mielőtt a token a
 * tárolóba kerülne). A 401 itt nem nyit újrabelépő ablakot. */
export const apiGetWithToken = <T>(path: string, token: string) =>
  request<T>('GET', path, undefined, token)
