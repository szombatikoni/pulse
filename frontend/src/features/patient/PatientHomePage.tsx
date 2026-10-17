import { Group, Loader, SimpleGrid, Stack, Text, Title } from '@mantine/core'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { useCurrentUser } from '../../api/auth'
import { usePatientQuestionnaires } from '../../api/questionnaires'
import { toLocalInput } from '../../format'
import i18n from '../../i18n'
import { LatestValues } from './LatestValues'
import { MeasurementForm, type MeasurementPreset } from './MeasurementForm'
import { MeasurementHistory } from './MeasurementHistory'
import { QuestionnaireForm } from './QuestionnaireForm'
import { TaskList } from './TaskList'

const FLASH_MS = 2000 // ennyi ideig emelik ki az előzmények az épp mentett sort

function scrollTo(id: string) {
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

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

function todayLabel(): string {
  const locale = i18n.language === 'en' ? 'en-GB' : 'hu-HU'
  return new Intl.DateTimeFormat(locale, { weekday: 'long', month: 'long', day: 'numeric' }).format(
    new Date(),
  )
}

/** A beteg kezdőoldala. Széles képernyőn két hasáb: balra a rögzítés és a kérdőív,
 * jobbra a saját adatok; telefonon egymás alatt, ugyanebben a sorrendben. */
export function PatientHomePage() {
  const { t } = useTranslation()
  const me = useCurrentUser()
  const patientId = me.data?.patient_id
  const [flashId, setFlashId] = useState<string | null>(null)
  // A teendők kártyájáról érkező beállítás; a számláló újraindítja az űrlapot.
  const [preset, setPreset] = useState<{ value: MeasurementPreset; key: number } | null>(null)
  const startMeasurement = (value: MeasurementPreset) => {
    setPreset((p) => ({ value, key: (p?.key ?? 0) + 1 }))
    scrollTo('meres-urlap')
  }

  useEffect(() => {
    if (!flashId) return
    const timer = window.setTimeout(() => setFlashId(null), FLASH_MS)
    return () => window.clearTimeout(timer)
  }, [flashId])

  if (!patientId) return null // a RequireAuth már betöltötte; betegnél mindig van

  return (
    <Stack gap="lg">
      <Group gap="md" align="baseline">
        <Title order={2}>{t('home.patient.title')}</Title>
        <Text c="dimmed">{todayLabel()}</Text>
      </Group>
      <TaskList
        patientId={patientId}
        onRecord={(typeCode) => startMeasurement({ typeCode })}
        onCatchUp={(typeCode, at) =>
          startMeasurement({ typeCode, measuredAt: toLocalInput(new Date(at)) })
        }
        onFill={(code) => scrollTo(`kerdoiv-${code}`)}
      />
      <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="xl" verticalSpacing="lg">
        <Stack gap="lg" maw={720}>
          <MeasurementForm
            key={preset?.key ?? 0}
            patientId={patientId}
            preset={preset?.value}
            onSaved={setFlashId}
          />
          <Stack gap="xs">
            <Title order={3}>{t('questionnaires.title')}</Title>
            <Questionnaires patientId={patientId} />
          </Stack>
        </Stack>
        <Stack gap="lg" maw={720}>
          <Stack gap="xs">
            <Title order={3}>{t('measurements.latestTitle')}</Title>
            <LatestValues patientId={patientId} />
          </Stack>
          <Stack gap="xs">
            <Title order={3}>{t('measurements.historyTitle')}</Title>
            <MeasurementHistory patientId={patientId} highlightId={flashId} />
          </Stack>
        </Stack>
      </SimpleGrid>
    </Stack>
  )
}
