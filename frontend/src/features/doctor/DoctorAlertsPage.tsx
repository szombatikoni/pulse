import { Loader, Text, Title } from '@mantine/core'
import { CaretRight } from '@phosphor-icons/react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import { type AlertListItem, useDoctorAlerts } from '../../api/alerts'
import { useMeasurementTypes } from '../../api/measurements'
import type { AlertState } from '../../api/patients'
import { useQuestionnaireTemplates } from '../../api/plans'
import { StatusIcon } from '../../components/StatusLabel'
import { formatRelative } from '../../format'
import { alertSeverityStatus, alertTitle, bigValue } from './alertText'
import './alertsPage.css'
import './patientDetail.css'
import './patientList.css'
import type { RuleTextContext } from './ruleText'

type Filter = 'all' | Exclude<AlertState, 'closed'>
const FILTERS: Filter[] = ['all', 'new', 'seen', 'assigned']

/** Egy nyitott riasztás sora; az egész sor link a beteg adatlapjára. */
function AlertRow({ alert, ctx }: { alert: AlertListItem; ctx: RuleTextContext }) {
  const { t } = useTranslation()
  const version = alert.rule_version
  const big = bigValue(t, alert.trigger)
  return (
    <Link
      to={`/doctor/patients/${alert.patient.id}`}
      className="pulse-prow pl-row al-row"
      data-s={alert.severity}
    >
      <StatusIcon status={alertSeverityStatus(alert)} size={20} />
      <span className="c-name">
        <span className="pl-name">{alert.patient.name}</span>
      </span>
      <span className="al-what">
        <span className="tt">{alertTitle(t, alert, alert.trigger, ctx)}</span>
        <span className="pd-meta">
          {' · '}
          {t('doctor.alert.rule', {
            type: t(`doctor.ruleTypes.${version.rule_type}`),
            version: version.version_no,
            severity: t(`severity.${alert.severity}`),
          })}
        </span>
      </span>
      <span className="al-val">
        {big && (
          <>
            {big.value}
            <small>{big.unit}</small>
          </>
        )}
      </span>
      <span className="al-state">
        <span className={alert.status === 'new' ? 'pd-chip' : 'pd-chip-soft'}>
          {t(`alerts.state.${alert.status}`)}
        </span>
        <span className="pd-meta">{formatRelative(t, alert.created_at)}</span>
      </span>
      <span className="al-owner">
        {alert.assigned_to ? alert.assigned_to.name : t('alerts.noOwner')}
      </span>
      <span className="c-chev" aria-hidden="true">
        <CaretRight size={16} weight="bold" />
      </span>
    </Link>
  )
}

/** Az orvos minden betegének nyitott riasztása (M3, A6; felületterv „Riasztások"):
 * szűrés állapot szerint, elöl a súlyosabb, azon belül a frissebb (a szerver sorrendje). */
export function DoctorAlertsPage() {
  const { t } = useTranslation()
  const alerts = useDoctorAlerts()
  const types = useMeasurementTypes()
  const templates = useQuestionnaireTemplates()
  const [filter, setFilter] = useState<Filter>('all')
  const ctx: RuleTextContext = {
    types: types.data ?? [],
    questionnaires: Object.fromEntries((templates.data ?? []).map((x) => [x.code, x.name])),
  }

  if (alerts.isPending) return <Loader />
  if (alerts.isError) return <Text c="red">{t('errors.unavailable')}</Text>

  const all = alerts.data
  const count = (f: Filter) => (f === 'all' ? all.length : all.filter((a) => a.status === f).length)
  const visible = all.filter((a) => filter === 'all' || a.status === filter)

  return (
    <div className="pl-page">
      <header className="pl-ph">
        <div className="pl-ph-text">
          <span className="pl-eyebrow">{t('alerts.eyebrow')}</span>
          <Title order={1} className="pl-title">
            {t('alerts.title')}
          </Title>
          <div className="pl-ph-meta">
            <span>{t('alerts.openCount', { count: all.length })}</span>
            <span>{t('alerts.newCount', { count: count('new') })}</span>
          </div>
        </div>
      </header>
      <div className="pd-filters">
        <div className="pd-seg" role="group" aria-label={t('alerts.filterLabel')}>
          {FILTERS.map((f) => (
            <button key={f} type="button" aria-pressed={filter === f} onClick={() => setFilter(f)}>
              {t(`alerts.filter.${f}`, { count: count(f) })}
            </button>
          ))}
        </div>
      </div>
      {visible.length === 0 ? (
        <p className="pl-no-match">{t(all.length ? 'alerts.noMatch' : 'alerts.empty')}</p>
      ) : (
        <section className="pl-plist" aria-label={t('alerts.listLabel')}>
          {visible.map((alert) => (
            <AlertRow key={alert.id} alert={alert} ctx={ctx} />
          ))}
        </section>
      )}
    </div>
  )
}
