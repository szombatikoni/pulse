import type { TFunction } from 'i18next'

import type { OccurrenceTrigger, StatusReason, Trigger } from '../../api/patients'
import { formatDateTime, formatNumber, formatViolation } from '../../format'

/** Egy alkalom olvashatóan: a célpont és a határidő, pl. „Vérnyomás, határidő
 * nov. 8. 10:00". */
export function occurrenceText(t: TFunction, o: OccurrenceTrigger): string {
  const name =
    o.target_kind === 'measurement'
      ? t(`measurementTypes.${o.code}`, { defaultValue: o.name })
      : t('doctor.occurrence.questionnaire', { name: o.name })
  return t('doctor.occurrence.text', { name, due: formatDateTime(o.due_at) })
}

/** Egy kiváltó adat olvashatóan: mérésnél a határátlépések, kitöltésnél a
 * pontszám és a sáv, pl. „„Közérzet” kérdőív: 6/13 pont (figyelmeztető sáv)”,
 * elmulasztott alkalomnál a célpont és a határidő. */
export function triggerText(t: TFunction, trigger: Trigger): string {
  if (trigger.submission) {
    const s = trigger.submission
    return t('questionnaires.scoreSummary', {
      name: s.questionnaire_name,
      score: s.total_score,
      max: s.max_score,
      band: t(`questionnaires.bands.${s.band}`, { defaultValue: s.band }),
    })
  }
  if (trigger.measurement) {
    const measurement = trigger.measurement
    return trigger.violations.map((v) => formatViolation(t, measurement, v)).join(', ')
  }
  if (trigger.occurrence) return occurrenceText(t, trigger.occurrence)
  return ''
}

/** A mérés átlépett határai röviden, a komponensek sorrendjében, pl. „> 140 / > 90"
 * vagy „< 50". A többkiváltós listák sorában áll, ahol az érték már előtte szerepel,
 * ezért itt csak a határ kell; a folyószöveges helyek a teljes triggerText-et használják. */
export function violationLimits(trigger: Trigger): string {
  const order = trigger.measurement?.values.map((v) => v.component) ?? []
  const rank = (component: string) => {
    const i = order.indexOf(component)
    return i === -1 ? order.length : i
  }
  return [...trigger.violations]
    .sort((a, b) => rank(a.component) - rank(b.component))
    .map((v) => `${v.bound === 'max' ? '>' : '<'} ${formatNumber(v.limit)}`)
    .join(' / ')
}

/** A kiváltó adat azonosítója (az ismétlődő okok kiszűréséhez és React-kulcsnak). */
export const triggerId = (trigger: Trigger | null | undefined) =>
  trigger?.submission?.id ?? trigger?.measurement?.id ?? trigger?.occurrence?.id

/** Az okok listája ismétlés nélkül: ha két riasztást ugyanaz az adat váltott ki
 * (pl. egy kritikus kitöltés a közepes és a súlyos szabályt is), az ok csak egyszer,
 * a súlyosabbnál jelenik meg. */
export function uniqueReasons(reasons: StatusReason[]): StatusReason[] {
  const seen = new Set<string>()
  return reasons.filter((reason) => {
    const id = triggerId(reason.trigger)
    if (!id) return true
    if (seen.has(id)) return false
    seen.add(id)
    return true
  })
}

/** Az „Ok" oszlop egy mondata egy státuszokhoz. Riasztásnál a legutóbbi kiváltó
 * mérés határátlépései, pl. „Szisztolés 152 Hgmm (> 140), Diasztolés 95 Hgmm (> 90)";
 * elmulasztott alkalomnál „Elmulasztott alkalom: Vérnyomás, határidő nov. 8. 10:00". */
export function reasonText(t: TFunction, reason: StatusReason): string {
  if (reason.code === 'open_alert' && reason.trigger) return triggerText(t, reason.trigger)
  if (reason.code === 'missed_occurrence' && reason.trigger?.occurrence) {
    return t('doctor.reasons.missedAt', { data: occurrenceText(t, reason.trigger.occurrence) })
  }
  return t(`doctor.reasons.${reason.code}`)
}
