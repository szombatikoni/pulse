import { Button, Checkbox, Loader, NativeSelect, NumberInput, Text } from '@mantine/core'
import { Plus } from '@phosphor-icons/react'
import type { TFunction } from 'i18next'
import { type ReactNode, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { ApiError } from '../../api/client'
import type { MeasurementType } from '../../api/measurements'
import type { RuleParams, RuleType, Severity } from '../../api/patients'
import { useQuestionnaireTemplates } from '../../api/plans'
import {
  type Rule,
  type RuleErrorDetail,
  type RuleVersionDetail,
  usePatientRules,
  useRuleMutations,
} from '../../api/rules'
import { StatusIcon } from '../../components/StatusLabel'
import { componentLabel, formatDate, formatNumber, todayInput, unitLabel } from '../../format'
import i18n from '../../i18n'
import './patientDetail.css'
import {
  type Mark,
  markChanged,
  ruleCondition,
  ruleSentence,
  ruleTarget,
  type RuleTextContext,
  splitMarked,
} from './ruleText'

/** A négy szabálytípus a felületterv sorrendjében (docs/design/felulet_2026-10-30,
 * „szabályok (M3 terv)"). */
const RULE_TYPES: RuleType[] = ['threshold', 'window', 'questionnaire', 'missing_data']
const SEVERITIES: Severity[] = ['moderate', 'severe']
// A kérdőívek kiértékelési sávjai. A /questionnaires végpont a sávokat nem adja
// vissza; a szerver az ismeretlen sávot elutasítja (unknown_band).
const BANDS = ['normal', 'warning', 'critical']

type Selection =
  { mode: 'edit'; ruleId: string } | { mode: 'pick' } | { mode: 'new'; ruleType: RuleType }
type Message = { ok: boolean; text: string }

/** Mióta érvényes a verzió: a helyi napja röviden („nov. 9."). */
const sinceDate = (iso: string) => formatDate(todayInput(new Date(iso)))

/** A súlyosság pöttye: közepesnél a Figyelem, súlyosnál a Súlyos színe. */
function SevDot({ severity }: { severity: Severity }) {
  return <span className={`pd-sev-dot ${severity}`} aria-hidden="true" />
}

/** A jelölt szöveg (markChanged) kiemelt darabjai `chg` osztállyal. */
function Marked({ text }: { text: string }) {
  return (
    <>
      {splitMarked(text).map(([chunk, hot], i) =>
        hot ? (
          <span key={i} className="chg">
            {chunk}
          </span>
        ) : (
          chunk
        ),
      )}
    </>
  )
}

/* ---------- a szerkesztő állapota ---------- */

type Num = number | string
type Draft = {
  measurementType: string
  /** komponensenként a felső és az alsó határ; az üres mező = nincs határ */
  limits: Record<string, { min: Num; max: Num }>
  count: Num
  windowDays: Num
  questionnaire: string
  condition: 'bands' | 'trend'
  bands: string[]
  trendCount: Num
  /** elmaradt adat célpontja: „measurement:kód" vagy „questionnaire:kód" */
  target: string
  consecutive: Num
  severity: Severity
}

/** A szerkesztő kezdőállapota: módosításnál az aktuális verzióból, új szabálynál
 * az alapértékekkel (az elmaradt adatnál a backend leírása szerint 2 elmulasztás). */
function draftFrom(version: RuleVersionDetail | null, firstQuestionnaire: string): Draft {
  const p = version?.params ?? {}
  const limits: Draft['limits'] = {}
  for (const [code, limit] of Object.entries(p.limits ?? {})) {
    limits[code] = { min: limit.min ?? '', max: limit.max ?? '' }
  }
  return {
    measurementType: p.measurement_type ?? 'blood_pressure',
    limits,
    count: p.count ?? 3,
    windowDays: p.window_days ?? 7,
    questionnaire: p.questionnaire ?? firstQuestionnaire,
    condition: p.trend_count !== undefined ? 'trend' : 'bands',
    bands: p.bands ?? [],
    trendCount: p.trend_count ?? 3,
    target: p.questionnaire
      ? `questionnaire:${p.questionnaire}`
      : `measurement:${p.measurement_type ?? 'blood_pressure'}`,
    consecutive: p.consecutive_missed ?? 2,
    severity: version?.severity ?? 'moderate',
  }
}

/** A mező értéke számként; üres mezőnél undefined, nem számnál NaN. */
function toNumber(value: Num): number | undefined {
  if (value === '' || value === undefined) return undefined
  return typeof value === 'number' ? value : Number(String(value).replace(',', '.'))
}

const isInt = (value: number | undefined, min: number): value is number =>
  value !== undefined && Number.isInteger(value) && value >= min

type Built = { params: RuleParams; error?: undefined } | { params?: undefined; error: string }

/** A szerkesztő állapotából a szerver paraméterei, vagy az első hiba szövege. A
 * feltételek a szerver pydantic-modelljeit követik (backend/app/services/rules.py);
 * a határoknál a méréstípus rögzíthető tartományát is (amit a beteg rögzíthet). */
function buildParams(t: TFunction, ruleType: RuleType, d: Draft, types: MeasurementType[]): Built {
  if (ruleType === 'threshold' || ruleType === 'window') {
    const type = types.find((x) => x.code === d.measurementType)
    if (!type) return { error: t('rules.errors.measurementType') }
    const limits: NonNullable<RuleParams['limits']> = {}
    for (const c of type.components) {
      const label = componentLabel(t, type.code, c.code)
      const raw = d.limits[c.code] ?? { min: '', max: '' }
      const min = toNumber(raw.min)
      const max = toNumber(raw.max)
      for (const v of [min, max]) {
        if (v !== undefined && !(Number.isFinite(v) && v >= c.min_value && v <= c.max_value)) {
          return {
            error: t('rules.errors.range', {
              label,
              min: formatNumber(c.min_value),
              max: formatNumber(c.max_value),
              unit: unitLabel(t, c.unit),
            }),
          }
        }
      }
      if (min !== undefined && max !== undefined && min >= max) {
        return { error: t('rules.errors.minMax', { label }) }
      }
      if (min !== undefined || max !== undefined) {
        limits[c.code] = {
          ...(min !== undefined ? { min } : {}),
          ...(max !== undefined ? { max } : {}),
        }
      }
    }
    if (Object.keys(limits).length === 0) return { error: t('rules.errors.noLimit') }
    if (ruleType === 'threshold') return { params: { measurement_type: type.code, limits } }
    const count = toNumber(d.count)
    const days = toNumber(d.windowDays)
    if (!isInt(count, 2)) return { error: t('rules.errors.count') }
    if (!isInt(days, 1)) return { error: t('rules.errors.days') }
    return { params: { measurement_type: type.code, limits, count, window_days: days } }
  }
  if (ruleType === 'questionnaire') {
    if (!d.questionnaire) return { error: t('rules.errors.questionnaire') }
    if (d.condition === 'bands') {
      if (d.bands.length === 0) return { error: t('rules.errors.bands') }
      const bands = BANDS.filter((b) => d.bands.includes(b))
      return { params: { questionnaire: d.questionnaire, bands } }
    }
    const trend = toNumber(d.trendCount)
    if (!isInt(trend, 2)) return { error: t('rules.errors.trend') }
    return { params: { questionnaire: d.questionnaire, trend_count: trend } }
  }
  const consecutive = toNumber(d.consecutive)
  if (!isInt(consecutive, 1)) return { error: t('rules.errors.consecutive') }
  const [kind, code] = d.target.split(':')
  return {
    params:
      kind === 'questionnaire'
        ? { questionnaire: code, consecutive_missed: consecutive }
        : { measurement_type: code, consecutive_missed: consecutive },
  }
}

/** A paraméterek lapított alakja az összehasonlításhoz: útvonal → érték. */
function flatten(params: RuleParams, severity: Severity): Record<string, string> {
  const flat: Record<string, string> = { severity }
  for (const [key, value] of Object.entries(params)) {
    if (key === 'limits') {
      for (const [code, limit] of Object.entries(value as NonNullable<RuleParams['limits']>)) {
        if (limit.min !== undefined) flat[`limits.${code}.min`] = String(limit.min)
        if (limit.max !== undefined) flat[`limits.${code}.max`] = String(limit.max)
      }
    } else if (Array.isArray(value)) {
      flat[key] = [...value].sort().join(',')
    } else if (value !== undefined) {
      flat[key] = String(value)
    }
  }
  return flat
}

/** A változott mezők az aktuális verzióhoz képest (a célpont „target" néven). */
function changedFields(
  before: RuleVersionDetail,
  params: RuleParams,
  severity: Severity,
): Set<string> {
  const a = flatten(before.params, before.severity)
  const b = flatten(params, severity)
  const changed = new Set<string>()
  for (const key of new Set([...Object.keys(a), ...Object.keys(b)])) {
    if (a[key] !== b[key]) changed.add(key)
  }
  if (changed.has('measurement_type') || changed.has('questionnaire')) changed.add('target')
  return changed
}

function serverErrorText(t: TFunction, error: unknown): string {
  const detail = error instanceof ApiError ? (error.detail as RuleErrorDetail | null) : null
  if (detail && typeof detail === 'object' && 'code' in detail) {
    return t(`rules.errors.server.${detail.code}`, {
      defaultValue: t('rules.errors.server.generic'),
    })
  }
  return t('rules.errors.server.generic')
}

/* ---------- mezők ---------- */

/** Szám mező a felületterv szerint: az egység a mező jobb szélén, léptetők nélkül,
 * a tartományon kívüli értéket nem írja át csendben (mint a mérésrögzítőben). */
function NumField({
  label,
  unit,
  value,
  onChange,
  decimals = 0,
  placeholder,
}: {
  label: string
  unit?: string
  value: Num
  onChange: (value: Num) => void
  decimals?: number
  placeholder?: string
}) {
  return (
    <NumberInput
      label={label}
      classNames={{ label: 'pd-field-label' }}
      value={value}
      onChange={onChange}
      rightSection={
        unit ? (
          <Text size="sm" c="dimmed" pr="xs">
            {unit}
          </Text>
        ) : undefined
      }
      rightSectionWidth={unit ? 64 : undefined}
      rightSectionPointerEvents="none"
      hideControls
      clampBehavior="none"
      allowNegative={false}
      decimalScale={decimals}
      decimalSeparator={i18n.language === 'en' ? '.' : ','}
      inputMode={decimals ? 'decimal' : 'numeric'}
      placeholder={placeholder}
      autoComplete="off"
    />
  )
}

/** Szegmensvezérlő (pd-seg); az `accent` változatban a kiválasztott teli fehér. */
function Seg<T extends string>({
  label,
  options,
  value,
  onChange,
  accent = false,
}: {
  label: string
  options: [T, string][]
  value: T
  onChange: (value: T) => void
  accent?: boolean
}) {
  return (
    <div className={accent ? 'pd-seg accent' : 'pd-seg'} role="group" aria-label={label}>
      {options.map(([id, text]) => (
        <button key={id} type="button" aria-pressed={value === id} onClick={() => onChange(id)}>
          {text}
        </button>
      ))}
    </div>
  )
}

/** A küszöb- és az időablakos szabály határai: komponensenként felső és alsó határ. */
function LimitFields({
  type,
  draft,
  setDraft,
}: {
  type: MeasurementType | undefined
  draft: Draft
  setDraft: (update: (d: Draft) => Draft) => void
}) {
  const { t } = useTranslation()
  if (!type) return null
  const none = t('rules.editor.noLimit')
  return (
    <>
      {type.components.map((c) => {
        const label = componentLabel(t, type.code, c.code)
        const unit = unitLabel(t, c.unit)
        const decimals = c.unit === 'mm[Hg]' || c.unit === '/min' ? 0 : 1
        const value = draft.limits[c.code] ?? { min: '', max: '' }
        const set = (bound: 'min' | 'max') => (v: Num) =>
          setDraft((d) => ({
            ...d,
            limits: { ...d.limits, [c.code]: { ...value, [bound]: v } },
          }))
        return (
          <div className="pd-two" key={c.code}>
            <NumField
              label={t('rules.editor.upper', { label })}
              unit={unit}
              value={value.max}
              onChange={set('max')}
              decimals={decimals}
              placeholder={none}
            />
            <NumField
              label={t('rules.editor.lower', { label })}
              unit={unit}
              value={value.min}
              onChange={set('min')}
              decimals={decimals}
              placeholder={none}
            />
          </div>
        )
      })}
      <p className="pd-meta">{t('rules.editor.limitsHint')}</p>
    </>
  )
}

/* ---------- szerkesztő ---------- */

/** A szabály szerkesztőkártyája a felületterv szerint: fejléc (típus · célpont, az
 * érvényes verzió), a típus mezői, súlyosság, élő előnézet a változott értékek
 * kiemelésével, tájékoztató, lábléc (Visszaállítás, Mentés N+1. verzióként), és a
 * verziólista. Új szabálynál ugyanez verziólista nélkül. */
function RuleEditor({
  patientId,
  ruleType,
  rule,
  ctx,
  onSaved,
  onCancel,
}: {
  patientId: string
  ruleType: RuleType
  rule: Rule | null
  ctx: RuleTextContext
  onSaved: (rule: Rule, message: Message) => void
  onCancel: () => void
}) {
  const { t } = useTranslation()
  const { create, addVersion } = useRuleMutations(patientId)
  const templates = useQuestionnaireTemplates()
  const firstQuestionnaire = templates.data?.[0]?.code ?? ''
  const current = rule?.current ?? null
  const [draft, setDraftState] = useState<Draft>(() => draftFrom(current, firstQuestionnaire))
  const [error, setError] = useState<string | null>(null)
  const setDraft = (update: (d: Draft) => Draft) => {
    setDraftState(update)
    setError(null)
  }

  // Ha a kérdőívlista a szerkesztő nyitása után érkezik meg, az új szabály ezt kapja.
  const questionnaire = draft.questionnaire || firstQuestionnaire
  const effective = { ...draft, questionnaire }
  const built = buildParams(t, ruleType, effective, ctx.types)
  const changed =
    built.params && current ? changedFields(current, built.params, draft.severity) : null
  const dirty = current ? !!changed && changed.size > 0 : true
  const canSave = !!built.params && dirty
  const nextNo = (current?.version_no ?? 0) + 1
  const pending = create.isPending || addVersion.isPending
  const type = ctx.types.find((x) => x.code === draft.measurementType)
  const titleId = rule ? `pd-h-rule-${rule.id}` : 'pd-h-rule-new'

  const save = () => {
    if (!built.params) return
    const params = built.params
    const saving = rule
      ? addVersion.mutateAsync({ ruleId: rule.id, params, severity: draft.severity })
      : create.mutateAsync({ rule_type: ruleType, params, severity: draft.severity })
    saving
      .then((saved) =>
        onSaved(saved, {
          ok: true,
          text: t(rule ? 'rules.savedVersion' : 'rules.created', {
            n: saved.current.version_no,
          }),
        }),
      )
      .catch((e: unknown) => setError(serverErrorText(t, e)))
  }

  let preview: ReactNode
  if (built.params) {
    const mark: Mark = markChanged(changed ?? new Set())
    const text = t('rules.editor.preview', {
      target: mark('target', ruleTarget(t, built.params, ctx)),
      condition: ruleCondition(t, ruleType, built.params, ctx, mark),
      severity: mark('severity', t(`severity.${draft.severity}`)),
    })
    preview = (
      <span>
        <Marked text={text} />
      </span>
    )
  } else {
    preview = (
      <span className="pd-err">
        <StatusIcon status="severe" size={14} />
        {built.error}
      </span>
    )
  }

  const measurementOptions = ctx.types.map((x) => ({
    value: x.code,
    label: t(`measurementTypes.${x.code}`, { defaultValue: x.name }),
  }))
  const questionnaireOptions = (templates.data ?? []).map((x) => ({ value: x.code, label: x.name }))
  const eyebrowTarget = built.params
    ? ruleTarget(t, built.params, ctx)
    : current
      ? ruleTarget(t, current.params, ctx)
      : ''

  return (
    <aside className="pd-card pd-editor" aria-labelledby={titleId}>
      <div className="pd-card-head flush">
        <div className="left">
          <span className="pd-eyebrow">
            {t(`doctor.ruleTypes.${ruleType}`)}
            {eyebrowTarget ? ` · ${eyebrowTarget}` : ''}
          </span>
          <h2 className="pd-h-card" id={titleId}>
            {t(rule ? 'rules.editor.titleEdit' : 'rules.editor.titleNew')}
          </h2>
        </div>
        {current && (
          <span className="pd-chip-soft">
            {t('rules.editor.current', { n: current.version_no })}
          </span>
        )}
      </div>

      {(ruleType === 'threshold' || ruleType === 'window') && (
        <>
          <NativeSelect
            label={t('rules.editor.measurementType')}
            classNames={{ label: 'pd-field-label' }}
            data={measurementOptions}
            value={draft.measurementType}
            onChange={(e) => {
              const value = e.currentTarget.value
              // Más méréstípusnak más komponensei vannak: a határok újrakezdődnek.
              setDraft((d) => ({ ...d, measurementType: value, limits: {} }))
            }}
          />
          <LimitFields type={type} draft={draft} setDraft={setDraft} />
        </>
      )}
      {ruleType === 'window' && (
        <div className="pd-two">
          <NumField
            label={t('rules.editor.count')}
            unit={t('rules.editor.countUnit')}
            value={draft.count}
            onChange={(v) => setDraft((d) => ({ ...d, count: v }))}
          />
          <NumField
            label={t('rules.editor.windowDays')}
            unit={t('rules.editor.daysUnit')}
            value={draft.windowDays}
            onChange={(v) => setDraft((d) => ({ ...d, windowDays: v }))}
          />
        </div>
      )}
      {ruleType === 'questionnaire' && (
        <>
          <NativeSelect
            label={t('rules.editor.questionnaire')}
            classNames={{ label: 'pd-field-label' }}
            data={questionnaireOptions}
            value={questionnaire}
            onChange={(e) => {
              const value = e.currentTarget.value
              setDraft((d) => ({ ...d, questionnaire: value }))
            }}
          />
          <div className="pd-field">
            <span className="pd-field-label">{t('rules.editor.condition')}</span>
            <Seg
              label={t('rules.editor.condition')}
              options={[
                ['bands', t('rules.editor.conditionBands')],
                ['trend', t('rules.editor.conditionTrend')],
              ]}
              value={draft.condition}
              onChange={(condition) => setDraft((d) => ({ ...d, condition }))}
            />
          </div>
          {draft.condition === 'bands' ? (
            <Checkbox.Group
              label={t('rules.editor.bands')}
              classNames={{ label: 'pd-field-label' }}
              value={draft.bands}
              onChange={(bands) => setDraft((d) => ({ ...d, bands }))}
            >
              <div className="pd-checks">
                {BANDS.map((b) => (
                  <Checkbox key={b} value={b} label={t(`questionnaires.bands.${b}`)} />
                ))}
              </div>
            </Checkbox.Group>
          ) : (
            <div className="pd-two">
              <NumField
                label={t('rules.editor.trendCount')}
                unit={t('rules.editor.submissionsUnit')}
                value={draft.trendCount}
                onChange={(v) => setDraft((d) => ({ ...d, trendCount: v }))}
              />
            </div>
          )}
        </>
      )}
      {ruleType === 'missing_data' && (
        <>
          <NativeSelect
            label={t('rules.editor.target')}
            classNames={{ label: 'pd-field-label' }}
            // Mint a követési terv „Mit ír elő?" mezője: mérés és kérdőív csoportban.
            data={[
              {
                group: t('doctor.plan.form.measurementGroup'),
                items: measurementOptions.map((x) => ({ ...x, value: `measurement:${x.value}` })),
              },
              {
                group: t('doctor.plan.form.questionnaireGroup'),
                items: questionnaireOptions.map((x) => ({
                  ...x,
                  value: `questionnaire:${x.value}`,
                })),
              },
            ]}
            value={draft.target}
            onChange={(e) => {
              const value = e.currentTarget.value
              setDraft((d) => ({ ...d, target: value }))
            }}
          />
          <div className="pd-two">
            <NumField
              label={t('rules.editor.consecutive')}
              unit={t('rules.editor.occasionsUnit')}
              value={draft.consecutive}
              onChange={(v) => setDraft((d) => ({ ...d, consecutive: v }))}
            />
          </div>
        </>
      )}

      <div className="pd-field">
        <span className="pd-field-label">{t('rules.editor.severity')}</span>
        <Seg
          accent
          label={t('rules.editor.severity')}
          options={SEVERITIES.map((s) => [s, t(`rules.editor.sev.${s}`)] as [Severity, string])}
          value={draft.severity}
          onChange={(severity) => setDraft((d) => ({ ...d, severity }))}
        />
      </div>

      <div className="pd-preview" aria-live="polite">
        <span className="k">{t('rules.editor.previewLabel')}</span>
        {preview}
      </div>
      <p className="pd-meta">{t(rule ? 'rules.editor.info' : 'rules.editor.infoNew')}</p>

      {error && (
        <div className="pd-receipt" role="alert">
          <StatusIcon status="severe" size={20} />
          <span>{error}</span>
        </div>
      )}
      <div className="pd-plan-foot">
        {rule ? (
          <Button
            variant="subtle"
            color="gray"
            onClick={() => {
              setDraftState(draftFrom(current, firstQuestionnaire))
              setError(null)
            }}
          >
            {t('rules.editor.reset')}
          </Button>
        ) : (
          <Button variant="subtle" color="gray" onClick={onCancel}>
            {t('rules.editor.cancel')}
          </Button>
        )}
        <Button disabled={!canSave} loading={pending} onClick={save}>
          {t('rules.editor.save', { n: nextNo })}
        </Button>
      </div>

      {rule && (
        <div className="pd-field">
          <h3 className="pd-eyebrow">{t('rules.editor.versions')}</h3>
          <ol className="pd-versions">
            {[...rule.versions].reverse().map((v) => {
              const sameTarget =
                ruleTarget(t, v.params, ctx) === ruleTarget(t, rule.current.params, ctx)
              const cond = sameTarget
                ? ruleCondition(t, v.rule_type, v.params, ctx)
                : ruleSentence(t, v.rule_type, v.params, ctx)
              return (
                <li key={v.id}>
                  <span className="vn">{t('rules.editor.versionNo', { n: v.version_no })}</span>
                  <span className="pd-muted">
                    {cond}, {t(`severity.${v.severity}`)}
                  </span>
                  <span className="pd-muted">
                    {sinceDate(v.created_at)}
                    {v.id === rule.current.id ? ` · ${t('rules.editor.valid')}` : ''}
                  </span>
                </li>
              )
            })}
          </ol>
        </div>
      )}
    </aside>
  )
}

/** Új szabály: előbb a típus (a négy típus a leírásával), utána a típus űrlapja. */
function TypePicker({
  onPick,
  onCancel,
}: {
  onPick: (ruleType: RuleType) => void
  onCancel: () => void
}) {
  const { t } = useTranslation()
  return (
    <aside className="pd-card pd-editor" aria-labelledby="pd-h-rule-pick">
      <div className="pd-card-head flush">
        <div className="left">
          <span className="pd-eyebrow">{t('rules.editor.titleNew')}</span>
          <h2 className="pd-h-card" id="pd-h-rule-pick">
            {t('rules.editor.pickTitle')}
          </h2>
        </div>
      </div>
      <div className="pd-rules">
        {RULE_TYPES.map((type) => (
          <button
            key={type}
            type="button"
            className="pd-rule pd-rule-pick"
            onClick={() => onPick(type)}
          >
            <span>
              <span className="cond">{t(`doctor.ruleTypes.${type}`)}</span>
              <span className="info">{t(`rules.typeDesc.${type}`)}</span>
            </span>
          </button>
        ))}
      </div>
      <p className="pd-meta">{t('rules.editor.pickHint')}</p>
      <div className="pd-plan-foot">
        <Button variant="subtle" color="gray" onClick={onCancel}>
          {t('rules.editor.cancel')}
        </Button>
      </div>
    </aside>
  )
}

/* ---------- a fül ---------- */

/** A beteg-adatlap Szabályok füle (F11, F12; M3, A4): bal oldalt a szabályok a
 * négy típus szerint csoportosítva, jobb oldalt a kiválasztott szabály
 * szerkesztője, illetve új szabálynál a típusválasztó. */
export function RulesTab({
  patientId,
  patientName,
  ctx,
}: {
  patientId: string
  patientName: string
  ctx: RuleTextContext
}) {
  const { t } = useTranslation()
  const rules = usePatientRules(patientId)
  const [selection, setSelection] = useState<Selection | null>(null)
  const [message, setMessage] = useState<Message | null>(null)

  // A szabályok a típusok sorrendjében (azon belül a szerver sorrendjében, létrehozás
  // szerint), ahogy a lista csoportjai is mutatják.
  const list = RULE_TYPES.flatMap((type) => (rules.data ?? []).filter((r) => r.rule_type === type))
  // Alapból a lista első szabálya van kiválasztva (mint a felülettervben).
  const selected: Selection | null =
    selection ?? (list.length ? { mode: 'edit', ruleId: list[0].id } : null)
  const selectedRule =
    selected?.mode === 'edit' ? (list.find((r) => r.id === selected.ruleId) ?? null) : null
  const select = (next: Selection | null) => {
    setSelection(next)
    setMessage(null)
  }

  let editor: ReactNode
  if (selected?.mode === 'pick') {
    editor = (
      <TypePicker
        onPick={(ruleType) => select({ mode: 'new', ruleType })}
        onCancel={() => select(null)}
      />
    )
  } else if (selected?.mode === 'new' || selectedRule) {
    const ruleType = selectedRule
      ? selectedRule.rule_type
      : (selected as { ruleType: RuleType }).ruleType
    editor = (
      <RuleEditor
        // Mentés után az új verzióval (a friss listából) újraindul az állapot.
        key={
          selectedRule ? `${selectedRule.id}-${selectedRule.current.version_no}` : `new-${ruleType}`
        }
        patientId={patientId}
        ruleType={ruleType}
        rule={selectedRule}
        ctx={ctx}
        onSaved={(saved, m) => {
          setSelection({ mode: 'edit', ruleId: saved.id })
          setMessage(m)
        }}
        onCancel={() => select(null)}
      />
    )
  } else if (rules.isSuccess) {
    editor = (
      <aside className="pd-card pd-editor">
        <p className="pd-muted">{t('rules.editor.empty')}</p>
      </aside>
    )
  }

  return (
    <div className="pd-grid-2">
      <section className="pd-sec" aria-labelledby="pd-h-rules">
        <div className="pd-sec-head">
          <div className="left">
            <h2 className="pd-h-sec" id="pd-h-rules">
              {t('rules.title', { name: patientName })}
            </h2>
          </div>
          <Button leftSection={<Plus size={16} />} onClick={() => select({ mode: 'pick' })}>
            {t('rules.add')}
          </Button>
        </div>
        <p className="pd-meta">{t('rules.intro')}</p>
        <div role="status">
          {message && (
            <div className="pd-receipt">
              <StatusIcon status={message.ok ? 'ok' : 'severe'} size={20} />
              <span>{message.text}</span>
            </div>
          )}
        </div>
        {rules.isPending && <Loader size="sm" />}
        {rules.isError && <Text c="red">{t('errors.unavailable')}</Text>}
        {rules.isSuccess && (
          <div className="pd-rules">
            {RULE_TYPES.map((type) => {
              const ofType = list.filter((r) => r.rule_type === type)
              return (
                <div
                  key={type}
                  className="pd-rule-type"
                  role="group"
                  aria-labelledby={`pd-h-rt-${type}`}
                >
                  <div className="pd-sec-head">
                    <div className="left">
                      <h3 className="pd-h-card" id={`pd-h-rt-${type}`}>
                        {t(`doctor.ruleTypes.${type}`)}
                      </h3>
                      <span className="pd-meta">{t(`rules.typeDesc.${type}`)}</span>
                    </div>
                  </div>
                  {ofType.length === 0 && <p className="pd-muted">{t('rules.none')}</p>}
                  {ofType.map((rule) => {
                    const sentence = ruleSentence(t, rule.rule_type, rule.current.params, ctx)
                    const isSel = selectedRule?.id === rule.id
                    return (
                      <article
                        key={rule.id}
                        className={isSel ? 'pd-rule sel' : 'pd-rule'}
                        aria-label={sentence}
                        aria-current={isSel ? 'true' : undefined}
                      >
                        <div>
                          <div className="cond">{sentence}</div>
                          <div className="info">
                            <span className="sv">
                              <SevDot severity={rule.current.severity} />
                              {t(`severity.${rule.current.severity}`)}
                            </span>
                            <span>
                              {t('rules.version', {
                                n: rule.current.version_no,
                                date: sinceDate(rule.current.created_at),
                              })}
                            </span>
                            {rule.open_alerts > 0 && (
                              <span>{t('rules.openAlerts', { count: rule.open_alerts })}</span>
                            )}
                          </div>
                        </div>
                        <Button
                          size="xs"
                          variant="default"
                          onClick={() => select({ mode: 'edit', ruleId: rule.id })}
                        >
                          {t('rules.edit')}
                        </Button>
                      </article>
                    )
                  })}
                </div>
              )
            })}
          </div>
        )}
      </section>
      {editor}
    </div>
  )
}
