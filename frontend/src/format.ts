import type { TFunction } from 'i18next'

import type { Measurement } from './api/measurements'
import type { Violation } from './api/patients'
import i18n from './i18n'

// A UCUM-egységkódok fordítási kulcsa (a kódban szögletes zárójel és perjel is van).
const UNIT_KEYS: Record<string, string> = {
  'mm[Hg]': 'mmHg',
  '/min': 'perMin',
  kg: 'kg',
  'mmol/L': 'mmolL',
}

const locale = () => (i18n.language === 'en' ? 'en-GB' : 'hu-HU')

export function unitLabel(t: TFunction, unit: string): string {
  const key = UNIT_KEYS[unit]
  return key ? t(`units.${key}`) : unit
}

/** A `datetime-local` mező formátuma helyi időben: 2026-10-12T07:30. */
export function toLocalInput(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

export function formatNumber(value: number): string {
  return new Intl.NumberFormat(locale(), { maximumFractionDigits: 1 }).format(value)
}

export function formatDateTime(iso: string): string {
  return new Intl.DateTimeFormat(locale(), {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(iso))
}

export function formatTime(date: Date): string {
  return new Intl.DateTimeFormat(locale(), { hour: '2-digit', minute: '2-digit' }).format(date)
}

/** „ma 07:30", „tegnap 07:30", „5 napja" — a beteglista „Utolsó adat" oszlopához. */
export function formatRelative(t: TFunction, iso: string, now = new Date()): string {
  const date = new Date(iso)
  const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
  const days = Math.round((startOfDay(now) - startOfDay(date)) / 86_400_000)
  if (days <= 0) return t('relative.today', { time: formatTime(date) })
  if (days === 1) return t('relative.yesterday', { time: formatTime(date) })
  return t('relative.daysAgo', { count: days })
}

export function ageInYears(birthDate: string, now = new Date()): number {
  const birth = new Date(birthDate)
  let age = now.getFullYear() - birth.getFullYear()
  const beforeBirthday =
    now.getMonth() < birth.getMonth() ||
    (now.getMonth() === birth.getMonth() && now.getDate() < birth.getDate())
  if (beforeBirthday) age -= 1
  return age
}

export function componentLabel(t: TFunction, typeCode: string, component: string): string {
  // Egyértékű mérésnél a komponens neve maga a méréstípus (pl. Pulzus).
  return component === 'value' ? t(`measurementTypes.${typeCode}`) : t(`components.${component}`)
}

/** Egy mérés értéke olvashatóan: „152/95 Hgmm", „72 /perc". */
export function formatMeasurementValue(t: TFunction, measurement: Measurement): string {
  const unit = unitLabel(t, measurement.values[0]?.unit ?? '')
  if (measurement.type_code === 'blood_pressure') {
    const byCode = Object.fromEntries(measurement.values.map((v) => [v.component, v.value]))
    return `${formatNumber(byCode.systolic)}/${formatNumber(byCode.diastolic)} ${unit}`
  }
  return measurement.values.map((v) => `${formatNumber(v.value)} ${unit}`).join(', ')
}

/** Egy mérés száma egység nélkül: „152/95", „85,8". */
export function formatMeasurementNumber(measurement: Measurement): string {
  if (measurement.type_code === 'blood_pressure') {
    const byCode = Object.fromEntries(measurement.values.map((v) => [v.component, v.value]))
    return `${formatNumber(byCode.systolic)}/${formatNumber(byCode.diastolic)}`
  }
  return measurement.values.map((v) => formatNumber(v.value)).join(', ')
}

/** A nap felirata az előzményekhez: „Ma, szombat", „Tegnap, péntek", „október 15., csütörtök". */
export function formatDayLabel(t: TFunction, iso: string, now = new Date()): string {
  const date = new Date(iso)
  const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
  const days = Math.round((startOfDay(now) - startOfDay(date)) / 86_400_000)
  const weekday = new Intl.DateTimeFormat(locale(), { weekday: 'long' }).format(date)
  if (days === 0) return t('relative.dayToday', { weekday })
  if (days === 1) return t('relative.dayYesterday', { weekday })
  const day = new Intl.DateTimeFormat(locale(), { month: 'long', day: 'numeric' }).format(date)
  return `${day}, ${weekday}`
}

/** Egy közeli időpont röviden: „ma 10:00", „holnap 21:00", „hétfő 20:00". */
export function formatSoon(t: TFunction, iso: string, now = new Date()): string {
  const date = new Date(iso)
  const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
  const days = Math.round((startOfDay(date) - startOfDay(now)) / 86_400_000)
  const time = formatTime(date)
  if (days === 0) return t('tasks.today', { time })
  if (days === 1) return t('tasks.tomorrow', { time })
  const day = new Intl.DateTimeFormat(locale(), { weekday: 'long' }).format(date)
  return t('tasks.weekday', { day, time })
}

/** Pótlási határ: éjfélre eső időpontnál „vasárnap éjfélig", különben „hétfő 10:00". */
export function formatUntil(t: TFunction, iso: string, now = new Date()): string {
  const date = new Date(iso)
  if (date.getHours() === 0 && date.getMinutes() === 0) {
    const dayBefore = new Date(date.getTime() - 60_000)
    const day = new Intl.DateTimeFormat(locale(), { weekday: 'long' }).format(dayBefore)
    return t('tasks.untilMidnight', { day })
  }
  return formatSoon(t, iso, now)
}

/** Határátlépés olvashatóan: „Szisztolés 152 Hgmm (> 140)". */
export function formatViolation(t: TFunction, measurement: Measurement, v: Violation): string {
  const unit = measurement.values.find((x) => x.component === v.component)?.unit ?? ''
  const sign = v.bound === 'max' ? '>' : '<'
  return `${componentLabel(t, measurement.type_code, v.component)} ${formatNumber(v.value)} ${unitLabel(t, unit)} (${sign} ${formatNumber(v.limit)})`
}
