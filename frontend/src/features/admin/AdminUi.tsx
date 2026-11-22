import { Modal } from '@mantine/core'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { adminErrorCode } from '../../api/admin'
import { StatusIcon } from '../../components/StatusLabel'

/** Az admin ablakai egységesen (az adatlap lezárás-ablakának mintájára). */
export function AdminModal({
  opened,
  onClose,
  title,
  children,
}: {
  opened: boolean
  onClose: () => void
  title: string
  children: ReactNode
}) {
  const { t } = useTranslation()
  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title={title}
      centered
      size={520}
      classNames={{
        content: 'pd-modal',
        header: 'pd-modal-head',
        title: 'pd-modal-title',
        body: 'pd-modal-body',
      }}
      overlayProps={{ backgroundOpacity: 0.6 }}
      closeButtonProps={{ 'aria-label': t('admin.closeDialog') }}
    >
      {children}
    </Modal>
  )
}

/** A szerver hibája a felhasználó nyelvén (a detail.code alapján). */
export function AdminErrorText({ error }: { error: unknown }) {
  const { t } = useTranslation()
  const code = adminErrorCode(error)
  return (
    <span className="pd-err" role="alert">
      <StatusIcon status="severe" size={14} />
      {t(`admin.errors.${code ?? 'generic'}`, { defaultValue: t('admin.errors.generic') })}
    </span>
  )
}

/** Állapot: pötty és szó (felületterv: „Aktív"; letiltva szürke pötty). */
export function ActiveBand({ active }: { active: boolean }) {
  const { t } = useTranslation()
  return (
    <span className="ad-band">
      <span className={active ? 'ad-dot' : 'ad-dot off'} aria-hidden="true" />
      {t(active ? 'admin.users.active' : 'account.disabled')}
    </span>
  )
}
