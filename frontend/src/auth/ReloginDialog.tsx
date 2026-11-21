import { Alert, Button, Modal, PasswordInput, TextInput } from '@mantine/core'
import { useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { type CurrentUser, login } from '../api/auth'
import { ApiError, apiGetWithToken, expireSession, setReloginHandler } from '../api/client'
import './relogin.css'
import { setToken } from './token'

/** Újrabelépés helyben, ha a munkamenet lejárt (M3, A8 D3; a hallgató döntése).
 *
 * Az API-kliens 401-nél (ha volt token) nem tölti újra az oldalt, hanem ezt az
 * ablakot nyitja meg; az oldal és a félig kitöltött űrlap a háttérben marad. Az
 * e-mail-cím rögzített: csak UGYANAZ a felhasználó léphet vissza így. Ha a belépés
 * más felhasználót adna, vagy a felhasználó a Kijelentkezést választja, a régi
 * útvonal fut (vissza a belépőoldalra, újratöltéssel), így más fiók adatai nem
 * maradnak a képernyőn. Sikeres belépés után a felhasználó újra megnyomja a
 * Mentést; a közben megakadt lekérdezések maguktól lefutnak. */
// Az Esc ne zárja be az alatta nyitott ablakot (pl. a riasztás lezárását): a Mantine
// ablakai az Esc-et az ablakon (window) figyelik, és kihagyják, ha a lenyomás célelemén
// ez a jelölés van. Az újrabelépő ablak fókuszcsapdája miatt a cél mindig az ablak
// tartalma vagy egy mezője, gombja, ezért mindegyik megkapja.
const STOP_ESCAPE = { 'data-mantine-stop-propagation': 'true' } as const

export function ReloginDialog({ user }: { user: CurrentUser }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [opened, setOpened] = useState(false)
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  // A várakozó lekérdezések közös ígérete: az újrabelépéskor teljesül.
  const waiting = useRef<{
    promise: Promise<void>
    resolve: () => void
    reject: (error: unknown) => void
  } | null>(null)

  useEffect(() => {
    const unregister = setReloginHandler(() => {
      if (!waiting.current) {
        let resolve = () => {}
        let reject: (error: unknown) => void = () => {}
        const promise = new Promise<void>((res, rej) => {
          resolve = res
          reject = rej
        })
        waiting.current = { promise, resolve, reject }
        setPassword('')
        setError(null)
        setOpened(true)
      }
      return waiting.current.promise
    })
    return () => {
      unregister()
      // Ha az ablak lebomlik (pl. kijelentkezés), a várakozó lekérdezések ne
      // maradjanak örökre folyamatban: a 401-es hibával zárulnak.
      waiting.current?.reject(new ApiError(401, '401 Unauthorized'))
      waiting.current = null
    }
  }, [])

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      const token = await login(user.email, password)
      // Az új tokent csak az ellenőrzés után tesszük a tárolóba.
      const me = await apiGetWithToken<CurrentUser>('/auth/me', token)
      if (me.id !== user.id) {
        expireSession()
        return
      }
      setToken(token)
      setOpened(false)
      setPassword('')
      waiting.current?.resolve()
      waiting.current = null
      // A várakozó lekérdezések maguktól újrafutnak; itt csak a hibaállapotúakat
      // frissítjük. Mindent nem: a kérdőívszerkesztő szándékosan nem kérdez le újra
      // (a verziószámhoz kötött vázlat elveszne, ha közben más orvos mentett).
      void queryClient.invalidateQueries({ predicate: (q) => q.state.status === 'error' })
    } catch (err) {
      // Az e-mail-cím rögzített, ezért a 401 (és a 422) csak a jelszó hibája lehet.
      const rejected = err instanceof ApiError && (err.status === 401 || err.status === 422)
      setError(t(rejected ? 'session.invalidPassword' : 'errors.unavailable'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      opened={opened}
      onClose={() => {}}
      title={t('session.title')}
      centered
      size={440}
      zIndex={1000}
      withCloseButton={false}
      closeOnClickOutside={false}
      closeOnEscape={false}
      // A háttér (oldalsáv és fejléc is) elmosva és sötétítve: a betegadat az ablak
      // mögött ne legyen olvasható (a hallgató döntése). Az átfedés teljes képernyős,
      // és a zIndex miatt minden más réteg fölött van.
      overlayProps={{ backgroundOpacity: 0.6, blur: 14 }}
      classNames={{
        content: 'pulse-relogin',
        header: 'pulse-relogin-head',
        title: 'pulse-relogin-title',
        body: 'pulse-relogin-body',
      }}
      attributes={{ content: STOP_ESCAPE }}
    >
      <form className="pulse-relogin-form" onSubmit={submit} noValidate>
        <p className="pulse-relogin-text">{t('session.text')}</p>
        <TextInput
          label={t('login.email')}
          type="email"
          autoComplete="username"
          value={user.email}
          readOnly
          {...STOP_ESCAPE}
        />
        <PasswordInput
          label={t('login.password')}
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.currentTarget.value)}
          visibilityToggleButtonProps={STOP_ESCAPE}
          data-autofocus
          {...STOP_ESCAPE}
        />
        {error && (
          <Alert color="red" role="alert">
            {error}
          </Alert>
        )}
        <div className="pulse-relogin-foot">
          <Button variant="subtle" color="gray" onClick={expireSession} {...STOP_ESCAPE}>
            {t('layout.logout')}
          </Button>
          <Button type="submit" loading={submitting} {...STOP_ESCAPE}>
            {t('login.submit')}
          </Button>
        </div>
      </form>
    </Modal>
  )
}
