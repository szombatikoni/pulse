import {
  Alert,
  Button,
  Group,
  NumberInput,
  Paper,
  Select,
  Stack,
  TextInput,
  Title,
} from '@mantine/core'
import { type FormEvent, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { ApiError } from '../../api/client'
import {
  type MeasurementErrorDetail,
  useMeasurementTypes,
  useRecordMeasurement,
} from '../../api/measurements'
import { componentLabel, unitLabel } from '../../format'

const BACKDATE_DAYS = 2 // a szerver is ezt ellenőrzi (F7)

/** A `datetime-local` mező formátuma helyi időben: 2026-10-12T07:30. */
function toLocalInput(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

/** Mérés rögzítése (F4): típusválasztás, értékek komponensenként, a mérés ideje. */
export function MeasurementForm({ patientId }: { patientId: string }) {
  const { t, i18n } = useTranslation()
  const types = useMeasurementTypes()
  const record = useRecordMeasurement(patientId)

  const [typeCode, setTypeCode] = useState('blood_pressure')
  const [values, setValues] = useState<Record<string, number | string>>({})
  const [measuredAt, setMeasuredAt] = useState(() => toLocalInput(new Date()))
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null)

  const type = types.data?.find((x) => x.code === typeCode)
  const now = new Date()
  const earliest = new Date(now.getTime() - BACKDATE_DAYS * 86_400_000)

  const errorText = (error: unknown): string => {
    if (error instanceof ApiError && error.status === 422 && error.detail) {
      const detail = error.detail as MeasurementErrorDetail
      const component = detail.component ? componentLabel(t, typeCode, detail.component) : ''
      const key = `measurements.errors.${detail.code}`
      return t(key, { component, defaultValue: t('measurements.errors.generic') })
    }
    return t('measurements.errors.generic')
  }

  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (!type) return
    setMessage(null)
    record.mutate(
      {
        type_code: type.code,
        // A helyi idő ISO-formában, időzónával (UTC-re váltva) megy a szerverre.
        measured_at: new Date(measuredAt).toISOString(),
        values: Object.fromEntries(type.components.map((c) => [c.code, Number(values[c.code])])),
      },
      {
        onSuccess: () => {
          setMessage({ ok: true, text: t('measurements.saved') })
          setValues({})
          setMeasuredAt(toLocalInput(new Date()))
        },
        onError: (error) => setMessage({ ok: false, text: errorText(error) }),
      },
    )
  }

  return (
    <Paper withBorder p="md">
      <form onSubmit={submit}>
        <Stack gap="sm">
          <Title order={3}>{t('measurements.newTitle')}</Title>
          {message && (
            <Alert variant="light" color={message.ok ? 'green' : 'red'}>
              {message.text}
            </Alert>
          )}
          <Select
            label={t('measurements.type')}
            data={(types.data ?? []).map((x) => ({
              value: x.code,
              label: t(`measurementTypes.${x.code}`, { defaultValue: x.name }),
            }))}
            value={typeCode}
            onChange={(value) => {
              if (value) setTypeCode(value)
              setValues({})
              setMessage(null)
            }}
            allowDeselect={false}
          />
          <Group grow align="flex-start">
            {type?.components.map((c) => (
              <NumberInput
                key={c.code}
                label={`${componentLabel(t, type.code, c.code)} (${unitLabel(t, c.unit)})`}
                value={values[c.code] ?? ''}
                onChange={(value) => setValues((v) => ({ ...v, [c.code]: value }))}
                min={c.min_value}
                max={c.max_value}
                allowNegative={false}
                decimalScale={c.unit === 'mm[Hg]' || c.unit === '/min' ? 0 : 1}
                decimalSeparator={i18n.language === 'en' ? '.' : ','}
                required
              />
            ))}
          </Group>
          <TextInput
            type="datetime-local"
            label={t('measurements.measuredAt')}
            description={t('measurements.measuredAtHint')}
            value={measuredAt}
            onChange={(e) => setMeasuredAt(e.currentTarget.value)}
            min={toLocalInput(earliest)}
            max={toLocalInput(now)}
            required
          />
          <Group>
            <Button type="submit" loading={record.isPending} disabled={!type}>
              {t('measurements.save')}
            </Button>
          </Group>
        </Stack>
      </form>
    </Paper>
  )
}
