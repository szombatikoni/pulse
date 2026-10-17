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
}

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
