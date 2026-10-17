import type { PatientStatus } from '../api/patients'

// A státuszterv színei (docs/design/statusz_javaslat.html; a hallgató
// jóváhagyta 2026-09-28). A színt mindig ikon és szó kíséri, így színtévesztővel
// és szürkeárnyalatban is megkülönböztethető.
export const STATUS_COLOR: Record<PatientStatus, string> = {
  severe: '#F0595E',
  attention: '#E3B341',
  no_data: '#8B949E',
  handled: '#58A6FF',
  ok: '#3FB950',
}
