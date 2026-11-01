import { Button } from '@mantine/core'
import { Check, ClipboardText, Drop, Gauge, Heart, type Icon, Scales } from '@phosphor-icons/react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { type Task, usePatientTasks } from '../../api/tasks'
import { StatusIcon } from '../../components/StatusLabel'
import { formatSoon, formatUntil } from '../../format'

export type Mark = 'done' | 'due' | 'late' | 'missed'

const MARK_COLOR: Record<Mark, string> = {
  done: 'var(--pulse-ok)',
  due: 'var(--mantine-color-dark-0)',
  late: 'var(--pulse-warn)',
  missed: 'var(--pulse-warn)',
}

/** Az állapot jele (az orvosi adatlap teendőinél): kész = pipa, esedékes = pöttyös
 * kör, lejárt/elmaradt = szaggatott kör. */
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

// A teendő jele: a méréstípus vagy a kérdőív ikonja (Phosphor), kész állapotban pipa.
const KIND_ICON: Record<string, Icon> = {
  blood_pressure: Gauge,
  heart_rate: Heart,
  body_weight: Scales,
  blood_glucose: Drop,
}
const ICON_CLASS: Record<Task['state'], string> = { done: 'ok', due: 'due', late: 'late' }

function TaskCard({
  task,
  form,
  onRecord,
  onCatchUp,
  onFill,
}: {
  task: Task
  /** A kártyán belül kinyitott rögzítés (ha ennél a teendőnél nyitott). */
  form: ReactNode
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
  const open = !!form
  const canCatchUp = !open && measurement && task.catch_up_until && task.catch_up_suggested_at

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
  const Glyph =
    task.state === 'done' ? Check : measurement ? (KIND_ICON[task.code] ?? Gauge) : ClipboardText

  const action =
    task.state === 'done' || open ? null : measurement ? (
      <Button size="lg" onClick={() => onRecord(task.code)}>
        {t('tasks.record')}
      </Button>
    ) : (
      <Button size="lg" onClick={() => onFill(task.code)}>
        {t('tasks.fill')}
      </Button>
    )

  // Vízszintes sor: ikon, szöveg, jobb szélen a gomb; az elmaradt alkalom külön alsó
  // sávban; a rögzítés a kártyán belül nyílik ki (felületterv, 2026-10-30, 2. változat).
  return (
    <article className={open ? 'pulse-task is-open' : 'pulse-task'} data-state={task.state}>
      <span className={`pulse-tico ${ICON_CLASS[task.state]}`} aria-hidden="true">
        <Glyph size={24} weight={task.state === 'done' ? 'bold' : 'regular'} />
      </span>
      <div className="pulse-task-body">
        <h3>
          {title}
          <span className="tm">
            {frequency} · {t('tasks.deadline', { when: formatSoon(t, task.due_at) })}
          </span>
        </h3>
        <p className="ts">
          <b>{t(`tasks.state.${task.state}`)}.</b> {text}
        </p>
      </div>
      {action && <div className="pulse-task-actions">{action}</div>}
      {canCatchUp && (
        <div className="pulse-task-missed">
          <StatusIcon status="attention" size={22} />
          <span>{t('tasks.missed', { until: formatUntil(t, task.catch_up_until!) })}</span>
          <Button
            variant="default"
            onClick={() => onCatchUp(task.code, task.catch_up_suggested_at!)}
          >
            {t('tasks.catchUp')}
          </Button>
        </div>
      )}
      {open && <div className="pulse-task-form">{form}</div>}
    </article>
  )
}

/** A beteg teendői a lap tetején (F6): mi esedékes, mi kész, mi maradt el, és meddig
 * pótolható. A szerver az előírások tárolt alkalmaiból adja (M3, A3). Ha nincs
 * előírás, nem jelenik meg. */
export function TaskList({
  patientId,
  renderForm,
  onRecord,
  onCatchUp,
  onFill,
}: {
  patientId: string
  /** A teendőhöz tartozó nyitott űrlap, vagy null, ha a kártya csukva van. */
  renderForm: (task: Task) => ReactNode
  onRecord: (typeCode: string) => void
  onCatchUp: (typeCode: string, measuredAt: string) => void
  onFill: (questionnaireCode: string) => void
}) {
  const { t } = useTranslation()
  const tasks = usePatientTasks(patientId)
  if (!tasks.data || tasks.data.length === 0) return null
  return (
    <section className="pulse-tasks" aria-label={t('tasks.label')}>
      {tasks.data.map((task) => (
        <TaskCard
          key={`${task.kind}-${task.code}`}
          task={task}
          form={renderForm(task)}
          onRecord={onRecord}
          onCatchUp={onCatchUp}
          onFill={onFill}
        />
      ))}
    </section>
  )
}
