import { Loader, Text } from '@mantine/core'
import { ArrowLeft, CaretRight } from '@phosphor-icons/react'
import { useQuery } from '@tanstack/react-query'
import type { TFunction } from 'i18next'
import { useId } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams, useSearchParams } from 'react-router'

import { ApiError, apiGet } from '../../api/client'
import { useMeasurementTypes } from '../../api/measurements'
import { type Alert, type PatientStatus, type Trigger, usePatient } from '../../api/patients'
import { useQuestionnaireTemplates } from '../../api/plans'
import { usePatientSubmissions } from '../../api/questionnaires'
import type { Task } from '../../api/tasks'
import { StatusIcon, StatusLabel } from '../../components/StatusLabel'
import {
  ageInYears,
  formatDateTime,
  formatMeasurementNumber,
  formatMeasurementValue,
  formatRelative,
  formatSoon,
  formatUntil,
  unitLabel,
} from '../../format'
import i18n from '../../i18n'
import { TaskIcon } from '../patient/TaskList'
import { CarePlan } from './CarePlan'
import { MeasurementCharts } from './charts/MeasurementCharts'
import './patientDetail.css'
import { reasonText, triggerId, triggerText, violationLimits } from './reasons'
import { ruleCondition, ruleTarget, type RuleTextContext } from './ruleText'
import { RulesTab } from './RulesTab'
import { SubmissionHistory } from './SubmissionHistory'

/** A beteg összes riasztása, a lezártakkal együtt: a lezárt kártyához és a
 * grafikon határvonalaihoz (a szabályverziók a riasztásokban érkeznek). */
function useAllAlerts(patientId: string) {
  return useQuery({
    queryKey: ['patients', patientId, 'alerts', 'all'],
    queryFn: () => apiGet<Alert[]>(`/patients/${patientId}/alerts?include_closed=true`),
  })
}

/** A legújabb kiváltó esemény összes kiváltó adata. Időablakos szabálynál ez az
 * ablak összes határsértő mérése, romló trendnél a kitöltések, elmaradt adatnál az
 * elmulasztott alkalmak (mind időrendben). */
function latestTriggers(alert: Alert): Trigger[] {
  for (let i = alert.events.length - 1; i >= 0; i -= 1) {
    const triggers = alert.events[i].triggers
    if (triggers.length) return triggers
  }
  return []
}

/** A riasztás legutóbbi kiváltó adata (a legújabb eseményből). */
function latestTrigger(alert: Alert): Trigger | undefined {
  return latestTriggers(alert).at(-1)
}

/** Több kiváltó adat egy elemének rövid alakja: mérésnél az érték és az ideje,
 * kitöltésnél a pontszám és az ideje, alkalomnál a célpont és a határidő. */
function triggerItemText(t: TFunction, trigger: Trigger): string {
  if (trigger.measurement) {
    const m = trigger.measurement
    return `${formatMeasurementValue(t, m)} (${formatDateTime(m.measured_at)})`
  }
  if (trigger.submission) {
    const s = trigger.submission
    return t('doctor.detail.submissionItem', {
      score: s.total_score,
      max: s.max_score,
      when: formatDateTime(s.submitted_at),
    })
  }
  return triggerText(t, trigger)
}

/** Egykiváltós esemény egysoros alakja (pl. küszöbriasztás): mérésnél az érték és
 * zárójelben a határsértés, egyébként a kiváltó adat mondata. */
function eventTriggerText(t: TFunction, trigger: Trigger): string {
  if (!trigger.measurement) return triggerText(t, trigger)
  const m = trigger.measurement
  const unit = unitLabel(t, m.values[0]?.unit ?? '')
  return `${formatMeasurementNumber(m)} ${unit} (${triggerText(t, trigger)})`
}

/** Több kiváltó adat egymás alatt, soronként egy: mérésnél az érték, csak az átlépett
 * határok (pl. „> 140 / > 90", mert az érték már előttük áll) és az időpont, kitöltésnél a pontszám és az ideje, alkalomnál a célpont és a
 * határidő. A mondatok a reasons.ts / ruleText.ts forrásaiból jönnek. */
function TriggerList({ triggers, labelledBy }: { triggers: Trigger[]; labelledBy?: string }) {
  const { t } = useTranslation()
  return (
    <ul className="pd-trig-list" aria-labelledby={labelledBy}>
      {triggers.map((tr) => (
        <li key={triggerId(tr)}>
          {tr.measurement ? (
            <>
              <span className="v">
                {formatMeasurementNumber(tr.measurement)}{' '}
                {unitLabel(t, tr.measurement.values[0]?.unit ?? '')}
              </span>
              {' · '}
              {violationLimits(tr)}
              {' · '}
              <span className="w">{formatDateTime(tr.measurement.measured_at)}</span>
            </>
          ) : (
            triggerItemText(t, tr)
          )}
        </li>
      ))}
    </ul>
  )
}

/** A riasztás címe: mi történt, hétköznapi szavakkal. */
function alertTitle(
  t: TFunction,
  alert: Alert,
  trigger: Trigger | undefined,
  ctx: RuleTextContext,
): string {
  const version = alert.rule_version
  if (version.rule_type === 'missing_data') {
    return t('doctor.alert.titleMissing', { name: ruleTarget(t, version.params, ctx) })
  }
  if (version.rule_type === 'questionnaire' && version.params.trend_count !== undefined) {
    return t('doctor.alert.titleTrend', { name: ruleTarget(t, version.params, ctx) })
  }
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

/** A nagy szám a kártya jobb oldalán: a kiváltó mérés vagy a kitöltés pontszáma. */
function bigValue(t: TFunction, trigger: Trigger | undefined) {
  if (trigger?.measurement) {
    const m = trigger.measurement
    return {
      value: formatMeasurementNumber(m),
      unit: unitLabel(t, m.values[0]?.unit ?? ''),
      at: formatRelative(t, m.measured_at),
    }
  }
  if (trigger?.submission) {
    const s = trigger.submission
    return {
      value: String(s.total_score),
      unit: t('doctor.alert.points', { max: s.max_score }),
      at: formatDateTime(s.submitted_at),
    }
  }
  return null
}

const has = (alert: Alert, type: string) => alert.events.some((e) => e.event_type === type)
const alertStatus = (alert: Alert): PatientStatus =>
  has(alert, 'assigned') ? 'handled' : alert.severity === 'severe' ? 'severe' : 'attention'

// Az életút lépései (F18); a gombok (megtekintés, felelős, lezárás) az M3-ban jönnek,
// most a lépéssor csak a meglévő eseményeket mutatja.
const STEPS = ['created', 'seen', 'assigned', 'closed'] as const

const CHECK = (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="3.2"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
  >
    <path d="m5 12.5 4.5 4.5L19 7.5" />
  </svg>
)

/** Egy nyitott riasztás magyarázattal (F17): mi történt, melyik szabályverzió, mely
 * adat, melyik feltétel; az életút lépései és az eseménytörténet. */
function AlertCard({ alert, ctx }: { alert: Alert; ctx: RuleTextContext }) {
  const { t } = useTranslation()
  const version = alert.rule_version
  const triggers = latestTriggers(alert)
  const trigger = triggers.at(-1)
  const big = bigValue(t, trigger)
  const title = alertTitle(t, alert, trigger, ctx)
  const firstTodo = STEPS.findIndex((s) => !has(alert, s))
  const triggersLabelId = useId()

  return (
    <article className="pd-alert" aria-label={title}>
      <div className="pd-alert-head">
        <StatusIcon status={alertStatus(alert)} size={22} />
        <div>
          <h3 className="pd-alert-title">
            {title}
            {alert.status === 'new' && <span className="pd-chip">{t('doctor.detail.new')}</span>}
          </h3>
          <p className="pd-alert-rule">
            {t('doctor.alert.rule', {
              type: t(`doctor.ruleTypes.${version.rule_type}`),
              version: version.version_no,
              severity: t(`severity.${alert.severity}`),
            })}
          </p>
        </div>
        {big && (
          <div className="pd-alert-val">
            <span className="v">{big.value}</span> <span className="u">{big.unit}</span>
            <span className="t">{big.at}</span>
          </div>
        )}
      </div>
      <div className="pd-why">
        <span className="k">{t('doctor.detail.why')}</span>
        <span>
          {t('doctor.alert.condition', {
            condition: ruleCondition(t, version.rule_type, version.params, ctx),
          })}
        </span>
        {triggers.length === 1 && (
          <span>{t('doctor.detail.triggerData', { data: triggerText(t, triggers[0]) })}</span>
        )}
        {triggers.length > 1 && (
          <>
            <span id={triggersLabelId}>
              {t('doctor.detail.triggerDataMany', { count: triggers.length })}
            </span>
            <TriggerList triggers={triggers} labelledBy={triggersLabelId} />
          </>
        )}
      </div>
      <ol className="pd-steps" aria-label={t('doctor.detail.lifecycle')}>
        {STEPS.map((step, i) => {
          const event = alert.events.find((e) => e.event_type === step)
          const cls = event ? 'done' : i === firstTodo ? 'now' : 'todo'
          return (
            <li key={step} className={`pd-step ${cls}`}>
              <span className="dot">{event ? CHECK : null}</span>
              <span className="lbl">{t(`doctor.alert.events.${step}`)}</span>
              <span>{event ? formatRelative(t, event.created_at) : ''}</span>
            </li>
          )
        })}
      </ol>
      <details className="pd-events">
        <summary>
          <CaretRight size={14} weight="bold" />
          {t('doctor.detail.history', { count: alert.events.length })}
        </summary>
        <ol className="pd-timeline">
          {[...alert.events].reverse().map((event, i) => (
            <li key={i}>
              <span className="d" aria-hidden="true" />
              <span className="w">{formatDateTime(event.created_at)}</span>
              <div>
                <span className="e">{t(`doctor.alert.events.${event.event_type}`)}</span>
                {event.triggers.length > 1 && (
                  <span className="pd-muted">
                    {' · '}
                    {t('doctor.detail.triggerCount', { count: event.triggers.length })}
                  </span>
                )}
                {event.triggers.length === 1 && (
                  <span>
                    {' · '}
                    {eventTriggerText(t, event.triggers[0])}
                  </span>
                )}
                {event.rule_version && event.rule_version.version_no !== version.version_no && (
                  <span className="pd-muted">
                    {' · '}
                    {t('doctor.alert.eventVersion', { version: event.rule_version.version_no })}
                  </span>
                )}
              </div>
              {event.triggers.length > 1 && <TriggerList triggers={event.triggers} />}
            </li>
          ))}
        </ol>
      </details>
    </article>
  )
}

/** Lezárt riasztás röviden (indoklás és visszajelzés az M3-ban kerül a végpontra). */
function ClosedAlert({ alert, ctx }: { alert: Alert; ctx: RuleTextContext }) {
  const { t } = useTranslation()
  const trigger = latestTrigger(alert)
  const big = bigValue(t, trigger)
  const title = alertTitle(t, alert, trigger, ctx)
  const closed = alert.events.find((e) => e.event_type === 'closed')
  return (
    <article className="pd-alert closed" aria-label={t('doctor.detail.closedLabel', { title })}>
      <div className="pd-alert-head">
        <StatusIcon status="ok" size={22} />
        <div>
          <h3 className="pd-alert-title">{title}</h3>
          {closed && (
            <p className="pd-alert-rule">
              {t('doctor.detail.closedAt', { when: formatRelative(t, closed.created_at) })}
            </p>
          )}
        </div>
        {big && (
          <div className="pd-alert-val sm">
            <span className="v">{big.value}</span> <span className="u">{big.unit}</span>
          </div>
        )}
      </div>
    </article>
  )
}

/** A teendők teljesítése az orvos szemszögéből: mi kész, mi esedékes, mi maradt el.
 * A terv 30 napos sávja napi előzményt kívánna; a végpont csak az aktuális
 * időszakot adja, ezért itt az előírásonkénti állapot látszik. */
function TaskProgress({ tasks }: { tasks: Task[] }) {
  const { t } = useTranslation()
  return (
    <section className="pd-card" aria-labelledby="pd-h-tasks">
      <div className="pd-card-head">
        <div className="left">
          <h2 className="pd-h-card" id="pd-h-tasks">
            {t('doctor.tasksTitle')}
          </h2>
          <span className="pd-meta">{t('doctor.detail.tasksMeta')}</span>
        </div>
      </div>
      {tasks.length === 0 ? (
        <p className="pd-muted">{t('doctor.noTasks')}</p>
      ) : (
        <div className="pd-adh">
          {tasks.map((task) => {
            const measurement = task.kind === 'measurement'
            const name = measurement ? t(`measurementTypes.${task.code}`) : task.name
            const frequency = t(`tasks.frequency.${task.frequency}`, {
              count: task.interval_days ?? 0,
            })
            let state: string
            if (task.state === 'done' && task.done_at) {
              state = t(
                measurement ? 'doctor.task.doneMeasurement' : 'doctor.task.doneQuestionnaire',
                { when: formatSoon(t, task.done_at) },
              )
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
              <div key={`${task.kind}-${task.code}`} className="pd-adh-row">
                <TaskIcon mark={task.state} />
                <div>
                  <div className="pd-adh-top">
                    <span className="nm">{name}</span> <span className="fr">{frequency}</span>
                  </div>
                  <div className="pd-adh-state">{state}</div>
                  {missed && <div className="pd-adh-missed">{missed}</div>}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </section>
  )
}

const formatBirth = (iso: string) =>
  new Intl.DateTimeFormat(i18n.language === 'en' ? 'en-GB' : 'hu-HU', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  }).format(new Date(iso))

// Az adatlap fülei (felületterv: Áttekintés, Szabályok, Követési terv). A követési
// terv az A2 óta az Áttekintés jobb hasábjában van, ezért külön fület (még) nem kap.
const TABS = ['overview', 'rules'] as const
type Tab = (typeof TABS)[number]

/** A beteg adatlapja az orvosnak (F10), a felületterv szerint: fejléc a státusszal,
 * alatta fülek. Az Áttekintés bal hasábjában a nyitott riasztások és a mérések
 * grafikonja, a jobb hasábban a teendők teljesítése, a követési terv (M3) és a
 * kérdőív-kitöltések; a Szabályok fülön a beteg szabályai és a szerkesztő (M3, A4). */
export function PatientDetailPage() {
  const { t } = useTranslation()
  const { patientId = '' } = useParams()
  const [search, setSearch] = useSearchParams()
  const patient = usePatient(patientId)
  const alerts = useAllAlerts(patientId)
  const submissions = usePatientSubmissions(patientId)
  const types = useMeasurementTypes()
  const templates = useQuestionnaireTemplates()
  // A fül az URL-ben (?tab=rules): frissítés és visszalépés után is megmarad.
  const tab: Tab = search.get('tab') === 'rules' ? 'rules' : 'overview'
  const ctx: RuleTextContext = {
    types: types.data ?? [],
    questionnaires: Object.fromEntries((templates.data ?? []).map((x) => [x.code, x.name])),
  }

  if (patient.isPending) return <Loader />
  if (patient.isError) {
    const forbidden = patient.error instanceof ApiError && patient.error.status === 403
    return <Text c="red">{t(forbidden ? 'errors.forbidden' : 'errors.unavailable')}</Text>
  }
  const p = patient.data
  const all = alerts.data ?? []
  const open = all
    .filter((a) => a.status !== 'closed')
    .sort((a, b) =>
      a.severity === b.severity
        ? b.created_at.localeCompare(a.created_at)
        : a.severity === 'severe'
          ? -1
          : 1,
    )
  const closed = all.filter((a) => a.status === 'closed')
  const assigned = open.filter((a) => has(a, 'assigned')).length
  const sentence = open.length
    ? t('doctor.openAlerts', { count: open.length }) +
      (assigned ? t('doctor.detail.assignedPart', { count: assigned }) : '')
    : reasonText(t, p.reasons[0])

  return (
    <div className="pd-page">
      <header className="pd-head">
        <nav className="pd-crumbs" aria-label={t('doctor.detail.backLabel')}>
          <Link to="/doctor">
            <ArrowLeft size={15} />
            {t('doctor.back')}
          </Link>
        </nav>
        <div className="pd-ph">
          <h1 className="pd-display">{p.name}</h1>
          <div className="pd-ph-meta">
            <span>{t('doctor.age', { age: ageInYears(p.birth_date) })}</span>
            <span>{t('doctor.detail.born', { date: formatBirth(p.birth_date) })}</span>
            <span>
              {t('doctor.lastData', {
                when: p.last_data_at ? formatRelative(t, p.last_data_at) : t('doctor.noData'),
              })}
            </span>
          </div>
        </div>
        <div className="pd-status">
          <StatusLabel status={p.status} />
          <span className="why">{sentence}</span>
        </div>
      </header>

      <div className="pd-tabs" role="tablist" aria-label={t('doctor.detail.tabsLabel')}>
        {TABS.map((id) => (
          <button
            key={id}
            type="button"
            role="tab"
            id={`pd-tab-${id}`}
            aria-selected={tab === id}
            aria-controls="pd-tabpanel"
            onClick={() => setSearch(id === 'overview' ? {} : { tab: id })}
          >
            {t(`doctor.detail.tabs.${id}`)}
          </button>
        ))}
      </div>

      <div id="pd-tabpanel" role="tabpanel" aria-labelledby={`pd-tab-${tab}`}>
        {tab === 'rules' ? (
          <RulesTab patientId={patientId} patientName={p.name} ctx={ctx} />
        ) : (
          <div className="pd-grid-2">
            <div className="pd-stack-lg">
              <section className="pd-sec" aria-labelledby="pd-h-alerts">
                <div className="pd-sec-head">
                  <div className="left">
                    <h2 className="pd-h-sec" id="pd-h-alerts">
                      {t('doctor.alertsTitle')}
                    </h2>
                    {open.length > 0 && (
                      <span
                        className={
                          open.some((a) => a.severity === 'severe')
                            ? 'pd-badge-n hot'
                            : 'pd-badge-n'
                        }
                      >
                        {open.length}
                      </span>
                    )}
                  </div>
                </div>
                {alerts.isPending && <Loader size="sm" />}
                {alerts.isError && <Text c="red">{t('errors.unavailable')}</Text>}
                {alerts.isSuccess && open.length === 0 && (
                  <div className="pd-card pd-empty">
                    <StatusIcon status="ok" size={22} />
                    <span>{t('doctor.noAlerts')}</span>
                  </div>
                )}
                {open.map((alert) => (
                  <AlertCard key={alert.id} alert={alert} ctx={ctx} />
                ))}
                {closed.map((alert) => (
                  <ClosedAlert key={alert.id} alert={alert} ctx={ctx} />
                ))}
              </section>
              <MeasurementCharts
                patientId={patientId}
                doctor
                alerts={all}
                submissions={submissions.data ?? []}
              />
            </div>
            <div className="pd-stack-lg">
              <TaskProgress tasks={p.tasks ?? []} />
              <CarePlan patientId={patientId} />
              <SubmissionHistory patientId={patientId} />
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
