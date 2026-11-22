import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiGet, apiPost } from './client'
import type { Alert, Trigger, UserRef } from './patients'

/** Egy nyitott riasztás a Riasztások oldalhoz: a kártya adatai, a beteg és a
 * legutóbbi kiváltó adat (backend: AlertListItemOut). */
export type AlertListItem = Alert & {
  patient: UserRef
  trigger: Trigger | null
}

/** Az indoklás és a betegüzenet felső határa (a szerverrel egyezik: REASON_MAX). */
export const CLOSE_TEXT_MAX = 500

/** Az orvos összes betegének nyitott riasztásai (Riasztások oldal, oldalsáv-jelvény). */
export function useDoctorAlerts({ enabled = true }: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: ['doctor', 'alerts'],
    queryFn: () => apiGet<AlertListItem[]>('/alerts'),
    enabled,
  })
}

/** A beteghez éppen hozzárendelt orvosok (a felelős-választóhoz). */
export function usePatientDoctors(patientId: string, { enabled = true } = {}) {
  return useQuery({
    queryKey: ['patients', patientId, 'doctors'],
    queryFn: () => apiGet<UserRef[]>(`/patients/${patientId}/doctors`),
    enabled,
  })
}

/** Az életút váltásai (megtekintés, felelőshöz rendelés, lezárás). Mindegyik a beteg
 * lekérdezéseit (['patients', id]: riasztások, státusz) és az orvosi listákat
 * (['doctor']: beteglista, Riasztások oldal, jelvények) frissíti. */
export function useAlertMutations(patientId: string) {
  const queryClient = useQueryClient()
  const onSuccess = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['patients', patientId] }),
      queryClient.invalidateQueries({ queryKey: ['doctor'] }),
    ])
  }
  return {
    // A megtekintés az adatlap megnyitásakor magától indul (useMarkSeen), hibát nem
    // mutat; ha mégis hibázik (pl. 409: közben lezárták), a felület akkor is
    // frissül, hogy a riasztás valós állapota látsszon.
    seen: useMutation({
      mutationFn: (id: string) => apiPost<Alert>(`/alerts/${id}/seen`, {}),
      onSuccess,
      onError: onSuccess,
    }),
    assign: useMutation({
      mutationFn: ({ id, doctorId }: { id: string; doctorId: string | null }) =>
        apiPost<Alert>(`/alerts/${id}/assign`, { doctor_id: doctorId }),
      onSuccess,
    }),
    close: useMutation({
      mutationFn: ({ id, reason, message }: { id: string; reason: string; message: string }) =>
        apiPost<Alert>(`/alerts/${id}/close`, { reason, message: message || null }),
      onSuccess,
    }),
  }
}
