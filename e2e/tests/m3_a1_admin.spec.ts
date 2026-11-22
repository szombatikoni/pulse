// Az admin-felület (M3, A1) a böngészőben: az admin létrehoz egy beteget,
// összerendeli Nagy doktorral, aki a listáján azonnal látja; letiltva „Letiltva”
// jelöléssel látja, visszaengedélyezés után anélkül; a megszüntetés után a beteg
// eltűnik a listájáról. Utána az admin újra letiltja a beteget: a már
// bejelentkezett beteg munkamenete megszűnik (az újrabelépő ablakból a
// belépőoldalra kerül), és belépni sem tud („A fiók le van tiltva.”).
// Frissen seedelt adatbázist vár (backend/seed). Minden futás új, egyedi
// e-mail-című beteget hoz létre (ismételt futásnál sem ütközik), és a végén az
// összerendelése megszűnik, a fiókja letiltva marad: a seedelt fiókokat és
// összerendeléseket nem módosítja. A fájlnév szerint az m2_folyamatok után fut,
// így az ott ellenőrzött orvosi listákon a teszt betege nem jelenik meg; a
// későbbi m3_a5 és m3_a8 spec Nagy doktor listáját nem ellenőrzi; riasztás és
// e-mail ebből a tesztből nem keletkezik (a betegnek nincs szabálya és adata).
import { expect, test, type Browser, type Page } from '@playwright/test'

const PASSWORD = 'pulse-demo-2026'

async function login(page: Page, email: string, password = PASSWORD) {
  await page.goto('/login')
  await page.getByLabel('E-mail-cím').fill(email)
  await page.getByLabel('Jelszó', { exact: false }).first().fill(password)
  await page.getByRole('button', { name: 'Belépés' }).click()
}

const suffix = Date.now().toString(36)
const PATIENT_NAME = `Próba Beteg ${suffix}`
const PATIENT_EMAIL = `proba.beteg.${suffix}@pulse.example`
const PATIENT_PASSWORD = 'proba-jelszo-2026'
const DOCTOR = 'Dr. Nagy Péter'

async function asDoctor(browser: Browser) {
  const context = await browser.newContext()
  const page = await context.newPage()
  await login(page, 'dr.nagy@pulse.example')
  await expect(page).toHaveURL(/\/doctor$/)
  return { context, page }
}

// A lépések egymásra épülnek (a második a most létrehozott beteget tiltja le).
test.describe.configure({ mode: 'serial' })

test('az admin létrehoz egy beteget és összerendeli: az orvos azonnal látja, a megszüntetés után már nem', async ({
  page,
  browser,
}) => {
  await login(page, 'admin@pulse.example')
  await expect(page).toHaveURL(/\/admin$/)
  await expect(page.getByRole('heading', { name: 'Felhasználók', level: 1 })).toBeVisible()

  // Új beteg: a szerepkör alapból Beteg.
  await page.getByRole('button', { name: 'Új felhasználó' }).click()
  const create = page.getByRole('dialog', { name: 'Új felhasználó' })
  await expect(create.getByRole('button', { name: 'Beteg' })).toHaveAttribute(
    'aria-pressed',
    'true',
  )
  await create.getByLabel('E-mail-cím').fill(PATIENT_EMAIL)
  await create.getByLabel('Név').fill(PATIENT_NAME)
  await create.getByLabel('Születési dátum').fill('1961-05-06')
  await create.getByLabel('Kezdeti jelszó').fill(PATIENT_PASSWORD)
  await create.getByRole('button', { name: 'Létrehozás' }).click()
  await expect(create).toBeHidden()

  // A listában megjelenik, aktívként; születési dátum a listában nincs.
  const row = page.getByRole('row', { name: new RegExp(PATIENT_NAME) })
  await expect(row).toContainText(PATIENT_EMAIL)
  await expect(row).toContainText('Beteg')
  await expect(row).toContainText('Aktív')
  await expect(row).toContainText('még nem lépett be')
  await expect(row).not.toContainText('1961')

  // Összerendelés Nagy doktorral.
  await page.getByRole('tab', { name: 'Összerendelések' }).click()
  await expect(page).toHaveURL(/\?tab=assignments$/)
  const card = page.getByRole('region', { name: DOCTOR })
  await card.getByRole('button', { name: `Új összerendelés: ${DOCTOR}` }).click()
  const assign = page.getByRole('dialog', { name: 'Új összerendelés' })
  await assign.getByLabel('Beteg').selectOption({ label: PATIENT_NAME })
  await assign.getByRole('button', { name: 'Összerendelés', exact: true }).click()
  await expect(assign).toBeHidden()
  const link = card.getByRole('row', { name: new RegExp(PATIENT_NAME) })
  await expect(link).toContainText('óta')

  // Az orvos azonnal látja a listáján (új belépés, friss lista).
  const doctor = await asDoctor(browser)
  await expect(doctor.page.getByRole('link', { name: PATIENT_NAME })).toBeVisible()

  // Letiltás az összerendelés alatt: az orvos listáján marad, „Letiltva” jelöléssel.
  // Utána visszaengedélyezés, hogy a következő teszt a beteggel be tudjon lépni.
  await page.getByRole('tab', { name: 'Felhasználók' }).click()
  await page.getByRole('button', { name: `${PATIENT_NAME} szerkesztése` }).click()
  const edit = page.getByRole('dialog', { name: PATIENT_NAME })
  await edit.getByRole('button', { name: 'Fiók letiltása' }).click()
  await edit.getByRole('button', { name: 'Letiltás', exact: true }).click()
  await expect(edit.getByRole('button', { name: 'Fiók visszaengedélyezése' })).toBeVisible()
  await doctor.page.reload()
  await expect(doctor.page.getByRole('link', { name: PATIENT_NAME })).toContainText('Letiltva')
  await edit.getByRole('button', { name: 'Fiók visszaengedélyezése' }).click()
  await expect(edit.getByRole('button', { name: 'Fiók letiltása' })).toBeVisible()
  await edit.getByRole('button', { name: 'Ablak bezárása' }).click()
  await doctor.page.reload()
  await expect(doctor.page.getByRole('link', { name: PATIENT_NAME })).not.toContainText('Letiltva')
  await page.getByRole('tab', { name: 'Összerendelések' }).click()

  // Megszüntetés: a sor a történetben marad, az orvos listájáról eltűnik.
  await link
    .getByRole('button', { name: `${PATIENT_NAME} és ${DOCTOR} összerendelésének megszüntetése` })
    .click()
  await expect(link).toContainText('Megszüntetve')
  await expect(link).toContainText('között')
  await doctor.page.reload()
  await expect(doctor.page.getByRole('heading', { name: 'Betegeim' })).toBeVisible()
  await expect(doctor.page.getByRole('link', { name: PATIENT_NAME })).toHaveCount(0)
  await doctor.context.close()
})

test('a letiltott beteg munkamenete megszűnik, és belépni sem tud', async ({ page, browser }) => {
  // A beteg előbb belép.
  const patientContext = await browser.newContext()
  const patientPage = await patientContext.newPage()
  await login(patientPage, PATIENT_EMAIL, PATIENT_PASSWORD)
  await expect(patientPage).toHaveURL(/\/patient$/)

  // Az admin letiltja (megerősítéssel).
  await login(page, 'admin@pulse.example')
  await expect(page).toHaveURL(/\/admin$/)
  await page.getByRole('button', { name: `${PATIENT_NAME} szerkesztése` }).click()
  const edit = page.getByRole('dialog', { name: PATIENT_NAME })
  await edit.getByRole('button', { name: 'Fiók letiltása' }).click()
  await expect(edit).toContainText('nem számítanak elmulasztottnak')
  await edit.getByRole('button', { name: 'Letiltás', exact: true }).click()
  await expect(edit.getByRole('button', { name: 'Fiók visszaengedélyezése' })).toBeVisible()
  await edit.getByRole('button', { name: 'Ablak bezárása' }).click()
  await expect(page.getByRole('row', { name: new RegExp(PATIENT_NAME) })).toContainText('Letiltva')

  // A már kiadott token a következő kérésnél érvénytelen: a nyitott oldalon az
  // újrabelépő ablak jön (M3, A8). Helyes jelszóra a szerver jelzi, hogy a fiók le
  // van tiltva, és a felület a belépőoldalra visz (nem kéri újra a jelszót).
  await patientPage.getByRole('link', { name: 'Előzményeim', exact: true }).click()
  const relogin = patientPage.getByRole('dialog', { name: 'Lejárt a munkamenet' })
  await expect(relogin).toBeVisible()
  await relogin.getByLabel('Jelszó', { exact: false }).first().fill(PATIENT_PASSWORD)
  await relogin.getByRole('button', { name: 'Belépés' }).click()
  // Egy lépésben: a belépőoldal rögtön a letiltás üzenetét mutatja, a „lejárt
  // munkamenet” üzenet nélkül.
  await expect(patientPage).toHaveURL(/\/login\?disabled=1$/)
  await expect(patientPage.getByText('A fiók le van tiltva.')).toBeVisible()
  await expect(patientPage.getByText('A munkamenet lejárt')).toHaveCount(0)
  // A belépőoldalon rossz jelszóval csak az általános hiba, helyessel csak a letiltás.
  await login(patientPage, PATIENT_EMAIL, 'rossz-jelszo-2026')
  await expect(patientPage.getByText('Hibás e-mail-cím vagy jelszó.')).toBeVisible()
  await expect(patientPage.getByText('A fiók le van tiltva.')).toHaveCount(0)
  await login(patientPage, PATIENT_EMAIL, PATIENT_PASSWORD)
  await expect(patientPage.getByText('A fiók le van tiltva.')).toBeVisible()
  await expect(patientPage.getByText('Hibás e-mail-cím vagy jelszó.')).toHaveCount(0)
  await expect(patientPage).toHaveURL(/\/login/)
  await patientContext.close()
})
