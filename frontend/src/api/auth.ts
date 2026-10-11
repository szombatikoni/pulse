import { useQuery } from '@tanstack/react-query'

import { getToken } from '../auth/token'
import { apiGet, apiPost } from './client'

export type Role = 'patient' | 'doctor' | 'admin'

export type CurrentUser = {
  id: string
  email: string
  role: Role
  name: string | null
}

type TokenResponse = { access_token: string; token_type: string; expires_in: number }

export async function login(email: string, password: string): Promise<string> {
  const result = await apiPost<TokenResponse>('/auth/login', { email, password })
  return result.access_token
}

export const currentUserQuery = {
  queryKey: ['me'],
  queryFn: () => apiGet<CurrentUser>('/auth/me'),
}

/** A bejelentkezett felhasználó; csak akkor kérdezi le, ha van token. */
export function useCurrentUser() {
  return useQuery({
    ...currentUserQuery,
    enabled: getToken() !== null,
    retry: false,
    staleTime: 5 * 60 * 1000,
  })
}

/** Az egyes szerepkörök kezdőoldala. */
export const HOME_BY_ROLE: Record<Role, string> = {
  patient: '/patient',
  doctor: '/doctor',
  admin: '/admin',
}
