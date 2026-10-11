import { AppShell, Button, Group, Text } from '@mantine/core'
import { useQueryClient } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'

import type { CurrentUser } from '../api/auth'
import { clearToken } from '../auth/token'

/** A bejelentkezett oldalak kerete: fejléc a felhasználó nevével és a kijelentkezéssel. */
export function AppLayout({ user, children }: { user: CurrentUser; children: ReactNode }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const logout = () => {
    clearToken()
    queryClient.clear() // az előző felhasználó adatai ne maradjanak a gyorsítótárban
    navigate('/login', { replace: true })
  }

  return (
    <AppShell header={{ height: 56 }} padding="md">
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between">
          <Text fw={700} c="pulseRed">
            PULSE
          </Text>
          <Group gap="md">
            <Text size="sm">
              {user.name ?? user.email}
              <Text span c="dimmed" size="sm">
                {' · '}
                {t(`roles.${user.role}`)}
              </Text>
            </Text>
            <Button variant="default" size="xs" onClick={logout}>
              {t('layout.logout')}
            </Button>
          </Group>
        </Group>
      </AppShell.Header>
      <AppShell.Main>{children}</AppShell.Main>
    </AppShell>
  )
}
