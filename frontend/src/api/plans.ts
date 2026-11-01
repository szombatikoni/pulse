import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiGet, apiPost } from './client'

export type Frequency = 'daily' | 'weekly' | 'every_n_days'
export type TargetKind = 'measurement' | 'questionnaire'

/** Az orvos egy előírása a követési tervben (érvényes vagy korábbi). */
export type Assignment = {
  id: string
  kind: TargetKind
  code: string
  name: string
  frequency: Frequency
  interval_days: number | null
  /** „HH:MM:SS" */
  due_time: string
  suggested_time: string | null
  /** „YYYY-MM-DD" */
  start_date: string
  end_date: string | null
  revoked_at: string | null
  assigned_by: string
  status: 'active' | 'upcoming' | 'ended' | 'revoked'
  /** Módosításnál az előírás, amely ennek a helyébe lépett. */
  replaced_by: string | null
}

/** Az előírás paraméterei (új előírásnál és módosításnál). */
export type PlanParams = {
  frequency: Frequency
  interval_days: number | null
  due_time: string
  suggested_time: string | null
  start_date: string | null
  end_date: string | null
}

export type AssignmentCreate = PlanParams & { kind: TargetKind; code: string }

export type PlanErrorDetail = { code: string }

export type QuestionnaireTemplate = { code: string; name: string }

export function usePatientPlan(patientId: string) {
  return useQuery({
    queryKey: ['patients', patientId, 'plan'],
    queryFn: () => apiGet<Assignment[]>(`/patients/${patientId}/assignments`),
  })
}

/** A kirendelhető kérdőívek (az új előírás űrlapjához). */
export function useQuestionnaireTemplates() {
  return useQuery({
    queryKey: ['questionnaire-templates'],
    queryFn: () => apiGet<QuestionnaireTemplate[]>('/questionnaires'),
  })
}

/** Új előírás, módosítás és visszavonás. Mindegyik a beteg összes lekérdezését
 * frissíti (['patients', id] előtag), így a teendők és a státusz is. */
export function usePlanMutations(patientId: string) {
  const queryClient = useQueryClient()
  const onSuccess = () => queryClient.invalidateQueries({ queryKey: ['patients', patientId] })
  const base = `/patients/${patientId}/assignments`
  return {
    create: useMutation({
      mutationFn: (body: AssignmentCreate) => apiPost<Assignment>(base, body),
      onSuccess,
    }),
    replace: useMutation({
      mutationFn: ({ id, params }: { id: string; params: PlanParams }) =>
        apiPost<Assignment>(`${base}/${id}/replace`, params),
      onSuccess,
    }),
    revoke: useMutation({
      mutationFn: (id: string) => apiPost<Assignment>(`${base}/${id}/revoke`, undefined),
      onSuccess,
    }),
  }
}
