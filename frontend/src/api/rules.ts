import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiGet, apiPost } from './client'
import type { RuleParams, RuleType, Severity } from './patients'

/** Egy szabályverzió a szabálylistához (immutabilis; a módosítás új verzió). */
export type RuleVersionDetail = {
  id: string
  version_no: number
  rule_type: RuleType
  severity: Severity
  params: RuleParams
  /** Mióta érvényes (a verzió létrejötte). */
  created_at: string
  /** A verziót létrehozó orvos neve. */
  created_by: string
}

/** A beteg egy szabálya az aktuális verziójával és a teljes verziólistával. */
export type Rule = {
  id: string
  rule_type: RuleType
  is_active: boolean
  created_at: string
  current: RuleVersionDetail
  /** Verziószám szerint növekvő sorrendben; az utolsó az aktuális. */
  versions: RuleVersionDetail[]
  open_alerts: number
}

export type RuleCreate = { rule_type: RuleType; params: RuleParams; severity: Severity }

/** A szerver hibája (422): a kód alapján a felület a saját nyelvén ír; szerkezeti
 * hibánál (invalid_params) a hibás mezők útja is jön, pl. „limits.systolic". */
export type RuleErrorDetail = { code: string; fields?: string[] }

export function usePatientRules(patientId: string) {
  return useQuery({
    queryKey: ['patients', patientId, 'rules'],
    queryFn: () => apiGet<Rule[]>(`/patients/${patientId}/rules`),
  })
}

/** Új szabály és új verzió. Mindkettő a beteg összes lekérdezését frissíti
 * (['patients', id] előtag): a módosítás a nyitott riasztás történetébe is
 * „A szabály módosult" eseményt ír. */
export function useRuleMutations(patientId: string) {
  const queryClient = useQueryClient()
  const onSuccess = () => queryClient.invalidateQueries({ queryKey: ['patients', patientId] })
  return {
    create: useMutation({
      mutationFn: (body: RuleCreate) => apiPost<Rule>(`/patients/${patientId}/rules`, body),
      onSuccess,
    }),
    // A típus nem váltható, ezért nem küldjük (a szerver a szabályét használja).
    addVersion: useMutation({
      mutationFn: ({
        ruleId,
        params,
        severity,
      }: {
        ruleId: string
        params: RuleParams
        severity: Severity
      }) => apiPost<Rule>(`/rules/${ruleId}/versions`, { params, severity }),
      onSuccess,
    }),
  }
}
