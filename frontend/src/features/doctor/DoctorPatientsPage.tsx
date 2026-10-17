import { Button, Group, Loader, Stack, Text, TextInput, Title } from '@mantine/core'
import type { TFunction } from 'i18next'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import { type PatientStatus, type PatientSummary, useDoctorPatients } from '../../api/patients'
import type { Task } from '../../api/tasks'
import { StatusIcon, StatusLabel } from '../../components/StatusLabel'
import { STATUS_COLOR } from '../../components/statusColors'
import { ageInYears, formatRelative, formatSoon } from '../../format'
import { reasonText, uniqueReasons } from './reasons'

const KPI_ORDER: PatientStatus[] = ['severe', 'attention', 'no_data', 'handled', 'ok']
const LOUD: PatientStatus[] = ['severe', 'attention']

type TaskTone = 'ok' | 'due' | 'late' | 'none'

/** A teendők egy sorban: előbb ami lejárt vagy elmaradt, aztán a ma esedékes;
 * ha egyik sincs, „a teendők rendben". */
function taskSummary(t: TFunction, tasks: Task[]): { tone: TaskTone; text: string } {
  if (tasks.length === 0) return { tone: 'none', text: '—' }
  const name = (task: Task) =>
    task.kind === 'measurement' ? t(`measurementTypes.${task.code}`) : task.name
  const late = tasks.filter((x) => x.state === 'late')
  const missed = tasks.filter((x) => x.state !== 'late' && x.catch_up_until)
  const today = new Date().toDateString()
  const dueToday = tasks.filter(
    (x) => x.state === 'due' && new Date(x.due_at).toDateString() === today,
  )
  const problems = late.length + missed.length
  const more = problems > 1 ? ` ${t('doctor.tasks.more', { count: problems - 1 })}` : ''
  if (late.length)
    return { tone: 'late', text: t('doctor.tasks.late', { name: name(late[0]) }) + more }
  if (missed.length)
    return { tone: 'late', text: t('doctor.tasks.missed', { name: name(missed[0]) }) + more }
  if (dueToday.length)
    return {
      tone: 'due',
      text: t('doctor.tasks.dueToday', {
        name: name(dueToday[0]),
        when: formatSoon(t, dueToday[0].due_at),
      }),
    }
  return { tone: 'ok', text: t('doctor.tasks.onTrack') }
}

const TONE_COLOR: Record<TaskTone, string | undefined> = {
  ok: 'var(--pulse-ok)',
  due: undefined,
  late: 'var(--pulse-warn)',
  none: 'var(--mantine-color-dark-2)',
}

/** Státuszonkénti darabszám, egyben szűrő; a nullás tételek halványak és nem kattinthatók. */
function StatusFilter({
  patients,
  value,
  onChange,
}: {
  patients: PatientSummary[]
  value: PatientStatus | 'all'
  onChange: (value: PatientStatus | 'all') => void
}) {
  const { t } = useTranslation()
  return (
    <Group gap={6} role="group" aria-label={t('doctor.filterLabel')} className="pulse-counts">
      <Button
        variant="default"
        size="sm"
        aria-pressed={value === 'all'}
        onClick={() => onChange('all')}
      >
        <Text span fw={700} mr={6}>
          {patients.length}
        </Text>
        {t('doctor.filterAll')}
      </Button>
      {KPI_ORDER.map((status) => {
        const count = patients.filter((p) => p.status === status).length
        return (
          <Button
            key={status}
            variant="default"
            size="sm"
            disabled={count === 0}
            aria-pressed={value === status}
            onClick={() => onChange(value === status ? 'all' : status)}
            leftSection={<StatusIcon status={status} />}
          >
            <Text span fw={700} mr={6}>
              {count}
            </Text>
            {t(`status.${status}`)}
          </Button>
        )
      })}
    </Group>
  )
}

/** Egy beteg sora: az egész sor link az adatlapra. */
function PatientRow({ p }: { p: PatientSummary }) {
  const { t } = useTranslation()
  const [primary, ...others] = uniqueReasons(p.reasons)
  const loud = LOUD.includes(p.status)
  const tasks = taskSummary(t, p.tasks ?? [])
  return (
    <Link
      to={`/doctor/patients/${p.id}`}
      className="pulse-prow"
      // Színcsík csak az orvosi döntést igénylő (Súlyos, Figyelem) soroknál.
      style={loud ? { boxShadow: `inset 3px 0 0 ${STATUS_COLOR[p.status]}` } : undefined}
    >
      <span className="c-status">
        <StatusLabel status={p.status} />
      </span>
      <span className="c-name">
        <Text span fw={600} display="block">
          {p.name}
        </Text>
        <Text span size="xs" c="dimmed">
          {t('doctor.age', { age: ageInYears(p.birth_date) })}
        </Text>
      </span>
      <span className="c-reason">
        <Text span size="sm" display="block" c={p.status === 'ok' ? 'dimmed' : undefined}>
          {reasonText(t, primary)}
        </Text>
        {others.map((r, i) => (
          <Group key={i} gap={6} mt={3} wrap="nowrap" component="span">
            <StatusIcon status={r.status} size={14} />
            <Text span size="xs" c="dimmed">
              {reasonText(t, r)}
            </Text>
          </Group>
        ))}
      </span>
      <Text span size="sm" className="c-tasks" style={{ color: TONE_COLOR[tasks.tone] }}>
        {tasks.text}
      </Text>
      <Text span size="sm" c="dimmed" className="c-fresh">
        {p.last_data_at ? formatRelative(t, p.last_data_at) : t('doctor.noData')}
      </Text>
    </Link>
  )
}

/** Az orvos priorizált beteglistája (F9): elöl a Súlyos, a végén a Rendben;
 * státusz szerint szűrhető, név szerint kereshető. */
export function DoctorPatientsPage() {
  const { t } = useTranslation()
  const patients = useDoctorPatients()
  const [filter, setFilter] = useState<PatientStatus | 'all'>('all')
  const [query, setQuery] = useState('')

  if (patients.isPending) return <Loader />
  if (patients.isError) return <Text c="red">{t('errors.unavailable')}</Text>

  const q = query.trim().toLocaleLowerCase('hu')
  const rows = patients.data.filter(
    (p) =>
      (filter === 'all' || p.status === filter) &&
      (!q || p.name.toLocaleLowerCase('hu').includes(q)),
  )

  return (
    <Stack gap="md">
      <Group justify="space-between" align="center" wrap="wrap" gap="sm">
        <Title order={2}>{t('home.doctor.title')}</Title>
        {patients.data.length > 0 && (
          <TextInput
            type="search"
            aria-label={t('doctor.search')}
            placeholder={t('doctor.search')}
            value={query}
            onChange={(e) => setQuery(e.currentTarget.value)}
            w={{ base: '100%', xs: 260 }}
            leftSection={
              <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
                <circle cx="7" cy="7" r="4.6" fill="none" stroke="currentColor" strokeWidth="1.6" />
                <path
                  d="m10.5 10.5 3.5 3.5"
                  stroke="currentColor"
                  strokeWidth="1.6"
                  strokeLinecap="round"
                />
              </svg>
            }
          />
        )}
      </Group>
      {patients.data.length === 0 ? (
        <Text c="dimmed">{t('doctor.empty')}</Text>
      ) : (
        <>
          <StatusFilter patients={patients.data} value={filter} onChange={setFilter} />
          <div className="pulse-ptable">
            <div className="pulse-prow-head" aria-hidden="true">
              <span>{t('doctor.columns.status')}</span>
              <span>{t('doctor.columns.patient')}</span>
              <span>{t('doctor.columns.reason')}</span>
              <span>{t('doctor.columns.tasks')}</span>
              <span>{t('doctor.columns.lastData')}</span>
            </div>
            {rows.length === 0 ? (
              <Text c="dimmed" p="md" className="pulse-card">
                {t('doctor.noMatch')}
              </Text>
            ) : (
              rows.map((p) => <PatientRow key={p.id} p={p} />)
            )}
          </div>
        </>
      )}
    </Stack>
  )
}
