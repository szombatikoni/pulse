import { Button, NumberInput, Stack, Text, TextInput, VisuallyHidden } from '@mantine/core'
import { Clock, Drop, Gauge, Heart, type Icon, Scales } from '@phosphor-icons/react'
import { type FormEvent, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { ApiError } from '../../api/client'
import {
  type Measurement,
  type MeasurementErrorDetail,
  useCorrectMeasurement,
  useMeasurementTypes,
  useRecordMeasurement,
} from '../../api/measurements'
import { StatusIcon } from '../../components/StatusLabel'
import {
  componentLabel,
  formatMeasurementNumber,
  formatMeasurementValue,
  formatRelative,
  formatTime,
  toLocalInput,
  unitLabel,
} from '../../format'

const BACKDATE_DAYS = 2 // a szerver is ezt ellenőrzi (F7)

/** Kívülről (a teendők kártyájáról) előre beállított mérés, pl. egy elmaradt alkalom
 * pótlása. A szülő `key`-jel újraindítja az űrlapot, így az a kezdőértékekből indul. */
export type MeasurementPreset = { typeCode: string; measuredAt?: string; catchUp?: boolean }

export type Message = { ok: boolean; title: string; text?: string }

// A gombsor sorrendje: a leggyakoribb mérés elöl (a szerver név szerint rendez).
const TYPE_ORDER = ['blood_pressure', 'heart_rate', 'body_weight', 'blood_glucose']
const TYPE_ICON: Record<string, Icon> = {
  blood_pressure: Gauge,
  heart_rate: Heart,
  body_weight: Scales,
  blood_glucose: Drop,
}
const byTypeOrder = (a: { code: string }, b: { code: string }) => {
  const rank = (code: string) => (TYPE_ORDER.includes(code) ? TYPE_ORDER.indexOf(code) : 99)
  return rank(a.code) - rank(b.code)
}

/** A javítás sávjának dátuma: „nov. 3-i” (magyarul a toldalékkal), angolul „3 Nov”. */
function correctionDate(iso: string, language: string): string {
  const date = new Date(iso)
  if (language === 'en') {
    return new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short' }).format(date)
  }
  const day = new Intl.DateTimeFormat('hu-HU', { month: 'short', day: 'numeric' }).format(date)
  return `${day.replace(/\.$/, '')}-i`
}

/** Mérés rögzítése (F4): típus, értékek komponensenként, a mérés ideje (alapból most).
 * A teendő kártyáján (`inTask`) a típust a teendő adja, ezért nincs típusválasztó és cím;
 * a mentés nyugtáját a szülő mutatja (`onSaved`), mert az űrlap ilyenkor bezárul.
 *
 * Javítás (`correction`, M3, A7): ugyanez az űrlap a mérés mostani értékeivel előtöltve,
 * a pótlás sávjának mintájára jelölve. A típus és a mérés ideje nem módosítható (D1),
 * ezért típusválasztó és időmező sincs; a mentés a javítás végpontjára megy. */
export function MeasurementForm({
  patientId,
  preset,
  correction,
  inTask = false,
  onSaved,
  onClose,
}: {
  patientId: string
  preset?: MeasurementPreset | null
  correction?: Measurement | null
  inTask?: boolean
  onSaved?: (measurementId: string, receipt: Message) => void
  onClose?: () => void
}) {
  const { t, i18n } = useTranslation()
  const types = useMeasurementTypes()
  const record = useRecordMeasurement(patientId)
  const correct = useCorrectMeasurement(patientId)
  const [typeCode, setTypeCode] = useState(
    correction?.type_code ?? preset?.typeCode ?? 'blood_pressure',
  )
  const [values, setValues] = useState<Record<string, number | string>>(() =>
    correction ? Object.fromEntries(correction.values.map((v) => [v.component, v.value])) : {},
  )
  // „Most" esetén a mentés pillanata lesz a mérés ideje; „Másik időpont" esetén a mező értéke.
  const [timeMode, setTimeMode] = useState<'now' | 'other'>(preset?.measuredAt ? 'other' : 'now')
  const [measuredAt, setMeasuredAt] = useState(() => preset?.measuredAt ?? toLocalInput(new Date()))
  const [message, setMessage] = useState<Message | null>(null)
  // Pótlás: a teendők kártyájáról, egy elmaradt alkalom időpontjával érkezett.
  const [catchUp, setCatchUp] = useState(!!preset?.catchUp)
  const [fieldError, setFieldError] = useState<{ component: string; text: string } | null>(null)
  const [now, setNow] = useState(() => new Date())

  // A „Most · 16:28" felirat percenként frissül.
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 30_000)
    return () => window.clearInterval(timer)
  }, [])

  const type = types.data?.find((x) => x.code === typeCode)
  const earliest = new Date(now.getTime() - BACKDATE_DAYS * 86_400_000)

  const showError = (error: unknown) => {
    if (error instanceof ApiError && error.status === 409) {
      setMessage({ ok: false, title: t('measurements.errors.already_corrected') })
      return
    }
    if (error instanceof ApiError && error.status === 422 && error.detail) {
      const detail = error.detail as MeasurementErrorDetail
      const component = detail.component ? componentLabel(t, typeCode, detail.component) : ''
      const text = t(`measurements.errors.${detail.code}`, {
        component,
        defaultValue: t('measurements.errors.generic'),
      })
      if (detail.component) setFieldError({ component: detail.component, text })
      else setMessage({ ok: false, title: text })
      return
    }
    setMessage({ ok: false, title: t('measurements.errors.generic') })
  }

  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (!type) return
    setMessage(null)
    setFieldError(null)
    const numbers = Object.fromEntries(type.components.map((c) => [c.code, Number(values[c.code])]))
    if (correction) {
      correct.mutate(
        { id: correction.id, values: numbers },
        {
          onSuccess: (measurement) => {
            const receipt = {
              ok: true,
              title: t('measurements.correctionSaved'),
              text: t('measurements.correctionSavedDetail', {
                from: formatMeasurementNumber(correction),
                to: formatMeasurementNumber(measurement),
                unit: unitLabel(t, measurement.values[0]?.unit ?? ''),
              }),
            }
            if (onSaved) onSaved(measurement.id, receipt)
            else setMessage(receipt)
          },
          onError: showError,
        },
      )
      return
    }
    const at = timeMode === 'now' ? new Date() : new Date(measuredAt)
    record.mutate(
      {
        type_code: type.code,
        // A helyi idő ISO-formában, időzónával (UTC-re váltva) megy a szerverre.
        measured_at: at.toISOString(),
        values: numbers,
      },
      {
        onSuccess: (measurement) => {
          const detail = t('measurements.savedDetail', {
            value: formatMeasurementValue(t, measurement),
            when: formatRelative(t, measurement.measured_at),
          })
          const receipt = {
            ok: true,
            title: t('measurements.saved'),
            text: catchUp ? `${detail} ${t('measurements.caughtUp')}` : detail,
          }
          setValues({})
          setTimeMode('now')
          setCatchUp(false)
          if (onSaved) onSaved(measurement.id, receipt)
          else setMessage(receipt)
        },
        onError: showError,
      },
    )
  }

  const cancelCatchUp = () => {
    setCatchUp(false)
    setTimeMode('now')
  }
  const sortedTypes = [...(types.data ?? [])].sort(byTypeOrder)

  // Javításnál a típus rögzített, mint a teendő kártyáján.
  const typeFixed = inTask || !!correction
  const form = (
    <form onSubmit={submit} className="pulse-mform">
      {correction && (
        <div className="pulse-receipt">
          <StatusIcon status="attention" size={22} />
          <div>
            <b>
              {t('measurements.correctionTitle', {
                date: correctionDate(correction.measured_at, i18n.language),
                type: t(`measurementTypes.${correction.type_code}`).toLocaleLowerCase('hu'),
              })}
            </b>
            <p className="pulse-hint">
              {t('measurements.correctionHint', {
                time: formatTime(new Date(correction.measured_at)),
              })}
            </p>
          </div>
        </div>
      )}
      {!typeFixed && (
        <div>
          <h2 className="pulse-h-sec" id="meres-cim">
            {t('measurements.freeTitle')}
          </h2>
          <span className="pulse-meta">{t('measurements.freeHint')}</span>
        </div>
      )}
      {catchUp && timeMode === 'other' && (
        <div className="pulse-receipt">
          <StatusIcon status="attention" size={22} />
          <div>
            <b>
              {t('measurements.catchUpTitle', {
                type: t(`measurementTypes.${typeCode}`).toLocaleLowerCase('hu'),
                when: formatRelative(t, new Date(measuredAt).toISOString()),
              })}
            </b>
            <p className="pulse-hint">{t('measurements.catchUpHint')}</p>
          </div>
        </div>
      )}
      {/* Méréstípus: rádiógombok címkével; a címke maga a nagy, ikonos gomb. */}
      {!typeFixed && (
        <div className="pulse-typeseg" role="radiogroup" aria-label={t('measurements.type')}>
          {sortedTypes.map((x) => {
            const Glyph = TYPE_ICON[x.code] ?? Gauge
            return (
              <label key={x.code}>
                <input
                  type="radio"
                  name="meres-tipus"
                  value={x.code}
                  checked={typeCode === x.code}
                  onChange={() => {
                    setTypeCode(x.code)
                    setValues({})
                    setMessage(null)
                    setFieldError(null)
                  }}
                />
                <Glyph size={20} aria-hidden="true" />
                {t(`measurementTypes.${x.code}`, { defaultValue: x.name })}
              </label>
            )
          })}
        </div>
      )}
      <div className={type && type.components.length > 1 ? 'pulse-two' : 'pulse-one'}>
        {type?.components.map((c, i) => {
          const unit = unitLabel(t, c.unit)
          return (
            <NumberInput
              key={c.code}
              // A teendők kártyájáról (pl. „Pótlás”) érkezve rögtön ide kerül a fókusz.
              autoFocus={i === 0 && (!!preset || !!correction)}
              // Az egység a mező jobb szélén látszik; a felolvasó a címkében is hallja.
              label={
                <>
                  {componentLabel(t, type.code, c.code)}
                  <VisuallyHidden> ({unit})</VisuallyHidden>
                </>
              }
              rightSection={
                <Text size="sm" c="dimmed" pr="xs">
                  {unit}
                </Text>
              }
              rightSectionWidth={68}
              rightSectionPointerEvents="none"
              classNames={{ input: 'pulse-input-big', label: 'pulse-field-label' }}
              hideControls
              inputMode={c.unit === 'mm[Hg]' || c.unit === '/min' ? 'numeric' : 'decimal'}
              value={values[c.code] ?? ''}
              onChange={(value) => {
                setValues((v) => ({ ...v, [c.code]: value }))
                if (fieldError?.component === c.code) setFieldError(null)
              }}
              min={c.min_value}
              max={c.max_value}
              // Ne írja át csendben a tartományon kívüli értéket (pl. 400 → 300):
              // a szerver utasítsa el, és a beteg lássa, miért.
              clampBehavior="none"
              allowNegative={false}
              decimalScale={c.unit === 'mm[Hg]' || c.unit === '/min' ? 0 : 1}
              decimalSeparator={i18n.language === 'en' ? '.' : ','}
              error={fieldError?.component === c.code ? fieldError.text : undefined}
              required
            />
          )
        })}
      </div>
      {/* A mérés ideje balra, a Mentés vele egy sorban a jobb szélen (a fő gomb
            mindig a terület jobb szélén áll). */}
      <div className="pulse-form-foot">
        <div className="pulse-form-time">
          {correction ? null : timeMode === 'now' ? (
            <Stack gap={7}>
              <span className="pulse-field-label">{t('measurements.measuredAt')}</span>
              <div className="pulse-row-wrap">
                <span className="pulse-timechip">
                  <Clock size={16} aria-hidden="true" />
                  {t('measurements.now', { time: formatTime(now) })}
                </span>
                <button
                  type="button"
                  className="pulse-linkbtn"
                  onClick={() => {
                    setMeasuredAt(toLocalInput(new Date()))
                    setTimeMode('other')
                  }}
                >
                  {t('measurements.otherTime')}
                </button>
              </div>
            </Stack>
          ) : (
            <TextInput
              type="datetime-local"
              label={t('measurements.measuredAt')}
              classNames={{ label: 'pulse-field-label' }}
              value={measuredAt}
              onChange={(e) => setMeasuredAt(e.currentTarget.value)}
              min={toLocalInput(earliest)}
              max={toLocalInput(now)}
              required
            />
          )}
        </div>
        <div className="pulse-form-actions">
          {onClose ? (
            <Button variant="subtle" color="gray" size="md" onClick={onClose}>
              {t('measurements.cancel')}
            </Button>
          ) : (
            catchUp &&
            timeMode === 'other' && (
              <Button variant="subtle" color="gray" size="md" onClick={cancelCatchUp}>
                {t('measurements.cancel')}
              </Button>
            )
          )}
          <Button
            type="submit"
            size="md"
            loading={record.isPending || correct.isPending}
            disabled={!type}
          >
            {correction ? t('measurements.saveCorrection') : t('measurements.save')}
          </Button>
        </div>
      </div>
      {timeMode === 'other' && !correction && (
        <div className="pulse-row-wrap">
          <span className="pulse-hint">{t('measurements.measuredAtHint')}</span>
          <button type="button" className="pulse-linkbtn" onClick={() => setTimeMode('now')}>
            {t('measurements.useNow')}
          </button>
        </div>
      )}
      <div role="status">
        {message && (
          <div className="pulse-receipt">
            <StatusIcon status={message.ok ? 'ok' : 'severe'} size={22} />
            <div>
              <b>{message.title}</b>
              {message.text && <p className="pulse-hint">{message.text}</p>}
            </div>
          </div>
        )}
      </div>
    </form>
  )
  if (inTask) return form
  if (correction)
    return (
      <section className="pulse-pcard" id="javitas-urlap" aria-label={t('measurements.correct')}>
        {form}
      </section>
    )
  return (
    <section className="pulse-pcard" id="meres-urlap" aria-labelledby="meres-cim">
      {form}
    </section>
  )
}
