import { ArrowsClockwise, MinusCircle } from '@phosphor-icons/react'
import type { TFunction } from 'i18next'
import { useTranslation } from 'react-i18next'

import { type AlertFeedbackNotice, type PlanNotice, usePlanNotices } from '../../api/tasks'
import { formatClock, formatDate, todayInput } from '../../format'

function noticeText(t: TFunction, n: PlanNotice): string {
  const date = formatDate(todayInput(new Date(n.changed_at)))
  if (n.kind === 'revoked') return t('tasks.notices.revoked', { date })
  const freq = t(`doctor.plan.freq.${n.new_frequency}`, { count: n.new_interval_days ?? 0 })
  const time = n.new_due_time ? formatClock(n.new_due_time) : ''
  // A még el nem kezdett új előírásnál a kezdete, különben „mostantól".
  return n.new_start_date && n.new_start_date > todayInput()
    ? t('tasks.notices.modifiedFrom', { date, start: formatDate(n.new_start_date), freq, time })
    : t('tasks.notices.modified', { date, freq, time })
}

const initials = (name: string) =>
  name
    .replace(/^Dr\.\s*/, '')
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0])
    .join('')
    .toUpperCase()

/** Miről szólt a lezárt riasztás, a beteg szavaival: „vérnyomás-riasztás" vagy
 * „„Közérzet” kérdőív-riasztás" (a szerver a szabály célpontját adja). */
function feedbackAbout(t: TFunction, isMeasurement: boolean, n: AlertFeedbackNotice): string {
  if (!isMeasurement) return t('tasks.feedback.aboutQuestionnaire', { name: n.target_name })
  const type = t(`measurementTypes.${n.target_code}`, { defaultValue: n.target_name })
  return t('tasks.feedback.aboutMeasurement', { type: type.toLocaleLowerCase() })
}

/** Az orvos visszajelzése egy riasztás lezárásakor (M3, A6; felületterv .msg
 * kártya): ki írta, melyik riasztás lezárásakor, mikor, és a szöveg. Egyirányú. */
function FeedbackCard({ n }: { n: AlertFeedbackNotice }) {
  const { t, i18n } = useTranslation()
  // A célpont méréstípus, ha ismert méréstípus-kód (az elmaradt adat szabálya
  // kérdőívre is vonatkozhat, ezért nem a szabály típusa dönt).
  const isMeasurement =
    n.rule_type !== 'questionnaire' && i18n.exists(`measurementTypes.${n.target_code}`)
  const date = formatDate(todayInput(new Date(n.changed_at)))
  return (
    <article className="pulse-msg">
      <span className="pulse-avatar" aria-hidden="true">
        {initials(n.doctor_name)}
      </span>
      <div>
        <p className="from">
          <span className="name">{n.doctor_name}</span>
          <span>
            {t('tasks.feedback.from', { about: feedbackAbout(t, isMeasurement, n), date })}
          </span>
        </p>
        <blockquote>{n.text}</blockquote>
      </div>
    </article>
  )
}

/** A beteg jelzései a teendők fölött: az orvos visszajelzései a riasztások
 * lezárásakor (M3, A6), és rövid jelzés, ha az orvos az utóbbi napokban visszavont
 * vagy módosított egy előírást, az indoklásával (a hallgató döntése, 2026-11-01). A
 * szerver egy listában, a kind szerint megkülönböztetve adja; ha nincs, nem jelenik meg. */
export function PlanNotices({ patientId }: { patientId: string }) {
  const { t } = useTranslation()
  const notices = usePlanNotices(patientId)
  const all = notices.data ?? []
  const feedback = all.filter((n): n is AlertFeedbackNotice => n.kind === 'alert_feedback')
  const plan = all.filter((n): n is PlanNotice => n.kind !== 'alert_feedback')
  return (
    <>
      {feedback.length > 0 && (
        <section className="pulse-msgs" aria-label={t('tasks.feedback.label')}>
          {feedback.map((n) => (
            <FeedbackCard key={`${n.alert_id}-${n.changed_at}`} n={n} />
          ))}
        </section>
      )}
      {plan.length > 0 && (
        <section className="pulse-notices" aria-label={t('tasks.notices.label')}>
          {plan.map((n) => {
            const Glyph = n.kind === 'revoked' ? MinusCircle : ArrowsClockwise
            const title =
              n.target_kind === 'measurement'
                ? t(`measurementTypes.${n.code}`, { defaultValue: n.name })
                : n.name
            return (
              <article
                key={`${n.target_kind}-${n.code}-${n.changed_at}`}
                className="pulse-notice"
                data-kind={n.kind}
              >
                <Glyph size={22} aria-hidden="true" />
                <div>
                  <p className="nt">
                    <b>{title}</b>
                    <span className="tm">
                      {t(`tasks.frequency.${n.frequency}`, { count: n.interval_days ?? 0 })}
                    </span>
                  </p>
                  <p className="nx">{noticeText(t, n)}</p>
                  {n.note && <p className="nn">{t('tasks.notices.note', { note: n.note })}</p>}
                </div>
              </article>
            )
          })}
        </section>
      )}
    </>
  )
}
