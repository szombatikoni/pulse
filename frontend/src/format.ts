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

function formatTime(date: Date): string {
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

/** Határátlépés olvashatóan: „Szisztolés 152 Hgmm (> 140)". */
export function formatViolation(t: TFunction, measurement: Measurement, v: Violation): string {
  const unit = measurement.values.find((x) => x.component === v.component)?.unit ?? ''
  const sign = v.bound === 'max' ? '>' : '<'
  return `${componentLabel(t, measurement.type_code, v.component)} ${formatNumber(v.value)} ${unitLabel(t, unit)} (${sign} ${formatNumber(v.limit)})`
}
