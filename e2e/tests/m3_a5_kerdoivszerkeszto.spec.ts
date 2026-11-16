// A kérdőívszerkesztő (M3, A5) a felületen: az orvos a Kérdőívek oldalon új kérdést
// ad a „Közérzet”-hez; a „Melyik vég jelenti a jobb állapotot?” választása nélkül
// a mentés tiltott, a választás után a mentés új verziót hoz létre, és a
// verziólistában a régiek is megmaradnak.
// Frissen seedelt adatbázist vár (a seedben a „Közérzet” 2. verziója az érvényes),
// és módosítja: a „Közérzet” 3. verziót kap. Ezért a futási sorrendben a többi
// spec után jön (a fájlnév szerint).
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
  await expect(q1.getByLabel('Kérdés', { exact: true })).toHaveValue('Hogyan aludt az elmúlt héten?')
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
