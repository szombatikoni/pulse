import { ActionIcon, Button, Loader, NumberInput, Radio, Text, TextInput } from '@mantine/core'
import { ArrowLeft, Plus, Trash, X } from '@phosphor-icons/react'
import { useQueryClient } from '@tanstack/react-query'
import type { TFunction } from 'i18next'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useLocation, useNavigate, useParams } from 'react-router'

import { ApiError } from '../../api/client'
import {
  BANDS,
  type EditorErrorDetail,
  LIMITS,
  type QuestionnaireDetail,
  type QuestionType,
  useQuestionnaireDetail,
  useQuestionnaireMutations,
} from '../../api/questionnaireEditor'
import { StatusIcon } from '../../components/StatusLabel'
import { formatDate, todayInput } from '../../format'
import './patientDetail.css'
import './questionnaireEditor.css'
import {
  buildSpec,
  type Draft,
  draftFrom,
  draftMax,
  isValid,
  newOption,
  newQuestion,
  type Num,
  type QuestionDraft,
  type QuestionErrors,
  questionMax,
  scalePoints,
  validate,
  withType,
} from './questionnaireDraft'

const TYPES: QuestionType[] = ['scale', 'single', 'multi']
const BAND_STATUS = { normal: 'ok', warning: 'attention', critical: 'severe' } as const

type Message = { ok: boolean; text: string; reload?: boolean }

/** A verzió napja röviden („nov. 16."). */
const versionDate = (iso: string) => formatDate(todayInput(new Date(iso)))

function serverError(t: TFunction, error: unknown): Message {
  const detail = error instanceof ApiError ? (error.detail as EditorErrorDetail | null) : null
  const code = detail && typeof detail === 'object' && 'code' in detail ? detail.code : undefined
  if (code === 'stale_version') {
    return {
      ok: false,
      reload: true,
      text: t('qeditor.errors.server.stale_version', { n: detail?.current_version_no }),
    }
  }
  return {
    ok: false,
    text: code
      ? t(`qeditor.errors.server.${code}`, { defaultValue: t('qeditor.errors.server.generic') })
      : t('qeditor.errors.server.generic'),
  }
}

/** Szegmensvezérlő (pd-seg), mint a szabályszerkesztőben. */
function Seg<T extends string | number>({
  label,
  options,
  value,
  onChange,
}: {
  label: string
  options: [T, string][]
  value: T
  onChange: (value: T) => void
}) {
  return (
    <div className="pd-seg" role="group" aria-label={label}>
      {options.map(([id, text]) => (
        <button key={id} type="button" aria-pressed={value === id} onClick={() => onChange(id)}>
          {text}
        </button>
      ))}
    </div>
  )
}

/** Egész szám mező léptetők nélkül; a tartományon kívüli értéket nem írja át csendben. */
function IntField({
  ariaLabel,
  value,
  onChange,
  error,
  className,
}: {
  ariaLabel: string
  value: Num
  onChange: (value: Num) => void
  error?: string
  className?: string
}) {
  return (
    <NumberInput
      aria-label={ariaLabel}
      classNames={{ label: 'pd-field-label' }}
      className={className}
      value={value}
      onChange={onChange}
      error={error}
      hideControls
      clampBehavior="none"
      allowNegative={false}
      allowDecimal={false}
      inputMode="numeric"
      autoComplete="off"
    />
  )
}

/** Egy kérdés szerkesztője: típus, szöveg, skálánál a skála, a jobb vég (kötelező,
 * alapértelmezés nélkül), a végfeliratok és a számolt pontok; választósnál a
 * lehetőségek felirattal és ponttal. */
function QuestionCard({
  q,
  no,
  errors,
  canRemove,
  onChange,
  onRemove,
}: {
  q: QuestionDraft
  no: number
  errors: QuestionErrors | undefined
  canRemove: boolean
  onChange: (q: QuestionDraft) => void
  onRemove: () => void
}) {
  const { t } = useTranslation()
  const set = (patch: Partial<QuestionDraft>) => onChange({ ...q, ...patch })
  const points = q.type === 'scale' ? scalePoints(q) : null
  const headId = `qe-q-${q.key}`

  return (
    <section className="qe-question" aria-labelledby={headId}>
      <div className="qe-q-head">
        <h3 className="pd-h-card" id={headId}>
          {t('qeditor.editor.questionNo', { n: no })}
        </h3>
        <Seg
          label={t('qeditor.editor.type')}
          options={TYPES.map(
            (type) => [type, t(`qeditor.types.${type}`)] as [QuestionType, string],
          )}
          value={q.type}
          onChange={(type) => onChange(withType(q, type))}
        />
        <ActionIcon
          variant="subtle"
          color="gray"
          onClick={onRemove}
          disabled={!canRemove}
          aria-label={t('qeditor.editor.removeQuestion', { n: no })}
          title={t('qeditor.editor.removeQuestion', { n: no })}
        >
          <Trash size={17} />
        </ActionIcon>
      </div>

      <TextInput
        label={t('qeditor.editor.text')}
        classNames={{ label: 'pd-field-label' }}
        value={q.text}
        onChange={(e) => set({ text: e.currentTarget.value })}
        error={errors?.text}
        autoComplete="off"
      />

      {q.type === 'scale' ? (
        <>
          <div className="pd-field">
            <span className="pd-field-label">{t('qeditor.editor.scale')}</span>
            <Seg
              label={t('qeditor.editor.scale')}
              options={[
                [5, '1–5'],
                [10, '1–10'],
              ]}
              value={q.scaleMax}
              onChange={(scaleMax) => set({ scaleMax })}
            />
            {errors?.scale && <span className="pd-err">{errors.scale}</span>}
          </div>
          <Radio.Group
            label={t('qeditor.editor.goodEnd')}
            classNames={{ label: 'pd-field-label' }}
            value={q.goodEnd ?? ''}
            onChange={(value) => set({ goodEnd: value as 'min' | 'max' })}
            error={errors?.goodEnd}
          >
            <div className="pd-checks">
              <Radio value="min" label={t('qeditor.editor.end', { n: 1 })} />
              <Radio value="max" label={t('qeditor.editor.end', { n: q.scaleMax })} />
            </div>
          </Radio.Group>
          <div className="pd-two">
            <TextInput
              label={t('qeditor.editor.endLabel', { n: 1 })}
              classNames={{ label: 'pd-field-label' }}
              value={q.minLabel}
              onChange={(e) => set({ minLabel: e.currentTarget.value })}
              error={errors?.minLabel}
              placeholder={t('qeditor.editor.optional')}
              autoComplete="off"
            />
            <TextInput
              label={t('qeditor.editor.endLabel', { n: q.scaleMax })}
              classNames={{ label: 'pd-field-label' }}
              value={q.maxLabel}
              onChange={(e) => set({ maxLabel: e.currentTarget.value })}
              error={errors?.maxLabel}
              placeholder={t('qeditor.editor.optional')}
              autoComplete="off"
            />
          </div>
          <p className="pd-meta qe-points">
            {points
              ? t('qeditor.editor.points', {
                  list: points.map(([v, p]) => `${v}→${p}`).join('  '),
                })
              : t('qeditor.editor.pointsPending')}
          </p>
        </>
      ) : (
        <div className="pd-field">
          <span className="pd-field-label">{t('qeditor.editor.options')}</span>
          <div className="qe-options">
            {q.options.map((o, i) => {
              const oe = errors?.option[o.key]
              const setOption = (patch: Partial<typeof o>) =>
                set({ options: q.options.map((x) => (x.key === o.key ? { ...x, ...patch } : x)) })
              return (
                <div className="qe-option" key={o.key}>
                  <TextInput
                    aria-label={t('qeditor.editor.optionLabel', { n: i + 1 })}
                    placeholder={t('qeditor.editor.optionLabel', { n: i + 1 })}
                    value={o.label}
                    onChange={(e) => setOption({ label: e.currentTarget.value })}
                    error={oe?.label}
                    autoComplete="off"
                  />
                  <IntField
                    ariaLabel={t('qeditor.editor.optionScore', { n: i + 1 })}
                    className="qe-score"
                    value={o.score}
                    onChange={(score) => setOption({ score })}
                    error={oe?.score}
                  />
                  <ActionIcon
                    variant="subtle"
                    color="gray"
                    onClick={() => set({ options: q.options.filter((x) => x.key !== o.key) })}
                    disabled={q.options.length <= 2}
                    aria-label={t('qeditor.editor.removeOption', { n: i + 1 })}
                    title={t('qeditor.editor.removeOption', { n: i + 1 })}
                  >
                    <X size={15} />
                  </ActionIcon>
                </div>
              )
            })}
          </div>
          {errors?.options && <span className="pd-err">{errors.options}</span>}
          <div>
            <Button
              variant="subtle"
              color="gray"
              size="xs"
              leftSection={<Plus size={14} />}
              onClick={() => set({ options: [...q.options, newOption(q.options)] })}
              disabled={q.options.length >= LIMITS.options}
            >
              {t('qeditor.editor.addOption')}
            </Button>
          </div>
          <p className="pd-meta">
            {t(q.type === 'multi' ? 'qeditor.editor.multiHint' : 'qeditor.editor.singleHint', {
              n: questionMax(q),
            })}
          </p>
        </div>
      )}
    </section>
  )
}

/** A szerkesztő: bal oldalt a kérdések, jobb oldalt a kiértékelés (a három rögzített
 * sáv két határa), a mentés új verzióként és a verziólista. Új kérdőívnél fent a név. */
function Editor({
  detail,
  onSaved,
}: {
  detail: QuestionnaireDetail | null
  onSaved: (saved: QuestionnaireDetail) => void
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const { create, addVersion } = useQuestionnaireMutations()
  const [initial] = useState(() => draftFrom(detail))
  const [draft, setDraftState] = useState<Draft>(initial)
  const [message, setMessage] = useState<Message | null>(null)
  const setDraft = (update: (d: Draft) => Draft) => {
    setDraftState(update)
    setMessage(null)
  }

  const isNew = detail === null
  const errors = validate(t, draft, isNew)
  const valid = isValid(errors)
  const dirty =
    isNew || !valid || JSON.stringify(buildSpec(draft)) !== JSON.stringify(buildSpec(initial))
  const canSave = valid && dirty
  const nextNo = (detail?.current.version_no ?? 0) + 1
  const max = draftMax(draft)
  const pending = create.isPending || addVersion.isPending

  const setQuestion = (key: string) => (q: QuestionDraft) =>
    setDraft((d) => ({ ...d, questions: d.questions.map((x) => (x.key === key ? q : x)) }))

  const save = () => {
    if (!canSave) return
    const spec = buildSpec(draft)
    const saving = detail
      ? addVersion.mutateAsync({
          code: detail.code,
          base_version_no: detail.current.version_no,
          ...spec,
        })
      : create.mutateAsync({ name: draft.name.trim(), ...spec })
    saving.then(onSaved).catch((e: unknown) => setMessage(serverError(t, e)))
  }

  const normal = Number(draft.normalMax)
  const warning = Number(draft.warningMax)
  const lower = {
    normal: '0',
    warning: errors.normalMax || draft.normalMax === '' ? '…' : String(normal + 1),
    critical: errors.warningMax || draft.warningMax === '' ? '…' : String(warning + 1),
  }

  return (
    <div className="pd-grid-2">
      <section className="pd-card qe-main" aria-labelledby="qe-h-questions">
        {isNew && (
          <TextInput
            label={t('qeditor.editor.name')}
            description={t('qeditor.editor.nameHint')}
            classNames={{ label: 'pd-field-label' }}
            value={draft.name}
            onChange={(e) => {
              const name = e.currentTarget.value
              setDraft((d) => ({ ...d, name }))
            }}
            error={errors.name}
            autoComplete="off"
          />
        )}
        <div className="pd-card-head flush">
          <div className="left">
            <span className="pd-eyebrow">
              {isNew
                ? t('qeditor.editor.titleNew')
                : `${detail.name} · ${t('qeditor.editor.editing')}`}
            </span>
            <h2 className="pd-h-sec" id="qe-h-questions">
              {t('qeditor.editor.questions')}
            </h2>
          </div>
          <span className="pd-chip-soft">
            {t('qeditor.questionCount', { count: draft.questions.length })}
          </span>
        </div>
        {draft.questions.map((q, i) => (
          <QuestionCard
            key={q.key}
            q={q}
            no={i + 1}
            errors={errors.question[q.key]}
            canRemove={draft.questions.length > 1}
            onChange={setQuestion(q.key)}
            onRemove={() =>
              setDraft((d) => ({ ...d, questions: d.questions.filter((x) => x.key !== q.key) }))
            }
          />
        ))}
        {errors.questions && <span className="pd-err">{errors.questions}</span>}
        <div>
          <Button
            variant="default"
            leftSection={<Plus size={16} />}
            onClick={() => setDraft((d) => ({ ...d, questions: [...d.questions, newQuestion()] }))}
            disabled={draft.questions.length >= LIMITS.questions}
          >
            {t('qeditor.editor.addQuestion')}
          </Button>
        </div>
      </section>

      <aside className="pd-card pd-editor" aria-labelledby="qe-h-eval">
        <div className="pd-card-head flush">
          <div className="left">
            <span className="pd-eyebrow">{t('qeditor.editor.evalEyebrow')}</span>
            <h2 className="pd-h-card" id="qe-h-eval">
              {t('qeditor.editor.evaluation')}
            </h2>
          </div>
          {detail && (
            <span className="pd-chip-soft">
              {t('qeditor.list.valid', { n: detail.current.version_no })}
            </span>
          )}
        </div>
        <p className="qe-max">{t('qeditor.editor.maxScore', { n: max })}</p>
        <div className="qe-bands" role="group" aria-label={t('qeditor.editor.evaluation')}>
          {BANDS.map((band) => (
            <div className="qe-band" key={band}>
              <span className="qe-band-name">
                <StatusIcon status={BAND_STATUS[band]} size={16} />
                {t(`qeditor.bands.${band}`)}
              </span>
              <span className="qe-band-range">
                <span className="lo">{lower[band]}</span>
                <span aria-hidden="true">–</span>
                {band === 'critical' ? (
                  <span className="hi">{max}</span>
                ) : (
                  <IntField
                    ariaLabel={t('qeditor.editor.bandUpper', {
                      band: t(`qeditor.bands.${band}`),
                    })}
                    className="qe-band-input"
                    value={band === 'normal' ? draft.normalMax : draft.warningMax}
                    onChange={(v) =>
                      setDraft((d) =>
                        band === 'normal' ? { ...d, normalMax: v } : { ...d, warningMax: v },
                      )
                    }
                  />
                )}
              </span>
            </div>
          ))}
        </div>
        {(errors.bands || errors.normalMax || errors.warningMax) && (
          <div className="qe-band-errors">
            {[errors.bands, errors.normalMax, errors.warningMax].filter(Boolean).map((text) => (
              <span className="pd-err" key={text}>
                <StatusIcon status="severe" size={14} />
                {text}
              </span>
            ))}
          </div>
        )}
        <p className="pd-meta">{t('qeditor.editor.bandsHint')}</p>

        <div className="qe-notice">
          <StatusIcon status="attention" size={18} />
          <span>{t(isNew ? 'qeditor.editor.infoNew' : 'qeditor.editor.info')}</span>
        </div>

        {message && (
          <div className="pd-receipt" role="alert">
            <StatusIcon status={message.ok ? 'ok' : 'severe'} size={20} />
            <span>{message.text}</span>
          </div>
        )}
        {message?.reload && detail && (
          <div>
            <Button
              variant="default"
              size="xs"
              onClick={() =>
                queryClient.invalidateQueries({
                  queryKey: ['questionnaire-templates', detail.code],
                })
              }
            >
              {t('qeditor.editor.reload')}
            </Button>
          </div>
        )}
        {!isNew && valid && !dirty && <p className="pd-meta">{t('qeditor.editor.unchanged')}</p>}
        <div className="pd-plan-foot">
          {isNew ? (
            <Button variant="subtle" color="gray" component={Link} to="/doctor/questionnaires">
              {t('qeditor.editor.cancel')}
            </Button>
          ) : (
            <Button
              variant="subtle"
              color="gray"
              onClick={() => {
                setDraftState(initial)
                setMessage(null)
              }}
            >
              {t('qeditor.editor.reset')}
            </Button>
          )}
          <Button disabled={!canSave} loading={pending} onClick={save}>
            {t('qeditor.editor.save', { n: nextNo })}
          </Button>
        </div>

        {detail && (
          <div className="pd-field">
            <h3 className="pd-eyebrow">{t('qeditor.editor.versions')}</h3>
            <ol className="pd-versions">
              {detail.versions.map((v) => (
                <li key={v.version_no}>
                  <span className="vn">{t('qeditor.editor.versionNo', { n: v.version_no })}</span>
                  <span className="pd-muted">
                    {t('qeditor.questionCount', { count: v.question_count })}
                  </span>
                  <span className="pd-muted">
                    {versionDate(v.created_at)}
                    {v.version_no === detail.current.version_no
                      ? ` · ${t('qeditor.editor.valid')}`
                      : ''}
                  </span>
                </li>
              ))}
            </ol>
          </div>
        )}
      </aside>
    </div>
  )
}

/** A kérdőív szerkesztőoldala (/doctor/questionnaires/:code), illetve új kérdőívnél
 * (/doctor/questionnaires/new) ugyanez üres űrlappal (M3, A5). Mentés után a
 * szerkesztő az új verzióval újraindul, fent a nyugtával. */
export function QuestionnaireEditorPage() {
  const { t } = useTranslation()
  const { code } = useParams()
  const navigate = useNavigate()
  const location = useLocation()
  const isNew = code === undefined
  const detail = useQuestionnaireDetail(code)
  // A mentés nyugtája: új kérdőívnél a navigáció állapotában érkezik.
  const [saved, setSaved] = useState<string | null>(
    (location.state as { saved?: string } | null)?.saved ?? null,
  )

  const onSaved = (result: QuestionnaireDetail) => {
    const n = result.current.version_no
    const text = t(n === 1 ? 'qeditor.editor.created' : 'qeditor.editor.saved', { n })
    if (isNew) {
      navigate(`/doctor/questionnaires/${result.code}`, { replace: true, state: { saved: text } })
    } else {
      setSaved(text)
    }
  }

  let body
  if (isNew) {
    body = <Editor detail={null} onSaved={onSaved} />
  } else if (detail.isPending) {
    body = <Loader />
  } else if (detail.isError) {
    const notFound = detail.error instanceof ApiError && detail.error.status === 404
    body = <Text c="red">{t(notFound ? 'qeditor.notFound' : 'errors.unavailable')}</Text>
  } else {
    body = (
      <Editor
        // Mentés után az új verzióval (a friss részletekből) újraindul az állapot.
        key={`${detail.data.code}-${detail.data.current.version_no}`}
        detail={detail.data}
        onSaved={onSaved}
      />
    )
  }

  const data = detail.data
  return (
    <div className="pd-page">
      <header className="pd-head">
        <nav className="pd-crumbs" aria-label={t('qeditor.editor.backLabel')}>
          <Link to="/doctor/questionnaires">
            <ArrowLeft size={15} />
            {t('qeditor.list.title')}
          </Link>
        </nav>
        <div className="pd-ph">
          <h1 className="pd-display">
            {isNew ? t('qeditor.editor.titleNew') : (data?.name ?? '')}
          </h1>
          {data && !isNew && (
            <div className="pd-ph-meta">
              <span>{t('qeditor.list.valid', { n: data.current.version_no })}</span>
              <span>{t('qeditor.questionCount', { count: data.current.questions.length })}</span>
              <span>{t('qeditor.list.maxScore', { n: data.current.max_score })}</span>
            </div>
          )}
        </div>
      </header>
      <div role="status">
        {saved && (
          <div className="pd-receipt">
            <StatusIcon status="ok" size={20} />
            <span>{saved}</span>
          </div>
        )}
      </div>
      {body}
    </div>
  )
}
