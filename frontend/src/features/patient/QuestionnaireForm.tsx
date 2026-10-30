import { Button, Checkbox, Group, Stack } from '@mantine/core'
import { useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { ApiError } from '../../api/client'
import {
  type Question,
  type Questionnaire,
  type SubmissionErrorDetail,
  useSubmitQuestionnaire,
} from '../../api/questionnaires'
import { usePatientTasks } from '../../api/tasks'
import { StatusIcon } from '../../components/StatusLabel'
import { formatDateTime, formatRelative } from '../../format'

type Answers = Record<string, string | string[]>

/** Egy választás nagy, érintésre is kényelmes gombokkal (skála vagy egy választás). */
function ChoiceButtons({
  question,
  value,
  onChange,
  showValue,
}: {
  question: Question
  value: string | undefined
  onChange: (value: string) => void
  showValue: boolean
}) {
  const n = question.options.length
  return (
    <div
      role="radiogroup"
      aria-label={question.text}
      className="pulse-hchoices"
      style={{
        gridTemplateColumns:
          n <= 5 ? `repeat(${n}, minmax(0, 1fr))` : 'repeat(auto-fit, minmax(96px, 1fr))',
      }}
    >
      {question.options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={value === o.value}
          className={showValue ? 'pulse-hchoice' : 'pulse-hchoice txt'}
          onClick={() => onChange(o.value)}
        >
          {showValue ? o.value : o.label}
        </button>
      ))}
    </div>
  )
}

function QuestionInput({
  question,
  value,
  onChange,
}: {
  question: Question
  value: string | string[] | undefined
  onChange: (value: string | string[]) => void
}) {
  const single = typeof value === 'string' ? value : undefined
  if (question.question_type === 'scale') {
    // A skála két végének felirata a válaszlehetőségekben van („1 – nagyon rosszul").
    const first = question.options[0]
    const last = question.options[question.options.length - 1]
    return (
      <>
        <ChoiceButtons question={question} value={single} onChange={onChange} showValue />
        <div className="pulse-scale-ends">
          <span>{first.label}</span>
          <span style={{ textAlign: 'right' }}>{last.label}</span>
        </div>
      </>
    )
  }
  if (question.question_type === 'single') {
    return (
      <ChoiceButtons question={question} value={single} onChange={onChange} showValue={false} />
    )
  }
  return (
    <Checkbox.Group
      value={Array.isArray(value) ? value : []}
      onChange={onChange}
      aria-label={question.text}
    >
      <Group gap="lg">
        {question.options.map((o) => (
          <Checkbox key={o.value} value={o.value} label={o.label} />
        ))}
      </Group>
    </Checkbox.Group>
  )
}

/** Egy kirendelt kérdőív kitöltése (F6). A beteg a pontszámot nem látja. A saját
 * oldalán (`onSubmitted`) a címet az oldal fejléce adja, és beküldés után a szülő
 * visz vissza a teendőkhöz. */
export function QuestionnaireForm({
  patientId,
  questionnaire,
  onSubmitted,
}: {
  patientId: string
  questionnaire: Questionnaire
  onSubmitted?: (submittedAt: string) => void
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const submit = useSubmitQuestionnaire(patientId)
  const [answers, setAnswers] = useState<Answers>({})
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null)
  // Sikeres beküldés után a kérdések helyén nyugta áll (ne tűnjön újra kitöltendőnek).
  const [receiptAt, setReceiptAt] = useState<string | null>(null)
  // Ha az aktuális időszakban már kitöltötte, csak egy sor látszik, újrakitöltési
  // lehetőséggel (a hallgató döntése, 2026-10-17).
  const [reopened, setReopened] = useState(false)
  const tasks = usePatientTasks(patientId)
  const task = tasks.data?.find((x) => x.kind === 'questionnaire' && x.code === questionnaire.code)

  // A többválasztós kérdésre az üres válasz is érvényes („egyik sem").
  const isAnswered = (q: Question) =>
    q.question_type === 'multi' || typeof answers[q.id] === 'string'
  const total = questionnaire.questions.length
  const answered = questionnaire.questions.filter(
    (q) =>
      typeof answers[q.id] === 'string' ||
      (Array.isArray(answers[q.id]) && answers[q.id].length > 0),
  ).length
  const complete = questionnaire.questions.every(isAnswered)

  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    setMessage(null)
    const payload = Object.fromEntries(
      questionnaire.questions.map((q) => [q.id, answers[q.id] ?? []]),
    )
    submit.mutate(
      { questionnaire_code: questionnaire.code, answers: payload },
      {
        onSuccess: (receipt) => {
          setAnswers({})
          setMessage(null)
          if (onSubmitted) onSubmitted(receipt.submitted_at)
          else setReceiptAt(receipt.submitted_at)
        },
        onError: (error) => {
          if (error instanceof ApiError && error.status === 422 && error.detail) {
            // Közben változhatott a kérdőív (új verzió, visszavont kirendelés):
            // frissítjük, és az okot a beteg nyelvén írjuk ki.
            const { code } = error.detail as SubmissionErrorDetail
            void queryClient.invalidateQueries({
              queryKey: ['patients', patientId, 'questionnaires'],
            })
            setMessage({
              ok: false,
              text: t(`questionnaires.errors.${code}`, {
                defaultValue: t('questionnaires.error'),
              }),
            })
          } else {
            setMessage({ ok: false, text: t('questionnaires.error') })
          }
        },
      },
    )
  }

  const id = `kerdoiv-${questionnaire.code}`
  const headingId = `${id}-cim`

  if (receiptAt) {
    return (
      <section className="pulse-pcard" id={id} aria-labelledby={headingId}>
        <Stack gap="md">
          <h3 className="pulse-h-sec" id={headingId}>
            {questionnaire.name}
          </h3>
          <div className="pulse-receipt" role="status">
            <StatusIcon status="ok" size={22} />
            <div>
              <b>{t('questionnaires.submitted')}</b>
              <p className="pulse-hint">
                {t('questionnaires.receipt', { when: formatRelative(t, receiptAt) })}
              </p>
            </div>
          </div>
        </Stack>
      </section>
    )
  }

  if (task?.state === 'done' && task.done_at && !reopened) {
    const key =
      task.frequency === 'daily'
        ? 'questionnaires.alreadyDaily'
        : task.frequency === 'weekly'
          ? 'questionnaires.alreadyWeekly'
          : 'questionnaires.alreadyPeriod'
    return (
      <section className="pulse-pcard" id={id} aria-labelledby={headingId}>
        <Group justify="space-between" align="center" gap="sm" wrap="wrap">
          <Stack gap={2}>
            <h3 className="pulse-h-sec" id={headingId}>
              {questionnaire.name}
            </h3>
            <span className="pulse-meta">{t(key, { when: formatRelative(t, task.done_at) })}</span>
          </Stack>
          <Button variant="default" onClick={() => setReopened(true)}>
            {t('questionnaires.refill')}
          </Button>
        </Group>
      </section>
    )
  }

  return (
    <section className="pulse-pcard" id={id} aria-labelledby={headingId}>
      <form onSubmit={onSubmit}>
        <Stack gap={18}>
          <Stack gap={2} display={onSubmitted ? 'none' : undefined}>
            <h3 className="pulse-h-sec" id={headingId}>
              {questionnaire.name}
            </h3>
            <span className="pulse-meta">
              {t('questionnaires.questionCount', { count: total })} ·{' '}
              {questionnaire.last_submitted_at
                ? t('questionnaires.lastSubmitted', {
                    when: formatDateTime(questionnaire.last_submitted_at),
                  })
                : t('questionnaires.neverSubmitted')}
            </span>
          </Stack>
          {message && (
            <div className="pulse-receipt" role="alert">
              <StatusIcon status={message.ok ? 'ok' : 'severe'} size={22} />
              <b>{message.text}</b>
            </div>
          )}
          <div className="pulse-qs">
            {questionnaire.questions.map((q) => (
              <div key={q.id} className="pulse-q">
                <span className="pulse-q-text">
                  {q.order_no}. {q.text}
                </span>
                <QuestionInput
                  question={q}
                  value={answers[q.id]}
                  onChange={(value) => setAnswers((a) => ({ ...a, [q.id]: value }))}
                />
              </div>
            ))}
          </div>
          <div className="pulse-q-foot">
            <Button type="submit" size="lg" loading={submit.isPending} disabled={!complete}>
              {t('questionnaires.submit')}
            </Button>
            <span className="pulse-meta">{t('questionnaires.progress', { answered, total })}</span>
          </div>
        </Stack>
      </form>
    </section>
  )
}
