import {
  Alert,
  Button,
  Center,
  Paper,
  PasswordInput,
  Stack,
  Text,
  TextInput,
  Title,
} from '@mantine/core'
import { useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Navigate, useNavigate, useSearchParams } from 'react-router'

import { currentUserQuery, HOME_BY_ROLE, login } from '../../api/auth'
import { ApiError } from '../../api/client'
import { getToken, setToken } from '../../auth/token'

/** Csak az oldalon belüli, relatív visszatérési útvonalat fogadjuk el, hogy a
 * belépőoldal ne irányíthasson át idegen webhelyre (open redirect). */
function safeNext(value: string | null): string | null {
  if (!value || !value.startsWith('/') || value.startsWith('//') || value.startsWith('/login')) {
    return null
  }
  return value
}

export function LoginPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [params] = useSearchParams()
  const expired = params.get('expired') === '1'
  const next = safeNext(params.get('next'))

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  // Aki már be van jelentkezve, annak nem kell újra belépnie.
  if (getToken() !== null && !expired) return <Navigate to="/" replace />

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      setToken(await login(email, password))
      const me = await queryClient.fetchQuery(currentUserQuery)
      navigate(next ?? HOME_BY_ROLE[me.role], { replace: true })
    } catch (err) {
      const rejected = err instanceof ApiError && (err.status === 401 || err.status === 422)
      setError(t(rejected ? 'login.invalid' : 'errors.unavailable'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Center mih="100vh" p="md">
      <Stack w={360} gap="md">
        <div>
          <Title order={1} c="pulseRed">
            PULSE
          </Title>
          <Text c="dimmed">{t('app.tagline')}</Text>
        </div>

        <Paper withBorder p="lg">
          <form onSubmit={submit}>
            <Stack gap="sm">
              {expired && <Alert color="yellow">{t('login.expired')}</Alert>}
              {error && <Alert color="red">{error}</Alert>}
              <TextInput
                label={t('login.email')}
                type="email"
                autoComplete="username"
                required
                value={email}
                onChange={(e) => setEmail(e.currentTarget.value)}
              />
              <PasswordInput
                label={t('login.password')}
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.currentTarget.value)}
              />
              <Button type="submit" loading={submitting} mt="xs">
                {t('login.submit')}
              </Button>
            </Stack>
          </form>
        </Paper>

        <Text size="xs" c="dimmed">
          {t('app.disclaimer')}
        </Text>
      </Stack>
    </Center>
  )
}
