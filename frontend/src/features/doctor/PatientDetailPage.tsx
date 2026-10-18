import { Anchor, Group, Loader, Paper, SimpleGrid, Stack, Text, Title } from '@mantine/core'
import type { TFunction } from 'i18next'
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router'

import { ApiError } from '../../api/client'
import { type MeasurementType, useMeasurementTypes } from '../../api/measurements'
import {
  type Alert,
  type RuleVersion,
  type Trigger,
  usePatient,
  usePatientAlerts,
} from '../../api/patients'
import type { Task } from '../../api/tasks'
import { StatusIcon, StatusLabel } from '../../components/StatusLabel'
import { STATUS_COLOR } from '../../components/statusColors'
import {
  ageInYears,
  componentLabel,
  formatDateTime,
  formatMeasurementNumber,
  formatNumber,
  formatRelative,
  formatSoon,
  formatUntil,
  unitLabel,
} from '../../format'
import { MeasurementHistory } from '../patient/MeasurementHistory'
import { TaskIcon } from '../patient/TaskList'
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

/** A riasztás legutóbbi kiváltó adata (a legújabb eseményből). */
function latestTrigger(alert: Alert): Trigger | undefined {
  for (let i = alert.events.length - 1; i >= 0; i -= 1) {
    const triggers = alert.events[i].triggers
    if (triggers.length) return triggers[triggers.length - 1]
  }
  return undefined
}

/** A riasztás címe: mi történt, hétköznapi szavakkal. */
function alertTitle(t: TFunction, alert: Alert, trigger: Trigger | undefined): string {
  const version = alert.rule_version
  if (version.rule_type === 'questionnaire' && trigger?.submission) {
    const s = trigger.submission
    return t('doctor.alert.titleQuestionnaire', {
      name: s.questionnaire_name,
      band: t(`questionnaires.bands.${s.band}`, { defaultValue: s.band }),
    })
  }
  const type = t(`measurementTypes.${version.params.measurement_type ?? ''}`, {
    defaultValue: version.params.measurement_type ?? '',
  })
  const below = trigger?.violations.some((v) => v.bound === 'min')
  return t(below ? 'doctor.alert.titleBelow' : 'doctor.alert.titleAbove', { type })
}

/** Egy riasztás magyarázattal (F17): mi történt, melyik szabályverzió, mely adatok,
 * melyik határ; az események idővonalon, a legújabb elöl. */
function AlertCard({ alert, types }: { alert: Alert; types: MeasurementType[] }) {
  const { t } = useTranslation()
  const status = alert.severity === 'severe' ? 'severe' : 'attention'
  const version = alert.rule_version
  const trigger = latestTrigger(alert)
  const questionnaireName = alert.events.flatMap((e) => e.triggers).find((x) => x.submission)
    ?.submission?.questionnaire_name

  let bigValue: { value: string; unit: string; at: string } | null = null
  if (trigger?.measurement) {
    const m = trigger.measurement
    bigValue = {
      value: formatMeasurementNumber(m),
      unit: unitLabel(t, m.values[0]?.unit ?? ''),
      at: formatRelative(t, m.measured_at),
    }
  } else if (trigger?.submission) {
    const s = trigger.submission
    bigValue = {
      value: String(s.total_score),
      unit: t('doctor.alert.points', { max: s.max_score }),
      at: formatDateTime(s.submitted_at),
    }
  }

  return (
    <div className="pulse-alert" style={{ boxShadow: `inset 3px 0 0 ${STATUS_COLOR[status]}` }}>
      <Group justify="space-between" align="flex-start" wrap="wrap" gap="xs">
        <Stack gap={2} style={{ minWidth: 0 }}>
          <Group gap="xs" wrap="nowrap">
            <StatusIcon status={status} />
            <Text fw={700}>{alertTitle(t, alert, trigger)}</Text>
          </Group>
          <Text size="xs" c="dimmed">
            {t('doctor.alert.rule', {
              type: t(`doctor.ruleTypes.${version.rule_type}`),
              version: version.version_no,
              severity: t(`severity.${alert.severity}`),
            })}
          </Text>
        </Stack>
        {bigValue && (
          <Stack gap={0} align="flex-end">
            <Text fw={700} fz={24} lh={1.1}>
              {bigValue.value}{' '}
              <Text span size="sm" fw={500} c="dimmed">
                {bigValue.unit}
              </Text>
            </Text>
            <Text size="xs" c="dimmed">
              {bigValue.at}
            </Text>
          </Stack>
        )}
      </Group>
      <Text size="sm" c="dimmed">
        {t('doctor.alert.condition', {
          condition: conditionText(t, version, types, questionnaireName),
        })}
      </Text>
      <ol className="pulse-timeline">
        {[...alert.events].reverse().map((event, i) => (
          <li key={i}>
            <span className="dot" aria-hidden="true" />
            <Text span size="sm" c="dimmed" className="when">
              {formatDateTime(event.created_at)}
            </Text>
            <span>
              <Text span size="sm" fw={600}>
                {t(`doctor.alert.events.${event.event_type}`)}
              </Text>
              {event.triggers.map((tr) => (
                <Text span size="sm" key={tr.measurement?.id ?? tr.submission?.id}>
                  {' · '}
                  {tr.measurement
                    ? `${formatMeasurementNumber(tr.measurement)} ${unitLabel(t, tr.measurement.values[0]?.unit ?? '')}`
                    : null}
                  <Text span size="sm" c="dimmed">
                    {tr.measurement ? ` (${triggerText(t, tr)})` : triggerText(t, tr)}
                  </Text>
                </Text>
              ))}
              {event.rule_version && event.rule_version.version_no !== version.version_no && (
                <Text span size="xs" c="dimmed">
                  {' · '}
                  {t('doctor.alert.eventVersion', { version: event.rule_version.version_no })}
                </Text>
              )}
            </span>
          </li>
        ))}
      </ol>
    </div>
  )
}

/** A teendők teljesítése az orvos szemszögéből: mi kész, mi esedékes, mi maradt el. */
function TaskProgress({ tasks }: { tasks: Task[] }) {
  const { t } = useTranslation()
  if (tasks.length === 0) return <Text c="dimmed">{t('doctor.noTasks')}</Text>
  return (
    <Stack gap="sm">
      {tasks.map((task) => {
        const measurement = task.kind === 'measurement'
        const name = measurement ? t(`measurementTypes.${task.code}`) : task.name
        const frequency = t(`tasks.frequency.${task.frequency}`, { count: task.interval_days ?? 0 })
        let state: string
        if (task.state === 'done' && task.done_at) {
          state = t(measurement ? 'doctor.task.doneMeasurement' : 'doctor.task.doneQuestionnaire', {
            when: formatSoon(t, task.done_at),
          })
        } else if (task.state === 'late') {
          state = t('doctor.task.late', { when: formatSoon(t, task.due_at) })
        } else {
          state = t('doctor.task.due', { when: formatSoon(t, task.due_at) })
        }
        const missed = task.catch_up_until
          ? t('doctor.task.missed', { until: formatUntil(t, task.catch_up_until) })
          : task.previous_missed
            ? t('doctor.task.missedFinal')
            : null
        return (
          <Group key={`${task.kind}-${task.code}`} gap="sm" align="flex-start" wrap="nowrap">
            <TaskIcon mark={task.state} />
            <Stack gap={0} style={{ minWidth: 0 }}>
              <Text size="sm">
                <b>{name}</b> · {frequency}
              </Text>
              <Text size="xs" c="dimmed">
                {state}
              </Text>
              {missed && (
                <Text size="xs" style={{ color: 'var(--pulse-warn)' }}>
                  {missed}
                </Text>
              )}
            </Stack>
          </Group>
        )
      })}
    </Stack>
  )
}

/** A beteg adatlapja az orvosnak (F10): összefoglaló sáv, nyitott riasztások,
 * kitöltések; a másik hasábban a teendők teljesítése és a mérések. */
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
  const openAlerts = p.reasons.filter((r) => r.code === 'open_alert').length
  // A riasztást kiváltó mérések az előzményekben jelölést kapnak.
  const flagged = new Set(
    (alerts.data ?? []).flatMap((a) =>
      a.events.flatMap((e) =>
        e.triggers.flatMap((tr) => (tr.measurement ? [tr.measurement.id] : [])),
      ),
    ),
  )

  return (
    <Stack gap="lg">
      <Anchor component={Link} to="/doctor" size="sm" c="dimmed">
        ← {t('doctor.back')}
      </Anchor>
      <Paper p="md" style={{ boxShadow: `inset 3px 0 0 ${STATUS_COLOR[p.status]}` }}>
        <Title order={2}>{p.name}</Title>
        <Group gap="lg" mt={6} wrap="wrap">
          <Text c="dimmed">{t('doctor.age', { age: ageInYears(p.birth_date) })}</Text>
          <StatusLabel status={p.status} />
          {openAlerts > 0 && <Text fw={600}>{t('doctor.openAlerts', { count: openAlerts })}</Text>}
          <Text c="dimmed">
            {t('doctor.lastData', {
              when: p.last_data_at ? formatRelative(t, p.last_data_at) : t('doctor.noData'),
            })}
          </Text>
        </Group>
        {openAlerts === 0 && (
          <Text size="sm" c="dimmed" mt={4}>
            {reasonText(t, p.reasons[0])}
          </Text>
        )}
      </Paper>

      <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="lg" verticalSpacing="lg">
        <Stack gap="lg" style={{ minWidth: 0 }}>
          <Paper p="md">
            <Stack gap="sm">
              <Title order={3}>{t('doctor.alertsTitle')}</Title>
              {alerts.isPending && <Loader size="sm" />}
              {alerts.isError && <Text c="red">{t('errors.unavailable')}</Text>}
              {alerts.data?.length === 0 && <Text c="dimmed">{t('doctor.noAlerts')}</Text>}
              {alerts.data?.map((alert) => (
                <AlertCard key={alert.id} alert={alert} types={types.data ?? []} />
              ))}
            </Stack>
          </Paper>
          <Paper p="md">
            <Stack gap="sm">
              <Title order={3}>{t('doctor.submissionsTitle')}</Title>
              <SubmissionHistory patientId={patientId} />
            </Stack>
          </Paper>
        </Stack>
        <Stack gap="lg" style={{ minWidth: 0 }}>
          <Paper p="md">
            <Stack gap="sm">
              <Title order={3}>{t('doctor.tasksTitle')}</Title>
              <TaskProgress tasks={p.tasks ?? []} />
            </Stack>
          </Paper>
          <Paper p="md">
            <Stack gap="sm">
              <Title order={3}>{t('doctor.measurementsTitle')}</Title>
              <MeasurementHistory patientId={patientId} flaggedIds={flagged} />
            </Stack>
          </Paper>
        </Stack>
      </SimpleGrid>
    </Stack>
  )
}
