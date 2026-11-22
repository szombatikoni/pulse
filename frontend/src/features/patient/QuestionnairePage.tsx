import { Loader, Text } from '@mantine/core'
import { ArrowLeft } from '@phosphor-icons/react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useParams } from 'react-router'

import { useCurrentUser } from '../../api/auth'
import { usePatientQuestionnaires } from '../../api/questionnaires'
import { formatDateTime, formatRelative } from '../../format'
import type { HomeState } from './PatientHomePage'
import { QuestionnaireForm } from './QuestionnaireForm'
import './home.css'

/** Egy kérdőív kitöltése saját, keskeny oldalon (felületterv, 2026-10-30, 2. változat):
 * a teendő „Kitöltés” gombja hozza ide; beküldés után vissza a teendőkhöz, a nyugtával. */
export function QuestionnairePage() {
  const { t } = useTranslation()
  const { code } = useParams()
  const navigate = useNavigate()
  const me = useCurrentUser()
  const patientId = me.data?.patient_id
  const questionnaires = usePatientQuestionnaires(patientId ?? '')

  if (!patientId) return null // a RequireAuth már betöltötte; betegnél mindig van

  const questionnaire = questionnaires.data?.find((q) => q.code === code)
  let content
  if (questionnaires.isPending) content = <Loader size="sm" />
  else if (questionnaires.isError) content = <Text c="red">{t('errors.unavailable')}</Text>
  else if (!questionnaire) content = <Text c="dimmed">{t('questionnaires.notAssigned')}</Text>
  else
    content = (
      <QuestionnaireForm
        patientId={patientId}
        questionnaire={questionnaire}
        onSubmitted={(submittedAt) => {
          const state: HomeState = {
            notice: {
              ok: true,
              title: t('questionnaires.submitted'),
              text: t('questionnaires.receipt', { when: formatRelative(t, submittedAt) }),
            },
          }
          navigate('/patient', { state })
        }}
      />
    )

  return (
    <div className="pulse-patient pulse-narrow">
      <nav className="pulse-crumbs" aria-label={t('home.patient.back')}>
        <Link to="/patient">
          <ArrowLeft size={15} aria-hidden="true" />
          {t('home.patient.title')}
        </Link>
      </nav>
      {questionnaire && (
        <header className="pulse-ph">
          <h1 className="pulse-display">{questionnaire.name}</h1>
          <span className="pulse-meta">
            {t('questionnaires.questionCount', { count: questionnaire.questions.length })} ·{' '}
            {questionnaire.last_submitted_at
              ? t('questionnaires.lastSubmitted', {
                  when: formatDateTime(questionnaire.last_submitted_at),
                })
              : t('questionnaires.neverSubmitted')}
          </span>
        </header>
      )}
      {content}
    </div>
  )
}
