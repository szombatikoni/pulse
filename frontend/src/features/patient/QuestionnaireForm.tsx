import {
  Alert,
  Button,
  Checkbox,
  Group,
  Paper,
  Radio,
  SegmentedControl,
  Stack,
  Text,
  Title,
} from '@mantine/core'
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
import { formatDateTime } from '../../format'

type Answers = Record<string, string | string[]>

function QuestionInput({
  question,
  value,
  onChange,
}: {
  question: Question
  value: string | string[] | undefined
  onChange: (value: string | string[]) => void
}) {
  if (question.question_type === 'scale') {
    // A skála két végének felirata a válaszlehetőségekben van („1 – nagyon rosszul").
    const first = question.options[0]
    const last = question.options[question.options.length - 1]
    return (
      <Stack gap={4}>
        <SegmentedControl
          data={question.options.map((o) => ({ value: o.value, label: o.value }))}
          value={typeof value === 'string' ? value : ''}
          onChange={onChange}
          aria-label={question.text}
        />
        <Group justify="space-between">
          <Text size="xs" c="dimmed">
            {first.label}
          </Text>
          <Text size="xs" c="dimmed">
            {last.label}
          </Text>
        </Group>
      </Stack>
    )
  }
  if (question.question_type === 'single') {
    return (
      <Radio.Group
        value={typeof value === 'string' ? value : null}
        onChange={onChange}
        aria-label={question.text}
      >
        <Group gap="lg">
          {question.options.map((o) => (
            <Radio key={o.value} value={o.value} label={o.label} />
          ))}
        </Group>
      </Radio.Group>
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

  // A többválasztós kérdésre az üres válasz is érvényes („egyik sem").
  const complete = questionnaire.questions.every(
    (q) => q.question_type === 'multi' || typeof answers[q.id] === 'string',
  )

  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    setMessage(null)
    const payload = Object.fromEntries(
      questionnaire.questions.map((q) => [q.id, answers[q.id] ?? []]),
    )
    submit.mutate(
      { questionnaire_code: questionnaire.code, answers: payload },
      {
        onSuccess: () => {
          setAnswers({})
          setMessage({ ok: true, text: t('questionnaires.submitted') })
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

  return (
    <Paper withBorder p="md">
      <form onSubmit={onSubmit}>
        <Stack gap="md">
          <div>
            <Title order={4}>{questionnaire.name}</Title>
            <Text size="sm" c="dimmed">
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
          <Group>
            <Button type="submit" loading={submit.isPending} disabled={!complete}>
              {t('questionnaires.submit')}
            </Button>
          </Group>
        </Stack>
      </form>
    </Paper>
  )
}
