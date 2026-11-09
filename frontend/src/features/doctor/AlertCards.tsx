import { Button, Modal, NativeSelect, Textarea } from '@mantine/core'
import { CaretRight, UserPlus } from '@phosphor-icons/react'
import type { TFunction } from 'i18next'
import { type FormEvent, useId, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { CLOSE_TEXT_MAX, useAlertMutations, usePatientDoctors } from '../../api/alerts'
import { useCurrentUser } from '../../api/auth'
import { ApiError } from '../../api/client'
import type { Alert, AlertEvent, AlertState, Trigger } from '../../api/patients'
import { StatusIcon } from '../../components/StatusLabel'
import {
  formatDateTime,
  formatMeasurementNumber,
  formatMeasurementValue,
  formatRelative,
  unitLabel,
} from '../../format'
import {
  alertSeverityStatus,
  alertTitle,
  bigValue,
  latestTrigger,
  latestTriggers,
} from './alertText'
import { triggerId, triggerText, violationLimits } from './reasons'
import { ruleCondition, type RuleTextContext } from './ruleText'

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
 * határok (pl. „> 140 / > 90", mert az érték már előttük áll) és az időpont, kitöltésnél
 * a pontszám és az ideje, alkalomnál a célpont és a határidő. A mondatok a reasons.ts /
 * ruleText.ts forrásaiból jönnek. */
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

/** Az életút lépései (F18) és a riasztás állapotának helye köztük. A lépés előre
 * kihagyható (pl. lezárás közvetlenül az új riasztásból), ezért a sáv az állapotból
 * rajzol: minden lépés kész, ami az aktuális állapotig tart; időpont ott áll, ahol
 * a lépésnek eseménye is van. */
const STEPS = ['created', 'seen', 'assigned', 'closed'] as const
const STATE_STEP: Record<AlertState, number> = { new: 0, seen: 1, assigned: 2, closed: 3 }

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

const lastEvent = (alert: Alert, type: string) =>
  alert.events.findLast((e) => e.event_type === type)

function Steps({ alert }: { alert: Alert }) {
  const { t } = useTranslation()
  const reached = STATE_STEP[alert.status]
  return (
    <ol className="pd-steps" aria-label={t('doctor.detail.lifecycle')}>
      {STEPS.map((step, i) => {
        const event = lastEvent(alert, step)
        const done = i <= reached
        const cls = done ? 'done' : i === reached + 1 ? 'now' : 'todo'
        return (
          <li key={step} className={`pd-step ${cls}`}>
            <span className="dot">{done ? CHECK : null}</span>
            <span className="lbl">{t(`doctor.alert.events.${step}`)}</span>
            <span>{event ? formatRelative(t, event.created_at) : ''}</span>
          </li>
        )
      })}
    </ol>
  )
}

/** Egy esemény kiegészítése: ki tette, kihez rendelte, mi volt az indoklás. */
function EventDetails({ event }: { event: AlertEvent }) {
  const { t } = useTranslation()
  if (event.event_type === 'assigned' && event.assignee) {
    const by = event.actor && event.actor.id !== event.assignee.id ? event.actor.name : null
    return (
      <span>
        {' · '}
        {t('doctor.alert.eventAssignee', { name: event.assignee.name })}
        {by && <span className="pd-muted">{` (${t('doctor.alert.eventBy', { name: by })})`}</span>}
      </span>
    )
  }
  return (
    <>
      {event.actor && <span>{` · ${event.actor.name}`}</span>}
      {event.reason && (
        <span className="pd-event-reason">
          {t('doctor.alert.eventReason', { reason: event.reason })}
        </span>
      )}
    </>
  )
}

/** A riasztás eseménytörténete (legújabb elöl), kinyitható. */
function EventHistory({ alert }: { alert: Alert }) {
  const { t } = useTranslation()
  const version = alert.rule_version
  return (
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
              <EventDetails event={event} />
            </div>
            {event.triggers.length > 1 && <TriggerList triggers={event.triggers} />}
          </li>
        ))}
      </ol>
    </details>
  )
}

/** Felelőshöz rendelés: a beteghez éppen hozzárendelt orvosok közül, alapból a
 * belépett orvos (A6 D2). A felületterv egy gombot mutat választó nélkül; a választó
 * a követési terv megerősítő sorát (pd-confirm) és legördülőjét követi. */
function AssignBox({
  alert,
  patientId,
  onDone,
}: {
  alert: Alert
  patientId: string
  onDone: () => void
}) {
  const { t } = useTranslation()
  const me = useCurrentUser()
  const doctors = usePatientDoctors(patientId)
  const { assign } = useAlertMutations(patientId)
  const [choice, setChoice] = useState<string | null>(null)
  const options = doctors.data ?? []
  // Amíg a belépett orvos (/auth/me) nem töltődött be, nincs alapérték és a gomb
  // tiltott: különben a lista első orvosa lenne kiválasztva „önmaga" helyett.
  const selected = me.isSuccess
    ? (choice ?? options.find((d) => d.id === me.data.id)?.id ?? '')
    : ''

  const submit = (e: FormEvent) => {
    e.preventDefault()
    assign.mutate({ id: alert.id, doctorId: selected || null }, { onSuccess: onDone })
  }

  return (
    <form className="pd-confirm pd-assign" onSubmit={submit}>
      <NativeSelect
        label={t('doctor.alert.assignee')}
        classNames={{ label: 'pd-field-label' }}
        data={[
          // Üres, nem választható sor, amíg nincs érték: így a natív választó sem
          // mutatja az első orvost kiválasztottnak.
          ...(selected === '' ? [{ value: '', label: '', disabled: true }] : []),
          ...options.map((d) => ({
            value: d.id,
            label: d.id === me.data?.id ? t('doctor.alert.assigneeMe', { name: d.name }) : d.name,
          })),
        ]}
        value={selected}
        onChange={(e) => setChoice(e.currentTarget.value)}
        disabled={!doctors.isSuccess || !me.isSuccess}
      />
      {assign.isError && (
        <span className="pd-err" role="alert">
          <StatusIcon status="severe" size={14} />
          {t(errorKey(assign.error))}
        </span>
      )}
      <div className="pd-plan-foot">
        <Button variant="subtle" color="gray" onClick={onDone}>
          {t('doctor.plan.cancel')}
        </Button>
        <Button type="submit" loading={assign.isPending} disabled={!selected}>
          {t('doctor.alert.assignSubmit')}
        </Button>
      </div>
    </form>
  )
}

/** A szerver hibakódjából a felület szövege (409: közben lezárták; 422: a felelős
 * már nincs hozzárendelve; egyéb: a szerver nem érhető el). */
function errorKey(error: unknown): string {
  if (error instanceof ApiError) {
    const code = (error.detail as { code?: string } | null)?.code
    if (code === 'already_closed') return 'doctor.alert.errors.already_closed'
    if (code === 'doctor_not_assigned') return 'doctor.alert.errors.doctor_not_assigned'
    if (error.status === 403) return 'errors.forbidden'
  }
  return 'errors.unavailable'
}

// A lezárás gyakori indoklásai (felületterv: QUICK); a gomb hozzáfűzi vagy kiveszi.
const QUICK = ['phone', 'medication', 'measurementError', 'noAction'] as const

/** A riasztás lezárása (felületterv: „Riasztás lezárása” párbeszéd): kötelező
 * indoklás gyorsválasztóval, és nem kötelező visszajelzés a betegnek. */
function CloseDialog({
  alert,
  patientId,
  title,
  opened,
  onClose,
}: {
  alert: Alert
  patientId: string
  title: string
  opened: boolean
  onClose: () => void
}) {
  const { t } = useTranslation()
  const { close } = useAlertMutations(patientId)
  const [reason, setReason] = useState('')
  const [message, setMessage] = useState('')
  const [missing, setMissing] = useState(false)
  const reasonId = useId()
  const big = bigValue(t, latestTrigger(alert))
  const version = alert.rule_version

  const toggle = (q: string) => {
    setMissing(false)
    setReason((r) =>
      r.includes(q)
        ? r
            .replace(q, '')
            .replace(/^[.\s]+|[.\s]+$/g, '')
            .replace(/\.\s*\./g, '.')
        : r.trim()
          ? `${r.trim().replace(/\.$/, '')}. ${q}.`
          : `${q}.`,
    )
  }

  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (!reason.trim()) {
      setMissing(true)
      document.getElementById(reasonId)?.focus()
      return
    }
    close.mutate(
      { id: alert.id, reason: reason.trim(), message: message.trim() },
      { onSuccess: onClose },
    )
  }

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title={t('doctor.alert.closeTitle')}
      centered
      size={580}
      classNames={{
        content: 'pd-modal',
        header: 'pd-modal-head',
        title: 'pd-modal-title',
        body: 'pd-modal-body',
      }}
      overlayProps={{ backgroundOpacity: 0.6 }}
      closeButtonProps={{ 'aria-label': t('doctor.alert.closeDialog') }}
    >
      <form className="pd-modal-form" onSubmit={submit} noValidate>
        <div className="pd-modal-sum">
          <StatusIcon status={alertSeverityStatus(alert)} size={22} />
          <div>
            <div className="t">{title}</div>
            <div className="pd-meta">
              {[
                big ? `${big.value} ${big.unit}` : null,
                t('doctor.alert.ruleShort', {
                  type: t(`doctor.ruleTypes.${version.rule_type}`),
                  version: version.version_no,
                }),
                formatRelative(t, alert.created_at),
              ]
                .filter(Boolean)
                .join(' · ')}
            </div>
          </div>
        </div>
        <div className="pd-field">
          <label className="pd-field-label" htmlFor={reasonId}>
            {t('doctor.alert.reasonLabel')}{' '}
            <span className="pd-muted">{t('doctor.alert.required')}</span>
          </label>
          <div className="pd-quick" role="group" aria-label={t('doctor.alert.quickLabel')}>
            {QUICK.map((key) => {
              const q = t(`doctor.alert.quick.${key}`)
              return (
                <button
                  key={key}
                  type="button"
                  aria-pressed={reason.includes(q)}
                  onClick={() => toggle(q)}
                >
                  {q}
                </button>
              )
            })}
          </div>
          <Textarea
            id={reasonId}
            value={reason}
            onChange={(e) => {
              setReason(e.currentTarget.value)
              setMissing(false)
            }}
            placeholder={t('doctor.alert.reasonPlaceholder')}
            maxLength={CLOSE_TEXT_MAX}
            autosize
            minRows={3}
            error={missing}
            aria-invalid={missing || undefined}
            aria-describedby={missing ? `${reasonId}-err` : undefined}
            data-autofocus
          />
          {missing && (
            <span className="pd-err" id={`${reasonId}-err`}>
              <StatusIcon status="severe" size={14} />
              {t('doctor.alert.reasonRequired')}
            </span>
          )}
        </div>
        <Textarea
          label={
            <>
              {t('doctor.alert.messageLabel')}{' '}
              <span className="pd-muted">{t('doctor.alert.optional')}</span>
            </>
          }
          classNames={{ label: 'pd-field-label', description: 'pd-hint' }}
          description={t('doctor.alert.messageHint')}
          inputWrapperOrder={['label', 'input', 'description', 'error']}
          value={message}
          onChange={(e) => setMessage(e.currentTarget.value)}
          placeholder={t('doctor.alert.messagePlaceholder')}
          maxLength={CLOSE_TEXT_MAX}
          autosize
          minRows={3}
        />
        {close.isError && (
          <span className="pd-err" role="alert">
            <StatusIcon status="severe" size={14} />
            {t(errorKey(close.error))}
          </span>
        )}
        <div className="pd-modal-foot">
          <Button variant="subtle" color="gray" onClick={onClose}>
            {t('doctor.plan.cancel')}
          </Button>
          <Button type="submit" loading={close.isPending}>
            {t('doctor.alert.closeSubmit')}
          </Button>
        </div>
      </form>
    </Modal>
  )
}

/** Egy nyitott riasztás magyarázattal (F17): mi történt, melyik szabályverzió, mely
 * adat, melyik feltétel; az életút lépései, az eseménytörténet és a váltások gombjai
 * (felelőshöz rendelés, lezárás; M3, A6). */
export function AlertCard({
  alert,
  ctx,
  patientId,
  patientName,
}: {
  alert: Alert
  ctx: RuleTextContext
  patientId: string
  patientName: string
}) {
  const { t } = useTranslation()
  const version = alert.rule_version
  const triggers = latestTriggers(alert)
  const trigger = triggers.at(-1)
  const big = bigValue(t, trigger)
  const title = alertTitle(t, alert, trigger, ctx)
  const triggersLabelId = useId()
  const [assigning, setAssigning] = useState(false)
  const [closing, setClosing] = useState(false)

  return (
    <article className="pd-alert" aria-label={title}>
      <div className="pd-alert-head">
        <StatusIcon status={alertSeverityStatus(alert)} size={22} />
        <div>
          <h3 className="pd-alert-title">
            {title}
            {alert.status === 'new' && <span className="pd-chip">{t('doctor.detail.new')}</span>}
            {alert.assigned_to && (
              <span className="pd-chip-soft">
                {t('doctor.alert.owner', { name: alert.assigned_to.name })}
              </span>
            )}
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
      <Steps alert={alert} />
      <div className="pd-alert-foot">
        <EventHistory alert={alert} />
        <div className="pd-alert-actions">
          {!alert.assigned_to && !assigning && (
            <Button
              variant="default"
              leftSection={<UserPlus size={16} />}
              onClick={() => setAssigning(true)}
            >
              {t('doctor.alert.assign')}
            </Button>
          )}
          <Button onClick={() => setClosing(true)}>{t('doctor.alert.close')}</Button>
        </div>
      </div>
      {assigning && (
        <AssignBox alert={alert} patientId={patientId} onDone={() => setAssigning(false)} />
      )}
      {closing && (
        <CloseDialog
          alert={alert}
          patientId={patientId}
          title={t('doctor.alert.closeSummary', { title, name: patientName })}
          opened={closing}
          onClose={() => setClosing(false)}
        />
      )}
    </article>
  )
}

/** Lezárt riasztás összecsukott alakban (felületterv): ki és mikor zárta le, az
 * indoklás, és kinyitható eseménytörténet. A betegnek írt visszajelzés nem itt
 * látszik (az a beteg értesítése, a riasztás végpontja nem adja ki). */
export function ClosedAlert({ alert, ctx }: { alert: Alert; ctx: RuleTextContext }) {
  const { t } = useTranslation()
  const trigger = latestTrigger(alert)
  const big = bigValue(t, trigger)
  const title = alertTitle(t, alert, trigger, ctx)
  const closed = lastEvent(alert, 'closed')
  return (
    <article className="pd-alert closed" aria-label={t('doctor.detail.closedLabel', { title })}>
      <div className="pd-alert-head">
        <StatusIcon status="ok" size={22} />
        <div>
          <h3 className="pd-alert-title">{title}</h3>
          {closed && (
            <p className="pd-alert-rule">
              {closed.actor
                ? t('doctor.detail.closedAtBy', {
                    when: formatRelative(t, closed.created_at),
                    name: closed.actor.name,
                  })
                : t('doctor.detail.closedAt', { when: formatRelative(t, closed.created_at) })}
            </p>
          )}
        </div>
        {big && (
          <div className="pd-alert-val sm">
            <span className="v">{big.value}</span> <span className="u">{big.unit}</span>
          </div>
        )}
      </div>
      {closed?.reason && (
        <div className="pd-why">
          <span className="k">{t('doctor.alert.reasonHeading')}</span>
          <span>{closed.reason}</span>
        </div>
      )}
      <EventHistory alert={alert} />
    </article>
  )
}
