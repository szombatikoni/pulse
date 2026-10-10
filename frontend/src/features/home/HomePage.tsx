import { Container, Group, Paper, Stack, Text, Title } from '@mantine/core'
import { useTranslation } from 'react-i18next'

import { useHealth } from '../../api/health'

// Ideiglenes kezdőoldal a projektvázhoz: igazolja, hogy a frontend eléri az
// API-t, az API pedig az adatbázist. A bejelentkezés elkészültével lecseréljük.
export function HomePage() {
  const { t } = useTranslation()
  const health = useHealth()

  const status = health.isPending
    ? { color: 'dimmed', text: t('health.checking') }
    : health.isSuccess
      ? { color: '#3FB950', text: t('health.ok') }
      : { color: '#F0595E', text: t('health.error') }

  return (
    <Container size="sm" py="xl">
      <Stack gap="lg">
        <div>
          <Title order={1}>PULSE</Title>
          <Text c="dimmed">{t('app.tagline')}</Text>
        </div>
        <Paper withBorder p="md">
          <Group justify="space-between">
            <Text fw={600}>{t('health.title')}</Text>
            <Text c={status.color}>{status.text}</Text>
          </Group>
        </Paper>
        <Text size="sm" c="dimmed">
          {t('app.disclaimer')}
        </Text>
      </Stack>
    </Container>
  )
}
