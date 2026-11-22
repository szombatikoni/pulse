import { Check, CloudSlash, type Icon, Siren, UserCheck, Warning } from '@phosphor-icons/react'
import { useTranslation } from 'react-i18next'

import type { PatientStatus } from '../api/patients'
import { STATUS_COLOR, STATUS_PILL } from './statusColors'

// A jel is különbözik, így szín nélkül is felismerhető: sziréna, figyelmeztető
// háromszög, áthúzott felhő (nincs friss adat), pipás alak (felelősnél), pipa.
const GLYPH: Record<PatientStatus, Icon> = {
  severe: Siren,
  attention: Warning,
  no_data: CloudSlash,
  handled: UserCheck,
  ok: Check,
}

/** Teli kör a státusz színében, benne fehér jel. */
export function StatusIcon({ status, size = 22 }: { status: PatientStatus; size?: number }) {
  const Glyph = GLYPH[status]
  return (
    <span
      className="pulse-si"
      aria-hidden="true"
      style={{ width: size, height: size, background: STATUS_COLOR[status] }}
    >
      <Glyph size={Math.round(size * 0.62)} weight="bold" />
    </span>
  )
}

/** Státusz = teli címke a saját színében: fehér jel és szó (felületterv, 2026-10-30). */
export function StatusLabel({ status }: { status: PatientStatus }) {
  const { t } = useTranslation()
  const Glyph = GLYPH[status]
  return (
    <span className="pulse-pill" style={{ background: STATUS_PILL[status] }}>
      <span className="pulse-pill-mark" aria-hidden="true" style={{ color: STATUS_PILL[status] }}>
        <Glyph size={12} weight="bold" />
      </span>
      {t(`status.${status}`)}
    </span>
  )
}
