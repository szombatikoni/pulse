import { useTranslation } from 'react-i18next'

import { type Measurement, usePatientMeasurements } from '../../api/measurements'
import { formatMeasurementNumber, formatRelative, unitLabel } from '../../format'

const TYPE_ORDER = ['blood_pressure', 'heart_rate', 'body_weight', 'blood_glucose']
const SERIES_LENGTH = 10 // ennyi utolsó mérés kerül a kis görbére

/** A görbe értéke: vérnyomásnál a szisztolés, egyébként az egyetlen érték. */
function primaryValue(m: Measurement): number {
  const systolic = m.values.find((v) => v.component === 'systolic')
  return (systolic ?? m.values[0]).value
}

/** Kis görbe az utolsó mérésekről; küszöbvonal szándékosan nincs rajta
 * (a beteg a saját adatát látja, nem értékelést). */
function Sparkline({ values }: { values: number[] }) {
  if (values.length < 2) return null
  const w = 120
  const h = 30
  const pad = 3
  let min = Math.min(...values)
  let max = Math.max(...values)
  if (max - min < 1) {
    max += 1
    min -= 1
  }
  const x = (i: number) => pad + (i * (w - 2 * pad)) / (values.length - 1)
  const y = (v: number) => pad + ((max - v) * (h - 2 * pad)) / (max - min)
  const line = values.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ')
  const last = values.length - 1
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-hidden="true" className="pulse-lspark">
      <polyline points={line} className="line" />
      <circle cx={x(last)} cy={y(values[last])} r={3.2} className="end" />
    </svg>
  )
}

/** Típusonként a legutóbbi érték egy sorban, jobbra a kis görbe (felületterv, 2026-10-30). */
export function LatestValues({ patientId }: { patientId: string }) {
  const { t } = useTranslation()
  const measurements = usePatientMeasurements(patientId)
  if (!measurements.data || measurements.data.length === 0) return null

  // A lista a legújabb méréssel kezdődik.
  const tiles = TYPE_ORDER.map((code) => {
    const list = measurements.data.filter((m) => m.type_code === code)
    return list.length ? { code, list } : null
  }).filter((x) => x !== null)

  return (
    <div className="pulse-latest">
      {tiles.map(({ code, list }) => {
        const latest = list[0]
        const series = list.slice(0, SERIES_LENGTH).reverse().map(primaryValue)
        return (
          <div key={code} className="pulse-lt">
            <span className="k">{t(`measurementTypes.${code}`)}</span>
            <span className="v">
              {formatMeasurementNumber(latest)}
              <small>{unitLabel(t, latest.values[0]?.unit ?? '')}</small>
            </span>
            <span className="w">{formatRelative(t, latest.measured_at)}</span>
            <Sparkline values={series} />
          </div>
        )
      })}
    </div>
  )
}
