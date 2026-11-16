import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiGet, apiPost } from './client'

/** A kérdőívszerkesztő (M3, A5) adatai: a backend EditorVersionSpec-je szerint. */
export type QuestionType = 'scale' | 'single' | 'multi'
export type GoodEnd = 'min' | 'max'
export type BandName = 'normal' | 'warning' | 'critical'

export type EditorOption = { value: string; label: string; score: number }

export type EditorQuestion = {
  question_type: QuestionType
  text: string
  scale_min?: number | null
  scale_max?: number | null
  good_end?: GoodEnd | null
  min_label?: string | null
  max_label?: string | null
  options: EditorOption[]
}

export type Band = { band: BandName; min: number; max: number }

export type VersionSpec = { questions: EditorQuestion[]; scoring_thresholds: Band[] }

export type QuestionnaireDetail = {
  code: string
  name: string
  current: VersionSpec & { version_no: number; created_at: string; max_score: number }
  /** A legújabb elöl. */
  versions: { version_no: number; created_at: string; question_count: number }[]
}

/** A szerver hibája: 409-nél stale_version (current_version_no-val) vagy code_taken,
 * 422-nél invalid_name; a többi 422 a FastAPI szokásos listája. */
export type EditorErrorDetail = { code?: string; current_version_no?: number }

/** A szerver korlátai (backend/app/services/questionnaires.py), a felület is ezeket
 * ellenőrzi azonnal. */
export const LIMITS = {
  name: 200,
  text: 300,
  endLabel: 100,
  optionLabel: 200,
  questions: 20,
  options: 10,
  score: 10,
} as const

export const BANDS: BandName[] = ['normal', 'warning', 'critical']

/** A szerkesztő ebből indul, és a kulcsa a verziószám: ha a háttérben frissülne
 * (pl. ablakfókuszra), a másik orvos közben mentett verziója szó nélkül felülírná a
 * nem mentett vázlatot. Ezért csak a saját mentés és a „Friss változat betöltése”
 * (mindkettő invalidál) tölti újra; az ütközést a mentéskori 409 jelzi. */
export function useQuestionnaireDetail(code: string | undefined) {
  return useQuery({
    queryKey: ['questionnaire-templates', code],
    queryFn: () => apiGet<QuestionnaireDetail>(`/questionnaires/${code}`),
    enabled: !!code,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  })
}

/** Új kérdőív és új verzió. Mindkettő a kérdőívlistát (és vele a részleteket) frissíti:
 * a lista a szabály- és a tervűrlap kérdőívválasztója is. */
export function useQuestionnaireMutations() {
  const queryClient = useQueryClient()
  const onSuccess = () => queryClient.invalidateQueries({ queryKey: ['questionnaire-templates'] })
  return {
    create: useMutation({
      mutationFn: (body: VersionSpec & { name: string }) =>
        apiPost<QuestionnaireDetail>('/questionnaires', body),
      onSuccess,
    }),
    addVersion: useMutation({
      mutationFn: ({ code, ...body }: VersionSpec & { code: string; base_version_no: number }) =>
        apiPost<QuestionnaireDetail>(`/questionnaires/${code}/versions`, body),
      onSuccess,
    }),
  }
}
