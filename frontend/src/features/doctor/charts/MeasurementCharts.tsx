import { Loader, Text } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { type ReactNode, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { apiGet } from '../../../api/client'
import type { Measurement } from '../../../api/measurements'
import type { Alert } from '../../../api/patients'
import type { Submission } from '../../../api/questionnaires'
import { StatusIcon } from '../../../components/StatusLabel'
import { formatDateTime, formatRelative } from '../../../format'
import '../patientDetail.css'
import {
  BpChart,
  type BpPoint,
  LineChart,
  type LinePoint,
  ScoreChart,
  type ScorePoint,
} from './charts'
import { BAND_STATUS, daysAgo, fmtNum, overKind, type Threshold, thresholdGroups } from './scale'

const PERIODS = [14, 30, 90]

/** A grafikonhoz a teljes, 90 napot lefedő sor kell; a lista 50 mérést kér, ez 500-at
 * (a végpont felső határa). Az előtag miatt a mérés mentése ezt is frissíti. */
function useMeasurementSeries(patientId: string) {
  return useQuery({
    queryKey: ['patients', patientId, 'measurements', 'series'],
    queryFn: () => apiGet<Measurement[]>(`/patients/${patientId}/measurements?limit=500`),
  })
}

/** A riasztások szabályverzióiból a méréstípus határai (szabályonként a legújabb
 * verzió). Szabálylista-végpont még nincs (M3), ezért csak a már jelzett szabályok
 * határa látszik; adatot nem találunk ki. */
function thresholdsFor(alerts: Alert[], typeCode: string): Threshold[] {
  const latest = new Map<string, Alert['rule_version']>()
  for (const version of alerts.flatMap((a) => [
    a.rule_version,
    ...a.events.flatMap((e) => (e.rule_version ? [e.rule_version] : [])),
  ])) {
    const prev = latest.get(version.rule_id)
    if (!prev || prev.version_no < version.version_no) latest.set(version.rule_id, version)
  }
  const out = new Map<string, Threshold>()
  for (const version of latest.values()) {
    if (version.params.measurement_type !== typeCode) continue
    const kind = version.severity === 'severe' ? 'sev' : 'mod'
    for (const [component, limit] of Object.entries(version.params.limits ?? {})) {
      for (const bound of ['max', 'min'] as const) {
        const value = limit[bound]
        if (value === undefined) continue
        const key = `${component}-${bound}-${value}`
        if (!out.has(key) || kind === 'sev') out.set(key, { value, component, bound, kind })
      }
    }
  }
  return [...out.values()]
}

function Seg<T extends string | number>({
  label,
  options,
  value,
  onChange,
}: {
  label: string
  options: [T, string][]
  value: T
  onChange: (v: T) => void
}) {
  return (
    <div className="pd-seg" role="group" aria-label={label}>
      {options.map(([v, l]) => (
        <button key={v} type="button" aria-pressed={v === value} onClick={() => onChange(v)}>
          {l}
        </button>
      ))}
    </div>
  )
}

const LegendDot = ({ color }: { color: string }) => (
  <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
    <circle cx="5" cy="5" r="4" fill={color} />
  </svg>
)
const LegendDash = ({ color }: { color: string }) => (
  <svg width="18" height="6" viewBox="0 0 18 6" aria-hidden="true">
    <path d="M0 3h5M8 3h5M16 3h2" stroke={color} strokeWidth="1.6" />
  </svg>
)
const LegendRing = () => (
  <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
    <circle cx="7" cy="7" r="5.5" fill="none" stroke="var(--pulse-ink-1)" strokeWidth="1.5" />
  </svg>
)

const Empty = ({ children }: { children: ReactNode }) => (
  <div className="pd-chart-empty">{children}</div>
)

const valueOf = (m: Measurement, component = 'value') =>
  (m.values.find((v) => v.component === component) ?? m.values[0])?.value ?? 0

/** Mérések grafikonon vagy táblázatban (felületterv: measurementsSection). Az
 * orvos a határvonalakat, a riasztást kiváltó méréseket és a kérdőív-pontszámot is
 * látja; a beteg csak a saját görbéit, értékelés nélkül. */
export function MeasurementCharts({
  patientId,
  doctor = false,
  alerts = [],
  submissions = [],
}: {
  patientId: string
  doctor?: boolean
  alerts?: Alert[]
  submissions?: Submission[]
}) {
  const { t } = useTranslation()
  const series = useMeasurementSeries(patientId)
  const [days, setDays] = useState(30)
  const [mode, setMode] = useState<'chart' | 'table'>('chart')
  const now = new Date()
  const table = mode === 'table'

  const head = (
    <div className="pd-sec-head">
      <h2 className="pd-h-sec">
        {doctor ? t('doctor.measurementsTitle') : t('measurements.charts.mine')}
      </h2>
      <div className="pd-filters">
        <Seg
          label={t('measurements.charts.period')}
          options={PERIODS.map((d) => [d, t('measurements.charts.days', { count: d })])}
          value={days}
          onChange={setDays}
        />
        <Seg
          label={t('measurements.charts.view')}
          options={[
            ['chart', t('measurements.charts.chart')],
            ['table', t('measurements.charts.table')],
          ]}
          value={mode}
          onChange={setMode}
        />
      </div>
    </div>
  )

  if (series.isPending)
    return (
      <section className="pd-sec">
        {head}
        <Loader size="sm" />
      </section>
    )
  if (series.isError)
    return (
      <section className="pd-sec">
        {head}
        <Text c="red">{t('errors.unavailable')}</Text>
      </section>
    )

  // A végpont a legújabbat adja elöl; a grafikon időrendben rajzol.
  const all = [...series.data].reverse()
  const ofType = (code: string) => all.filter((m) => m.type_code === code)
  const inRange = <P extends { t: Date }>(arr: P[]) => arr.filter((p) => daysAgo(p.t, now) < days)

  const flagged = new Set(
    alerts.flatMap((a) =>
      a.events.flatMap((e) =>
        e.triggers.flatMap((tr) => (tr.measurement ? [tr.measurement.id] : [])),
      ),
    ),
  )
  const bpThr = doctor ? thresholdsFor(alerts, 'blood_pressure') : []
  const groups = thresholdGroups(bpThr)

  const bpAll: BpPoint[] = ofType('blood_pressure').map((m) => ({
    id: m.id,
    t: new Date(m.measured_at),
    sys: valueOf(m, 'systolic'),
    dia: valueOf(m, 'diastolic'),
    trig: flagged.has(m.id),
  }))
  const lineOf = (code: string): LinePoint[] =>
    ofType(code).map((m) => ({ id: m.id, t: new Date(m.measured_at), v: valueOf(m) }))

  if (all.length === 0) {
    return (
      <section className="pd-sec">
        {head}
        <div className="pd-card">
          <Empty>{t('measurements.charts.noneYet')}</Empty>
        </div>
      </section>
    )
  }

  const bp = inRange(bpAll)
  const lastBP = bpAll[bpAll.length - 1]
  const mmHg = t('units.mmHg')
  const rangeLabel = (title: string) => t('measurements.charts.rangeLabel', { title, count: days })
  const bpBody = !bp.length ? (
    <Empty>{t('measurements.charts.noBp')}</Empty>
  ) : table ? (
    <BpTable points={bp} thresholds={bpThr} doctor={doctor} />
  ) : (
    <BpChart
      points={bpAll}
      thresholds={bpThr}
      days={days}
      height={270}
      label={rangeLabel(t('measurementTypes.blood_pressure'))}
      now={now}
    />
  )

  const multiples: ReactNode[] = []
  const lineCard = (code: string, unitCode: string, dec: number, gap: number, always: boolean) => {
    const full = lineOf(code)
    // Az orvos a fő típusokat üresen is látja; a beteg csak azt, amiből van mérése.
    if (!(always && doctor) && !full.length) return
    const pts = inRange(full)
    const last = full[full.length - 1]
    const unit = t(`units.${unitCode}`)
    const title = t(`measurementTypes.${code}`)
    const thr = doctor
      ? thresholdsFor(alerts, code).map((th) => ({ ...th, component: 'value' }))
      : []
    multiples.push(
      <div className="pd-card" key={code}>
        <div className="pd-mult-head">
          <h3 className="pd-h-card">{title}</h3>
          {last && (
            <span className="v">
              {fmtNum(last.v, dec)} <small>{unit}</small>
            </span>
          )}
        </div>
        {!pts.length ? (
          <Empty>{t('measurements.charts.noneInRange')}</Empty>
        ) : table ? (
          <LineTable points={pts} unit={unit} dec={dec} />
        ) : (
          <LineChart
            points={full}
            unit={unit}
            dec={dec}
            gap={gap}
            thresholds={thr}
            days={days}
            height={150}
            label={rangeLabel(title)}
            now={now}
          />
        )}
      </div>,
    )
  }
  lineCard('heart_rate', 'perMin', 0, 3, true)
  lineCard('body_weight', 'kg', 1, 10, true)
  lineCard('blood_glucose', 'mmolL', 1, 3, false)

  if (doctor) {
    // Kérdőívenként egy kis grafikon (a demóban egy: Közérzet).
    const byCode = new Map<string, Submission[]>()
    for (const s of submissions)
      byCode.set(s.questionnaire_code, [...(byCode.get(s.questionnaire_code) ?? []), s])
    for (const [code, list] of byCode) {
      const full: ScorePoint[] = [...list].reverse().map((s) => ({
        id: s.id,
        t: new Date(s.submitted_at),
        score: s.total_score,
        max: s.max_score,
        band: s.band,
      }))
      const pts = inRange(full)
      const last = full[full.length - 1]
      const title = list[0].questionnaire_name
      multiples.push(
        <div className="pd-card" key={`q-${code}`}>
          <div className="pd-mult-head">
            <h3 className="pd-h-card">{title}</h3>
            {last && (
              <span className="v">
                {last.score}
                <small>{t('doctor.alert.points', { max: last.max })}</small>
              </span>
            )}
          </div>
          {!pts.length ? (
            <Empty>{t('measurements.charts.noSubmissionInRange')}</Empty>
          ) : table ? (
            <ScoreTable points={[...pts].reverse()} />
          ) : (
            <ScoreChart
              points={full}
              days={days}
              height={150}
              label={rangeLabel(title)}
              now={now}
            />
          )}
        </div>,
      )
    }
  }

  return (
    <section className="pd-sec" aria-label={t('doctor.measurementsTitle')}>
      {head}
      <div className="pd-card pd-chart-card">
        <div className="pd-card-head">
          <div className="left">
            <h3 className="pd-h-card">{t('measurementTypes.blood_pressure')}</h3>
            <span className="pd-meta">
              {mmHg} · {t('measurements.charts.countInRange', { count: bp.length })}
            </span>
          </div>
          {lastBP && (
            <div className="pd-mult-head">
              <span className="v">
                {lastBP.sys}/{lastBP.dia}
                <small>
                  {mmHg}, {formatRelative(t, lastBP.t.toISOString())}
                </small>
              </span>
            </div>
          )}
        </div>
        {!table && bp.length > 0 && (
          <div className="pd-legend">
            <span className="k">
              <LegendDot color="var(--pulse-ink-1)" />
              {t('measurements.charts.systolicDot')}
            </span>
            <span className="k">
              <LegendDot color="var(--pulse-ink-3)" />
              {t('measurements.charts.diastolicDot')}
            </span>
            {groups.mod && (
              <span className="k">
                <LegendDash color="var(--pulse-warn)" />
                {t('measurements.charts.modLimit', { value: groups.mod })}
              </span>
            )}
            {groups.sev && (
              <span className="k">
                <LegendDash color="var(--pulse-severe)" />
                {t('measurements.charts.sevLimit', { value: groups.sev })}
              </span>
            )}
            {doctor && bp.some((p) => p.trig) && (
              <span className="k">
                <LegendRing />
                {t('doctor.flagged')}
              </span>
            )}
          </div>
        )}
        {bpBody}
      </div>
      <div className={multiples.length === 2 ? 'pd-multiples two' : 'pd-multiples'}>
        {multiples}
      </div>
    </section>
  )
}

function BpTable({
  points,
  thresholds,
  doctor,
}: {
  points: BpPoint[]
  thresholds: Threshold[]
  doctor: boolean
}) {
  const { t } = useTranslation()
  return (
    <div className="pd-tbl-wrap">
      <table className="pd-tbl">
        <thead>
          <tr>
            <th>{t('measurements.charts.time')}</th>
            <th className="n">{t('components.systolic')}</th>
            <th className="n">{t('components.diastolic')}</th>
            {doctor && <th>{t('measurements.charts.note')}</th>}
          </tr>
        </thead>
        <tbody>
          {[...points].reverse().map((p) => {
            const sys = thresholds.length ? overKindOf(thresholds, p) : ''
            return (
              <tr key={p.id}>
                <td>{formatDateTime(p.t.toISOString())}</td>
                <td className="n strong">{p.sys}</td>
                <td className="n strong">{p.dia}</td>
                {doctor && (
                  <td>
                    {sys && (
                      <span className="pd-flag">
                        <StatusIcon status={sys === 'sev' ? 'severe' : 'attention'} size={14} />
                        {t(
                          sys === 'sev'
                            ? 'measurements.charts.flagSevere'
                            : 'measurements.charts.flagLimit',
                        )}
                      </span>
                    )}
                    {p.trig && (
                      <span className="pd-muted"> · {t('measurements.charts.flagAlert')}</span>
                    )}
                  </td>
                )}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function overKindOf(thresholds: Threshold[], p: BpPoint): 'mod' | 'sev' | '' {
  const sys = overKind(thresholds, 'systolic', p.sys)
  const dia = overKind(thresholds, 'diastolic', p.dia)
  return sys === 'sev' || dia === 'sev' ? 'sev' : sys || dia
}

function LineTable({ points, unit, dec }: { points: LinePoint[]; unit: string; dec: number }) {
  const { t } = useTranslation()
  return (
    <div className="pd-tbl-wrap">
      <table className="pd-tbl">
        <thead>
          <tr>
            <th>{t('measurements.charts.time')}</th>
            <th className="n">{unit}</th>
          </tr>
        </thead>
        <tbody>
          {[...points].reverse().map((p) => (
            <tr key={p.id}>
              <td>{formatDateTime(p.t.toISOString())}</td>
              <td className="n strong">{fmtNum(p.v, dec)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ScoreTable({ points }: { points: ScorePoint[] }) {
  const { t } = useTranslation()
  return (
    <div className="pd-tbl-wrap">
      <table className="pd-tbl">
        <thead>
          <tr>
            <th>{t('questionnaires.columns.time')}</th>
            <th className="n">{t('measurements.charts.points')}</th>
            <th>{t('questionnaires.columns.band')}</th>
          </tr>
        </thead>
        <tbody>
          {points.map((p) => (
            <tr key={p.id}>
              <td>{formatDateTime(p.t.toISOString())}</td>
              <td className="n strong">
                {p.score}/{p.max}
              </td>
              <td>
                <span className="pd-flag">
                  <StatusIcon status={BAND_STATUS[p.band] ?? 'ok'} size={14} />
                  {t(`questionnaires.bands.${p.band}`, { defaultValue: p.band })}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
