// A kérdőívszerkesztő (M3, A5) állapota és ellenőrzése, a felülettől függetlenül.
// A feltételek a szerver EditorVersionSpec-jét követik
// (backend/app/services/questionnaires.py); a felület azonnal jelzi a hibát, a
// szerver 422-je csak védőháló.
import type { TFunction } from 'i18next'

import {
  BANDS,
  type EditorQuestion,
  type GoodEnd,
  LIMITS,
  type QuestionnaireDetail,
  type QuestionType,
  type VersionSpec,
} from '../../api/questionnaireEditor'

export type Num = number | string

export type OptionDraft = { key: string; value: string; label: string; score: Num }

export type QuestionDraft = {
  key: string
  type: QuestionType
  text: string
  /** A skála felső vége; az alsó mindig 1 (1–5 vagy 1–10). */
  scaleMax: number
  /** Új kérdésnél üres, amíg az orvos nem választ (nincs alapértelmezés). */
  goodEnd: GoodEnd | null
  minLabel: string
  maxLabel: string
  options: OptionDraft[]
}

export type Draft = {
  name: string
  questions: QuestionDraft[]
  /** A „rendben" és a „figyelmeztető" sáv felső határa; a „kritikus" a legnagyobb
   * pontszámig tart (a három sáv neve rögzített, D2). */
  normalMax: Num
  warningMax: Num
}

let seq = 0
const nextKey = () => `k${++seq}`

function optionsFrom(q: EditorQuestion): OptionDraft[] {
  return q.options.map((o) => ({ key: nextKey(), value: o.value, label: o.label, score: o.score }))
}

/** A szerkesztő kezdőállapota: módosításnál az aktuális verzióból, új kérdőívnél
 * egy üres skálás kérdéssel és üres sávhatárokkal. */
export function draftFrom(detail: QuestionnaireDetail | null): Draft {
  if (!detail) {
    return { name: '', questions: [newQuestion()], normalMax: '', warningMax: '' }
  }
  const bands = detail.current.scoring_thresholds
  return {
    name: detail.name,
    questions: detail.current.questions.map((q) => ({
      key: nextKey(),
      type: q.question_type,
      text: q.text,
      scaleMax: q.scale_max ?? 5,
      goodEnd: q.good_end ?? null,
      minLabel: q.min_label ?? '',
      maxLabel: q.max_label ?? '',
      options: optionsFrom(q),
    })),
    normalMax: bands.find((b) => b.band === 'normal')?.max ?? '',
    warningMax: bands.find((b) => b.band === 'warning')?.max ?? '',
  }
}

export function newQuestion(): QuestionDraft {
  return {
    key: nextKey(),
    type: 'scale',
    text: '',
    scaleMax: 5,
    goodEnd: null,
    minLabel: '',
    maxLabel: '',
    options: [],
  }
}

/** Új lehetőség a kérdés lehetőségeitől különböző belső értékkel (a betegnek a
 * felirat látszik, a kitöltés az értéket tárolja). */
export function newOption(existing: OptionDraft[]): OptionDraft {
  const used = new Set(existing.map((o) => o.value))
  let i = existing.length + 1
  while (used.has(`o${i}`)) i += 1
  return { key: nextKey(), value: `o${i}`, label: '', score: '' }
}

/** Típusváltáskor a választós kérdés legalább két (üres) lehetőséggel indul. */
export function withType(q: QuestionDraft, type: QuestionType): QuestionDraft {
  if (type === 'scale' || q.options.length >= 2) return { ...q, type }
  const options = [...q.options]
  while (options.length < 2) options.push(newOption(options))
  return { ...q, type, options }
}

export function toNumber(value: Num): number | undefined {
  if (value === '' || value === undefined) return undefined
  return typeof value === 'number' ? value : Number(String(value).replace(',', '.'))
}

const isIntIn = (v: number | undefined, min: number, max: number): v is number =>
  v !== undefined && Number.isInteger(v) && v >= min && v <= max

/** A skála válasz → pont táblája a jobb vég szerint (a jobb vég 0 pont), mint a szerveren. */
export function scalePoints(q: QuestionDraft): [number, number][] | null {
  if (!q.goodEnd) return null
  const values = Array.from({ length: q.scaleMax }, (_, i) => i + 1)
  return values.map((v) => [v, q.goodEnd === 'min' ? v - 1 : q.scaleMax - v])
}

/** A kérdés legnagyobb pontszáma (skálánál a skála hossza − 1, egyválasztósnál a
 * legnagyobb, többválasztósnál az összeg); a még hibás pontot 0-nak veszi. */
export function questionMax(q: QuestionDraft): number {
  if (q.type === 'scale') return q.scaleMax - 1
  const scores = q.options.map((o) => {
    const n = toNumber(o.score)
    return isIntIn(n, 0, LIMITS.score) ? n : 0
  })
  if (scores.length === 0) return 0
  return q.type === 'multi' ? scores.reduce((a, b) => a + b, 0) : Math.max(...scores)
}

export const draftMax = (d: Draft) => d.questions.reduce((sum, q) => sum + questionMax(q), 0)

export type OptionErrors = { label?: string; score?: string }
export type QuestionErrors = {
  text?: string
  scale?: string
  goodEnd?: string
  minLabel?: string
  maxLabel?: string
  options?: string
  option: Record<string, OptionErrors>
}
export type DraftErrors = {
  name?: string
  questions?: string
  bands?: string
  normalMax?: string
  warningMax?: string
  question: Record<string, QuestionErrors>
}

function textError(t: TFunction, value: string, max: number, required = true) {
  const trimmed = value.trim()
  if (required && !trimmed) return t('qeditor.errors.required')
  if (trimmed.length > max) return t('qeditor.errors.tooLong', { n: max })
  return undefined
}

function questionErrors(t: TFunction, q: QuestionDraft): QuestionErrors {
  const e: QuestionErrors = { option: {} }
  e.text = textError(t, q.text, LIMITS.text)
  if (q.type === 'scale') {
    if (q.scaleMax !== 5 && q.scaleMax !== 10) e.scale = t('qeditor.errors.scale')
    if (!q.goodEnd) e.goodEnd = t('qeditor.errors.goodEnd')
    e.minLabel = textError(t, q.minLabel, LIMITS.endLabel, false)
    e.maxLabel = textError(t, q.maxLabel, LIMITS.endLabel, false)
    return e
  }
  if (q.options.length < 2) e.options = t('qeditor.errors.optionsMin')
  if (q.options.length > LIMITS.options) {
    e.options = t('qeditor.errors.optionsMax', { n: LIMITS.options })
  }
  for (const o of q.options) {
    const oe: OptionErrors = {}
    oe.label = textError(t, o.label, LIMITS.optionLabel)
    if (!isIntIn(toNumber(o.score), 0, LIMITS.score)) {
      oe.score = t('qeditor.errors.score', { max: LIMITS.score })
    }
    if (oe.label || oe.score) e.option[o.key] = oe
  }
  return e
}

const hasQuestionError = (e: QuestionErrors) =>
  !!(e.text || e.scale || e.goodEnd || e.minLabel || e.maxLabel || e.options) ||
  Object.keys(e.option).length > 0

/** Minden hiba mezőnként; üres objektum (és üres question) = érvényes. */
export function validate(t: TFunction, d: Draft, isNew: boolean): DraftErrors {
  const e: DraftErrors = { question: {} }
  if (isNew) e.name = textError(t, d.name, LIMITS.name)
  if (d.questions.length === 0) e.questions = t('qeditor.errors.questionsMin')
  if (d.questions.length > LIMITS.questions) {
    e.questions = t('qeditor.errors.questionsMax', { n: LIMITS.questions })
  }
  for (const q of d.questions) {
    const qe = questionErrors(t, q)
    if (hasQuestionError(qe)) e.question[q.key] = qe
  }
  const max = draftMax(d)
  const normal = toNumber(d.normalMax)
  const warning = toNumber(d.warningMax)
  if (max < 2) {
    e.bands = t('qeditor.errors.bandsTooSmall')
  } else {
    if (!isIntIn(normal, 0, max - 2)) {
      e.normalMax = t('qeditor.errors.normalMax', { max: max - 2 })
    }
    if (!isIntIn(warning, (isIntIn(normal, 0, max) ? normal : 0) + 1, max - 1)) {
      e.warningMax = t('qeditor.errors.warningMax', {
        min: (isIntIn(normal, 0, max) ? normal : 0) + 1,
        max: max - 1,
      })
    }
  }
  return e
}

export const isValid = (e: DraftErrors) =>
  !e.name &&
  !e.questions &&
  !e.bands &&
  !e.normalMax &&
  !e.warningMax &&
  Object.keys(e.question).length === 0

/** A szerkesztő állapotából a szerver verziója (csak érvényes állapotra hívandó). */
export function buildSpec(d: Draft): VersionSpec {
  const max = draftMax(d)
  const normal = toNumber(d.normalMax) ?? 0
  const warning = toNumber(d.warningMax) ?? 0
  const bounds: [number, number][] = [
    [0, normal],
    [normal + 1, warning],
    [warning + 1, max],
  ]
  return {
    questions: d.questions.map((q) =>
      q.type === 'scale'
        ? {
            question_type: 'scale',
            text: q.text.trim(),
            scale_min: 1,
            scale_max: q.scaleMax,
            good_end: q.goodEnd,
            min_label: q.minLabel.trim() || null,
            max_label: q.maxLabel.trim() || null,
            options: [],
          }
        : {
            question_type: q.type,
            text: q.text.trim(),
            options: q.options.map((o) => ({
              value: o.value,
              label: o.label.trim(),
              score: toNumber(o.score) ?? 0,
            })),
          },
    ),
    scoring_thresholds: BANDS.map((band, i) => ({ band, min: bounds[i][0], max: bounds[i][1] })),
  }
}
