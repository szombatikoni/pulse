import { Alert, Button, PasswordInput, TextInput, Title } from '@mantine/core'
import { useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Navigate, useNavigate, useSearchParams } from 'react-router'

import { currentUserQuery, HOME_BY_ROLE, login, type Role } from '../../api/auth'
import { ApiError } from '../../api/client'
import { getToken, setToken } from '../../auth/token'
import './login.css'

// A bemutató fiókok (backend/seed): a gomb csak az e-mail-címet tölti ki, a jelszót nem.
const DEMO_ACCOUNTS: { role: Role; name: string; email: string }[] = [
  { role: 'doctor', name: 'Dr. Kovács Éva', email: 'dr.kovacs@pulse.example' },
  { role: 'patient', name: 'Tóth Mária', email: 'toth.maria@pulse.example' },
  { role: 'admin', name: 'Adminisztrátor', email: 'admin@pulse.example' },
]

const initials = (name: string) =>
  name
    .replace(/^Dr\.\s*/, '')
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0])
    .join('')
    .toUpperCase()

/** Csak az oldalon belüli, relatív visszatérési útvonalat fogadjuk el, hogy a
 * belépőoldal ne irányíthasson át idegen webhelyre (open redirect). */
function safeNext(value: string | null): string | null {
  if (!value || !value.startsWith('/') || value.startsWith('//') || value.startsWith('/login')) {
    return null
  }
  return value
}

/** Belépés, felületterv 2026-10-30: balra a márka (betűszó egy sorban), jobbra az űrlap. */
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
    <div className="lg">
      <section className="lg-brand">
        <div className="lg-hero">
          <h1 className="lg-word">PULSE</h1>
          <p className="lg-acro" lang="en">
            <b>P</b>atient <b>U</b>nderstanding through <b>L</b>imits, <b>S</b>ignals and <b>E</b>
            valuation
          </p>
          <p className="lg-tag">{t('app.tagline')}</p>
        </div>
      </section>

      <section className="lg-main">
        <form className="lg-card" onSubmit={submit}>
          <div className="lg-title">
            <Title order={2}>{t('login.title')}</Title>
            <p className="lg-meta">{t('login.subtitle')}</p>
          </div>
          {expired && <Alert color="yellow">{t('login.expired')}</Alert>}
          {error && <Alert color="red">{error}</Alert>}
          <TextInput
            label={t('login.email')}
            type="email"
            autoComplete="username"
            required
            size="md"
            value={email}
            onChange={(e) => setEmail(e.currentTarget.value)}
          />
          <PasswordInput
            label={t('login.password')}
            autoComplete="current-password"
            required
            size="md"
            value={password}
            onChange={(e) => setPassword(e.currentTarget.value)}
          />
          <Button type="submit" size="md" fullWidth loading={submitting}>
            {t('login.submit')}
          </Button>
          <div className="lg-demo">
            <span className="lg-demo-label">
              {t('login.demoAccounts')} <span className="lg-hint">{t('login.demoHint')}</span>
            </span>
            {DEMO_ACCOUNTS.map((a) => (
              <button key={a.email} type="button" onClick={() => setEmail(a.email)}>
                <span className="pulse-avatar" aria-hidden="true">
                  {initials(a.name)}
                </span>
                <span className="lg-who">
                  <b>{a.name}</b>
                  <span>{a.email}</span>
                </span>
                <span className="lg-chip">{t(`roles.${a.role}`)}</span>
              </button>
            ))}
          </div>
          <p className="lg-disclaimer">{t('app.disclaimer')}</p>
        </form>
      </section>
    </div>
  )
}
