import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiGet, apiPost } from './client'
import type { UserRef } from './patients'

/** Orvosi megjegyzés a beteghez (M3, A8; F16). Csak hozzáírható: nem
 * szerkeszthető és nem törölhető; a beteg nem látja. */
export type Note = {
  id: string
  text: string
  /** A szerző (orvos) felhasználója és neve. */
  author: UserRef
  created_at: string
}

/** A szöveg felső határa (a szerverrel egyezik: NOTE_TEXT_MAX). */
export const NOTE_TEXT_MAX = 1000

/** A beteg megjegyzései, a legújabb elöl (csak a hozzárendelt orvos érheti el). */
export function usePatientNotes(patientId: string) {
  return useQuery({
    queryKey: ['patients', patientId, 'notes'],
    queryFn: () => apiGet<Note[]>(`/patients/${patientId}/notes`),
  })
}

export function useAddNote(patientId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (text: string) => apiPost<Note>(`/patients/${patientId}/notes`, { text }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['patients', patientId, 'notes'] }),
  })
}
