import { ArrowsClockwise, MinusCircle } from '@phosphor-icons/react'
import type { TFunction } from 'i18next'
import { useTranslation } from 'react-i18next'

import { type PlanNotice, usePlanNotices } from '../../api/tasks'
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

/** Rövid jelzés a teendők fölött, ha az orvos az utóbbi napokban visszavont vagy
 * módosított egy előírást, az indoklásával (a hallgató döntése, 2026-11-01). A
 * szerver az előírás-adatokból számolja; ha nincs ilyen, nem jelenik meg. */
export function PlanNotices({ patientId }: { patientId: string }) {
  const { t } = useTranslation()
  const notices = usePlanNotices(patientId)
  if (!notices.data || notices.data.length === 0) return null
  return (
    <section className="pulse-notices" aria-label={t('tasks.notices.label')}>
      {notices.data.map((n) => {
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
  )
}
