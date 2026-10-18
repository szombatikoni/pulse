import { Loader, Text } from '@mantine/core'
import { useTranslation } from 'react-i18next'

import { usePatientSubmissions } from '../../api/questionnaires'
import { formatDateTime } from '../../format'

const BAND_COLOR: Record<string, string> = {
  normal: 'var(--pulse-ok)',
  warning: 'var(--pulse-warn)',
  critical: 'var(--pulse-severe)',
}

/** A beteg kérdőív-kitöltései (csak az orvos látja): a pontszám sávként a maximumhoz
 * képest, a sáv neve; a sorra kattintva a válaszok és a kérdésenkénti pontok. */
export function SubmissionHistory({ patientId }: { patientId: string }) {
  const { t } = useTranslation()
  const submissions = usePatientSubmissions(patientId)

  if (submissions.isPending) return <Loader size="sm" />
  if (submissions.isError) return <Text c="red">{t('errors.unavailable')}</Text>
  if (submissions.data.length === 0) return <Text c="dimmed">{t('questionnaires.empty')}</Text>

  return (
    <div className="pulse-subs">
      {submissions.data.map((s) => {
        const share = s.max_score ? (s.total_score / s.max_score) * 100 : 0
        const band = t(`questionnaires.bands.${s.band}`, { defaultValue: s.band })
        return (
          <details key={s.id}>
            <summary>
              <span className="when">{formatDateTime(s.submitted_at)}</span>
              <span className="name">
                {s.questionnaire_name}{' '}
                <Text span size="xs" c="dimmed">
                  {t('questionnaires.version', { version: s.version_no })}
                </Text>
              </span>
              <span className="bar" aria-hidden="true">
                <i style={{ width: `${share.toFixed(1)}%` }} />
              </span>
              <span className="score">
                {s.total_score}/{s.max_score}
              </span>
              <span className="band" style={{ color: BAND_COLOR[s.band] }}>
                {band}
              </span>
            </summary>
            <ol className="answers" aria-label={t('doctor.answers')}>
              {s.answers.map((a) => (
                <li key={a.question_id}>
                  <span>
                    {a.order_no}. {a.text}
                  </span>
                  <span className="a">
                    {a.label}{' '}
                    <Text span c="dimmed">
                      ({a.score})
                    </Text>
                  </span>
                </li>
              ))}
            </ol>
          </details>
        )
      })}
    </div>
  )
}
