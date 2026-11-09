import { AppShell, Box, Burger, UnstyledButton } from '@mantine/core'
import { useDisclosure } from '@mantine/hooks'
import {
  Bell,
  ChartLine,
  type Icon,
  House,
  ShieldCheck,
  SignOut,
  Users,
} from '@phosphor-icons/react'
import { useQueryClient } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { NavLink, useLocation, useNavigate } from 'react-router'

import { useDoctorAlerts } from '../api/alerts'
import { type CurrentUser, HOME_BY_ROLE, type Role } from '../api/auth'
import { useDoctorPatients } from '../api/patients'
import { clearToken } from '../auth/token'

type NavItem = {
  to: string
  label: string
  icon: Icon
  count?: number
  hot?: boolean
  /** Saját illesztés, ha az alapértelmezett (előtag szerinti) nem jó. */
  match?: (path: string) => boolean
}

/** A márkajel: teli akciószínű négyzet, benne a pulzusvonal; mellette a név serifben. */
export function Brand() {
  return (
    <span className="pulse-brand">
      <span className="pulse-brand-mark" aria-hidden="true">
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.1"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M3 12.5h3.7l2.3-5.6 3.8 11 2.5-7.1 1.4 1.7H21" />
        </svg>
      </span>
      <span className="pulse-brand-name">PULSE</span>
    </span>
  )
}

/** Orvosnál a menüpont mellett: hány beteg vár döntésre (Súlyos + Figyelem). */
function useDoctorNav(enabled: boolean): Pick<NavItem, 'count' | 'hot'> {
  const patients = useDoctorPatients({ enabled })
  const list = patients.data ?? []
  return {
    count: list.filter((p) => p.status === 'severe' || p.status === 'attention').length,
    hot: list.some((p) => p.status === 'severe'),
  }
}

/** A Riasztások menüpont mellett: hány nyitott riasztásnak nincs még felelőse
 * (felületterv: a felelős nélküli nyitottak száma). */
function useAlertsNav(enabled: boolean): Pick<NavItem, 'count'> {
  const alerts = useDoctorAlerts({ enabled })
  return { count: (alerts.data ?? []).filter((a) => !a.assigned_to).length }
}

const initials = (name: string) =>
  name
    .replace(/^Dr\.\s*/, '')
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0])
    .join('')
    .toUpperCase()

/** A bejelentkezett oldalak kerete: bal oldalsáv (telefonon lenyíló), a tartalom
 * legfeljebb 1240 px széles. Felületterv, 2026-10-30. */
export function AppLayout({ user, children }: { user: CurrentUser; children: ReactNode }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const queryClient = useQueryClient()
  const [opened, { toggle, close }] = useDisclosure()
  const doctorNav = useDoctorNav(user.role === 'doctor')
  const alertsNav = useAlertsNav(user.role === 'doctor')

  const logout = () => {
    clearToken()
    queryClient.clear() // az előző felhasználó adatai ne maradjanak a gyorsítótárban
    navigate('/login', { replace: true })
  }

  const items: Record<Role, NavItem[]> = {
    doctor: [
      {
        to: '/doctor',
        label: t('home.doctor.title'),
        icon: Users,
        ...doctorNav,
        // Az adatlap a Betegeimhez tartozik, a Riasztások oldal nem.
        match: (path) => path === '/doctor' || path.startsWith('/doctor/patients'),
      },
      { to: '/doctor/alerts', label: t('alerts.title'), icon: Bell, ...alertsNav },
    ],
    patient: [
      {
        to: '/patient',
        label: t('home.patient.title'),
        icon: House,
        // A kérdőív kitöltése a Teendőimhez tartozik, az Előzményeim nem.
        match: (path) => path === '/patient' || path.startsWith('/patient/questionnaires'),
      },
      { to: '/patient/history', label: t('home.patient.historyTitle'), icon: ChartLine },
    ],
    admin: [{ to: '/admin', label: t('home.admin.title'), icon: ShieldCheck }],
  }
  const name = user.name ?? user.email

  return (
    <AppShell
      header={{ height: { base: 58, md: 0 } }}
      navbar={{ width: 252, breakpoint: 'md', collapsed: { mobile: !opened } }}
      padding={{ base: 16, md: 40 }}
    >
      <AppShell.Header hiddenFrom="md" className="pulse-topbar">
        <Burger opened={opened} onClick={toggle} size="sm" aria-label={t('layout.openMenu')} />
        <Brand />
      </AppShell.Header>
      <AppShell.Navbar className="pulse-side">
        <NavLink to={HOME_BY_ROLE[user.role]} className="pulse-brand-link" onClick={close}>
          <Brand />
        </NavLink>
        <nav className="pulse-nav" aria-label={t('layout.nav')}>
          {items[user.role].map(({ to, label, icon: ItemIcon, count, hot, match }) => (
            <NavLink
              key={to}
              to={to}
              onClick={close}
              className={({ isActive }) => ((match ? match(pathname) : isActive) ? 'active' : '')}
            >
              <ItemIcon size={18} />
              <span>{label}</span>
              {!!count && <span className={hot ? 'pulse-count hot' : 'pulse-count'}>{count}</span>}
            </NavLink>
          ))}
        </nav>
        <div className="pulse-me">
          <span className="pulse-avatar">{initials(name)}</span>
          <span className="pulse-me-text">
            <span className="pulse-me-name">{name}</span>
            <span className="pulse-me-role">{t(`roles.${user.role}`)}</span>
          </span>
          <UnstyledButton
            className="pulse-ibtn"
            onClick={logout}
            aria-label={t('layout.logout')}
            title={t('layout.logout')}
          >
            <SignOut size={17} />
          </UnstyledButton>
        </div>
      </AppShell.Navbar>
      <AppShell.Main className="pulse-main">
        <Box maw={1240} mx="auto">
          {children}
        </Box>
      </AppShell.Main>
    </AppShell>
  )
}
