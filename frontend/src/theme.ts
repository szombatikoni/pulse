import { createTheme, type MantineColorsTuple } from '@mantine/core'

// Piros akcentus; a 6. árnyalat az alapszín (#e5484d).
const pulseRed: MantineColorsTuple = [
  '#ffeaeb',
  '#fdd4d5',
  '#f6a7a9',
  '#f0777b',
  '#eb5a5e',
  '#e84f54',
  '#e5484d',
  '#cb393e',
  '#b53136',
  '#9e262c',
]

// Sötét skála a státuszterv színeiből (docs/design/statusz_javaslat.html).
// A Mantine sötét témában: 0 = szöveg, 2 = másodlagos szöveg, 4 = keret,
// 6 = mezők és gombok háttere, 7 = oldalháttér.
// 2026-10-17: semleges (nem kékes) szürke skála, a megszokott sötét
// fejlesztői felületekhez hasonló árnyalatokkal; a háttér nem majdnem fekete,
// a másodlagos szöveg kontrasztosabb.
const dark: MantineColorsTuple = [
  '#f3f2f1',
  '#c8c6c4',
  '#a19f9d',
  '#797775',
  '#484644',
  '#3b3a39',
  '#323130',
  '#252423',
  '#201f1e',
  '#1b1a19',
]

const fontFamily = "'Inter Variable', system-ui, sans-serif"

export const theme = createTheme({
  primaryColor: 'pulseRed',
  primaryShade: 6,
  colors: { pulseRed, dark },
  defaultRadius: 0,
  fontFamily,
  headings: { fontFamily },
})
