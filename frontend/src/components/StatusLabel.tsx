import { Group, Text } from '@mantine/core'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import type { PatientStatus } from '../api/patients'
import { STATUS_COLOR } from './statusColors'

const INK = '#2b2a29' // az ikonon belüli jel színe (a kártyák háttere, index.css --pulse-card)

const ICONS: Record<PatientStatus, ReactNode> = {
  severe: (
    <>
      <path d="M8 1 15 8 8 15 1 8Z" fill="currentColor" />
      <path d="M8 4.2v4.6M8 11.4v.4" stroke={INK} strokeWidth="2.2" strokeLinecap="round" />
    </>
  ),
  attention: (
    <>
      <path d="M8 1.5 15 14H1Z" fill="currentColor" />
      <path d="M8 5.6v4M8 12v.3" stroke={INK} strokeWidth="2.1" strokeLinecap="round" />
    </>
  ),
  no_data: (
    <circle
      cx="8"
      cy="8"
      r="6"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeDasharray="2.6 2"
    />
  ),
  handled: (
    <>
      <circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <path
        d="M8 4.6V8l2.4 1.6"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
    </>
  ),
  ok: (
    <>
      <circle cx="8" cy="8" r="7" fill="currentColor" />
      <path
        d="m4.8 8.2 2.2 2.2 4.2-4.4"
        fill="none"
        stroke={INK}
        strokeWidth="2.1"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </>
  ),
}

export function StatusIcon({ status, size = 18 }: { status: PatientStatus; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      aria-hidden="true"
      style={{ color: STATUS_COLOR[status], flexShrink: 0 }}
    >
      {ICONS[status]}
    </svg>
  )
}

/** Státusz = színes ikon + egy szó, doboz nélkül; a szó a normál szövegszínű. */
export function StatusLabel({ status }: { status: PatientStatus }) {
  const { t } = useTranslation()
  const loud = status === 'severe' || status === 'attention'
  return (
    <Group gap={6} wrap="nowrap">
      <StatusIcon status={status} />
      <Text span size="sm" fw={loud ? 700 : 500}>
        {t(`status.${status}`)}
      </Text>
    </Group>
  )
}
