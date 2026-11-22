// Használhatósági kiegészítők (M3, A8) a felületen: az orvos megjegyzést ír a beteghez
// (a kártyán a szerzővel jelenik meg); a grafikon határvonala a szabálylistából jön,
// így egy még nem riasztott szabály vonala is látszik; lejárt munkamenetnél az
// újrabelépő ablak után a beírt szöveg megvan, és a mentés sikerül.
//
// Futási sorrend és adatfeltevések: a fájlnév szerint a k2_nice, az m2_folyamatok és
// az m3_a5_kerdoivszerkeszto után fut, frissen seedelt adatbázison (újrafuttatáshoz
// újra kell seedelni). Mindhárom teszt Kovács doktorral Molnár Katalin adatlapján
// dolgozik: őt a korábbi specek csak a betegoldalon nézik (k2_nice, olvasás), az
// orvosi listán Rendben, és nincs riasztása. A megjegyzés semmilyen státuszt, listát
// vagy riasztásszámot nem érint. Az új vérnyomás-szabály (szisztolés > 160, közepes)
// nem értékel visszamenőleg (api/rules.py), és ez a fájl Molnár Katalinnak mérést nem
// rögzít, így riasztás és státuszváltozás sem lesz belőle.
import { expect, test, type Page } from '@playwright/test'

const PASSWORD = 'pulse-demo-2026'
const DOCTOR = 'dr.kovacs@pulse.example'
const PATIENT = 'Molnár Katalin'

async function login(page: Page, email: string) {
  await page.goto('/login')
  await page.getByLabel('E-mail-cím').fill(email)
  await page.getByLabel('Jelszó', { exact: false }).first().fill(PASSWORD)
  await page.getByRole('button', { name: 'Belépés' }).click()
}

async function openPatient(page: Page) {
  await login(page, DOCTOR)
  await expect(page).toHaveURL(/\/doctor$/)
  await page.getByRole('link', { name: PATIENT }).click()
  await expect(page).toHaveURL(/\/doctor\/patients\//)
  await expect(page.getByRole('heading', { level: 1, name: PATIENT })).toBeVisible()
}

const notesCard = (page: Page) => page.getByRole('region', { name: 'Megjegyzések' })
const noteItems = (page: Page) => notesCard(page).getByRole('listitem')

test.describe.configure({ mode: 'serial' })

test('megjegyzés, orvos: a fejléc gombja megnyitja az űrlapot, a mentett megjegyzés a szerzővel látszik', async ({
  page,
}) => {
  await openPatient(page)
  const notes = notesCard(page)
  await expect(notes).toContainText('Még nincs megjegyzés.')

  // A fejléc „Megjegyzés” gombja a kártyához görget, és a szövegmezőre fókuszál.
  await page.getByRole('button', { name: 'Megjegyzés', exact: true }).click()
  const field = notes.getByRole('textbox', { name: 'Új megjegyzés' })
  await expect(field).toBeFocused()
  // Nyitott űrlap mellett a kártya „Új” gombja nem látszik (egy területen egy fő gomb).
  await expect(notes.getByRole('button', { name: 'Új', exact: true })).toHaveCount(0)

  // Üres szöveggel nem ment: a fókusz a mezőn marad, új megjegyzés nem jelenik meg.
  await notes.getByRole('button', { name: 'Mentés', exact: true }).click()
  await expect(field).toBeFocused()
  await expect(noteItems(page)).toHaveCount(0)

  await field.fill('Telefonon egyeztetve: a vérnyomása stabil, a gyógyszerelés marad.')
  await notes.getByRole('button', { name: 'Mentés', exact: true }).click()

  // Mentés után az űrlap bezárul, a megjegyzés a szerzővel és az időponttal látszik.
  await expect(field).toHaveCount(0)
  await expect(noteItems(page)).toHaveCount(1)
  await expect(noteItems(page).first()).toContainText(
    'Telefonon egyeztetve: a vérnyomása stabil, a gyógyszerelés marad.',
  )
  await expect(noteItems(page).first()).toContainText(/Dr\. Kovács Éva · \S/)
  // Csak hozzáírható: a megjegyzésnél nincs szerkesztő vagy törlő gomb.
  await expect(noteItems(page).first().getByRole('button')).toHaveCount(0)
  await expect(notes.getByRole('button', { name: 'Új', exact: true })).toBeVisible()
})

test('küszöbvonal, orvos: a még nem riasztott szabály határa is látszik a grafikonon', async ({
  page,
}) => {
  await openPatient(page)
  const bp = page.locator('main .pd-chart-card')
  const legend = bp.locator('.pd-legend')
  // A seed szabályai (küszöb: szisztolés > 180, súlyos; időablakos: > 140 / > 90,
  // közepes) Molnár Katalinnál soha nem riasztottak, a vonaluk mégis látszik.
  await expect(legend).toContainText('140/90, közepes határ')
  await expect(legend).toContainText('180, súlyos határ')
  await expect(bp.locator('text.thl').filter({ hasText: /^160$/ })).toHaveCount(0)

  // Új küszöbszabály a Szabályok fülön: szisztolés > 160, közepes.
  await page.getByRole('tab', { name: 'Szabályok' }).click()
  await expect(page).toHaveURL(/\?tab=rules$/)
  const rules = page.getByRole('region', { name: `${PATIENT} szabályai` })
  await rules.getByRole('button', { name: 'Új szabály' }).click()
  const picker = page.getByRole('complementary', { name: 'Milyen típusú szabály legyen?' })
  await picker.getByRole('button', { name: /^Küszöbszabály/ }).click()
  const editor = page.getByRole('complementary', { name: 'Új szabály' })
  await editor.getByLabel('Szisztolés felső határ').fill('160')
  await expect(editor.locator('.pd-preview')).toContainText(
    'Vérnyomás: Szisztolés > 160 Hgmm esetén közepes riasztás.',
  )
  await editor.getByRole('button', { name: 'Mentés 1. verzióként' }).click()
  await expect(rules).toContainText('Az új szabály elmentve.')
  await expect(
    rules.getByRole('article', { name: 'Vérnyomás: Szisztolés > 160 Hgmm' }),
  ).toBeVisible()

  // Vissza az Áttekintésre: az új határ vonala és felirata megjelenik, riasztás nélkül.
  await page.getByRole('tab', { name: 'Áttekintés' }).click()
  await expect(bp.locator('text.thl').filter({ hasText: /^160$/ })).toHaveCount(1)
  await expect(legend).toContainText('160/140/90, közepes határ')
  await expect(page.locator('main .pd-status')).toContainText('Rendben')
  await expect(page.locator('main article.pd-alert')).toHaveCount(0)
})

test('lejárt munkamenet: újrabelépés helyben, a beírt szöveg megmarad, és a mentés sikerül', async ({
  page,
}) => {
  await openPatient(page)
  const notes = notesCard(page)
  await notes.getByRole('button', { name: 'Új', exact: true }).click()
  const field = notes.getByRole('textbox', { name: 'Új megjegyzés' })
  const text = 'Kontroll két hét múlva, addig napi egy vérnyomásmérés.'
  await field.fill(text)
  // A piszkozat a fülváltást is túléli (a kártya közben lebomlik).
  await page.getByRole('tab', { name: 'Szabályok' }).click()
  await expect(field).toHaveCount(0)
  await page.getByRole('tab', { name: 'Áttekintés' }).click()
  await expect(field).toHaveValue(text)

  // A munkamenet „lejár”: a token érvénytelenre cserélődik (nem törlődik: törölt
  // tokennél a régi út, a belépőoldal jön). Feltevés: a csere és a Mentés között
  // nem indul lekérdezés (nincs időzített frissítés, és a lap fókusza sem változik);
  // ha indulna, az ablak a kattintás előtt nyílna meg.
  await page.evaluate(() => sessionStorage.setItem('pulse.accessToken', 'lejart-token'))
  const rejected = page.waitForResponse(
    (r) => r.url().endsWith('/notes') && r.request().method() === 'POST',
  )
  await notes.getByRole('button', { name: 'Mentés', exact: true }).click()
  expect((await rejected).status()).toBe(401)

  // Az oldal nem töltődik újra: az újrabelépő ablak jön, az e-mail-cím rögzített.
  const dialog = page.getByRole('dialog', { name: 'Lejárt a munkamenet' })
  await expect(dialog).toBeVisible()
  await expect(page).toHaveURL(/\/doctor\/patients\//)
  await expect(dialog.getByLabel('E-mail-cím')).toHaveValue(DOCTOR)
  await expect(dialog.getByLabel('E-mail-cím')).not.toBeEditable()

  // Hibás jelszó: az ablak marad, hibaüzenettel.
  await dialog.getByLabel('Jelszó', { exact: false }).first().fill('rossz-jelszo')
  await dialog.getByRole('button', { name: 'Belépés' }).click()
  await expect(dialog).toContainText('Hibás jelszó.')
  // Az Esc nem zárja be az ablakot.
  await page.keyboard.press('Escape')
  await expect(dialog).toBeVisible()

  await dialog.getByLabel('Jelszó', { exact: false }).first().fill(PASSWORD)
  await dialog.getByRole('button', { name: 'Belépés' }).click()
  await expect(dialog).toHaveCount(0)

  // A beírt szöveg megvan; a felhasználó újra megnyomja a Mentést, és most sikerül.
  await expect(field).toHaveValue(text)
  await notes.getByRole('button', { name: 'Mentés', exact: true }).click()
  await expect(field).toHaveCount(0)
  // A legújabb elöl: az új megjegyzés az első teszt megjegyzése fölött.
  await expect(noteItems(page)).toHaveCount(2)
  await expect(noteItems(page).first()).toContainText(text)
  await expect(noteItems(page).first()).toContainText(/Dr\. Kovács Éva · \S/)
  // Az új token a tárolóban van: az oldal újratöltése után is be van jelentkezve.
  await page.reload()
  await expect(page.getByRole('heading', { level: 1, name: PATIENT })).toBeVisible()
  await expect(noteItems(page)).toHaveCount(2)
})
