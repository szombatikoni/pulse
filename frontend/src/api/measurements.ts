import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiGet, apiPost } from './client'

export type MeasurementComponent = {
  code: string
  name: string
  loinc_code: string
  /** UCUM-egységkód, pl. `mm[Hg]`; a kiírt jelölés az i18n `units` kulcsából jön. */
  unit: string
  min_value: number
  max_value: number
}

export type MeasurementType = {
  code: string
  name: string
  loinc_code: string
  components: MeasurementComponent[]
}

export type MeasurementValue = { component: string; value: number; unit: string }

export type Measurement = {
  id: string
  type_code: string
  measured_at: string
  recorded_at: string
  values: MeasurementValue[]
  /** Javításnál a javított (eredeti) mérés azonosítója (M3, A7). */
  corrected_from?: string | null
  /** Ha a mérést felülírták, a javítás azonosítója: az előzményben jelölve marad,
   * a grafikon kihagyja. */
  corrected_by?: string | null
}

/** A mérés még érvényes (nem írta felül javítás); a grafikon csak ezeket rajzolja. */
export const isCurrent = (m: Measurement) => !m.corrected_by

export type MeasurementCreate = {
  type_code: string
  measured_at: string
  values: Record<string, number>
}

/** Az érvénytelen mérés oka a szervertől (422). */
export type MeasurementErrorDetail = { code: string; component: string | null }

export function useMeasurementTypes() {
  return useQuery({
    queryKey: ['measurement-types'],
    queryFn: () => apiGet<MeasurementType[]>('/measurement-types'),
    staleTime: Infinity, // törzsadat, munkamenet közben nem változik
  })
}

export function usePatientMeasurements(patientId: string) {
  return useQuery({
    queryKey: ['patients', patientId, 'measurements'],
    queryFn: () => apiGet<Measurement[]>(`/patients/${patientId}/measurements?limit=50`),
  })
}

export function useRecordMeasurement(patientId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: MeasurementCreate) =>
      apiPost<Measurement>(`/patients/${patientId}/measurements`, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['patients', patientId] }),
  })
}

/** Mérés javítása (M3, A7): csak az értékek; a mérés ideje az eredetié marad. */
export function useCorrectMeasurement(patientId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, values }: { id: string; values: Record<string, number> }) =>
      apiPost<Measurement>(`/patients/${patientId}/measurements/${id}/correction`, { values }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['patients', patientId] }),
  })
}
