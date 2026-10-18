import { Alert, Center, Loader } from '@mantine/core'
import { useTranslation } from 'react-i18next'
import { Navigate, Outlet, useLocation } from 'react-router'

import { HOME_BY_ROLE, type Role, useCurrentUser } from '../api/auth'
import { AppLayout } from '../components/AppLayout'
import { getToken } from './token'

/** Védett útvonalcsoport: csak bejelentkezve, és csak a megadott szerepkörrel.
 * A valódi védelem a szerveren van (minden végpont ellenőriz); ez csak azt
 * dönti el, melyik oldalt mutassuk. */
export function RequireAuth({ role }: { role: Role }) {
  const { t } = useTranslation()
  const location = useLocation()
  const me = useCurrentUser()

  if (getToken() === null) {
    const next = encodeURIComponent(location.pathname + location.search)
    return <Navigate to={`/login?next=${next}`} replace />
  }
  if (me.isPending) {
    return (
      <Center h="100vh">
        <Loader />
      </Center>
    )
  }
  if (me.isError) {
    // A lejárt munkamenetet (401) az API-kliens már kezeli; ide csak más hiba jut.
    return (
      <Center h="100vh">
        <Alert color="red">{t('errors.unavailable')}</Alert>
      </Center>
    )
  }
  if (me.data.role !== role) {
    return <Navigate to={HOME_BY_ROLE[me.data.role]} replace />
  }
  return (
    <AppLayout user={me.data}>
      <Outlet />
    </AppLayout>
  )
}

/** A gyökéroldal: bejelentkezve a saját kezdőoldalra, különben a belépésre visz. */
export function RootRedirect() {
  const { t } = useTranslation()
  const me = useCurrentUser()
  if (getToken() === null) return <Navigate to="/login" replace />
  if (me.isPending) {
    return (
      <Center h="100vh">
        <Loader />
      </Center>
    )
  }
  if (me.isError) {
    // NEM a belépőoldalra irányítunk: a token megvan, ezért a belépőoldal
    // visszaküldene ide, és végtelen kör lenne (független átnézés lelete). A
    // lejárt munkamenetet (401) az API-kliens már kezeli; ide csak más hiba jut.
    return (
      <Center h="100vh">
        <Alert color="red">{t('errors.unavailable')}</Alert>
      </Center>
    )
  }
  return <Navigate to={HOME_BY_ROLE[me.data.role]} replace />
}
