import { Button, Loader, NativeSelect, NumberInput, Text, Textarea, TextInput } from '@mantine/core'
import { ClipboardText, Drop, Gauge, Heart, type Icon, Plus, Scales } from '@phosphor-icons/react'
import type { TFunction } from 'i18next'
import { type FormEvent, type ReactNode, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { ApiError } from '../../api/client'
import { useMeasurementTypes } from '../../api/measurements'
import {
  type Assignment,
  type Frequency,
  NOTE_MAX,
  type PlanErrorDetail,
  type PlanParams,
  type TargetKind,
  usePatientPlan,
  usePlanMutations,
  useQuestionnaireTemplates,
} from '../../api/plans'
import { StatusIcon } from '../../components/StatusLabel'
import { formatClock, formatDate, todayInput } from '../../format'
import './patientDetail.css'

const KIND_ICON: Record<string, Icon> = {
  blood_pressure: Gauge,
  heart_rate: Heart,
  body_weight: Scales,
  blood_glucose: Drop,
}
const FREQUENCIES: Frequency[] = ['daily', 'weekly', 'every_n_days']

type Editor = { mode: 'new' } | { mode: 'replace'; assignment: Assignment }
type Message = { ok: boolean; text: string }

const targetName = (t: TFunction, a: Assignment) =>
  a.kind === 'measurement' ? t(`measurementTypes.${a.code}`, { defaultValue: a.name }) : a.name

/** „Naponta" (sor elején) vagy „naponta" (mondat közben). */
function frequencyText(
  t: TFunction,
  a: Pick<Assignment, 'frequency' | 'interval_days'>,
  inline = false,
) {
  const key = inline ? `doctor.plan.freq.${a.frequency}` : `tasks.frequency.${a.frequency}`
  return t(key, { count: a.interval_days ?? 0 })
}

/** A visszavonás helyi napja („YYYY-MM-DD"). */
const revokedDay = (a: Assignment) => (a.revoked_at ? todayInput(new Date(a.revoked_at)) : null)

/** Mettől meddig érvényes (volt) az előírás. */
function periodText(t: TFunction, a: Assignment): string {
  const from = formatDate(a.start_date)
  const revoked = revokedDay(a)
  if (revoked) {
    // A még el sem kezdett, visszavont előírásnál nincs értelmes időszak.
    return revoked >= a.start_date
      ? t('doctor.plan.range', { from, to: formatDate(revoked) })
      : t('doctor.plan.startsOn', { date: from })
  }
  if (a.end_date) return t('doctor.plan.range', { from, to: formatDate(a.end_date) })
  return a.status === 'upcoming'
    ? t('doctor.plan.startsOn', { date: from })
    : t('doctor.plan.since', { date: from })
}

/** A váltás jelzése (a2_terv 6/1. pont): mi változott az előző előíráshoz képest,
 * pl. „Módosítva okt. 30.: naponta → hetente, határidő 10:00 → 20:00". */
function changeText(t: TFunction, prev: Assignment, next: Assignment): string {
  const none = t('doctor.plan.none')
  const parts: string[] = []
  if (prev.frequency !== next.frequency || prev.interval_days !== next.interval_days) {
    parts.push(`${frequencyText(t, prev, true)} → ${frequencyText(t, next, true)}`)
  }
  if (prev.due_time !== next.due_time) {
    parts.push(
      t('doctor.plan.changeDue', {
        from: formatClock(prev.due_time),
        to: formatClock(next.due_time),
      }),
    )
  }
  if (prev.suggested_time !== next.suggested_time) {
    const clock = (v: string | null) => (v ? formatClock(v) : none)
    parts.push(
      t('doctor.plan.changeSuggested', {
        from: clock(prev.suggested_time),
        to: clock(next.suggested_time),
      }),
    )
  }
  if (prev.end_date !== next.end_date) {
    const day = (v: string | null) => (v ? formatDate(v) : t('doctor.plan.noEnd'))
    parts.push(t('doctor.plan.changeEnd', { from: day(prev.end_date), to: day(next.end_date) }))
  }
  const date = formatDate(revokedDay(prev) ?? next.start_date)
  return parts.length
    ? t('doctor.plan.changed', { date, changes: parts.join(', ') })
    : t('doctor.plan.changedPlain', { date })
}

/** Indoklás a betegnek (visszavonásnál és módosításnál): nem kötelező, a beteg a
 * teendői között látja (a hallgató döntése, 2026-11-01). */
function NoteField({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const { t } = useTranslation()
  return (
    <Textarea
      label={t('doctor.plan.note.label')}
      description={t('doctor.plan.note.hint')}
      classNames={{ label: 'pd-field-label' }}
      value={value}
      onChange={(e) => onChange(e.currentTarget.value)}
      maxLength={NOTE_MAX}
      autosize
      minRows={2}
      maxRows={5}
    />
  )
}

function errorText(t: TFunction, error: unknown): string {
  const detail = error instanceof ApiError ? (error.detail as PlanErrorDetail | null) : null
  // A szerver saját kódja (pl. overlap); a szerkezeti hibákra (lista) általános szöveg.
  if (detail && typeof detail === 'object' && 'code' in detail) {
    return t(`doctor.plan.errors.${detail.code}`, {
      defaultValue: t('doctor.plan.errors.generic'),
    })
  }
  return t('doctor.plan.errors.generic')
}

/** Új előírás vagy módosítás űrlapja. Módosításnál a régi értékekkel előtöltve,
 * a cél nem választható (az új előírás ugyanarra a célra szól). */
function PlanForm({
  patientId,
  editor,
  onDone,
  onCancel,
}: {
  patientId: string
  editor: Editor
  onDone: (message: Message) => void
  onCancel: () => void
}) {
  const { t } = useTranslation()
  const types = useMeasurementTypes()
  const templates = useQuestionnaireTemplates()
  const { create, replace } = usePlanMutations(patientId)
  const old = editor.mode === 'replace' ? editor.assignment : null
  const today = todayInput()

  const [target, setTarget] = useState('measurement:blood_pressure')
  const [frequency, setFrequency] = useState<Frequency>(old?.frequency ?? 'daily')
  const [intervalDays, setIntervalDays] = useState<number | string>(old?.interval_days ?? 2)
  const [due, setDue] = useState(old ? formatClock(old.due_time) : '10:00')
  const [suggested, setSuggested] = useState(
    old?.suggested_time ? formatClock(old.suggested_time) : '',
  )
  // Módosításnál a kezdet nem választható (review K3, a hallgató döntése, 2026-11-01):
  // az új ma indul, a még el nem kezdett régi helyére a kezdetén. A szerver dönti el
  // (üres start_date), mert a böngésző mai napja eltérhet a szerver időzónájáétól;
  // itt csak a vége mező alsó határához kell.
  const [start, setStart] = useState(old && old.start_date > today ? old.start_date : today)
  const [end, setEnd] = useState(old?.end_date ?? '')
  const [note, setNote] = useState('')
  const [error, setError] = useState<string | null>(null)

  const titleId = old ? `pd-h-plan-edit-${old.id}` : 'pd-h-plan-new'
  const pending = create.isPending || replace.isPending

  const submit = (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    const params: PlanParams = {
      frequency,
      interval_days: frequency === 'every_n_days' ? Number(intervalDays) : null,
      due_time: due,
      suggested_time: suggested || null,
      start_date: old ? null : start || null,
      end_date: end || null,
    }
    // A mutateAsync ígérete akkor is teljesül, ha az űrlap közben eltűnik: módosításnál
    // a lista frissülésekor a régi előírás (és benne az űrlap) a korábbiak közé kerül,
    // a mutate saját visszahívása ilyenkor már nem futna le.
    const [kind, code] = target.split(':') as [TargetKind, string]
    const saving = old
      ? replace
          .mutateAsync({ id: old.id, params, note: note.trim() })
          .then(() => t('doctor.plan.replaced'))
      : create.mutateAsync({ kind, code, ...params }).then(() => t('doctor.plan.saved'))
    saving
      .then((text) => onDone({ ok: true, text }))
      .catch((e: unknown) => setError(errorText(t, e)))
  }

  const targetData = [
    {
      group: t('doctor.plan.form.measurementGroup'),
      items: (types.data ?? []).map((x) => ({
        value: `measurement:${x.code}`,
        label: t(`measurementTypes.${x.code}`, { defaultValue: x.name }),
      })),
    },
    {
      group: t('doctor.plan.form.questionnaireGroup'),
      items: (templates.data ?? []).map((x) => ({
        value: `questionnaire:${x.code}`,
        label: x.name,
      })),
    },
  ]

  return (
    <form className="pd-plan-form" onSubmit={submit} aria-labelledby={titleId}>
      <h3 className="pd-h-card" id={titleId}>
        {t(old ? 'doctor.plan.form.titleReplace' : 'doctor.plan.form.titleNew')}
      </h3>
      {!old && (
        <NativeSelect
          label={t('doctor.plan.form.target')}
          classNames={{ label: 'pd-field-label' }}
          data={targetData}
          value={target}
          onChange={(e) => setTarget(e.currentTarget.value)}
        />
      )}
      <div className="pd-field">
        <span className="pd-field-label" id={`${titleId}-freq`}>
          {t('doctor.plan.form.frequency')}
        </span>
        <div className="pd-plan-freq">
          <div className="pd-seg" role="group" aria-labelledby={`${titleId}-freq`}>
            {FREQUENCIES.map((f) => (
              <button
                key={f}
                type="button"
                aria-pressed={frequency === f}
                onClick={() => setFrequency(f)}
              >
                {f === 'every_n_days' ? t('doctor.plan.form.everyN') : t(`tasks.frequency.${f}`)}
              </button>
            ))}
          </div>
          {frequency === 'every_n_days' && (
            <NumberInput
              label={t('doctor.plan.form.every')}
              classNames={{ label: 'pd-field-label' }}
              value={intervalDays}
              onChange={setIntervalDays}
              min={1}
              max={365}
              allowDecimal={false}
              allowNegative={false}
              clampBehavior="none"
              required
              w={140}
            />
          )}
        </div>
      </div>
      <div className="pd-two">
        <TextInput
          type="time"
          label={t('doctor.plan.form.due')}
          description={t('doctor.plan.form.dueHint')}
          classNames={{ label: 'pd-field-label' }}
          value={due}
          onChange={(e) => setDue(e.currentTarget.value)}
          required
        />
        <TextInput
          type="time"
          label={t('doctor.plan.form.suggested')}
          description={t('doctor.plan.form.optional')}
          classNames={{ label: 'pd-field-label' }}
          value={suggested}
          onChange={(e) => setSuggested(e.currentTarget.value)}
        />
      </div>
      <div className="pd-two">
        {!old && (
          <TextInput
            type="date"
            label={t('doctor.plan.form.start')}
            classNames={{ label: 'pd-field-label' }}
            value={start}
            min={today}
            onChange={(e) => setStart(e.currentTarget.value)}
            required
          />
        )}
        <TextInput
          type="date"
          label={t('doctor.plan.form.end')}
          description={t('doctor.plan.form.optional')}
          classNames={{ label: 'pd-field-label' }}
          value={end}
          min={start || today}
          onChange={(e) => setEnd(e.currentTarget.value)}
        />
      </div>
      {old && <NoteField value={note} onChange={setNote} />}
      {old && (
        <p className="pd-meta">
          {t('doctor.plan.form.replaceHint', {
            date: formatDate(old.start_date > today ? old.start_date : today),
          })}
        </p>
      )}
      {error && (
        <div className="pd-receipt" role="alert">
          <StatusIcon status="severe" size={20} />
          <span>{error}</span>
        </div>
      )}
      <div className="pd-plan-foot">
        <Button variant="subtle" color="gray" onClick={onCancel}>
          {t('doctor.plan.cancel')}
        </Button>
        <Button type="submit" loading={pending}>
          {t(old ? 'doctor.plan.form.saveReplace' : 'doctor.plan.form.save')}
        </Button>
      </div>
    </form>
  )
}

/** Egy előírás a listában: mit, milyen gyakran, határidő, mettől meddig, ki írta
 * elő; ha egy korábbi előírás helyébe lépett, a váltás is. */
function PlanItem({
  assignment: a,
  previous,
  past = false,
  children,
}: {
  assignment: Assignment
  previous?: Assignment
  past?: boolean
  children?: ReactNode
}) {
  const { t } = useTranslation()
  const Glyph = a.kind === 'measurement' ? (KIND_ICON[a.code] ?? Gauge) : ClipboardText
  const name = targetName(t, a)
  const times = [
    t('doctor.plan.due', { time: formatClock(a.due_time) }),
    a.suggested_time ? t('doctor.plan.suggested', { time: formatClock(a.suggested_time) }) : null,
  ]
    .filter(Boolean)
    .join(', ')
  let state: string | null = null
  if (past) {
    const date = formatDate(revokedDay(a) ?? a.start_date)
    state = a.replaced_by
      ? t('doctor.plan.state.replaced', { date })
      : a.status === 'revoked'
        ? t('doctor.plan.state.revoked', { date })
        : t('doctor.plan.state.ended')
  }
  return (
    <article className={past ? 'pd-plan-item past' : 'pd-plan-item'} aria-label={name}>
      <span className="pd-tico" aria-hidden="true">
        <Glyph size={20} />
      </span>
      <div className="pd-plan-body">
        <div className="pd-plan-name">
          <span className="nm">{name}</span>
          {a.status === 'upcoming' && (
            <span className="pd-plan-tag">{t('doctor.plan.state.upcoming')}</span>
          )}
          {state && <span className="pd-plan-tag">{state}</span>}
        </div>
        <div className="pd-meta">
          {frequencyText(t, a)} · {times}
        </div>
        <div className="pd-meta">
          {periodText(t, a)} · {t('doctor.plan.by', { name: a.assigned_by })}
        </div>
        {previous && <div className="pd-plan-change">{changeText(t, previous, a)}</div>}
        {a.revoke_note && (
          <div className="pd-plan-note">{t('doctor.plan.note.shown', { note: a.revoke_note })}</div>
        )}
      </div>
      {children}
    </article>
  )
}

/** A beteg követési terve az orvosnak (F14; M3, A2): az érvényes előírások
 * módosítással és visszavonással, alattuk halványabban a korábbiak időrendben.
 * Módosítás = a régi lezárása + új előírás (a2_terv 6/1. pont). */
export function CarePlan({ patientId }: { patientId: string }) {
  const { t } = useTranslation()
  const plan = usePatientPlan(patientId)
  const { revoke } = usePlanMutations(patientId)
  const [editor, setEditor] = useState<Editor | null>(null)
  const [confirming, setConfirming] = useState<string | null>(null)
  const [revokeNote, setRevokeNote] = useState('')
  const [message, setMessage] = useState<Message | null>(null)

  const all = plan.data ?? []
  const current = all.filter((a) => a.status === 'active' || a.status === 'upcoming')
  const past = all.filter((a) => a.status === 'revoked' || a.status === 'ended')
  const previousOf = new Map(all.filter((a) => a.replaced_by).map((a) => [a.replaced_by, a]))

  const open = (next: Editor | null) => {
    setEditor(next)
    setConfirming(null)
    setRevokeNote('')
    setMessage(null)
  }
  const done = (m: Message) => {
    setEditor(null)
    setMessage(m)
  }
  const doRevoke = (id: string) =>
    revoke.mutate(
      { id, note: revokeNote.trim() },
      {
        onSuccess: () => {
          setConfirming(null)
          setMessage({ ok: true, text: t('doctor.plan.revoked') })
        },
        onError: (e) => setMessage({ ok: false, text: errorText(t, e) }),
      },
    )

  return (
    <section className="pd-card" aria-labelledby="pd-h-plan">
      <div className="pd-card-head">
        <div className="left">
          <h2 className="pd-h-card" id="pd-h-plan">
            {t('doctor.plan.title')}
          </h2>
          <span className="pd-meta">{t('doctor.plan.meta')}</span>
        </div>
        {editor?.mode !== 'new' && (
          <Button size="xs" leftSection={<Plus size={14} />} onClick={() => open({ mode: 'new' })}>
            {t('doctor.plan.add')}
          </Button>
        )}
      </div>
      <div className="pd-plan">
        {editor?.mode === 'new' && (
          <PlanForm
            patientId={patientId}
            editor={editor}
            onDone={done}
            onCancel={() => open(null)}
          />
        )}
        <div role="status">
          {message && (
            <div className="pd-receipt">
              <StatusIcon status={message.ok ? 'ok' : 'severe'} size={20} />
              <span>{message.text}</span>
            </div>
          )}
        </div>
        {plan.isPending && <Loader size="sm" />}
        {plan.isError && <Text c="red">{t('errors.unavailable')}</Text>}
        {plan.isSuccess && current.length === 0 && (
          <p className="pd-muted">{t('doctor.plan.empty')}</p>
        )}
        {current.map((a) => {
          const editing = editor?.mode === 'replace' && editor.assignment.id === a.id
          return (
            <PlanItem key={a.id} assignment={a} previous={previousOf.get(a.id)}>
              {editing ? (
                <div className="pd-plan-wide">
                  <PlanForm
                    patientId={patientId}
                    editor={editor}
                    onDone={done}
                    onCancel={() => open(null)}
                  />
                </div>
              ) : confirming === a.id ? (
                <div className="pd-plan-wide pd-confirm">
                  <p>{t('doctor.plan.confirmRevoke')}</p>
                  <NoteField value={revokeNote} onChange={setRevokeNote} />
                  <div className="pd-plan-foot">
                    <Button variant="subtle" color="gray" onClick={() => setConfirming(null)}>
                      {t('doctor.plan.cancel')}
                    </Button>
                    <Button loading={revoke.isPending} onClick={() => doRevoke(a.id)}>
                      {t('doctor.plan.revoke')}
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="pd-plan-actions">
                  <Button
                    size="xs"
                    variant="default"
                    onClick={() => open({ mode: 'replace', assignment: a })}
                  >
                    {t('doctor.plan.modify')}
                  </Button>
                  <Button
                    size="xs"
                    variant="subtle"
                    color="gray"
                    onClick={() => {
                      open(null)
                      setConfirming(a.id)
                    }}
                  >
                    {t('doctor.plan.revoke')}
                  </Button>
                </div>
              )}
            </PlanItem>
          )
        })}
        {past.length > 0 && (
          <div className="pd-plan-past">
            <h3 className="pd-plan-sub">{t('doctor.plan.pastTitle', { count: past.length })}</h3>
            {past.map((a) => (
              <PlanItem key={a.id} assignment={a} previous={previousOf.get(a.id)} past />
            ))}
          </div>
        )}
      </div>
    </section>
  )
}
