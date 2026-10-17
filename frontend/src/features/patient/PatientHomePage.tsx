import { Loader, Stack, Text, Title } from '@mantine/core'
import { useTranslation } from 'react-i18next'

import { useCurrentUser } from '../../api/auth'
import { usePatientQuestionnaires } from '../../api/questionnaires'
import { MeasurementForm } from './MeasurementForm'
import { MeasurementHistory } from './MeasurementHistory'
import { QuestionnaireForm } from './QuestionnaireForm'

/** A betegnek kirendelt kérdőívek, mindegyik kitölthető (F6). */
function Questionnaires({ patientId }: { patientId: string }) {
  const { t } = useTranslation()
  const questionnaires = usePatientQuestionnaires(patientId)
  if (questionnaires.isPending) return <Loader size="sm" />
  if (questionnaires.isError) return <Text c="red">{t('errors.unavailable')}</Text>
  if (questionnaires.data.length === 0) return <Text c="dimmed">{t('questionnaires.none')}</Text>
  return (
    <>
      {questionnaires.data.map((q) => (
        <QuestionnaireForm key={q.code} patientId={patientId} questionnaire={q} />
      ))}
    </>
  )
}

/** A beteg kezdőoldala: kitöltendő kérdőívek, új mérés, korábbi mérések. */
export function PatientHomePage() {
  const { t } = useTranslation()
  const me = useCurrentUser()
  const patientId = me.data?.patient_id
  if (!patientId) return null // a RequireAuth már betöltötte; betegnél mindig van

  return (
    <Stack gap="lg" maw={720}>
      <Title order={2}>{t('home.patient.title')}</Title>
      <Stack gap="xs">
        <Title order={3}>{t('questionnaires.title')}</Title>
        <Questionnaires patientId={patientId} />
      </Stack>
      <MeasurementForm patientId={patientId} />
      <Stack gap="xs">
        <Title order={3}>{t('measurements.historyTitle')}</Title>
        <MeasurementHistory patientId={patientId} />
      </Stack>
    </Stack>
  )
}
