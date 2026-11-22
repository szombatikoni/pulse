import type { TFunction } from 'i18next'

import type { Alert, AlertEvent, PatientStatus, Trigger } from '../../api/patients'
import { formatDateTime, formatMeasurementNumber, formatRelative, unitLabel } from '../../format'
import { ruleTarget, type RuleTextContext } from './ruleText'

/** A riasztás közös szövegei: a beteg-adatlap kártyája és a Riasztások oldal sora
 * ugyanabból a forrásból írja ki, mi történt. */

/** A legújabb kiváltó esemény összes kiváltó adata. Időablakos szabálynál ez az
 * ablak összes határsértő mérése, romló trendnél a kitöltések, elmaradt adatnál az
 * elmulasztott alkalmak (mind időrendben). A „kiváltó adat javítva” esemény nem
 * kiértékelés (a kiváltói az eredeti és a javított mérés), ezért kimarad (A7). */
export function latestTriggers(alert: Alert): Trigger[] {
  for (let i = alert.events.length - 1; i >= 0; i -= 1) {
    const event = alert.events[i]
    if (event.event_type === 'trigger_corrected') continue
    if (event.triggers.length) return event.triggers
  }
  return []
}

/** A riasztás legutóbbi kiváltó adata (a legújabb eseményből). */
export function latestTrigger(alert: Alert): Trigger | undefined {
  return latestTriggers(alert).at(-1)
}

/** A riasztás címe: mi történt, hétköznapi szavakkal. */
export function alertTitle(
  t: TFunction,
  alert: Alert,
  trigger: Trigger | null | undefined,
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
export function bigValue(t: TFunction, trigger: Trigger | null | undefined) {
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

/** A „kiváltó adat javítva” esemény mondata (A7), pl. „148/92 → 131/82 Hgmm · a
 * feltétel már nem teljesül”. A kiváltók sorrendje: [eredeti, javított]. */
export function correctionText(t: TFunction, event: AlertEvent): string {
  const [from, to] = event.triggers.map((tr) => tr.measurement)
  if (!from || !to) return ''
  const unit = unitLabel(t, to.values[0]?.unit ?? '')
  const change = `${formatMeasurementNumber(from)} → ${formatMeasurementNumber(to)} ${unit}`
  if (event.condition_met === null || event.condition_met === undefined) return change
  const condition = event.condition_met
    ? t('doctor.alert.conditionStillMet')
    : t('doctor.alert.conditionNoLongerMet')
  return `${change} · ${condition}`
}

/** A riasztás jele a súlyossága szerint. A felelősnél lévő riasztás sem „Kezelve”:
 * a Kezelve a lezárást jelenti (07-es dokumentum, A6 D4a). */
export const alertSeverityStatus = (alert: Alert): PatientStatus =>
  alert.severity === 'severe' ? 'severe' : 'attention'
