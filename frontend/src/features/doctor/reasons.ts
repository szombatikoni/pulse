import type { TFunction } from 'i18next'

import type { StatusReason, Trigger } from '../../api/patients'
import { formatViolation } from '../../format'

/** Egy kiváltó adat olvashatóan: mérésnél a határátlépések, kitöltésnél a
 * pontszám és a sáv, pl. „„Közérzet” kérdőív: 6/13 pont (figyelmeztető sáv)”. */
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
  return ''
}

/** Az okok listája ismétlés nélkül: ha két riasztást ugyanaz az adat váltott ki
 * (pl. egy kritikus kitöltés a közepes és a súlyos szabályt is), az ok csak egyszer,
 * a súlyosabbnál jelenik meg. */
export function uniqueReasons(reasons: StatusReason[]): StatusReason[] {
  const seen = new Set<string>()
  return reasons.filter((reason) => {
    const id = reason.trigger?.submission?.id ?? reason.trigger?.measurement?.id
    if (!id) return true
    if (seen.has(id)) return false
    seen.add(id)
    return true
  })
}

/** Az „Ok" oszlop egy mondata egy státuszokhoz. Riasztásnál a legutóbbi kiváltó
 * mérés határátlépései, pl. „Szisztolés 152 Hgmm (> 140), Diasztolés 95 Hgmm (> 90)". */
export function reasonText(t: TFunction, reason: StatusReason): string {
  if (reason.code === 'open_alert' && reason.trigger) return triggerText(t, reason.trigger)
  return t(`doctor.reasons.${reason.code}`)
}
