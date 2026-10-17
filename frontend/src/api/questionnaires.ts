import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiGet, apiPost } from './client'

export type QuestionOption = { value: string; label: string }

export type Question = {
  id: string
  order_no: number
  question_type: 'scale' | 'single' | 'multi'
  text: string
  options: QuestionOption[]
}

/** A betegnek kirendelt kérdőív az aktuális verziójával (pontok nélkül). */
export type Questionnaire = {
  code: string
  name: string
  version_no: number
  questions: Question[]
  last_submitted_at: string | null
}

export type SubmissionAnswer = {
  question_id: string
  order_no: number
  text: string
  value: string | string[]
  label: string
  score: number
}

/** Egy kitöltés pontszámmal és sávval (csak az orvos kapja meg). */
export type Submission = {
  id: string
  questionnaire_code: string
  questionnaire_name: string
  version_no: number
  submitted_at: string
  total_score: number
  max_score: number
  band: string
  answers: SubmissionAnswer[]
}

export type SubmissionCreate = {
  questionnaire_code: string
  answers: Record<string, string | string[]>
}

export type SubmissionErrorDetail = { code: string; question_id: string | null }

export function usePatientQuestionnaires(patientId: string) {
  return useQuery({
    queryKey: ['patients', patientId, 'questionnaires'],
    queryFn: () => apiGet<Questionnaire[]>(`/patients/${patientId}/questionnaires`),
  })
}

export function usePatientSubmissions(patientId: string) {
  return useQuery({
    queryKey: ['patients', patientId, 'submissions'],
    queryFn: () => apiGet<Submission[]>(`/patients/${patientId}/submissions?limit=20`),
  })
}

export function useSubmitQuestionnaire(patientId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: SubmissionCreate) =>
      apiPost<{ id: string; submitted_at: string }>(`/patients/${patientId}/submissions`, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['patients', patientId] }),
  })
}
