import { Button, Loader, NumberInput, Text } from '@mantine/core'
import { type FormEvent, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { useUpdateRanges } from '../../api/admin'
import { type MeasurementType, useMeasurementTypes } from '../../api/measurements'
import { StatusIcon } from '../../components/StatusLabel'
import { componentLabel, formatNumber, unitLabel } from '../../format'
import { AdminErrorText, AdminModal } from './AdminUi'

// A szerver józan határai (backend/app/services/admin.py: RANGE_FLOOR, RANGE_CEILING).
const RANGE_FLOOR = 0
const RANGE_CEILING = 1000
// A felület sorrendje (mint a beteg mérésrögzítőjén; a szerver név szerint rendez).
const TYPE_ORDER = ['blood_pressure', 'heart_rate', 'body_weight', 'blood_glucose']
const rank = (code: string) => (TYPE_ORDER.includes(code) ? TYPE_ORDER.indexOf(code) : 99)

/** Méréstípusok fül (a hallgató döntése, 2026-11-16, (a) változat; a felülettervben
 * nincs, a másik két fül mintájára): típusonként egy kártya a komponensek rögzíthető
 * tartományával. Csak a tartomány szerkeszthető; a kód, a LOINC, az egység és a név
 * nem, új típus sincs. A tartomány az elírást szűri a rögzítéskor, nem orvosi
 * határérték, és a meglévő mérések, szabályok, riasztások jelentését nem érinti. */
export function MeasurementTypesTab() {
  const { t } = useTranslation()
  const types = useMeasurementTypes()
  const [editing, setEditing] = useState<string | null>(null)

  if (types.isPending) return <Loader />
  if (types.isError) return <Text c="red">{t('errors.unavailable')}</Text>
  const sorted = [...types.data].sort((a, b) => rank(a.code) - rank(b.code))
  const current = sorted.find((x) => x.code === editing)
  const typeName = (x: MeasurementType) => t(`measurementTypes.${x.code}`, { defaultValue: x.name })

  return (
    <div className="ad-stack">
      {sorted.map((type) => (
        <section key={type.code} className="pd-card ad-card" aria-label={typeName(type)}>
          <div className="pd-card-head">
            <div className="left">
              <h2 className="pd-h-card">{typeName(type)}</h2>
              <span className="pd-meta">{t('admin.types.loinc', { code: type.loinc_code })}</span>
            </div>
            <Button
              variant="default"
              size="xs"
              onClick={() => setEditing(type.code)}
              aria-label={t('admin.types.editLabel', { type: typeName(type) })}
            >
              {t('admin.types.edit')}
            </Button>
          </div>
          <div className="pd-tbl-wrap">
            <table className="pd-tbl">
              <thead>
                <tr>
                  <th>{t('admin.types.columns.component')}</th>
                  <th>{t('admin.types.columns.unit')}</th>
                  <th className="n">{t('admin.types.columns.min')}</th>
                  <th className="n">{t('admin.types.columns.max')}</th>
                </tr>
              </thead>
              <tbody>
                {type.components.map((c) => (
                  <tr key={c.code}>
                    <td className="strong">{componentLabel(t, type.code, c.code)}</td>
                    <td>{unitLabel(t, c.unit)}</td>
                    <td className="n">{formatNumber(c.min_value)}</td>
                    <td className="n">{formatNumber(c.max_value)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ))}
      <p className="ad-note">{t('admin.types.note')}</p>
      {current && (
        <RangeDialog
          key={current.code}
          type={current}
          title={t('admin.types.dialogTitle', { type: typeName(current) })}
          onClose={() => setEditing(null)}
        />
      )}
    </div>
  )
}

type Bounds = Record<string, { min: number | string; max: number | string }>

/** A tartomány szerkesztése: komponensenként legkisebb és legnagyobb érték. */
function RangeDialog({
  type,
  title,
  onClose,
}: {
  type: MeasurementType
  title: string
  onClose: () => void
}) {
  const { t, i18n } = useTranslation()
  const update = useUpdateRanges()
  const [bounds, setBounds] = useState<Bounds>(() =>
    Object.fromEntries(
      type.components.map((c) => [c.code, { min: c.min_value, max: c.max_value }]),
    ),
  )
  const [shown, setShown] = useState(false)
  const invalid = (code: string) => {
    const { min, max } = bounds[code]
    const lo = typeof min === 'number' ? min : Number.NaN
    const hi = typeof max === 'number' ? max : Number.NaN
    return !(RANGE_FLOOR <= lo && lo < hi && hi <= RANGE_CEILING)
  }
  const anyInvalid = type.components.some((c) => invalid(c.code))
  const unchanged = type.components.every(
    (c) => bounds[c.code].min === c.min_value && bounds[c.code].max === c.max_value,
  )

  const submit = (e: FormEvent) => {
    e.preventDefault()
    setShown(true)
    if (anyInvalid) return
    update.mutate(
      {
        code: type.code,
        components: type.components.map((c) => ({
          code: c.code,
          min_value: Number(bounds[c.code].min),
          max_value: Number(bounds[c.code].max),
        })),
      },
      { onSuccess: onClose },
    )
  }

  const field = (code: string, key: 'min' | 'max', label: string, unit: string) => (
    <NumberInput
      label={label}
      classNames={{ label: 'pd-field-label' }}
      value={bounds[code][key]}
      onChange={(value) => setBounds((b) => ({ ...b, [code]: { ...b[code], [key]: value } }))}
      min={RANGE_FLOOR}
      max={RANGE_CEILING}
      clampBehavior="none"
      allowNegative={false}
      decimalScale={1}
      decimalSeparator={i18n.language === 'en' ? '.' : ','}
      hideControls
      rightSection={
        <Text size="sm" c="dimmed" pr="xs">
          {unit}
        </Text>
      }
      rightSectionWidth={68}
      rightSectionPointerEvents="none"
      error={shown && invalid(code)}
      required
    />
  )

  return (
    <AdminModal opened onClose={onClose} title={title}>
      <form className="pd-modal-form" onSubmit={submit} noValidate>
        <p className="pd-hint">{t('admin.types.dialogHint')}</p>
        {type.components.map((c) => {
          const label = componentLabel(t, type.code, c.code)
          const unit = unitLabel(t, c.unit)
          return (
            <fieldset key={c.code} className="pd-field ad-fieldset">
              {type.components.length > 1 && <legend className="pd-field-label">{label}</legend>}
              <div className="pd-two">
                {field(c.code, 'min', t('admin.types.min'), unit)}
                {field(c.code, 'max', t('admin.types.max'), unit)}
              </div>
            </fieldset>
          )
        })}
        {shown && anyInvalid && (
          <span className="pd-err" role="alert">
            <StatusIcon status="severe" size={14} />
            {t('admin.errors.range_invalid')}
          </span>
        )}
        {update.isError && <AdminErrorText error={update.error} />}
        <div className="pd-modal-foot">
          <Button variant="subtle" color="gray" onClick={onClose}>
            {t('admin.cancel')}
          </Button>
          <Button type="submit" loading={update.isPending} disabled={unchanged}>
            {t('admin.types.save')}
          </Button>
        </div>
      </form>
    </AdminModal>
  )
}
