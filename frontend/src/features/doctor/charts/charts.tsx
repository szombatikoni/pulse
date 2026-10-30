import { Bell } from '@phosphor-icons/react'
import { useTranslation } from 'react-i18next'

import { StatusIcon } from '../../../components/StatusLabel'
import { ChartShell, ThresholdLines, XAxis, YGrid } from './chartKit'
import {
  BAND_STATUS,
  daysAgo,
  fmtDayLong,
  fmtNum,
  lin,
  type Margin,
  nice,
  overKind,
  type Threshold,
  thresholdGroups,
  timeFrame,
} from './scale'

export type BpPoint = { id: string; t: Date; sys: number; dia: number; trig: boolean }
export type LinePoint = { id: string; t: Date; v: number }
export type ScorePoint = { id: string; t: Date; score: number; max: number; band: string }

/** Vérnyomás „súlyzóként": napi pálca, fent a szisztolés, lent a diasztolés pont.
 * A határ fölötti pont a státusz színét kapja, a riasztást kiváltó mérés gyűrűt. */
export function BpChart({
  points,
  thresholds,
  days,
  height,
  label,
  now,
}: {
  points: BpPoint[]
  thresholds: Threshold[]
  days: number
  height: number
  label: string
  now: Date
}) {
  const { t } = useTranslation()
  const m: Margin = { l: 36, r: thresholds.length ? 40 : 24, t: 10, b: 26 }
  const groups = thresholdGroups(thresholds)
  const unit = t('units.mmHg')

  return (
    <ChartShell
      height={height}
      label={label}
      margin={m}
      draw={(w) => {
        const f = timeFrame(w, days, m, now)
        const pts = points.filter((p) => daysAgo(p.t, now) < days)
        const vals = pts.flatMap((p) => [p.sys, p.dia])
        const tv = thresholds.map((th) => th.value)
        const nk = nice(Math.min(...vals, ...tv) - 8, Math.max(...vals, ...tv) + 8, 5)
        const y = lin(nk.lo, nk.hi, height - m.b, m.t)
        const r = Math.max(2.6, Math.min(4.5, f.dw * 0.3))
        const sw = Math.max(1.5, Math.min(2, r * 0.45))
        const lines = thresholds.map((th) => ({
          value: th.value,
          kind: th.kind,
          label: fmtNum(th.value),
        }))
        return {
          grid: (
            <>
              <YGrid ticks={nk.ticks} y={y} f={f} />
              <XAxis f={f} h={height} now={now} />
              <ThresholdLines thresholds={lines} y={y} f={f} />
            </>
          ),
          marks: (hot) =>
            pts.map((p, i) => {
              const X = f.xt(p.t).toFixed(1)
              const cs = overKind(thresholds, 'systolic', p.sys)
              const cd = overKind(thresholds, 'diastolic', p.dia)
              return (
                <g key={p.id}>
                  <line
                    className="stem"
                    x1={X}
                    x2={X}
                    y1={y(p.sys).toFixed(1)}
                    y2={y(p.dia).toFixed(1)}
                    strokeWidth={sw}
                  />
                  <circle className={`dot dia ${cd}`} cx={X} cy={y(p.dia).toFixed(1)} r={r} />
                  <circle
                    className={`dot sys ${cs}${hot === i ? ' is-hot' : ''}`}
                    cx={X}
                    cy={y(p.sys).toFixed(1)}
                    r={r}
                  />
                  {p.trig && thresholds.length > 0 && (
                    <circle className="trig" cx={X} cy={y(p.sys).toFixed(1)} r={r + 3.5} />
                  )}
                </g>
              )
            }),
          xs: pts.map((p) => f.xt(p.t)),
          ys: pts.map((p) => y(p.sys)),
          tip: (i) => {
            const p = pts[i]
            const sev = overKind(thresholds, 'systolic', p.sys) === 'sev'
            const mod =
              !sev &&
              (overKind(thresholds, 'systolic', p.sys) !== '' ||
                overKind(thresholds, 'diastolic', p.dia) !== '')
            return (
              <>
                <span className="tl">{fmtDayLong(p.t)}</span>
                <span className="tv">
                  {p.sys}/{p.dia} <small>{unit}</small>
                </span>
                {sev && (
                  <span className="tf">
                    <StatusIcon status="severe" size={14} />
                    {t('measurements.charts.overSevere', { value: groups.sev })}
                  </span>
                )}
                {mod && (
                  <span className="tf">
                    <StatusIcon status="attention" size={14} />
                    {t('measurements.charts.overLimit', { value: groups.mod || groups.sev })}
                  </span>
                )}
                {p.trig && thresholds.length > 0 && (
                  <span className="tf">
                    <Bell size={14} weight="bold" />
                    {t('doctor.flagged')}
                  </span>
                )}
              </>
            )
          },
        }
      }}
    />
  )
}

/** Egyértékű mérés (pulzus, testsúly, vércukor) vonalként. A vonal megszakad, ha
 * két mérés között a megszokottnál nagyobb a szünet; terület nincs, mert a tengely
 * nem nulláról indul, és a kitöltés nagyságot sugallna. */
export function LineChart({
  points,
  unit,
  dec,
  gap,
  thresholds,
  days,
  height,
  label,
  now,
}: {
  points: LinePoint[]
  unit: string
  dec: number
  gap: number
  thresholds: Threshold[]
  days: number
  height: number
  label: string
  now: Date
}) {
  const m: Margin = { l: 34, r: 40, t: 12, b: 26 }
  return (
    <ChartShell
      height={height}
      label={label}
      margin={m}
      draw={(w) => {
        const f = timeFrame(w, days, m, now)
        const pts = points.filter((p) => daysAgo(p.t, now) < days)
        const vs = [...pts.map((p) => p.v), ...thresholds.map((th) => th.value)]
        const span = Math.max(...vs) - Math.min(...vs)
        const pad = Math.max(span * 0.3, dec ? 1 : 4)
        const nk = nice(Math.min(...vs) - pad, Math.max(...vs) + pad, 3)
        const y = lin(nk.lo, nk.hi, height - m.b, m.t)
        const segs: LinePoint[][] = []
        let cur: LinePoint[] = []
        pts.forEach((p, i) => {
          if (i && daysAgo(pts[i - 1].t, now) - daysAgo(p.t, now) > gap) {
            segs.push(cur)
            cur = []
          }
          cur.push(p)
        })
        if (cur.length) segs.push(cur)
        const dots = gap > 3
        const last = pts[pts.length - 1]
        const lines = thresholds.map((th) => ({
          value: th.value,
          kind: th.kind,
          label: fmtNum(th.value),
        }))
        return {
          grid: (
            <>
              <YGrid
                ticks={nk.ticks}
                y={y}
                f={f}
                fmt={(v) => fmtNum(v, Number.isInteger(v) ? 0 : 1)}
              />
              <XAxis f={f} h={height} now={now} />
              <ThresholdLines thresholds={lines} y={y} f={f} />
            </>
          ),
          marks: (hot) => (
            <>
              {segs.map((s) => (
                <g key={s[0].id}>
                  {s.length > 1 && (
                    <path
                      className="line"
                      d={s
                        .map(
                          (p, i) => `${i ? 'L' : 'M'}${f.xt(p.t).toFixed(1)},${y(p.v).toFixed(1)}`,
                        )
                        .join('')}
                    />
                  )}
                  {(s.length === 1 || dots) &&
                    s.map((p) => (
                      <circle
                        key={p.id}
                        className={`dot pt ${overKind(thresholds, 'value', p.v)}`}
                        cx={f.xt(p.t).toFixed(1)}
                        cy={y(p.v).toFixed(1)}
                        r={3.5}
                      />
                    ))}
                </g>
              ))}
              {hot !== null && hot !== pts.length - 1 && (
                <circle
                  className="dot pt is-hot"
                  cx={f.xt(pts[hot].t).toFixed(1)}
                  cy={y(pts[hot].v).toFixed(1)}
                  r={4}
                />
              )}
              {last && (
                <>
                  <circle
                    className={hot === pts.length - 1 ? 'end is-hot' : 'end'}
                    cx={f.xt(last.t).toFixed(1)}
                    cy={y(last.v).toFixed(1)}
                    r={4.5}
                  />
                  <text
                    className="endl"
                    x={(f.xt(last.t) + 9).toFixed(1)}
                    y={(y(last.v) + 4).toFixed(1)}
                  >
                    {fmtNum(last.v, dec)}
                  </text>
                </>
              )}
            </>
          ),
          xs: pts.map((p) => f.xt(p.t)),
          ys: pts.map((p) => y(p.v)),
          tip: (i) => (
            <>
              <span className="tl">{fmtDayLong(pts[i].t)}</span>
              <span className="tv">
                {fmtNum(pts[i].v, dec)} <small>{unit}</small>
              </span>
            </>
          ),
        }
      }}
    />
  )
}

/** Kérdőív-pontszám: a pont a sáv színét kapja (kritikus = Súlyos, figyelmeztető =
 * Figyelem). A sávhatárt a kitöltés nem tartalmazza, ezért vonal nincs. */
export function ScoreChart({
  points,
  days,
  height,
  label,
  now,
}: {
  points: ScorePoint[]
  days: number
  height: number
  label: string
  now: Date
}) {
  const { t } = useTranslation()
  const m: Margin = { l: 34, r: 40, t: 12, b: 26 }
  return (
    <ChartShell
      height={height}
      label={label}
      margin={m}
      draw={(w) => {
        const f = timeFrame(w, days, m, now)
        const pts = points.filter((p) => daysAgo(p.t, now) < days)
        const max = Math.max(...pts.map((p) => p.max), 1)
        const nk = nice(0, max, 3)
        const y = lin(0, Math.max(max, nk.hi), height - m.b, m.t)
        const last = pts[pts.length - 1]
        return {
          grid: (
            <>
              <YGrid ticks={nk.ticks.filter((v) => v <= max)} y={y} f={f} />
              <XAxis f={f} h={height} now={now} />
            </>
          ),
          marks: (hot) => (
            <>
              {pts.length > 1 && (
                <path
                  className="line thin"
                  d={pts
                    .map(
                      (p, i) => `${i ? 'L' : 'M'}${f.xt(p.t).toFixed(1)},${y(p.score).toFixed(1)}`,
                    )
                    .join('')}
                />
              )}
              {pts.map((p, i) => {
                const cls = p.band === 'critical' ? 'sev' : p.band === 'warning' ? 'mod' : 'pt'
                return (
                  <circle
                    key={p.id}
                    className={`dot ${cls}${hot === i ? ' is-hot' : ''}`}
                    cx={f.xt(p.t).toFixed(1)}
                    cy={y(p.score).toFixed(1)}
                    r={4.5}
                  />
                )
              })}
              {last && (
                <text
                  className="endl"
                  x={(f.xt(last.t) + 9).toFixed(1)}
                  y={(y(last.score) + 4).toFixed(1)}
                >
                  {last.score}
                </text>
              )}
            </>
          ),
          xs: pts.map((p) => f.xt(p.t)),
          ys: pts.map((p) => y(p.score)),
          tip: (i) => {
            const p = pts[i]
            return (
              <>
                <span className="tl">{fmtDayLong(p.t)}</span>
                <span className="tv">
                  {p.score}
                  <small>{t('doctor.alert.points', { max: p.max })}</small>
                </span>
                <span className="tf">
                  <StatusIcon status={BAND_STATUS[p.band] ?? 'ok'} size={14} />
                  {t('measurements.charts.band', {
                    band: t(`questionnaires.bands.${p.band}`, { defaultValue: p.band }),
                  })}
                </span>
              </>
            )
          },
        }
      }}
    />
  )
}
