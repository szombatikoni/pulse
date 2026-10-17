import { Paper, SimpleGrid, Text } from '@mantine/core'
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
  const w = 160
  const h = 34
  const pad = 3
  let min = Math.min(...values)
  let max = Math.max(...values)
  if (max === min) {
    max += 1
    min -= 1
  }
  const points = values.map((v, i) => [
    pad + (i * (w - 2 * pad)) / (values.length - 1),
    pad + ((max - v) * (h - 2 * pad)) / (max - min),
  ])
  const line = points.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ')
  const [lastX, lastY] = points[points.length - 1]
  const area = `M${points[0][0]},${h - pad} L${line.split(' ').join(' L')} L${lastX},${h - pad} Z`
  return (
    <svg
      width={w}
      height={h}
      viewBox={`0 0 ${w} ${h}`}
      style={{ maxWidth: '100%' }}
      aria-hidden="true"
      className="pulse-spark"
    >
      <path d={area} className="area" />
      <polyline points={line} className="line" vectorEffect="non-scaling-stroke" />
      <circle cx={lastX} cy={lastY} r={2.6} className="dot" />
    </svg>
  )
}

/** Típusonként a legutóbbi érték és egy kis görbe (a teljes grafikon az M3-ban, F5). */
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
    <SimpleGrid cols={{ base: 1, xs: Math.min(tiles.length, 3) }} spacing="sm">
      {tiles.map(({ code, list }) => {
        const latest = list[0]
        const series = list.slice(0, SERIES_LENGTH).reverse().map(primaryValue)
        return (
          <Paper key={code} withBorder p="sm" className="pulse-tile">
            <Text size="xs" c="dimmed">
              {t(`measurementTypes.${code}`)}
            </Text>
            <Text fw={700} fz={22} lh={1.2}>
              {formatMeasurementNumber(latest)}{' '}
              <Text span size="sm" fw={500} c="dimmed">
                {unitLabel(t, latest.values[0]?.unit ?? '')}
              </Text>
            </Text>
            <Text size="xs" c="dimmed">
              {formatRelative(t, latest.measured_at)}
            </Text>
            <Sparkline values={series} />
          </Paper>
        )
      })}
    </SimpleGrid>
  )
}
