import { useQuery } from '@tanstack/react-query'

import { apiGet } from './client'
import type { Measurement } from './measurements'
import type { Submission } from './questionnaires'
import type { Task } from './tasks'

export type PatientStatus = 'severe' | 'attention' | 'no_data' | 'handled' | 'ok'
export type Severity = 'moderate' | 'severe'

export type Violation = {
  component: string
  value: number
  bound: 'max' | 'min'
  limit: number
}

/** Egy alkalom (elmaradt adatnál a kiváltó, Adathiánynál az ok): mit kellett
 * volna rögzíteni (méréstípus vagy kérdőív) és mikorra. */
export type OccurrenceTrigger = {
  id: string
  due_at: string
  status: 'due' | 'fulfilled' | 'fulfilled_late' | 'missed'
  target_kind: 'measurement' | 'questionnaire'
  code: string
  name: string
}

/** Egy kiváltó adat: mérés a határátlépéseivel, kérdőív-kitöltés a sávjával, vagy
 * elmulasztott alkalom. */
export type Trigger = {
  measurement: Measurement | null
  violations: Violation[]
  submission: Submission | null
  band: string | null
  occurrence?: OccurrenceTrigger | null
}

export type RuleType = 'threshold' | 'window' | 'questionnaire' | 'missing_data'

/** A szabályverzió paraméterei; a típustól függ, mely kulcsok vannak (a szerver a
 * hiányzókat elhagyja, lásd backend/app/services/rules.py). */
export type RuleParams = {
  measurement_type?: string
  limits?: Record<string, { min?: number; max?: number }>
  /** időablakos: legalább ennyi határsértő mérés … */
  count?: number
  /** … ennyi napon belül */
  window_days?: number
  questionnaire?: string
  bands?: string[]
  /** kérdőív, romló trend: ennyi kitöltésen át */
  trend_count?: number
  /** elmaradt adat: ennyi egymást követő elmulasztott alkalom */
  consecutive_missed?: number
}

export type RuleVersion = {
  rule_id: string
  version_no: number
  rule_type: RuleType
  severity: Severity
  params: RuleParams
}

/** Egy felhasználó röviden (orvosnál a profil szerinti név); az id a users.id. */
export type UserRef = { id: string; name: string }

export type AlertEvent = {
  event_type: string
  created_at: string
  rule_version: RuleVersion | null
  triggers: Trigger[]
  /** Ki váltotta ki; üres = a rendszer (kiértékelés). */
  actor?: UserRef | null
  /** Lezárásnál az orvos indoklása. */
  reason?: string | null
  /** Felelőshöz rendelésnél: kihez rendelték. */
  assignee?: UserRef | null
  /** „Kiváltó adat javítva” eseménynél: a feltétel a javítás után még teljesül-e
   * (a kiváltók ilyenkor [eredeti, javított] mérés). */
  condition_met?: boolean | null
}

export type AlertState = 'new' | 'seen' | 'assigned' | 'closed'

export type Alert = {
  id: string
  status: AlertState
  severity: Severity
  created_at: string
  needs_review: boolean
  rule_version: RuleVersion
  events: AlertEvent[]
  /** Az aktuális felelős orvos; üres = még nincs felelős. */
  assigned_to?: UserRef | null
}

export type StatusReason = {
  status: PatientStatus
  code:
    | 'open_alert'
    | 'missed_occurrence'
    | 'no_data_yet'
    | 'stale_data'
    | 'closed_awaiting_data'
    | 'fresh_data'
  at: string | null
  alert_id: string | null
  severity: Severity | null
  trigger: Trigger | null
  /** Kezelve oknál (closed_awaiting_data) a lezáró orvos; az at a lezárás ideje. */
  actor?: UserRef | null
}

export type PatientSummary = {
  id: string
  name: string
  birth_date: string
  status: PatientStatus
  reasons: StatusReason[]
  /** A legutóbbi adat (mérés vagy kérdőív-kitöltés) ideje. */
  last_data_at: string | null
  /** A beteg teendői az előírásai szerint (követi-e a tervet). */
  tasks: Task[]
}

export function useDoctorPatients({ enabled = true }: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: ['doctor', 'patients'],
    queryFn: () => apiGet<PatientSummary[]>('/doctor/patients'),
    // Az oldalsáv számlálója is ezt használja; nem orvosnál ne kérdezze le.
    enabled,
  })
}

export function usePatient(patientId: string) {
  return useQuery({
    queryKey: ['patients', patientId, 'summary'],
    queryFn: () => apiGet<PatientSummary>(`/patients/${patientId}`),
  })
}

export function usePatientAlerts(patientId: string) {
  return useQuery({
    queryKey: ['patients', patientId, 'alerts'],
    queryFn: () => apiGet<Alert[]>(`/patients/${patientId}/alerts`),
  })
}
