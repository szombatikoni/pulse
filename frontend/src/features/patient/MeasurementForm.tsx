import {
  Alert,
  Anchor,
  Button,
  Group,
  NumberInput,
  Paper,
  SegmentedControl,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
  Title,
  VisuallyHidden,
} from '@mantine/core'
import { type FormEvent, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { ApiError } from '../../api/client'
import {
  type MeasurementErrorDetail,
  useMeasurementTypes,
  useRecordMeasurement,
} from '../../api/measurements'
import {
  componentLabel,
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

type Message = { ok: boolean; title: string; text?: string }

// A gombsor sorrendje: a leggyakoribb mérés elöl (a szerver név szerint rendez).
const TYPE_ORDER = ['blood_pressure', 'heart_rate', 'body_weight', 'blood_glucose']
const byTypeOrder = (a: { code: string }, b: { code: string }) => {
  const rank = (code: string) => (TYPE_ORDER.includes(code) ? TYPE_ORDER.indexOf(code) : 99)
  return rank(a.code) - rank(b.code)
}

/** Mérés rögzítése (F4): típus, értékek komponensenként, a mérés ideje (alapból most). */
export function MeasurementForm({
  patientId,
  preset,
  onSaved,
}: {
  patientId: string
  preset?: MeasurementPreset | null
  onSaved?: (measurementId: string) => void
}) {
  const { t, i18n } = useTranslation()
  const types = useMeasurementTypes()
  const record = useRecordMeasurement(patientId)
  const [typeCode, setTypeCode] = useState(preset?.typeCode ?? 'blood_pressure')
  const [values, setValues] = useState<Record<string, number | string>>({})
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
    const at = timeMode === 'now' ? new Date() : new Date(measuredAt)
    record.mutate(
      {
        type_code: type.code,
        // A helyi idő ISO-formában, időzónával (UTC-re váltva) megy a szerverre.
        measured_at: at.toISOString(),
        values: Object.fromEntries(type.components.map((c) => [c.code, Number(values[c.code])])),
      },
      {
        onSuccess: (measurement) => {
          const detail = t('measurements.savedDetail', {
            value: formatMeasurementValue(t, measurement),
            when: formatRelative(t, measurement.measured_at),
          })
          setMessage({
            ok: true,
            title: t('measurements.saved'),
            text: catchUp ? `${detail} ${t('measurements.caughtUp')}` : detail,
          })
          setValues({})
          setTimeMode('now')
          setCatchUp(false)
          onSaved?.(measurement.id)
        },
        onError: showError,
      },
    )
  }

  return (
    <Paper withBorder p="md" id="meres-urlap">
      <form onSubmit={submit}>
        <Stack gap="md">
          <Title order={3}>{t('measurements.newTitle')}</Title>
          {catchUp && timeMode === 'other' && (
            <Alert
              variant="light"
              color="yellow"
              title={t('measurements.catchUpTitle', {
                type: t(`measurementTypes.${typeCode}`).toLocaleLowerCase('hu'),
                when: formatRelative(t, new Date(measuredAt).toISOString()),
              })}
            >
              <Group justify="space-between" gap="sm" wrap="wrap">
                <Text size="sm">{t('measurements.catchUpHint')}</Text>
                <Button
                  size="xs"
                  variant="default"
                  onClick={() => {
                    setCatchUp(false)
                    setTimeMode('now')
                  }}
                >
                  {t('measurements.cancel')}
                </Button>
              </Group>
            </Alert>
          )}
          <SegmentedControl
            fullWidth
            aria-label={t('measurements.type')}
            data={[...(types.data ?? [])].sort(byTypeOrder).map((x) => ({
              value: x.code,
              label: t(`measurementTypes.${x.code}`, { defaultValue: x.name }),
            }))}
            value={typeCode}
            onChange={(value) => {
              setTypeCode(value)
              setValues({})
              setMessage(null)
              setFieldError(null)
            }}
          />
          <SimpleGrid cols={{ base: type && type.components.length > 1 ? 2 : 1, xs: 2 }}>
            {type?.components.map((c, i) => {
              const unit = unitLabel(t, c.unit)
              return (
                <NumberInput
                  key={c.code}
                  // A teendők kártyájáról (pl. „Pótlás”) érkezve rögtön ide kerül a fókusz.
                  autoFocus={i === 0 && !!preset}
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
                  rightSectionWidth={64}
                  rightSectionPointerEvents="none"
                  classNames={{ input: 'pulse-number-input' }}
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
          </SimpleGrid>
          {timeMode === 'now' ? (
            <Stack gap={6}>
              <Text size="sm" fw={500}>
                {t('measurements.measuredAt')}
              </Text>
              <Group gap="md">
                <Text size="sm" className="pulse-time-chip">
                  {t('measurements.now', { time: formatTime(now) })}
                </Text>
                <Anchor
                  component="button"
                  type="button"
                  size="sm"
                  c="dimmed"
                  td="underline"
                  onClick={() => {
                    setMeasuredAt(toLocalInput(new Date()))
                    setTimeMode('other')
                  }}
                >
                  {t('measurements.otherTime')}
                </Anchor>
              </Group>
            </Stack>
          ) : (
            <Group align="flex-end" gap="md" wrap="wrap">
              <TextInput
                type="datetime-local"
                label={t('measurements.measuredAt')}
                description={t('measurements.measuredAtHint')}
                value={measuredAt}
                onChange={(e) => setMeasuredAt(e.currentTarget.value)}
                min={toLocalInput(earliest)}
                max={toLocalInput(now)}
                required
                style={{ flex: '1 1 240px' }}
              />
              <Anchor
                component="button"
                type="button"
                size="sm"
                c="dimmed"
                td="underline"
                mb={10}
                onClick={() => setTimeMode('now')}
              >
                {t('measurements.useNow')}
              </Anchor>
            </Group>
          )}
          <Group gap="md">
            <Button type="submit" loading={record.isPending} disabled={!type}>
              {t('measurements.save')}
            </Button>
          </Group>
          <div role="status">
            {message && (
              <Alert variant="light" color={message.ok ? 'green' : 'red'} title={message.title}>
                {message.text}
              </Alert>
            )}
          </div>
        </Stack>
      </form>
    </Paper>
  )
}
