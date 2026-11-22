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

/** Jelzés a betegnek: az orvos visszajelzése egy riasztás lezárásakor (M3, A6).
 * Egyirányú, válaszolni nem lehet. A changed_at a létrehozás ideje. */
export type AlertFeedbackNotice = {
  kind: 'alert_feedback'
  changed_at: string
  text: string
  doctor_name: string
  alert_id: string
  /** Miről szólt a riasztás: a szabály típusa és célpontja (méréstípus vagy kérdőív). */
  rule_type: 'threshold' | 'window' | 'questionnaire' | 'missing_data'
  target_code: string
  target_name: string
}

/** A beteg jelzései egy listában, a kind szerint megkülönböztetve (a legújabb elöl). */
export type Notice = PlanNotice | AlertFeedbackNotice

export function usePlanNotices(patientId: string) {
  return useQuery({
    queryKey: ['patients', patientId, 'plan-notices'],
    queryFn: () => apiGet<Notice[]>(`/patients/${patientId}/plan-notices`),
  })
}
