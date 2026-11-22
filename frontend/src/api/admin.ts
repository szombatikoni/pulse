import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import type { Role } from './auth'
import { apiGet, apiPatch, apiPost, apiPut } from './client'
import type { MeasurementType } from './measurements'

/** Egy felhasználó az admin-listában (M3, A1). Betegadat nincs benne (F2). */
export type AdminUser = {
  id: string
  email: string
  role: Role
  /** Beteg- és orvosprofil neve; adminnál üres. */
  name: string | null
  /** A beteg- vagy orvosprofil azonosítója (az összerendeléshez); adminnál üres. */
  profile_id: string | null
  is_active: boolean
  created_at: string
  last_login_at: string | null
}

export type AdminUserCreate = {
  email: string
  password: string
  role: Role
  name?: string
  /** Csak betegnél: „YYYY-MM-DD". */
  birth_date?: string
}

/** Orvos–beteg összerendelés; az azonosítók profil-azonosítók. */
export type AdminAssignment = {
  id: string
  doctor_id: string
  doctor_name: string
  patient_id: string
  patient_name: string
  valid_from: string
  /** Üres = érvényes, nyitott végű. */
  valid_to: string | null
}

export type ComponentRange = { code: string; min_value: number; max_value: number }

/** A szerver hibakódja (detail.code), ha volt. */
export function adminErrorCode(error: unknown): string | undefined {
  const detail = (error as { detail?: unknown } | null)?.detail
  return (detail as { code?: string } | null)?.code
}

const USERS = ['admin', 'users']
const ASSIGNMENTS = ['admin', 'assignments']

export function useAdminUsers() {
  return useQuery({ queryKey: USERS, queryFn: () => apiGet<AdminUser[]>('/admin/users') })
}

export function useAdminAssignments() {
  return useQuery({
    queryKey: ASSIGNMENTS,
    queryFn: () => apiGet<AdminAssignment[]>('/admin/assignments'),
  })
}

/** A felhasználók és az összerendelések együtt frissülnek: a név és az állapot
 * mindkét fülön látszik. */
function useInvalidateAdmin() {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: ['admin'] })
}

export function useCreateUser() {
  const invalidate = useInvalidateAdmin()
  return useMutation({
    mutationFn: (body: AdminUserCreate) => apiPost<AdminUser>('/admin/users', body),
    onSuccess: invalidate,
  })
}

export function useRenameUser() {
  const invalidate = useInvalidateAdmin()
  return useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) =>
      apiPatch<AdminUser>(`/admin/users/${id}`, { name }),
    onSuccess: invalidate,
  })
}

/** Letiltás (active = false) vagy visszaengedélyezés (active = true). */
export function useSetUserActive() {
  const invalidate = useInvalidateAdmin()
  return useMutation({
    mutationFn: ({ id, active }: { id: string; active: boolean }) =>
      apiPost<AdminUser>(`/admin/users/${id}/${active ? 'enable' : 'disable'}`, {}),
    onSuccess: invalidate,
  })
}

export function useCreateAssignment() {
  const invalidate = useInvalidateAdmin()
  return useMutation({
    mutationFn: (body: { doctor_id: string; patient_id: string }) =>
      apiPost<AdminAssignment>('/admin/assignments', body),
    onSuccess: invalidate,
  })
}

export function useEndAssignment() {
  const invalidate = useInvalidateAdmin()
  return useMutation({
    mutationFn: (id: string) => apiPost<AdminAssignment>(`/admin/assignments/${id}/end`, {}),
    onSuccess: invalidate,
  })
}

/** A méréstípus rögzíthető tartománya; a közös típuslista (a beteg űrlapja és a
 * szabályszerkesztő is ezt használja) újratöltődik. */
export function useUpdateRanges() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ code, components }: { code: string; components: ComponentRange[] }) =>
      apiPut<MeasurementType>(`/admin/measurement-types/${code}/ranges`, { components }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['measurement-types'] }),
  })
}
