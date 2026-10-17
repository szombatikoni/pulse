import { useQuery } from '@tanstack/react-query'

import { apiGet } from './client'
import type { Measurement } from './measurements'
import type { Submission } from './questionnaires'

export type PatientStatus = 'severe' | 'attention' | 'no_data' | 'handled' | 'ok'
export type Severity = 'moderate' | 'severe'

export type Violation = {
  component: string
  value: number
  bound: 'max' | 'min'
  limit: number
}

/** Egy kiváltó adat: mérés a határátlépéseivel, vagy kérdőív-kitöltés a sávjával. */
export type Trigger = {
  measurement: Measurement | null
  violations: Violation[]
  submission: Submission | null
  band: string | null
}

export type RuleVersion = {
  rule_id: string
  version_no: number
  rule_type: 'threshold' | 'window' | 'questionnaire' | 'missing_data'
  severity: Severity
  params: {
    measurement_type?: string
    limits?: Record<string, { min?: number; max?: number }>
    questionnaire?: string
    bands?: string[]
  }
}

export type AlertEvent = {
  event_type: string
  created_at: string
  rule_version: RuleVersion | null
  triggers: Trigger[]
}

export type Alert = {
  id: string
  status: 'new' | 'seen' | 'assigned' | 'closed'
  severity: Severity
  created_at: string
  needs_review: boolean
  rule_version: RuleVersion
  events: AlertEvent[]
}

export type StatusReason = {
  status: PatientStatus
  code: 'open_alert' | 'no_data_yet' | 'stale_data' | 'fresh_data'
  at: string | null
  alert_id: string | null
  severity: Severity | null
  trigger: Trigger | null
}

export type PatientSummary = {
  id: string
  name: string
  birth_date: string
  status: PatientStatus
  reasons: StatusReason[]
  /** A legutóbbi adat (mérés vagy kérdőív-kitöltés) ideje. */
  last_data_at: string | null
}

export function useDoctorPatients() {
  return useQuery({
    queryKey: ['doctor', 'patients'],
    queryFn: () => apiGet<PatientSummary[]>('/doctor/patients'),
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
