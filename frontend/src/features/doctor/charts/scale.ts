import type { PatientStatus } from '../../../api/patients'
import i18n from '../../../i18n'

// A grafikonok skálái és formázói (a komponensek a chartKit.tsx-ben).

export const DAY = 86_400_000
export const startOfDay = (d: Date) =>
  new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
export const daysAgo = (d: Date, now: Date) => Math.round((startOfDay(now) - startOfDay(d)) / DAY)

const locale = () => (i18n.language === 'en' ? 'en-GB' : 'hu-HU')

/** „okt. 30." */
export const fmtDay = (d: Date) =>
  new Intl.DateTimeFormat(locale(), { month: 'short', day: 'numeric' }).format(d)
/** „okt. 30., péntek · 07:24" a tooltiphez. */
export const fmtDayLong = (d: Date) =>
  `${new Intl.DateTimeFormat(locale(), { month: 'short', day: 'numeric', weekday: 'long' }).format(d)} · ${new Intl.DateTimeFormat(locale(), { hour: '2-digit', minute: '2-digit' }).format(d)}`
/** Rögzített tizedesjegyű szám: a testsúly mindig „86,4", sosem „86". */
export const fmtNum = (v: number, dec = 0) =>
  new Intl.NumberFormat(locale(), {
    minimumFractionDigits: dec,
    maximumFractionDigits: dec,
  }).format(v)

/** Egy határvonal: melyik összetevőre, felső vagy alsó határ, közepes vagy súlyos. */
export type Threshold = {
  value: number
  component: string
  bound: 'max' | 'min'
  kind: 'mod' | 'sev'
}

/** Az érték melyik határt lépi át: a súlyos erősebb a közepesnél. */
export function overKind(
  thresholds: Threshold[],
  component: string,
  value: number,
): 'mod' | 'sev' | '' {
  let kind: 'mod' | 'sev' | '' = ''
  for (const th of thresholds) {
    if (th.component !== component) continue
    const over = th.bound === 'max' ? value > th.value : value < th.value
    if (over && (kind === '' || th.kind === 'sev')) kind = th.kind
  }
  return kind
}

export const lin = (d0: number, d1: number, r0: number, r1: number) => (v: number) =>
  r0 + ((v - d0) * (r1 - r0)) / (d1 - d0 || 1)

/** Kerek osztásköz: 1, 2, 5 vagy 10 hatványai. */
export function nice(lo: number, hi: number, count: number) {
  const raw = (hi - lo || 1) / count
  const mag = 10 ** Math.floor(Math.log10(raw))
  const f = raw / mag
  const step = (f >= 7.5 ? 10 : f >= 3.5 ? 5 : f >= 1.5 ? 2 : 1) * mag
  const a = Math.floor(lo / step) * step
  const b = Math.ceil(hi / step) * step
  const ticks: number[] = []
  for (let v = a; v <= b + step * 1e-6; v += step) ticks.push(Math.round(v * 1e6) / 1e6)
  return { lo: a, hi: b, ticks }
}

export type Margin = { l: number; r: number; t: number; b: number }

/** Az időtengely: a napok egyenlő oszlopok, a napon belül az óra szerint toljuk el
 * a pontot (a reggeli és az esti mérés így nem esik egymásra). */
export function timeFrame(w: number, days: number, m: Margin, now: Date) {
  const x0 = m.l
  const x1 = w - m.r
  const dw = (x1 - x0) / days
  const xt = (d: Date) =>
    x0 + (days - 1 - daysAgo(d, now) + (d.getHours() * 60 + d.getMinutes()) / 1440) * dw
  return { n: days, x0, x1, dw, xt }
}
export type Frame = ReturnType<typeof timeFrame>

export const BAND_STATUS: Record<string, PatientStatus> = {
  normal: 'ok',
  warning: 'attention',
  critical: 'severe',
}

/** A határok felirata: a közepesek egy csoportban („140/90"), a súlyosak külön. */
export function thresholdGroups(thresholds: Threshold[]) {
  const values = (kind: 'mod' | 'sev') =>
    [...new Set(thresholds.filter((th) => th.kind === kind).map((th) => th.value))]
      .sort((a, b) => b - a)
      .map((v) => fmtNum(v))
      .join('/')
  return { mod: values('mod'), sev: values('sev') }
}
