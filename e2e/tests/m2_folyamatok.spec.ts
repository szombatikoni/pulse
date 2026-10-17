// A két M2-folyamat a felületen végigvíve: a beteg mér és kérdőívet tölt ki,
// az orvos a priorizált listán és az adatlapon látja a jelzést, idegen beteg
// adatához pedig nem fér hozzá. Frissen seedelt adatbázist vár (backend/seed),
// és módosítja az adatokat (Tóth Mária új mérései és kitöltése).
import { expect, test, type Page } from '@playwright/test'

const PASSWORD = 'pulse-demo-2026'

async function login(page: Page, email: string) {
  await page.goto('/login')
  await page.getByLabel('E-mail-cím').fill(email)
  await page.getByLabel('Jelszó', { exact: false }).first().fill(PASSWORD)
  await page.getByRole('button', { name: 'Belépés' }).click()
}

// A táblázatsorok és az oldal szövege egy sorba fűzve, egyszerű szóközökkel.
const rowsText = async (page: Page) =>
  (await page.locator('tbody tr').allInnerTexts()).map((t) => t.replace(/\s+/g, ' ').trim())
const mainText = async (page: Page) =>
  (await page.locator('main').innerText()).replace(/\s+/g, ' ')

// A lépések egymásra épülnek: ha egy elbukik, a többi nem fut tovább.
test.describe.configure({ mode: 'serial' })

test('az orvosi lista minden M2-státuszt mutat, prioritás szerint, idegen beteg nélkül', async ({
  page,
}) => {
  await login(page, 'dr.kovacs@pulse.example')
  await expect(page).toHaveURL(/\/doctor$/)
  await page.locator('tbody tr').first().waitFor()
  const rows = await rowsText(page)

  expect(rows.map((r) => r.split(' ')[0])).toEqual(['Súlyos', 'Figyelem', 'Adathiány', 'Rendben'])
  expect(rows[0]).toContain('Varga Béla')
  expect(rows[1]).toContain('Szisztolés 152 Hgmm (> 140)')
  expect(rows.some((r) => r.includes('Tóth Mária'))).toBe(false)
})

test('az adatlapon a riasztás magyarázattal és eseménytörténettel látszik', async ({ page }) => {
  await login(page, 'dr.kovacs@pulse.example')
  await page.getByRole('link', { name: 'Szabó János' }).click()
  // Az adatlap részei (riasztások, kitöltések, mérések) külön kéréssel töltődnek
  // be, ezért az ellenőrzés addig vár, amíg a szöveg megjelenik (expect … toContainText).
  const main = page.locator('main')
  await expect(main).toContainText('Küszöbszabály, 1. verzió · közepes')
  await expect(main).toContainText('Feltétel: Szisztolés > 140 Hgmm vagy Diasztolés > 90 Hgmm')
  await expect(main).toContainText('Keletkezett')
  await expect(main).toContainText('Ismételt aktiválódás')
  await expect(main).toContainText(/86,4 kg|85,8 kg/)
})

test('idegen beteg adatlapja: a szerver 403-at ad, a felület jogosultsági hibát mutat', async ({
  browser,
  page,
}) => {
  // Tóth Mária azonosítója a saját orvosa (Nagy doktor) listájából.
  const nagy = await browser.newContext()
  const nagyPage = await nagy.newPage()
  await login(nagyPage, 'dr.nagy@pulse.example')
  await expect(nagyPage).toHaveURL(/\/doctor$/)
  const href = await nagyPage.getByRole('link', { name: 'Tóth Mária' }).getAttribute('href')
  await nagy.close()
  const tothId = href!.split('/').pop()

  await login(page, 'dr.kovacs@pulse.example')
  await expect(page).toHaveURL(/\/doctor$/)
  const response = page.waitForResponse((r) => r.url().includes(`/api/patients/${tothId}`))
  await page.goto(`/doctor/patients/${tothId}`)
  expect((await response).status()).toBe(403)
  await expect(page.getByText('Ehhez a beteghez nincs hozzáférésed.')).toBeVisible()
})

test('mérés-folyamat, beteg: vérnyomás és pulzus rögzítése', async ({ page }) => {
  await login(page, 'toth.maria@pulse.example')
  await expect(page).toHaveURL(/\/patient$/)
  await page.getByText('Új mérés').waitFor()

  // Többértékű mérés: a vérnyomás két értéke egy mérésben.
  await page.getByLabel('Szisztolés (Hgmm)').fill('165')
  await page.getByLabel('Diasztolés (Hgmm)').fill('98')
  await page.getByRole('button', { name: 'Mentés' }).click()
  await expect(page.getByText('A mérés elmentve.')).toBeVisible()
  await expect(page.getByRole('cell', { name: '165/98 Hgmm' }).first()).toBeVisible()

  // Egyértékű mérés: pulzus.
  await page.locator('input[aria-haspopup="listbox"]').click()
  await page.getByRole('option', { name: 'Pulzus' }).click()
  await page.getByLabel('Pulzus (/perc)').fill('72')
  await page.getByRole('button', { name: 'Mentés' }).click()
  await expect(page.getByRole('cell', { name: '72 /perc' }).first()).toBeVisible()
})

test('kérdőív-folyamat, beteg: kitöltés és beküldés, a pontszám nem látszik', async ({ page }) => {
  await login(page, 'toth.maria@pulse.example')
  await expect(page).toHaveURL(/\/patient$/)
  await page.getByText('Kitöltendő kérdőívek').waitFor()

  // Alvás 1, fáradtság 5, szédülés naponta: 4 + 4 + 5 = 13 pont (kritikus sáv).
  await page
    .getByRole('radiogroup', { name: 'Hogyan aludt az elmúlt éjszaka?' })
    .getByText('1', { exact: true })
    .click()
  await page
    .getByRole('radiogroup', { name: 'Mennyire fáradt ma?' })
    .getByText('5', { exact: true })
    .click()
  await page.getByLabel('Naponta').check()
  await page.getByRole('button', { name: 'Beküldés' }).click()
  await expect(page.getByText('Köszönjük, a kitöltés beérkezett.')).toBeVisible()

  const text = await mainText(page)
  expect(text).not.toMatch(/\d+\s*(\/\s*\d+\s*)?pont/)
  expect(text).not.toContain('sáv')
})

test('az orvos látja: Tóth Mária Súlyos, az okok között a kérdőív és a mérés', async ({
  page,
}) => {
  await login(page, 'dr.nagy@pulse.example')
  await expect(page).toHaveURL(/\/doctor$/)
  await page.locator('tbody tr').first().waitFor()
  const [first] = await rowsText(page)

  expect(first.startsWith('Súlyos')).toBe(true)
  // A kérdőív két szabálya (figyelmeztető és kritikus) ugyanazt az okot egyszer írja ki.
  expect(first.split('13/13 pont (kritikus sáv)')).toHaveLength(2)
  expect(first).toContain('Szisztolés 165 Hgmm (> 140)')

  await page.getByRole('link', { name: 'Tóth Mária' }).click()
  const main = page.locator('main')
  await expect(main).toContainText('Kérdőívszabály, 1. verzió')
  await expect(main).toContainText('pontszáma a(z) figyelmeztető vagy kritikus sávban')
  await expect(main).toContainText('13 / 13')
  await expect(main).toContainText('kritikus')
})
