import { Button, Loader, Stack, Text } from '@mantine/core'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { isCurrent, type Measurement, usePatientMeasurements } from '../../api/measurements'
import { formatDayLabel, formatMeasurementNumber, formatTime, unitLabel } from '../../format'
import '../doctor/patientDetail.css'

const DAYS_SHOWN = 4 // ennyi nap látszik alapból, a többi gombnyomásra
const TYPE_ORDER = ['blood_pressure', 'heart_rate', 'body_weight', 'blood_glucose']

type Day = { key: string; label: string; items: Measurement[] }

/** A mérések napokra bontva, a legújabb elöl (a lista már így érkezik). */
function groupByDay(t: ReturnType<typeof useTranslation>['t'], list: Measurement[]): Day[] {
  const days: Day[] = []
  for (const m of list) {
    const d = new Date(m.measured_at)
    const key = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`
    const last = days[days.length - 1]
    if (last?.key === key) last.items.push(m)
    else days.push({ key, label: formatDayLabel(t, m.measured_at), items: [m] })
  }
  return days
}

/** A beteg méréseinek előzményei napokra bontva, típus szerinti szűrővel (F5). A
 * grafikonos nézet: doctor/charts/MeasurementCharts (a betegoldalon doctor=false).
 *
 * A felülírt (javított) mérés a listában marad: szürkén, áthúzott értékkel, „javítva”
 * címkével, közvetlenül a javítása alatt (M3, A7). A betegoldalon (`onCorrect`) az
 * érvényes sorokon „Javítás” művelet nyitja a rögzítő-űrlapot. */
export function MeasurementHistory({
  patientId,
  highlightId,
  flaggedIds,
  onCorrect,
}: {
  patientId: string
  highlightId?: string | null
  /** Az orvosi nézetben: a riasztást kiváltó mérések jelölést kapnak. */
  flaggedIds?: Set<string>
  /** A betegoldalon: a sor „Javítás” gombja ezt hívja a méréssel. */
  onCorrect?: (measurement: Measurement) => void
}) {
  const { t } = useTranslation()
  const measurements = usePatientMeasurements(patientId)
  const [filter, setFilter] = useState('all')
  const [showAll, setShowAll] = useState(false)

  if (measurements.isPending) return <Loader size="sm" />
  if (measurements.isError) return <Text c="red">{t('errors.unavailable')}</Text>
  if (measurements.data.length === 0) return <Text c="dimmed">{t('measurements.empty')}</Text>

  const present = TYPE_ORDER.filter((code) => measurements.data.some((m) => m.type_code === code))
  const list =
    filter === 'all' ? measurements.data : measurements.data.filter((m) => m.type_code === filter)
  const days = groupByDay(t, list)
  const visible = showAll ? days : days.slice(0, DAYS_SHOWN)

  return (
    <Stack gap="sm">
      {present.length > 1 && (
        <div className="pd-seg" role="group" aria-label={t('measurements.filterLabel')}>
          {['all', ...present].map((code) => (
            <button
              key={code}
              type="button"
              aria-pressed={filter === code}
              onClick={() => setFilter(code)}
            >
              {code === 'all' ? t('measurements.filterAll') : t(`measurementTypes.${code}`)}
            </button>
          ))}
        </div>
      )}
      {visible.length === 0 && <Text c="dimmed">{t('measurements.noneOfType')}</Text>}
      <div className="pd-days">
        {visible.map((day) => (
          <div key={day.key} className="pd-day">
            <h4>{day.label}</h4>
            <ul className="pulse-history" aria-label={day.label}>
              {day.items.map((m) => {
                const superseded = !isCurrent(m)
                const className = [
                  m.id === highlightId ? 'flash' : '',
                  superseded ? 'superseded' : '',
                  onCorrect ? 'with-action' : '',
                ]
                  .filter(Boolean)
                  .join(' ')
                const value = formatMeasurementNumber(m)
                const unit = unitLabel(t, m.values[0]?.unit ?? '')
                return (
                  <li key={m.id} className={className || undefined}>
                    <span className="tm">{formatTime(new Date(m.measured_at))}</span>
                    <span className="ty">
                      {t(`measurementTypes.${m.type_code}`)}
                      {superseded && (
                        <span className="pulse-tag">{t('measurements.corrected')}</span>
                      )}
                    </span>
                    <span className="vl">
                      {flaggedIds?.has(m.id) && (
                        <i
                          className="over"
                          title={t('doctor.flagged')}
                          aria-label={t('doctor.flagged')}
                        />
                      )}
                      {superseded ? <s>{value}</s> : value} <small className="unit">{unit}</small>
                    </span>
                    {onCorrect && (
                      <span className="ac">
                        {!superseded && (
                          <button
                            type="button"
                            className="pulse-linkbtn"
                            aria-label={t('measurements.correctAria', {
                              value: `${value} ${unit}`,
                              when: formatTime(new Date(m.measured_at)),
                            })}
                            onClick={() => onCorrect(m)}
                          >
                            {t('measurements.correct')}
                          </button>
                        )}
                      </span>
                    )}
                  </li>
                )
              })}
            </ul>
          </div>
        ))}
      </div>
      {!showAll && days.length > DAYS_SHOWN && (
        <Button
          size="xs"
          variant="default"
          style={{ alignSelf: 'flex-start' }}
          onClick={() => setShowAll(true)}
        >
          {t('measurements.moreDays', { count: days.length - DAYS_SHOWN })}
        </Button>
      )}
    </Stack>
  )
}
