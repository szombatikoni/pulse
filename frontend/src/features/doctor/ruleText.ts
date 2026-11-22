import type { TFunction } from 'i18next'

import type { MeasurementType } from '../../api/measurements'
import type { RuleParams, RuleType } from '../../api/patients'
import { componentLabel, formatNumber, unitLabel } from '../../format'

/** A szabály szövegéhez kellő törzsadat: a méréstípusok (komponensek, egységek)
 * és a kérdőívek neve kód szerint. */
export type RuleTextContext = {
  types: MeasurementType[]
  questionnaires: Record<string, string>
}

/** Egy paraméter szövegének jelölése. Az előnézetben a változott értéket
 * kiemeli (markChanged), máshol változatlanul adja vissza. A mező neve a
 * paraméter útja, pl. „limits.systolic.max", „count", „severity". */
export type Mark = (field: string, text: string) => string

const plain: Mark = (_field, text) => text

// A kiemelés jelei a szövegben; a renderelés (splitMarked) ezek mentén bont.
const START = '\u0002'
const END = '\u0003'

/** Kiemelő jelölő: a `changed` mezőket jelekkel veszi körül. */
export function markChanged(changed: Set<string>): Mark {
  return (field, text) => (changed.has(field) ? `${START}${text}${END}` : text)
}

/** A jelölt szöveg darabjai: [szöveg, kiemelt-e]. */
export function splitMarked(text: string): [string, boolean][] {
  const parts: [string, boolean][] = []
  for (const [i, chunk] of text.split(START).entries()) {
    if (i === 0) {
      if (chunk) parts.push([chunk, false])
      continue
    }
    const [hot, rest = ''] = chunk.split(END)
    parts.push([hot, true])
    if (rest) parts.push([rest, false])
  }
  return parts
}

/** A szabály célpontja: a méréstípus vagy a kérdőív neve. */
export function ruleTarget(t: TFunction, params: RuleParams, ctx: RuleTextContext): string {
  if (params.questionnaire) return ctx.questionnaires[params.questionnaire] ?? params.questionnaire
  const code = params.measurement_type ?? ''
  return t(`measurementTypes.${code}`, { defaultValue: code })
}

/** A határok felsorolva, a méréstípus komponenseinek sorrendjében:
 * „Szisztolés > 140 Hgmm vagy Diasztolés > 90 Hgmm". */
export function limitsText(
  t: TFunction,
  params: RuleParams,
  types: MeasurementType[],
  mark: Mark = plain,
): string {
  const typeCode = params.measurement_type ?? ''
  const type = types.find((x) => x.code === typeCode)
  const limits = params.limits ?? {}
  const order = type ? type.components.map((c) => c.code) : []
  const codes = [
    ...order.filter((c) => c in limits),
    ...Object.keys(limits).filter((c) => !order.includes(c)),
  ]
  return codes
    .flatMap((component) => {
      const limit = limits[component]
      const label = componentLabel(t, typeCode, component)
      const unit = unitLabel(t, type?.components.find((c) => c.code === component)?.unit ?? '')
      const parts: string[] = []
      if (limit.min !== undefined) {
        parts.push(`${label} < ${mark(`limits.${component}.min`, formatNumber(limit.min))} ${unit}`)
      }
      if (limit.max !== undefined) {
        parts.push(`${label} > ${mark(`limits.${component}.max`, formatNumber(limit.max))} ${unit}`)
      }
      return parts
    })
    .join(t('doctor.alert.or'))
}

/** A szabály feltétele a célpont nélkül, pl. „Szisztolés > 140 Hgmm, legalább 3
 * mérésnél 7 napon belül" vagy „a pontszám a(z) kritikus sávban". A riasztás
 * magyarázata, a szabálylista és a szerkesztő előnézete is ezt használja. */
export function ruleCondition(
  t: TFunction,
  ruleType: RuleType,
  params: RuleParams,
  ctx: RuleTextContext,
  mark: Mark = plain,
): string {
  switch (ruleType) {
    case 'threshold':
      return limitsText(t, params, ctx.types, mark)
    case 'window': {
      const count = params.count ?? 0
      const days = params.window_days ?? 0
      return t('rules.cond.window', {
        limits: limitsText(t, params, ctx.types, mark),
        count,
        n: mark('count', String(count)),
        days: t('rules.cond.days', { count: days, n: mark('window_days', String(days)) }),
      })
    }
    case 'questionnaire': {
      if (params.trend_count !== undefined) {
        return t('rules.cond.trend', {
          count: params.trend_count,
          n: mark('trend_count', String(params.trend_count)),
        })
      }
      const bands = (params.bands ?? [])
        .map((b) => t(`questionnaires.bands.${b}`, { defaultValue: b }))
        .join(t('doctor.alert.or'))
      return t('rules.cond.bands', { bands: mark('bands', bands) })
    }
    case 'missing_data': {
      const count = params.consecutive_missed ?? 0
      return t('rules.cond.missing', { count, n: mark('consecutive_missed', String(count)) })
    }
  }
}

/** A szabály mondata a listában: „Vérnyomás: Szisztolés > 180 Hgmm". */
export function ruleSentence(
  t: TFunction,
  ruleType: RuleType,
  params: RuleParams,
  ctx: RuleTextContext,
): string {
  return `${ruleTarget(t, params, ctx)}: ${ruleCondition(t, ruleType, params, ctx)}`
}
