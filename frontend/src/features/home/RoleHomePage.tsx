import { Stack, Text, Title } from '@mantine/core'
import { useTranslation } from 'react-i18next'

import type { Role } from '../../api/auth'

/** Ideiglenes kezdőoldal szerepkörönként; a tartalom a mérés- és a
 * kérdőív-folyamattal érkezik. */
export function RoleHomePage({ role }: { role: Role }) {
  const { t } = useTranslation()
  return (
    <Stack gap="xs">
      <Title order={2}>{t(`home.${role}.title`)}</Title>
      <Text c="dimmed">{t(`home.${role}.placeholder`)}</Text>
    </Stack>
  )
}
