import { Button, Group, Paper, SimpleGrid, Stack, Text } from '@mantine/core'
import { useTranslation } from 'react-i18next'

import { type Task, usePatientTasks } from '../../api/tasks'
import { formatSoon, formatUntil } from '../../format'

export type Mark = 'done' | 'due' | 'late' | 'missed'

const MARK_COLOR: Record<Mark, string> = {
  done: 'var(--pulse-ok)',
  due: 'var(--mantine-color-dark-0)',
  late: 'var(--pulse-warn)',
  missed: 'var(--pulse-warn)',
}

/** Az állapot jele: kész = pipa, esedékes = pöttyös kör, lejárt/elmaradt = szaggatott kör. */
export function TaskIcon({ mark }: { mark: Mark }) {
  const color = MARK_COLOR[mark]
  return (
    <svg width="20" height="20" viewBox="0 0 16 16" aria-hidden="true" style={{ flexShrink: 0 }}>
      {mark === 'done' && (
        <>
          <circle cx="8" cy="8" r="7" fill={color} />
          <path
            d="m4.8 8.2 2.2 2.2 4.2-4.4"
            fill="none"
            stroke="var(--mantine-color-body)"
            strokeWidth="2.1"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </>
      )}
      {mark === 'due' && (
        <>
          <circle cx="8" cy="8" r="6.2" fill="none" stroke={color} strokeWidth="1.9" />
          <circle cx="8" cy="8" r="2.4" fill={color} />
        </>
      )}
      {(mark === 'late' || mark === 'missed') && (
        <circle
          cx="8"
          cy="8"
          r="6"
          fill="none"
          stroke={color}
          strokeWidth="1.9"
          strokeDasharray="2.6 2"
        />
      )}
    </svg>
  )
}

function Chip({ mark }: { mark: Mark }) {
  const { t } = useTranslation()
  return (
    <Text span size="xs" fw={700} className="pulse-task-chip" style={{ color: MARK_COLOR[mark] }}>
      {t(`tasks.state.${mark}`).toUpperCase()}
    </Text>
  )
}

function TaskCard({
  task,
  onRecord,
  onCatchUp,
  onFill,
}: {
  task: Task
  onRecord: (typeCode: string) => void
  onCatchUp: (typeCode: string, measuredAt: string) => void
  onFill: (questionnaireCode: string) => void
}) {
  const { t } = useTranslation()
  const measurement = task.kind === 'measurement'
  const title = measurement
    ? t(`measurementTypes.${task.code}`, { defaultValue: task.name })
    : task.name
  const frequency = t(`tasks.frequency.${task.frequency}`, { count: task.interval_days ?? 0 })
  const canCatchUp = measurement && task.catch_up_until && task.catch_up_suggested_at

  let text: string
  if (task.state === 'done' && task.done_at) {
    text = t(measurement ? 'tasks.doneMeasurement' : 'tasks.doneQuestionnaire', {
      when: formatSoon(t, task.done_at),
    })
  } else if (task.state === 'late') {
    text = t('tasks.late')
  } else {
    const daily = task.frequency === 'daily'
    text = t(
      measurement
        ? daily
          ? 'tasks.dueMeasurementToday'
          : 'tasks.dueMeasurement'
        : daily
          ? 'tasks.dueQuestionnaireToday'
          : 'tasks.dueQuestionnaire',
    )
  }
  const mark: Mark = task.state === 'done' ? 'done' : task.state

  const action =
    task.state === 'done' ? null : measurement ? (
      <Button size="xs" onClick={() => onRecord(task.code)}>
        {t('tasks.record')}
      </Button>
    ) : (
      <Button size="xs" onClick={() => onFill(task.code)}>
        {t('tasks.fill')}
      </Button>
    )

  return (
    <Paper withBorder p="sm" className="pulse-task" data-state={task.state}>
      <Stack gap={8}>
        <Group gap="sm" wrap="nowrap" align="flex-start">
          <TaskIcon mark={mark} />
          <Stack gap={2} style={{ flex: 1, minWidth: 0 }}>
            <Text fw={600}>{title}</Text>
            <Text size="xs" c="dimmed">
              {frequency} · {t('tasks.deadline', { when: formatSoon(t, task.due_at) })}
            </Text>
            <Text size="sm">
              <Chip mark={mark} /> {text}
            </Text>
          </Stack>
          {action}
        </Group>
        {canCatchUp && (
          <Group gap="sm" wrap="nowrap" align="flex-start" className="pulse-task-missed">
            <TaskIcon mark="missed" />
            <Text size="sm" style={{ flex: 1, minWidth: 0 }}>
              <Chip mark="missed" />{' '}
              {t('tasks.missed', { until: formatUntil(t, task.catch_up_until!) })}
            </Text>
            <Button
              size="xs"
              variant="default"
              onClick={() => onCatchUp(task.code, task.catch_up_suggested_at!)}
            >
              {t('tasks.catchUp')}
            </Button>
          </Group>
        )}
      </Stack>
    </Paper>
  )
}

/** A beteg teendői a lap tetején (F6): mi esedékes, mi kész, mi maradt el, és meddig
 * pótolható. A szerver számolja az előírásokból (számított előnézet; az M3-ban
 * tárolt alkalmak). Ha nincs előírás, nem jelenik meg. */
export function TaskList({
  patientId,
  onRecord,
  onCatchUp,
  onFill,
}: {
  patientId: string
  onRecord: (typeCode: string) => void
  onCatchUp: (typeCode: string, measuredAt: string) => void
  onFill: (questionnaireCode: string) => void
}) {
  const { t } = useTranslation()
  const tasks = usePatientTasks(patientId)
  if (!tasks.data || tasks.data.length === 0) return null
  return (
    <SimpleGrid
      cols={{ base: 1, sm: 2, lg: 3 }}
      spacing="sm"
      component="section"
      aria-label={t('tasks.label')}
    >
      {tasks.data.map((task) => (
        <TaskCard
          key={`${task.kind}-${task.code}`}
          task={task}
          onRecord={onRecord}
          onCatchUp={onCatchUp}
          onFill={onFill}
        />
      ))}
    </SimpleGrid>
  )
}
