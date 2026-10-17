import { Anchor, Group, Loader, Paper, Stack, Text, Title } from '@mantine/core'
import type { TFunction } from 'i18next'
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router'

import { ApiError } from '../../api/client'
import { type MeasurementType, useMeasurementTypes } from '../../api/measurements'
import { type Alert, type RuleVersion, usePatient, usePatientAlerts } from '../../api/patients'
import { StatusIcon, StatusLabel } from '../../components/StatusLabel'
import { STATUS_COLOR } from '../../components/statusColors'
import {
  ageInYears,
  componentLabel,
  formatDateTime,
  formatMeasurementValue,
  formatNumber,
  unitLabel,
} from '../../format'
import { MeasurementHistory } from '../patient/MeasurementHistory'
import { reasonText, triggerText } from './reasons'
import { SubmissionHistory } from './SubmissionHistory'

/** A szabályverzió feltétele olvashatóan: mérésnél „Szisztolés > 140 Hgmm vagy
 * Diasztolés > 90 Hgmm", kérdőívnél „„Közérzet” pontszáma a(z) figyelmeztető vagy
 * kritikus sávban". */
function conditionText(
  t: TFunction,
  version: RuleVersion,
  types: MeasurementType[],
  questionnaireName: string | undefined,
): string {
  if (version.rule_type === 'questionnaire') {
    const bands = (version.params.bands ?? [])
      .map((b) => t(`questionnaires.bands.${b}`, { defaultValue: b }))
      .join(t('doctor.alert.or'))
    return t('doctor.alert.questionnaireCondition', {
      name: questionnaireName ?? version.params.questionnaire,
      bands,
    })
  }
  const typeCode = version.params.measurement_type ?? ''
  const type = types.find((x) => x.code === typeCode)
  return Object.entries(version.params.limits ?? {})
    .flatMap(([component, limit]) => {
      const label = componentLabel(t, typeCode, component)
      const unitCode = type?.components.find((c) => c.code === component)?.unit ?? ''
      const unit = unitLabel(t, unitCode)
      const parts: string[] = []
      if (limit.max !== undefined) parts.push(`${label} > ${formatNumber(limit.max)} ${unit}`)
      if (limit.min !== undefined) parts.push(`${label} < ${formatNumber(limit.min)} ${unit}`)
      return parts
    })
    .join(t('doctor.alert.or'))
}

/** Egy riasztás magyarázattal (F17): melyik szabályverzió, mely adatok, melyik határ. */
function AlertCard({ alert, types }: { alert: Alert; types: MeasurementType[] }) {
  const { t } = useTranslation()
  const status = alert.severity === 'severe' ? 'severe' : 'attention'
  const version = alert.rule_version
  const questionnaireName = alert.events.flatMap((e) => e.triggers).find((x) => x.submission)
    ?.submission?.questionnaire_name
  return (
    <Paper withBorder p="md" style={{ boxShadow: `inset 3px 0 0 ${STATUS_COLOR[status]}` }}>
      <Stack gap="xs">
        <Group gap="xs">
          <StatusIcon status={status} />
          <Text fw={600}>
            {t('doctor.alert.rule', {
              type: t(`doctor.ruleTypes.${version.rule_type}`),
              version: version.version_no,
              severity: t(`severity.${alert.severity}`),
            })}
          </Text>
        </Group>
        <Text size="sm" c="dimmed">
          {t('doctor.alert.condition', {
            condition: conditionText(t, version, types, questionnaireName),
          })}
        </Text>
        <Stack gap={4} mt={4}>
          {alert.events.map((event, i) => (
            <Group key={i} gap="sm" align="baseline" wrap="nowrap">
              <Text size="sm" w={110} c="dimmed" style={{ flexShrink: 0 }}>
                {formatDateTime(event.created_at)}
              </Text>
              <Text size="sm" fw={500} w={170} style={{ flexShrink: 0 }}>
                {t(`doctor.alert.events.${event.event_type}`)}
              </Text>
              <Stack gap={0}>
                {event.triggers.map((trigger) =>
                  trigger.measurement ? (
                    <Text size="sm" key={trigger.measurement.id}>
                      {formatMeasurementValue(t, trigger.measurement)}
                      <Text span c="dimmed" size="sm">
                        {' — '}
                        {triggerText(t, trigger)}
                      </Text>
                    </Text>
                  ) : (
                    <Text size="sm" key={trigger.submission?.id}>
                      {triggerText(t, trigger)}
                    </Text>
                  ),
                )}
                {event.rule_version && event.rule_version.version_no !== version.version_no && (
                  <Text size="xs" c="dimmed">
                    {t('doctor.alert.eventVersion', { version: event.rule_version.version_no })}
                  </Text>
                )}
              </Stack>
            </Group>
          ))}
        </Stack>
      </Stack>
    </Paper>
  )
}

/** A beteg adatlapja az orvosnak (F10): státusz, nyitott riasztások,
 * kérdőív-kitöltések és mérések. */
export function PatientDetailPage() {
  const { t } = useTranslation()
  const { patientId = '' } = useParams()
  const patient = usePatient(patientId)
  const alerts = usePatientAlerts(patientId)
  const types = useMeasurementTypes()

  if (patient.isPending) return <Loader />
  if (patient.isError) {
    const forbidden = patient.error instanceof ApiError && patient.error.status === 403
    return <Text c="red">{t(forbidden ? 'errors.forbidden' : 'errors.unavailable')}</Text>
  }
  const p = patient.data

  return (
    <Stack gap="lg" maw={960}>
      <Anchor component={Link} to="/doctor" size="sm" c="dimmed">
        ← {t('doctor.back')}
      </Anchor>
      <Group gap="md" align="center">
        <Title order={2}>{p.name}</Title>
        <Text c="dimmed">{t('doctor.age', { age: ageInYears(p.birth_date) })}</Text>
        <StatusLabel status={p.status} />
        <Text size="sm" c="dimmed">
          {reasonText(t, p.reasons[0])}
        </Text>
      </Group>

      <Stack gap="xs">
        <Title order={3}>{t('doctor.alertsTitle')}</Title>
        {alerts.isPending && <Loader size="sm" />}
        {alerts.isError && <Text c="red">{t('errors.unavailable')}</Text>}
        {alerts.data?.length === 0 && <Text c="dimmed">{t('doctor.noAlerts')}</Text>}
        {alerts.data?.map((alert) => (
          <AlertCard key={alert.id} alert={alert} types={types.data ?? []} />
        ))}
      </Stack>

      <Stack gap="xs">
        <Title order={3}>{t('doctor.submissionsTitle')}</Title>
        <SubmissionHistory patientId={patientId} />
      </Stack>

      <Stack gap="xs">
        <Title order={3}>{t('doctor.measurementsTitle')}</Title>
        <MeasurementHistory patientId={patientId} />
      </Stack>
    </Stack>
  )
}
