import type { PatientStatus } from '../api/patients'

// Felületterv, 2026-10-30: a státusz teli kör / teli címke a saját színében, fehér
// jellel és szóval. A színek fehér jelhez mérve (kontraszt, színtévesztő-szimuláció);
// a piros és a zöld színtévesztővel összemosódhat, ezért mindig ikon és szó együtt.
export const STATUS_COLOR: Record<PatientStatus, string> = {
  severe: 'var(--pulse-severe)',
  attention: 'var(--pulse-warn)',
  no_data: 'var(--pulse-nodata)',
  handled: 'var(--pulse-handled)',
  ok: 'var(--pulse-ok)',
}

// A teli címke háttere: a Figyelem borostyánja itt sötétebb, hogy a fehér felirat
// olvasható legyen (4,6:1; az ikon borostyánján csak 3,3:1).
export const STATUS_PILL: Record<PatientStatus, string> = {
  ...STATUS_COLOR,
  attention: 'var(--pulse-warn-pill)',
}
