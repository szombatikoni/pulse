import { Stack, Text, Title } from '@mantine/core'
import { useTranslation } from 'react-i18next'

/** Ideiglenes kezdőoldal; már csak az adminé az (az admin-felület később jön). */
export function RoleHomePage({ role }: { role: 'admin' }) {
  const { t } = useTranslation()
  return (
    <Stack gap="xs">
      <Title order={2}>{t(`home.${role}.title`)}</Title>
      <Text c="dimmed">{t(`home.${role}.placeholder`)}</Text>
    </Stack>
  )
}
