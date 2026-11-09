import { Loader, Text } from '@mantine/core'
import { ArrowLeft } from '@phosphor-icons/react'
import { useQuery } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams, useSearchParams } from 'react-router'

import { useAlertMutations } from '../../api/alerts'
import { ApiError, apiGet } from '../../api/client'
import { useMeasurementTypes } from '../../api/measurements'
import { type Alert, usePatient } from '../../api/patients'
import { useQuestionnaireTemplates } from '../../api/plans'
import { usePatientSubmissions } from '../../api/questionnaires'
import type { Task } from '../../api/tasks'
import { StatusIcon, StatusLabel } from '../../components/StatusLabel'
import { ageInYears, formatRelative, formatSoon, formatUntil } from '../../format'
import i18n from '../../i18n'
import { TaskIcon } from '../patient/TaskList'
import { AlertCard, ClosedAlert } from './AlertCards'
import { CarePlan } from './CarePlan'
import { MeasurementCharts } from './charts/MeasurementCharts'
import './patientDetail.css'
import { reasonText } from './reasons'
import type { RuleTextContext } from './ruleText'
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

/** Megtekintett (A6 D1): amikor az orvos az adatlapot megnyitja, az új (new)
 * riasztásokat külön POST-tal megtekintettnek jelöli, riasztásonként egyszer. A
 * lekérdezés maga csak olvas; a szerver oldalon a megtekintés idempotens. */
function useMarkSeen(patientId: string, alerts: Alert[] | undefined) {
  const { seen } = useAlertMutations(patientId)
  const sent = useRef(new Set<string>())
  const { mutate } = seen
  useEffect(() => {
    for (const alert of alerts ?? []) {
      if (alert.status !== 'new' || sent.current.has(alert.id)) continue
      sent.current.add(alert.id)
      mutate(alert.id)
    }
  }, [alerts, mutate])
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
  useMarkSeen(patientId, alerts.data)
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
  const assigned = open.filter((a) => a.status === 'assigned').length
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
                  <AlertCard
                    key={alert.id}
                    alert={alert}
                    ctx={ctx}
                    patientId={patientId}
                    patientName={p.name}
                  />
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
