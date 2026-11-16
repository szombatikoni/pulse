// A NICE-kiértékelés panelje az orvos adatlapján (M3, K2, 3. lépés). Az első két
// teszt a valódi láncon fut (API → CQL-szolgáltatás a saját konténerében); a seed
// relatív időpontú, ezért a számokat nem rögzítjük, csak a formájukat. A hibaágakat
// (503, eltérés) a böngészőben elfogott válasszal (page.route) próbáljuk ki. A
// kiértékelés semmit nem tárol, így ez a fájl az adatokon nem változtat; az
// adatlap megnyitása Szabó János riasztásait megtekintettnek jelöli, mint az
// m2_folyamatok 2. tesztje is. Varga Béla adatlapját szándékosan nem nyitjuk meg
// (az új riasztásait a Riasztások oldal tesztje még újként várja).
import { expect, test, type Page } from '@playwright/test'

const PASSWORD = 'pulse-demo-2026'
const NICE = '**/api/patients/*/nice-evaluation'

async function login(page: Page, email: string) {
  await page.goto('/login')
  await page.getByLabel('E-mail-cím').fill(email)
  await page.getByLabel('Jelszó', { exact: false }).first().fill(PASSWORD)
  await page.getByRole('button', { name: 'Belépés' }).click()
}

async function openPatient(page: Page, name: string) {
  await login(page, 'dr.kovacs@pulse.example')
  await expect(page).toHaveURL(/\/doctor$/)
  await page.getByRole('link', { name }).click()
}

const panel = (page: Page) => page.getByRole('region', { name: 'Otthoni vérnyomásátlag (NICE)' })

test('NICE, valódi lánc: Szabó Jánosnál átlag, ítélet és egyezés a gomb után', async ({ page }) => {
  await openPatient(page, 'Szabó János')
  const nice = panel(page)
  // Alaphelyzetben semmi nem fut, csak a magyarázat és a gomb látszik.
  await expect(nice).toContainText('nem tárolódik')
  await expect(nice).toContainText('Demonstráció, nem orvosi döntés.')
  await nice.getByRole('button', { name: 'Kiértékelés' }).click()

  await expect(nice.getByRole('button', { name: 'Újra' })).toBeVisible()
  await expect(nice).toContainText(/Kiértékelve ma \d\d:\d\d/)
  // Az átlag egy tizedesre, tizedesvesszővel: „137,7 / 86,8”.
  await expect(nice.locator('.pd-nice-val .v')).toHaveText(/^\d{2,3},\d{1,2} \/ \d{2,3},\d{1,2}$/)
  await expect(nice.locator('.pd-nice-verdict')).toHaveText(/^Cél (nem )?teljesül$/)
  await expect(nice).toContainText('Célérték: 135 / 85 Hgmm alatt')
  await expect(nice).toContainText('A CQL-motor és a saját számítás egyezik')
  // A Részletek alapból csukva; kinyitva a két számítás mezőnként.
  const details = nice.locator('details')
  await expect(details).not.toHaveAttribute('open')
  await details.locator('summary').click()
  await expect(nice.getByRole('columnheader', { name: 'CQL-motor' })).toBeVisible()
  await expect(nice).toContainText('PulseHbpmAverage 0.1.0')
})

test('NICE, valódi lánc: Kiss Ilonánál kevés a nap, „Nem értékelhető”, nagy átlag nélkül', async ({
  page,
}) => {
  await openPatient(page, 'Kiss Ilona')
  const nice = panel(page)
  await nice.getByRole('button', { name: 'Kiértékelés' }).click()
  await expect(nice.locator('.pd-nice-verdict')).toHaveText('Nem értékelhető')
  await expect(nice).toContainText(/Az első nap után \d mérési nap maradt, legalább 3 kell\./)
  await expect(nice.locator('.pd-nice-val')).toHaveCount(0)
  await expect(nice).not.toContainText('Célérték')
})

test('NICE, elérhetetlen motor (503): hibaszöveg, Újrapróbálás, utána eredmény', async ({
  page,
}) => {
  await page.route(NICE, (route) =>
    route.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({ detail: { code: 'cql_unavailable' } }),
    }),
  )
  await openPatient(page, 'Molnár Katalin')
  const nice = panel(page)
  await nice.getByRole('button', { name: 'Kiértékelés' }).click()
  await expect(nice).toContainText('A kiértékelő szolgáltatás most nem érhető el.')
  await expect(nice).toContainText('A riasztások és a státusz ettől nem változnak.')
  await expect(nice.locator('.pd-nice-verdict')).toHaveCount(0)

  // Automatikus újrapróbálás nincs; a gombbal a (már elérhető) motor válaszol.
  await page.unroute(NICE)
  await nice.getByRole('button', { name: 'Újrapróbálás' }).click()
  await expect(nice.locator('.pd-nice-verdict')).toBeVisible()
  await expect(nice).not.toContainText('nem érhető el')
})

test('NICE, eltérés a két számítás között: nincs ítélet, a Részletek nyitva, az eltérő sor jelölve', async ({
  page,
}) => {
  // A valódi válasz, az S1 ismert eset mintájára átírva: a pontos átlag 135, a
  // motor lebegőpontosan 134,99999999999997-et kap, így csak a target_met tér el.
  await page.route(NICE, async (route) => {
    const response = await route.fetch()
    const body = await response.json()
    body.cql.mean_systolic = 134.99999999999997
    body.own.mean_systolic = 135
    body.cql.target_met = true
    body.own.target_met = false
    body.matches = false
    body.mismatched_fields = ['target_met']
    await route.fulfill({ response, json: body })
  })
  await openPatient(page, 'Molnár Katalin')
  const nice = panel(page)
  await nice.getByRole('button', { name: 'Kiértékelés' }).click()

  await expect(nice.locator('.pd-nice-verdict')).toHaveText('Eltér a két számítás')
  await expect(nice).toContainText(
    'A CQL-motor és a saját számítás eredménye eltér: cél teljesül. Az eredményt ezért nem minősítjük.',
  )
  await expect(nice).not.toContainText('egyezik')
  await expect(nice.locator('details')).toHaveAttribute('open')
  const diff = nice.locator('tr.diff')
  await expect(diff).toHaveCount(1)
  await expect(diff).toContainText('Cél teljesül')
  await expect(diff).toContainText('igen')
  await expect(diff).toContainText('nem')
  await expect(nice).toContainText('134,99999999999997')
})

test('NICE: a beteg felületén nincs panel', async ({ page }) => {
  await login(page, 'molnar.katalin@pulse.example')
  await expect(page).toHaveURL(/\/patient$/)
  await page.locator('.pulse-task').first().waitFor()
  await expect(page.getByText('Otthoni vérnyomásátlag (NICE)')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Kiértékelés' })).toHaveCount(0)
})
