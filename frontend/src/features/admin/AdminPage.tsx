import { Button, Loader, Text, Title } from '@mantine/core'
import { Plus } from '@phosphor-icons/react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router'

import { useAdminUsers } from '../../api/admin'
import { useCurrentUser } from '../../api/auth'
import '../doctor/patientDetail.css'
import '../doctor/patientList.css'
import './admin.css'
import { AssignmentsTab } from './AssignmentsTab'
import { MeasurementTypesTab } from './MeasurementTypesTab'
import { CreateUserDialog, UsersTab } from './UsersTab'

// A felületterv két füle (Felhasználók, Összerendelések), és a méréstípusok
// rögzíthető tartománya (a hallgató döntése, 2026-11-16; a tervben nincs, a két
// fül mintájára).
const TABS = ['users', 'assignments', 'types'] as const
type Tab = (typeof TABS)[number]

/** Az admin-felület (M3, A1; F20), felületterv 2026-10-30: fejléc a felhasználók
 * számával és az „Új felhasználó" fő gombbal, alatta a fülek. */
export function AdminPage() {
  const { t } = useTranslation()
  const [search, setSearch] = useSearchParams()
  const users = useAdminUsers()
  const me = useCurrentUser()
  const [creating, setCreating] = useState(false)
  // A fül az URL-ben (?tab=assignments): frissítés és visszalépés után is megmarad.
  const tab: Tab = TABS.find((id) => id === search.get('tab')) ?? 'users'

  const all = users.data ?? []
  const count = (role: string) => all.filter((u) => u.role === role).length

  return (
    <div className="pl-page">
      <header className="pl-ph">
        <div className="pl-ph-text">
          <span className="pl-eyebrow">{t('admin.eyebrow')}</span>
          <Title order={1} className="pl-title">
            {t('admin.title')}
          </Title>
          {users.isSuccess && (
            <div className="pl-ph-meta">
              <span>{t('admin.count', { count: all.length })}</span>
              <span>
                {t('admin.byRole', {
                  doctors: count('doctor'),
                  patients: count('patient'),
                  admins: count('admin'),
                })}
              </span>
            </div>
          )}
        </div>
        <div className="pl-ph-actions">
          <Button leftSection={<Plus size={16} />} onClick={() => setCreating(true)}>
            {t('admin.create.open')}
          </Button>
        </div>
      </header>

      <div className="pd-tabs" role="tablist" aria-label={t('admin.tabsLabel')}>
        {TABS.map((id) => (
          <button
            key={id}
            type="button"
            role="tab"
            id={`ad-tab-${id}`}
            aria-selected={tab === id}
            aria-controls="ad-tabpanel"
            onClick={() => setSearch(id === 'users' ? {} : { tab: id })}
          >
            {t(`admin.tabs.${id}`)}
          </button>
        ))}
      </div>

      <div id="ad-tabpanel" role="tabpanel" aria-labelledby={`ad-tab-${tab}`}>
        {tab === 'types' ? (
          <MeasurementTypesTab />
        ) : users.isPending ? (
          <Loader />
        ) : users.isError ? (
          <Text c="red">{t('errors.unavailable')}</Text>
        ) : tab === 'assignments' ? (
          <AssignmentsTab users={all} />
        ) : (
          <UsersTab users={all} meId={me.data?.id} />
        )}
      </div>

      <CreateUserDialog opened={creating} onClose={() => setCreating(false)} />
    </div>
  )
}
