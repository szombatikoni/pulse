// A kérdőívszerkesztő (M3, A5) a felületen: az orvos a Kérdőívek oldalon új kérdést
// ad a „Közérzet”-hez; a „Melyik vég jelenti a jobb állapotot?” választása nélkül
// a mentés tiltott, a választás után a mentés új verziót hoz létre, és a
// verziólistában a régiek is megmaradnak.
// Frissen seedelt adatbázist vár (a seedben a „Közérzet” 2. verziója az érvényes),
// és módosítja: a „Közérzet” 3. verziót kap. Ezért a futási sorrendben a többi
// spec után jön (a fájlnév szerint). A második teszt (ütközés két orvos között)
// a verziószámot az API-ból olvassa, és újabb verziót ment.
import { expect, test, type Page } from '@playwright/test'

const PASSWORD = 'pulse-demo-2026'

async function login(page: Page, email: string) {
  await page.goto('/login')
  await page.getByLabel('E-mail-cím').fill(email)
  await page.getByLabel('Jelszó', { exact: false }).first().fill(PASSWORD)
  await page.getByRole('button', { name: 'Belépés' }).click()
}

test('az orvos új kérdést ad a kérdőívhez, és új verzióként menti', async ({ page }) => {
  await login(page, 'dr.kovacs@pulse.example')
  await expect(page).toHaveURL(/\/doctor$/)
  await page.getByRole('link', { name: 'Kérdőívek' }).click()
  await expect(page).toHaveURL(/\/doctor\/questionnaires$/)

  const list = page.getByRole('region', { name: 'Kérdőívek' })
  await expect(list).toContainText('Közérzet')
  await expect(list).toContainText('2. verzió érvényes')
  await expect(list).toContainText('3 kérdés')
  await expect(list).toContainText('legfeljebb 13 pont')

  await page.getByRole('link', { name: '„Közérzet” szerkesztése' }).click()
  await expect(page).toHaveURL(/\/doctor\/questionnaires\/wellbeing$/)
  const save = page.getByRole('button', { name: 'Mentés 3. verzióként' })
  // A seed 2. verziója: a kérdések az elmúlt hétre kérdeznek.
  const q1 = page.getByRole('region', { name: '1. kérdés' })
  await expect(q1.getByLabel('Kérdés', { exact: true })).toHaveValue(
    'Hogyan aludt az elmúlt héten?',
  )
  // Változtatás nélkül nem menthető.
  await expect(save).toBeDisabled()
  await expect(page.getByText('Nincs változás az érvényes verzióhoz képest.')).toBeVisible()

  // Új skálás kérdés: a jobb vég választása kötelező, alapértelmezés nincs.
  await page.getByRole('button', { name: 'Új kérdés' }).click()
  const q4 = page.getByRole('region', { name: '4. kérdés' })
  await q4.getByLabel('Kérdés', { exact: true }).fill('Mennyire volt nehézlégzése az elmúlt héten?')
  await expect(q4).toContainText('Válaszd ki, melyik vég jelenti a jobb állapotot.')
  await expect(save).toBeDisabled()

  await q4.getByRole('radio', { name: '1', exact: true }).check()
  await expect(q4).toContainText('Pontok (számolt): 1→0  2→1  3→2  4→3  5→4')
  // 13 + 4 = 17 pont; a kritikus sáv a legnagyobb pontszámig nő.
  await expect(page.getByText('Legnagyobb pontszám: 17')).toBeVisible()
  await expect(save).toBeEnabled()
  await save.click()

  await expect(
    page.getByText('Mentve, mostantól a 3. verzió érvényes. A már megnyílt alkalmak'),
  ).toBeVisible()
  await expect(page.getByRole('button', { name: 'Mentés 4. verzióként' })).toBeDisabled()
  const versions = page.locator('.pd-versions li')
  await expect(versions).toHaveCount(3)
  await expect(versions.nth(0)).toContainText('3. verzió')
  await expect(versions.nth(0)).toContainText('4 kérdés')
  await expect(versions.nth(0)).toContainText('érvényes')
  await expect(versions.nth(1)).toContainText('2. verzió')
  await expect(versions.nth(2)).toContainText('1. verzió')

  // A listán is az új verzió látszik.
  await page.getByRole('link', { name: 'Kérdőívek' }).first().click()
  await expect(page.getByRole('region', { name: 'Kérdőívek' })).toContainText('3. verzió érvényes')
})

test('ha közben más orvos ment, a vázlat nem vész el szó nélkül: a mentés ütközést jelez', async ({
  page,
  request,
}) => {
  // Nagy doktor az API-n keresztül ment (mintha egy másik böngészőben tenné).
  const tokenResponse = await request.post('/api/auth/login', {
    data: { email: 'dr.nagy@pulse.example', password: PASSWORD },
  })
  expect(tokenResponse.ok()).toBeTruthy()
  const headers = {
    Authorization: `Bearer ${(await tokenResponse.json()).access_token}`,
  }
  const detailResponse = await request.get('/api/questionnaires/wellbeing', {
    headers,
  })
  expect(detailResponse.ok()).toBeTruthy()
  const current = (await detailResponse.json()).current
  const base: number = current.version_no

  await login(page, 'dr.kovacs@pulse.example')
  await expect(page).toHaveURL(/\/doctor$/)
  await page.goto('/doctor/questionnaires/wellbeing')
  const q1Text = page
    .getByRole('region', { name: '1. kérdés' })
    .getByLabel('Kérdés', { exact: true })
  const q2Text = page
    .getByRole('region', { name: '2. kérdés' })
    .getByLabel('Kérdés', { exact: true })
  await expect(q1Text).toHaveValue(current.questions[0].text)
  // Kovács doktor módosít, de még nem ment.
  await q1Text.fill('Kovács doktor nem mentett módosítása')

  const nagyText = `Nagy doktor szövege (${Date.now()})`
  const questions = structuredClone(current.questions)
  questions[1].text = nagyText
  const saved = await request.post('/api/questionnaires/wellbeing/versions', {
    headers,
    data: {
      base_version_no: base,
      questions,
      scoring_thresholds: current.scoring_thresholds,
    },
  })
  expect(saved.status()).toBe(201)

  // Az ablak fókuszt vált, majd vissza: a részletek nem töltődnek újra a háttérben,
  // a vázlat megmarad.
  let refetches = 0
  page.on('request', (r) => {
    if (r.method() === 'GET' && r.url().endsWith('/api/questionnaires/wellbeing')) refetches += 1
  })
  // A React Query a window visibilitychange eseményére figyel (a fókuszváltás így
  // jut el hozzá); a régi beállítással itt újratöltött, és a vázlat elveszett.
  await page.evaluate(() => window.dispatchEvent(new Event('visibilitychange')))
  await page.waitForTimeout(500)
  expect(refetches).toBe(0)
  await expect(q1Text).toHaveValue('Kovács doktor nem mentett módosítása')

  // A mentés ütközés: üzenet és a friss változat betöltése.
  await page.getByRole('button', { name: `Mentés ${base + 1}. verzióként` }).click()
  await expect(
    page.getByText(`Közben valaki elmentette a(z) ${base + 1}. verziót.`, {
      exact: false,
    }),
  ).toBeVisible()
  await expect(q1Text).toHaveValue('Kovács doktor nem mentett módosítása')
  await page.getByRole('button', { name: 'Friss változat betöltése' }).click()
  await expect(q2Text).toHaveValue(nagyText)
  await expect(q1Text).toHaveValue(current.questions[0].text)
  await expect(page.getByRole('button', { name: `Mentés ${base + 2}. verzióként` })).toBeDisabled()
})
