import { Alert, Button, Modal, PasswordInput, TextInput } from '@mantine/core'
import { useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { type CurrentUser, login } from '../api/auth'
import {
  accountDisabled,
  ApiError,
  apiGetWithToken,
  expireSession,
  setReloginHandler,
  showAccountDisabled,
} from '../api/client'
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
// ez a jelölés van. A cél általában az ablak tartalma vagy egy mezője, gombja, ezért
// ezek megkapják; ha a fókusz mégis a <body>-ra kerül (pl. kattintás az elmosott
// háttérre, vagy a betöltés alatt letiltott gomb után), a jelölés nyitott ablaknál a
// <body>-n is ott van (lásd a hatást lent), és sikertelen belépés után a fókusz
// visszakerül a jelszómezőre.
const STOP_ESCAPE_ATTR = 'data-mantine-stop-propagation'
const STOP_ESCAPE = { [STOP_ESCAPE_ATTR]: 'true' } as const

export function ReloginDialog({ user }: { user: CurrentUser }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [opened, setOpened] = useState(false)
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const passwordRef = useRef<HTMLInputElement>(null)
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
        // Ha az ablak lebomlik, és épp nincs várakozó lekérdezés, az elutasítás ne
        // legyen kezeletlen (a várakozók a saját águkon továbbra is megkapják).
        promise.catch(() => {})
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

  // Nyitott ablaknál a <body> is megkapja az Esc-jelölést (lásd fent); bezáráskor és
  // lebontáskor lekerül, ha mi tettük fel.
  useEffect(() => {
    if (!opened) return
    const body = document.body
    if (body.getAttribute(STOP_ESCAPE_ATTR) === 'true') return
    body.setAttribute(STOP_ESCAPE_ATTR, 'true')
    return () => body.removeAttribute(STOP_ESCAPE_ATTR)
  }, [opened])

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
      // A fiókot közben letiltották (M3, A1): a szerver ezt csak helyes jelszóra
      // árulja el. Itt nincs mit újra próbálni: a belépőoldalra a letiltás üzenetével,
      // újratöltéssel (a régi adatok nem maradnak a háttérben).
      if (err instanceof ApiError && accountDisabled(err)) {
        showAccountDisabled()
        return
      }
      // Az e-mail-cím rögzített, ezért a 401 (és a 422) csak a jelszó hibája lehet.
      const rejected = err instanceof ApiError && (err.status === 401 || err.status === 422)
      setError(t(rejected ? 'session.invalidPassword' : 'errors.unavailable'))
      // A fókusz a jelszómezőre (a betöltés alatt letiltott gomb után a <body>-n
      // maradna).
      passwordRef.current?.focus()
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
          ref={passwordRef}
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
