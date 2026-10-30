import { createTheme, type MantineColorsTuple } from '@mantine/core'

// Felületterv, 2026-10-30 (docs/design/felulet_2026-10-30): csak sötét téma,
// meleg szürke rétegek; a fő gomb teli fehér, sötét felirattal.

// Az akciószín: törtfehér; a 6. árnyalat az alap (#f2ede6). A felirat színét az
// index.css adja (--on-accent), mert a Mantine alapból fehér szöveget tenne rá.
const paper: MantineColorsTuple = [
  '#ffffff',
  '#fdfcfa',
  '#faf8f5',
  '#f7f4ef',
  '#f5f1eb',
  '#f3efe8',
  '#f2ede6',
  '#ddd6cc',
  '#c8c0b5',
  '#b3ab9f',
]

// A Mantine sötét skálája a terv tokenjeiből: 0 = szöveg, 2 = halvány szöveg,
// 4 = keret, 5 = semleges gomb, 6 = kiemelt felület és mezők, 7 = oldalháttér,
// 8 = oldalsáv.
const dark: MantineColorsTuple = [
  '#f4efe9',
  '#d6cec5',
  '#aaa198',
  '#7b736a',
  '#413b36',
  '#3a3531',
  '#2a2724',
  '#1a1816',
  '#141210',
  '#100e0d',
]

const fontFamily = "'Instrument Sans Variable', system-ui, -apple-system, 'Segoe UI', sans-serif"
const serif = "'Source Serif 4 Variable', Georgia, 'Times New Roman', serif"

export const theme = createTheme({
  primaryColor: 'paper',
  primaryShade: 6,
  colors: { paper, dark },
  defaultRadius: 'md',
  radius: { xs: '4px', sm: '6px', md: '8px', lg: '12px', xl: '16px' },
  fontFamily,
  headings: { fontFamily: serif, fontWeight: '500' },
})
