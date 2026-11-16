import { useMutation } from '@tanstack/react-query'

import { apiPost } from './client'

/** Egy számítás eredménye (backend: NiceResultOut); a CQL-motoré és a PULSE
 * saját számításáé ugyanezekkel a mezőkkel. */
export type NiceResult = {
  excluded_first_day: string | null
  excluded_reading_ids: string[]
  included_reading_ids: string[]
  included_days: string[]
  included_day_count: number | null
  enough_data: boolean | null
  mean_systolic: number | null
  mean_diastolic: number | null
  age_in_years: number | null
  target_systolic: number | null
  target_diastolic: number | null
  /** null = nincs elég adat (sosem kedvező). */
  target_met: boolean | null
}

/** A NICE-kiértékelés válasza (backend: NiceEvaluationOut). */
export type NiceEvaluation = {
  patient_id: string
  evaluation_time: string
  /** [start, end): a vége a mai nap éjfele, az már nem számít bele. */
  period: { start: string; end: string; start_closed: boolean; end_closed: boolean }
  /** A szolgáltatásnak átadott paraméterek, a CQL nevével. */
  parameters: Record<string, unknown>
  cql: NiceResult
  own: NiceResult
  matches: boolean
  /** Az eltérő mezők, a backend COMPARED_FIELDS sorrendjében. */
  mismatched_fields: (keyof NiceResult)[]
  library: { id?: string; version?: string; sha256?: string }
  engine: Record<string, string>
  duration_ms: number | null
}

/** A NICE NG136 szerinti otthoni vérnyomásátlag kiértékelése gombnyomásra (M3,
 * K2). Mutáció, nem lekérdezés: semmit nem tárol, és az eredmény csak a
 * komponens állapotában él (lapváltáskor eltűnik). Más lekérdezést nem
 * frissít, mert státuszt és riasztást nem érint. */
export function useNiceEvaluation(patientId: string) {
  return useMutation({
    mutationFn: () => apiPost<NiceEvaluation>(`/patients/${patientId}/nice-evaluation`, {}),
  })
}
