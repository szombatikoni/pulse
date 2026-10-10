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
const dark: MantineColorsTuple = [
  '#e8eaed',
  '#b4b9c1',
  '#7d848f',
  '#5c636e',
  '#2c313b',
  '#262a32',
  '#1e222a',
  '#101216',
  '#0b0d10',
  '#07080a',
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
