// A két M2-folyamat a felületen végigvíve: a beteg mér és kérdőívet tölt ki,
// az orvos a priorizált listán és az adatlapon látja a jelzést, idegen beteg
// adatához pedig nem fér hozzá. A végén az orvos a követési tervet szerkeszti
// (M3, A2). Frissen seedelt adatbázist vár (backend/seed), és módosítja az
// adatokat (Tóth Mária új mérései, kitöltése és testsúly-előírása).
import { expect, test, type Page } from '@playwright/test'

const PASSWORD = 'pulse-demo-2026'

async function login(page: Page, email: string) {
  await page.goto('/login')
  await page.getByLabel('E-mail-cím').fill(email)
  await page.getByLabel('Jelszó', { exact: false }).first().fill(PASSWORD)
  await page.getByRole('button', { name: 'Belépés' }).click()
}

// A beteglista sorai és az oldal szövege egy sorba fűzve, egyszerű szóközökkel.
const rowsText = async (page: Page) =>
  (await page.locator('.pulse-prow').allInnerTexts()).map((t) => t.replace(/\s+/g, ' ').trim())
// Az előzmények sorai (napokra bontott lista).
const history = (page: Page) => page.locator('.pulse-history li')
const mainText = async (page: Page) => (await page.locator('main').innerText()).replace(/\s+/g, ' ')

// A lépések egymásra épülnek: ha egy elbukik, a többi nem fut tovább.
test.describe.configure({ mode: 'serial' })

test('az orvosi lista minden M2-státuszt mutat, prioritás szerint, idegen beteg nélkül', async ({
  page,
}) => {
  await login(page, 'dr.kovacs@pulse.example')
  await expect(page).toHaveURL(/\/doctor$/)
  await page.locator('.pulse-prow').first().waitFor()
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
  await page.locator('.pulse-task').first().waitFor()

  // Előírás nélküli mérés: a teendők alatti gomb nyitja a típusválasztós űrlapot.
  await page.getByRole('button', { name: 'Előírás nélküli mérés' }).click()
  await page
    .locator('label')
    .filter({ hasText: /^Vérnyomás$/ })
    .click()

  // Elgépelt érték (400 Hgmm): a felület nem írja át csendben 300-ra, hanem a
  // szerver elutasítja, és a beteg látja, miért; a mező tartalma megmarad.
  await page.getByLabel('Szisztolés (Hgmm)').fill('400')
  await page.getByLabel('Diasztolés (Hgmm)').fill('98')
  await page.getByRole('button', { name: 'Mentés' }).click()
  await expect(
    page.getByText('A(z) Szisztolés értéke kívül esik a rögzíthető tartományon.'),
  ).toBeVisible()
  await expect(page.getByLabel('Szisztolés (Hgmm)')).toHaveValue('400')

  // Többértékű mérés: a vérnyomás két értéke egy mérésben. Mentés után az űrlap
  // bezárul, a nyugta a teendők alatt marad.
  await page.getByLabel('Szisztolés (Hgmm)').fill('165')
  await page.getByLabel('Diasztolés (Hgmm)').fill('98')
  await page.getByRole('button', { name: 'Mentés' }).click()
  await expect(page.getByText('A mérés elmentve.')).toBeVisible()
  await expect(page.getByText(/165\/98 Hgmm/)).toBeVisible()

  // Egyértékű mérés a teendő kártyájáról: a „Rögzítés” a kártyán belül nyitja az
  // űrlapot, típusválasztó nélkül.
  const pulseTask = page.locator('.pulse-task').filter({ hasText: 'Pulzus' })
  await pulseTask.getByRole('button', { name: 'Rögzítés' }).click()
  await pulseTask.getByLabel('Pulzus (/perc)').fill('72')
  await pulseTask.getByRole('button', { name: 'Mentés' }).click()
  await expect(page.getByText(/72 \/perc/)).toBeVisible()

  // A mai pulzus kész, a tegnapi elmaradt, de pótolható. A „Pótlás” a tegnapi
  // időponttal nyitja ki az űrlapot a kártyán.
  await expect(pulseTask).toContainText('Kész.')
  await pulseTask.getByRole('button', { name: 'Pótlás' }).click()
  // Az űrlap kiírja, hogy pótlás történik, és melyik mérés hiányzik.
  await expect(page.getByText(/Pótlás: az elmaradt pulzusmérés/)).toBeVisible()
  await expect(page.getByLabel('A mérés ideje')).toBeVisible()
  await page.getByLabel('Pulzus (/perc)').fill('70')
  await page.getByRole('button', { name: 'Mentés' }).click()
  await expect(page.getByText('A mérés elmentve.')).toBeVisible()
  await expect(page.getByText(/70 \/perc, .*Az elmaradt mérés pótolva\./)).toBeVisible()
  await expect(pulseTask.getByRole('button', { name: 'Pótlás' })).toHaveCount(0)

  // Az Előzményeim oldal mérési naplójában mindhárom mérés ott van, a hibás nincs.
  await page.getByRole('link', { name: 'Előzményeim', exact: true }).click()
  await expect(page).toHaveURL(/\/patient\/history$/)
  await expect(history(page).filter({ hasText: '165/98 Hgmm' }).first()).toBeVisible()
  await expect(history(page).filter({ hasText: '72 /perc' }).first()).toBeVisible()
  await expect(history(page).filter({ hasText: '70 /perc' }).first()).toBeVisible()
  await expect(history(page).filter({ hasText: /(300|400)\/98 Hgmm/ })).toHaveCount(0)
})

test('kérdőív-folyamat, beteg: kitöltés és beküldés, a pontszám nem látszik', async ({ page }) => {
  await login(page, 'toth.maria@pulse.example')
  await expect(page).toHaveURL(/\/patient$/)
  const wellbeingTask = page.locator('.pulse-task').filter({ hasText: 'Közérzet' })
  await expect(wellbeingTask).toContainText('Esedékes.')

  // A „Kitöltés” a kérdőív saját oldalára visz.
  await wellbeingTask.getByRole('button', { name: 'Kitöltés' }).click()
  await expect(page).toHaveURL(/\/patient\/questionnaires\/[^/]+$/)
  const fillUrl = page.url()

  // Alvás 1, fáradtság 5, szédülés naponta: 4 + 4 + 5 = 13 pont (kritikus sáv).
  await page
    .getByRole('radiogroup', { name: 'Hogyan aludt az elmúlt éjszaka?' })
    .getByText('1', { exact: true })
    .click()
  await page
    .getByRole('radiogroup', { name: 'Mennyire fáradt ma?' })
    .getByText('5', { exact: true })
    .click()
  await page.getByRole('radio', { name: 'Naponta' }).click()
  await page.getByRole('button', { name: 'Beküldés' }).click()

  // Beküldés után vissza a teendőkhöz, a nyugtával; a teendő kész.
  await expect(page).toHaveURL(/\/patient$/)
  await expect(page.getByText('Köszönjük, a kitöltés beérkezett.')).toBeVisible()
  await expect(wellbeingTask).toContainText('Kész.')

  const text = await mainText(page)
  expect(text).not.toMatch(/\d+\s*(\/\s*\d+\s*)?pont/)
  expect(text).not.toContain('sáv')

  // A kérdőív oldala ezután nem kínálja fel úgy, mintha még kitöltendő lenne, de
  // újra kitölthető.
  await page.goto(fillUrl)
  await expect(page.getByText(/Erre a hétre már kitöltötted/)).toBeVisible()
  await expect(page.getByRole('button', { name: 'Mégis kitöltöm újra' })).toBeVisible()
})

test('az orvos látja: Tóth Mária Súlyos, az okok között a kérdőív és a mérés', async ({ page }) => {
  await login(page, 'dr.nagy@pulse.example')
  await expect(page).toHaveURL(/\/doctor$/)
  await page.locator('.pulse-prow').first().waitFor()
  const [first] = await rowsText(page)

  expect(first.startsWith('Súlyos')).toBe(true)
  // A kérdőív két szabálya (figyelmeztető és kritikus) ugyanazt az okot egyszer írja ki.
  expect(first.split('13/13 pont (kritikus sáv)')).toHaveLength(2)
  expect(first).toContain('Szisztolés 165 Hgmm (> 140)')

  await page.getByRole('link', { name: 'Tóth Mária' }).click()
  const main = page.locator('main')
  await expect(main).toContainText('Kérdőívszabály, 1. verzió')
  await expect(main).toContainText('pontszáma a(z) figyelmeztető vagy kritikus sávban')
  await expect(main).toContainText('13/13')
  await expect(main).toContainText('kritikus')
})

test('követési terv, orvos: új előírás, módosítás és visszavonás, a lista mutatja a váltást', async ({
  page,
}) => {
  await login(page, 'dr.nagy@pulse.example')
  await expect(page).toHaveURL(/\/doctor$/)
  await page.getByRole('link', { name: 'Tóth Mária' }).click()
  const plan = page.getByRole('region', { name: 'Követési terv' })
  const current = plan.locator('.pd-plan-item:not(.past)').filter({ hasText: 'Testsúly' })
  const past = plan.locator('.pd-plan-item.past').filter({ hasText: 'Testsúly' })

  // Új előírás: testsúly hetente, 9:00-ig (a seedben Tóth Máriának nincs ilyen).
  await plan.getByRole('button', { name: 'Új előírás' }).click()
  await plan.getByLabel('Mit ír elő?').selectOption({ label: 'Testsúly' })
  await plan.getByRole('button', { name: 'Hetente' }).click()
  await plan.getByLabel('Határidő').fill('09:00')
  await plan.getByRole('button', { name: 'Mentés', exact: true }).click()
  await expect(plan).toContainText('Az előírás elmentve.')
  await expect(current).toContainText('Hetente · határidő 09:00')
  await expect(current).toContainText('előírta: Dr. Nagy Péter')

  // Módosítás: az űrlap a régi értékekkel nyílik; mentéskor a régi lezárul, és
  // ugyanarra a célra új előírás indul.
  await current.getByRole('button', { name: 'Módosítás' }).click()
  await expect(current.getByLabel('Határidő')).toHaveValue('09:00')
  await expect(current.getByRole('button', { name: 'Hetente' })).toHaveAttribute(
    'aria-pressed',
    'true',
  )
  await current.getByRole('button', { name: 'N naponta' }).click()
  await current.getByLabel('Hány naponta').fill('3')
  await current.getByRole('button', { name: 'Mentés módosításként' }).click()
  await expect(plan).toContainText('Az előírás módosítva.')

  // A váltás az új előírásnál látszik, a régi halványan a korábbiak között.
  await expect(current).toHaveCount(1)
  await expect(current).toContainText('3 naponta · határidő 09:00')
  await expect(current).toContainText(/Módosítva .+: hetente → 3 naponta/)
  await expect(past).toHaveCount(1)
  await expect(past).toContainText('Módosítva')

  // Visszavonás megerősítéssel: az előírás a korábbiak közé kerül.
  await current.getByRole('button', { name: 'Visszavonás' }).click()
  await expect(current).toContainText('Biztosan visszavonod?')
  await current.getByRole('button', { name: 'Visszavonás' }).click()
  await expect(plan).toContainText('Az előírás visszavonva.')
  await expect(current).toHaveCount(0)
  await expect(past).toHaveCount(2)
  await expect(past.last()).toContainText('Visszavonva')
})
