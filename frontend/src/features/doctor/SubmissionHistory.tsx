import { Loader, Text } from '@mantine/core'
import { useTranslation } from 'react-i18next'

import { usePatientSubmissions } from '../../api/questionnaires'
import { StatusIcon } from '../../components/StatusLabel'
import { formatDateTime } from '../../format'
import { BAND_STATUS } from './charts/scale'
import './patientDetail.css'

const BAR_CLASS: Record<string, string> = { warning: 'warn', critical: 'crit' }

/** A beteg kérdőív-kitöltései (csak az orvos látja), kártyában: a pontszám sávként
 * a maximumhoz képest, a sáv jellel és szóval; a sorra kattintva a válaszok és a
 * kérdésenkénti pontok. */
export function SubmissionHistory({ patientId }: { patientId: string }) {
  const { t } = useTranslation()
  const submissions = usePatientSubmissions(patientId)
  const list = submissions.data ?? []
  // A fejlécben a kérdőív neve és verziója, ha mind ugyanaz (a demóban: Közérzet).
  const kinds = [
    ...new Set(
      list.map(
        (s) =>
          `${s.questionnaire_name} · ${t('questionnaires.version', { version: s.version_no })}`,
      ),
    ),
  ]

  return (
    <section className="pd-card" aria-labelledby="pd-h-subs">
      <div className="pd-card-head">
        <div className="left">
          <h2 className="pd-h-card" id="pd-h-subs">
            {t('doctor.submissionsTitle')}
          </h2>
          {list.length > 0 && (
            <span className="pd-meta">
              {kinds.length === 1 ? `${kinds[0]} · ` : ''}
              {t('doctor.detail.clickForAnswers')}
            </span>
          )}
        </div>
      </div>
      {submissions.isPending && <Loader size="sm" />}
      {submissions.isError && <Text c="red">{t('errors.unavailable')}</Text>}
      {submissions.isSuccess && list.length === 0 && (
        <p className="pd-muted">{t('questionnaires.empty')}</p>
      )}
      {list.length > 0 && (
        <div className="pd-subs">
          {list.map((s) => {
            const share = s.max_score ? (s.total_score / s.max_score) * 100 : 0
            const band = t(`questionnaires.bands.${s.band}`, { defaultValue: s.band })
            return (
              <details key={s.id} className="pd-sub">
                <summary>
                  <span className="when">{formatDateTime(s.submitted_at)}</span>
                  <span className="pd-scorebar" aria-hidden="true">
                    <i
                      className={BAR_CLASS[s.band] ?? ''}
                      style={{ width: `${share.toFixed(1)}%` }}
                    />
                  </span>
                  <span className="score">
                    {s.total_score}/{s.max_score}
                  </span>
                  <span className="band">
                    <StatusIcon status={BAND_STATUS[s.band] ?? 'ok'} size={14} />
                    {band}
                  </span>
                  {kinds.length > 1 && (
                    <span className="name">
                      {s.questionnaire_name} ·{' '}
                      {t('questionnaires.version', { version: s.version_no })}
                    </span>
                  )}
                </summary>
                <ol className="pd-answers" aria-label={t('doctor.answers')}>
                  {s.answers.map((a) => (
                    <li key={a.question_id}>
                      <span>
                        {a.order_no}. {a.text}
                      </span>
                      <span className="a">
                        {a.label}{' '}
                        <span className="pd-muted">
                          {t('doctor.detail.answerPoints', { score: a.score })}
                        </span>
                      </span>
                    </li>
                  ))}
                </ol>
              </details>
            )
          })}
        </div>
      )}
    </section>
  )
}
