// A bejelentkezési token a böngésző munkamenet-tárolójában (sessionStorage) él:
// oldalfrissítés után megmarad, a lap bezárásakor törlődik, más lapok nem látják.
// A tároló egyes böngészőbeállításoknál nem elérhető, ezért minden hozzáférés védett.
const KEY = 'pulse.accessToken'

export function getToken(): string | null {
  try {
    return sessionStorage.getItem(KEY)
  } catch {
    return null
  }
}

export function setToken(token: string): void {
  try {
    sessionStorage.setItem(KEY, token)
  } catch {
    // ha nincs tároló, a bejelentkezés csak az oldal újratöltéséig él
  }
}

export function clearToken(): void {
  try {
    sessionStorage.removeItem(KEY)
  } catch {
    // nincs teendő
  }
}
