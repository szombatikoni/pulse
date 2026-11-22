import { Prohibit } from '@phosphor-icons/react'
import { useTranslation } from 'react-i18next'

import './disabledMark.css'

/** „Letiltva" jel a letiltott fiók mellett (M3, A1): jel és szó, semleges színnel,
 * hogy ne legyen összetéveszthető a beteg színes státuszcímkéjével. */
export function DisabledMark() {
  const { t } = useTranslation()
  return (
    <span className="pulse-disabled-mark">
      <Prohibit size={13} weight="bold" aria-hidden="true" />
      {t('account.disabled')}
    </span>
  )
}
