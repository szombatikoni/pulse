import { Alert, Button, Checkbox, Group, Paper, Stack, Text, Title } from '@mantine/core'
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
      className="pulse-choices"
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
          className="pulse-choice"
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
      <Stack gap={4}>
        <ChoiceButtons question={question} value={single} onChange={onChange} showValue />
        <Group justify="space-between" wrap="nowrap" gap="md">
          <Text size="xs" c="dimmed">
            {first.label}
          </Text>
          <Text size="xs" c="dimmed" ta="right">
            {last.label}
          </Text>
        </Group>
      </Stack>
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

/** Egy kirendelt kérdőív kitöltése (F6). A beteg a pontszámot nem látja. */
export function QuestionnaireForm({
  patientId,
  questionnaire,
}: {
  patientId: string
  questionnaire: Questionnaire
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
          setReceiptAt(receipt.submitted_at)
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

  if (receiptAt) {
    return (
      <Paper withBorder p="md" id={`kerdoiv-${questionnaire.code}`}>
        <Stack gap="sm">
          <Title order={4}>{questionnaire.name}</Title>
          <Alert variant="light" color="green" title={t('questionnaires.submitted')} role="status">
            {t('questionnaires.receipt', { when: formatRelative(t, receiptAt) })}
          </Alert>
        </Stack>
      </Paper>
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
      <Paper withBorder p="md" id={`kerdoiv-${questionnaire.code}`}>
        <Group justify="space-between" align="center" gap="sm" wrap="wrap">
          <div>
            <Title order={4}>{questionnaire.name}</Title>
            <Text size="sm" c="dimmed">
              {t(key, { when: formatRelative(t, task.done_at) })}
            </Text>
          </div>
          <Button variant="default" size="xs" onClick={() => setReopened(true)}>
            {t('questionnaires.refill')}
          </Button>
        </Group>
      </Paper>
    )
  }

  return (
    <Paper withBorder p="md" id={`kerdoiv-${questionnaire.code}`}>
      <form onSubmit={onSubmit}>
        <Stack gap="md">
          <div>
            <Title order={4}>{questionnaire.name}</Title>
            <Text size="sm" c="dimmed">
              {t('questionnaires.questionCount', { count: total })} ·{' '}
              {questionnaire.last_submitted_at
                ? t('questionnaires.lastSubmitted', {
                    when: formatDateTime(questionnaire.last_submitted_at),
                  })
                : t('questionnaires.neverSubmitted')}
            </Text>
          </div>
          {message && (
            <Alert variant="light" color={message.ok ? 'green' : 'red'}>
              {message.text}
            </Alert>
          )}
          {questionnaire.questions.map((q) => (
            <Stack key={q.id} gap={6}>
              <Text fw={500}>
                {q.order_no}. {q.text}
              </Text>
              <QuestionInput
                question={q}
                value={answers[q.id]}
                onChange={(value) => setAnswers((a) => ({ ...a, [q.id]: value }))}
              />
            </Stack>
          ))}
          <Group gap="md">
            <Button type="submit" loading={submit.isPending} disabled={!complete}>
              {t('questionnaires.submit')}
            </Button>
            <Text size="sm" c="dimmed">
              {t('questionnaires.progress', { answered, total })}
            </Text>
          </Group>
        </Stack>
      </form>
    </Paper>
  )
}
