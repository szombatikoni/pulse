import type { PatientStatus } from '../api/patients'

// A státuszterv színei (docs/design/statusz_javaslat.html; a hallgató
// jóváhagyta 2026-09-28; 2026-10-17-én a szürke háttérhez telítettebbre
// állítva, a hallgató kérésére). A színt mindig ikon és szó kíséri, így
// színtévesztővel és szürkeárnyalatban is megkülönböztethető.
export const STATUS_COLOR: Record<PatientStatus, string> = {
  severe: '#FF4545',
  attention: '#FFB020',
  no_data: '#B3B3B3',
  handled: '#4DA3FF',
  ok: '#2FCB4A',
}
