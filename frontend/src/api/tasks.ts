import { useQuery } from '@tanstack/react-query'

import { apiGet } from './client'

/** Egy előírás aktuális időszaka a beteg szemszögéből (a szerver a tárolt alkalomból adja). */
export type Task = {
  kind: 'measurement' | 'questionnaire'
  code: string
  name: string
  frequency: 'daily' | 'weekly' | 'every_n_days'
  interval_days: number | null
  due_time: string
  period_start: string
  period_end: string
  due_at: string
  state: 'done' | 'due' | 'late'
  done_at: string | null
  previous_missed: boolean
  /** Csak mérésnél: meddig, és milyen időponttal pótolható az előző időszak. */
  catch_up_until: string | null
  catch_up_suggested_at: string | null
}

export function usePatientTasks(patientId: string) {
  return useQuery({
    // A mérés és a kitöltés mentése a ['patients', id] előtagot frissíti, így ezt is.
    queryKey: ['patients', patientId, 'tasks'],
    queryFn: () => apiGet<Task[]>(`/patients/${patientId}/tasks`),
  })
}

/** Jelzés a betegnek: egy előírását a közelmúltban visszavonták vagy módosították
 * (a szerver az előírás-adatokból számolja; egy módosítási láncból egy jelzés). */
export type PlanNotice = {
  kind: 'revoked' | 'modified'
  changed_at: string
  note: string | null
  target_kind: 'measurement' | 'questionnaire'
  code: string
  name: string
  /** A lezárt (régi) előírás gyakorisága. */
  frequency: Task['frequency']
  interval_days: number | null
  /** Csak módosításnál: az új előírás. */
  new_frequency: Task['frequency'] | null
  new_interval_days: number | null
  new_due_time: string | null
  new_start_date: string | null
}

export function usePlanNotices(patientId: string) {
  return useQuery({
    queryKey: ['patients', patientId, 'plan-notices'],
    queryFn: () => apiGet<PlanNotice[]>(`/patients/${patientId}/plan-notices`),
  })
}
