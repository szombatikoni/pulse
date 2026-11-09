// A két M2-folyamat a felületen végigvíve: a beteg mér és kérdőívet tölt ki,
// az orvos a priorizált listán és az adatlapon látja a jelzést, idegen beteg
// adatához pedig nem fér hozzá. A végén az orvos a követési tervet szerkeszti
// (M3, A2), indoklással, és a beteg a teendői közt látja a változást (M3, A3);
// végül a Szabályok fülön a küszöbszabályt módosítja új verzióként (M3, A4).
// A riasztás-életút (M3, A6): a Riasztások oldal, a megtekintés az adatlap
// megnyitásakor, a felelőshöz rendelés és a lezárás indoklással és betegüzenettel;
// a beteglistán Kezelve, a beteg a teendői fölött látja a visszajelzést.
// Frissen seedelt adatbázist vár (backend/seed), és módosítja az adatokat
// (Tóth Mária új mérései, kitöltése, testsúly-előírása és küszöbszabálya, Szabó
// János két lezárt riasztása, Varga Béla megtekintett riasztásai).
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
  // Szabó János: az időablakos riasztás legutóbbi kiváltó mérése.
  expect(rows[1]).toContain('Szisztolés 152 Hgmm (> 140)')
  // Kiss Ilona: Adathiány a kérdőív elmulasztott alkalma miatt (M3, A4), célponttal
  // és határidővel.
  expect(rows[2]).toContain('Kiss Ilona')
  expect(rows[2]).toMatch(/Elmulasztott alkalom: „Közérzet” kérdőív, határidő .+ 20:00/)
  expect(rows.some((r) => r.includes('Tóth Mária'))).toBe(false)
})

test('az adatlapon a riasztás magyarázattal és eseménytörténettel látszik', async ({ page }) => {
  await login(page, 'dr.kovacs@pulse.example')
  await page.getByRole('link', { name: 'Szabó János' }).click()
  // Az adatlap részei (riasztások, kitöltések, mérések) külön kéréssel töltődnek
  // be, ezért az ellenőrzés addig vár, amíg a szöveg megjelenik (expect … toContainText).
  const main = page.locator('main')
  // A seedben (M3, A4) a tartós eltérést az időablakos szabály jelzi: legalább 3
  // határsértő mérés 7 napon belül. A magyarázat az ablak összes kiváltó mérését
  // felsorolja (a negyedik ismételt aktiválódásként kapcsolódott hozzá).
  await expect(main).toContainText('Időablakos szabály, 1. verzió · közepes')
  await expect(main).toContainText(
    'Feltétel: Szisztolés > 140 Hgmm vagy Diasztolés > 90 Hgmm, legalább 3 mérésnél 7 napon belül',
  )
  // A több kiváltó adat egymás alatti lista, soronként egy mérés: az érték, utána csak
  // az átlépett határok a komponensek sorrendjében (az érték nem ismétlődik), és az időpont.
  const triggerList = main.getByRole('list', { name: 'Kiváltó adatok (4):' })
  const triggers = triggerList.getByRole('listitem')
  await expect(triggers).toHaveCount(4)
  await expect(triggers.first()).toHaveText(/^146\/92 Hgmm · > 140 \/ > 90 · \S/)
  await expect(triggers.last()).toHaveText(/^152\/95 Hgmm · > 140 \/ > 90 · \S/)
  await expect(triggerList).not.toContainText('Szisztolés')
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

test('az orvos látja: Tóth Mária Súlyos, az ok a kritikus kérdőív', async ({ page }) => {
  await login(page, 'dr.nagy@pulse.example')
  await expect(page).toHaveURL(/\/doctor$/)
  await page.locator('.pulse-prow').first().waitFor()
  const [first] = await rowsText(page)

  expect(first.startsWith('Súlyos')).toBe(true)
  // A kérdőív két szabálya (figyelmeztető és kritikus) ugyanazt az okot egyszer írja ki.
  expect(first.split('13/13 pont (kritikus sáv)')).toHaveLength(2)
  // A 165/98-as mérés már nem nyit riasztást (M3, A4 seed): a küszöbszabály csak
  // 180 fölött jelez, az időablakos pedig legalább 3 határsértő mérést kér 7 napon belül.
  expect(first).not.toContain('Szisztolés 165')

  await page.getByRole('link', { name: 'Tóth Mária' }).click()
  const main = page.locator('main')
  await expect(main).toContainText('Kérdőívszabály, 1. verzió')
  await expect(main).toContainText('Feltétel: a pontszám a(z) figyelmeztető vagy kritikus sávban')
  await expect(main).toContainText('13/13')
  await expect(main).toContainText('kritikus')
})

// A követési terv a beteg adatlapján, a testsúly-előírás aktuális és korábbi kártyái.
async function openPlan(page: Page) {
  await login(page, 'dr.nagy@pulse.example')
  await expect(page).toHaveURL(/\/doctor$/)
  await page.getByRole('link', { name: 'Tóth Mária' }).click()
  const plan = page.getByRole('region', { name: 'Követési terv' })
  return {
    plan,
    current: plan.locator('.pd-plan-item:not(.past)').filter({ hasText: 'Testsúly' }),
    past: plan.locator('.pd-plan-item.past').filter({ hasText: 'Testsúly' }),
  }
}

// A beteg teendői fölötti jelzés a testsúly-előírás változásáról.
async function weightNotice(page: Page) {
  await login(page, 'toth.maria@pulse.example')
  await expect(page).toHaveURL(/\/patient$/)
  const notices = page.getByRole('region', {
    name: 'Változások az előírásaidban',
  })
  return notices.locator('.pulse-notice').filter({ hasText: 'Testsúly' })
}

test('követési terv, orvos: új előírás és módosítás indoklással, a lista mutatja a váltást', async ({
  page,
}) => {
  const { plan, current, past } = await openPlan(page)

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
  // A kezdet módosításnál nem választható: az új ma indul (review K3).
  await expect(current.getByLabel('Kezdete')).toHaveCount(0)
  await expect(current).toContainText('új indul (kezdete:')
  await current.getByRole('button', { name: 'N naponta' }).click()
  await current.getByLabel('Hány naponta').fill('3')
  // Az indoklás nem kötelező; a felület jelzi, hogy a beteg is látja.
  await expect(current).toContainText('A beteg is látja a teendői között.')
  await current
    .getByLabel('Indoklás a betegnek (nem kötelező)')
    .fill('Elég háromnaponta mérni, stabil a testsúlya.')
  await current.getByRole('button', { name: 'Mentés módosításként' }).click()
  await expect(plan).toContainText('Az előírás módosítva.')

  // A váltás az új előírásnál látszik, a régi halványan a korábbiak között.
  await expect(current).toHaveCount(1)
  await expect(current).toContainText('3 naponta · határidő 09:00')
  await expect(current).toContainText(/Módosítva .+: hetente → 3 naponta/)
  await expect(past).toHaveCount(1)
  await expect(past).toContainText('Módosítva')
  // Az indoklás a lezárt (régi) előírásnál halványan látszik.
  await expect(past).toContainText('Indoklás: „Elég háromnaponta mérni, stabil a testsúlya.”')
})

test('a beteg a teendői közt látja a módosítást és az indoklást', async ({ page }) => {
  const notice = await weightNotice(page)
  await expect(notice).toHaveCount(1)
  await expect(notice).toContainText(
    /Az előírás módosult \(.+\): mostantól 3 naponta, határidő 09:00\./,
  )
  await expect(notice).toContainText(
    'Az orvos indoklása: „Elég háromnaponta mérni, stabil a testsúlya.”',
  )
  // Az új előírás teendője is ott van (ma még nincs testsúlymérés).
  await expect(page.locator('.pulse-task').filter({ hasText: 'Testsúly' })).toContainText(
    'Esedékes.',
  )
})

test('követési terv, orvos: visszavonás megerősítéssel és indoklással', async ({ page }) => {
  const { plan, current, past } = await openPlan(page)
  await current.getByRole('button', { name: 'Visszavonás' }).click()
  await expect(current).toContainText('Biztosan visszavonod?')
  await current.getByLabel('Indoklás a betegnek (nem kötelező)').fill('Egyelőre nem kell mérni.')
  await current.getByRole('button', { name: 'Visszavonás' }).click()
  await expect(plan).toContainText('Az előírás visszavonva.')
  await expect(current).toHaveCount(0)
  await expect(past).toHaveCount(2)
  await expect(past.last()).toContainText('Visszavonva')
  await expect(past.last()).toContainText('Indoklás: „Egyelőre nem kell mérni.”')
})

test('a beteg a visszavonást látja, a teendő eltűnik', async ({ page }) => {
  const notice = await weightNotice(page)
  // A módosítás és a visszavonás egy láncban: egyetlen jelzés, a végállapottal.
  await expect(notice).toHaveCount(1)
  await expect(notice).toContainText(/Az orvos visszavonta ezt az előírást \(.+\)\./)
  await expect(notice).toContainText('Az orvos indoklása: „Egyelőre nem kell mérni.”')
  await page.locator('.pulse-task').first().waitFor()
  await expect(page.locator('.pulse-task').filter({ hasText: 'Testsúly' })).toHaveCount(0)
})

// A beteg szabályai az adatlap Szabályok fülén (M3, A4).
async function openRules(page: Page) {
  await login(page, 'dr.nagy@pulse.example')
  await expect(page).toHaveURL(/\/doctor$/)
  await page.getByRole('link', { name: 'Tóth Mária' }).click()
  await page.getByRole('tab', { name: 'Szabályok' }).click()
  await expect(page).toHaveURL(/\?tab=rules$/)
  return page.getByRole('region', { name: 'Tóth Mária szabályai' })
}

test('szabályok, orvos: a küszöbszabály módosítása új verziót hoz létre', async ({ page }) => {
  const rules = await openRules(page)
  // A négy típus csoportban, mindegyik a leírásával; a seed szabályai a helyükön.
  for (const type of ['Küszöbszabály', 'Időablakos szabály', 'Kérdőívszabály', 'Elmaradt adat']) {
    await expect(rules.getByRole('group', { name: type })).toBeVisible()
  }
  const threshold = rules.getByRole('article', {
    name: 'Vérnyomás: Szisztolés > 180 Hgmm',
  })
  await expect(threshold).toContainText('súlyos')
  await expect(threshold).toContainText(/1\. verzió, .+ óta/)
  await expect(
    rules.getByRole('article', {
      name: 'Vérnyomás: Szisztolés > 140 Hgmm vagy Diasztolés > 90 Hgmm, legalább 3 mérésnél 7 napon belül',
    }),
  ).toBeVisible()
  await expect(
    rules.getByRole('article', {
      name: 'Vérnyomás: 2 egymást követő alkalom elmulasztva',
    }),
  ).toBeVisible()

  // Szerkesztés: a szerkesztő az aktuális verzióval nyílik; változás nélkül nem menthető.
  await threshold.getByRole('button', { name: 'Szerkesztés' }).click()
  const editor = page.getByRole('complementary', {
    name: 'Szabály szerkesztése',
  })
  await expect(editor).toContainText('Küszöbszabály · Vérnyomás')
  await expect(editor).toContainText('1. verzió érvényes')
  const save = editor.getByRole('button', { name: 'Mentés 2. verzióként' })
  await expect(save).toBeDisabled()

  // Érvénytelen érték: az előnézet a hibát mutatja, a mentés tiltva marad.
  const upper = editor.getByLabel('Szisztolés felső határ')
  await upper.fill('20')
  await expect(editor).toContainText('Szisztolés: a határ 50 és 300 Hgmm közötti szám lehet.')
  await expect(save).toBeDisabled()

  // 180 → 175: az élő előnézet kiemeli a változott értéket.
  await upper.fill('175')
  await expect(editor.locator('.pd-preview')).toContainText(
    'Vérnyomás: Szisztolés > 175 Hgmm esetén súlyos riasztás.',
  )
  await expect(editor.locator('.pd-preview .chg')).toHaveText('175')
  await expect(save).toBeEnabled()
  await save.click()

  // A lista az új verziót mutatja, a szerkesztő a 2. verzióval nyílik újra, és a
  // verziólistában a régi is megmarad.
  await expect(rules).toContainText('A szabály módosítva, mostantól a(z) 2. verzió érvényes.')
  const changed = rules.getByRole('article', {
    name: 'Vérnyomás: Szisztolés > 175 Hgmm',
  })
  await expect(changed).toContainText(/2\. verzió, .+ óta/)
  await expect(
    rules.getByRole('article', { name: 'Vérnyomás: Szisztolés > 180 Hgmm' }),
  ).toHaveCount(0)
  await expect(editor).toContainText('2. verzió érvényes')
  await expect(editor.getByRole('button', { name: 'Mentés 3. verzióként' })).toBeDisabled()
  const versions = editor.locator('.pd-versions li')
  await expect(versions).toHaveCount(2)
  await expect(versions.first()).toContainText('2. verzió')
  await expect(versions.first()).toContainText('Szisztolés > 175 Hgmm, súlyos')
  await expect(versions.first()).toContainText('érvényes')
  await expect(versions.last()).toContainText('Szisztolés > 180 Hgmm, súlyos')
})

test('szabályok, orvos: új szabálynál előbb a típus választható, utána az űrlapja', async ({
  page,
}) => {
  const rules = await openRules(page)
  await rules.getByRole('button', { name: 'Új szabály' }).click()
  const picker = page.getByRole('complementary', {
    name: 'Milyen típusú szabály legyen?',
  })
  for (const type of ['Küszöbszabály', 'Időablakos szabály', 'Kérdőívszabály', 'Elmaradt adat']) {
    await expect(picker.getByRole('button', { name: new RegExp(`^${type}`) })).toBeVisible()
  }
  await picker.getByRole('button', { name: /^Elmaradt adat/ }).click()

  // Az elmaradt adat űrlapja: célpont (mérés vagy kérdőív) és az elmulasztások száma.
  const editor = page.getByRole('complementary', { name: 'Új szabály' })
  await expect(editor).toContainText('Elmaradt adat · Vérnyomás')
  await editor.getByLabel('Mit figyeljen?').selectOption({ label: 'Közérzet' })
  await expect(editor.locator('.pd-preview')).toContainText(
    'Közérzet: 2 egymást követő alkalom elmulasztva esetén közepes riasztás.',
  )
  await expect(editor.getByRole('button', { name: 'Mentés 1. verzióként' })).toBeEnabled()
  // Mentés nélkül vissza: a lista nem változik.
  await editor.getByRole('button', { name: 'Mégse' }).click()
  await expect(page.getByRole('complementary', { name: 'Új szabály' })).toHaveCount(0)
  await expect(
    rules.getByRole('group', { name: 'Elmaradt adat' }).getByRole('article'),
  ).toHaveCount(1)
})

// --- Riasztás-életút (M3, A6) ---------------------------------------------------------

// A Riasztások oldal szűrője: a gomb neve a darabszámmal együtt, pl. „Új (2)".
const alertFilter = (page: Page, name: string) =>
  page.getByRole('group', { name: 'Szűrés állapot szerint' }).getByRole('button', { name })
const alertRows = (page: Page) =>
  page.getByRole('region', { name: 'Nyitott riasztások' }).locator('.al-row')

test('Riasztások oldal: szűrés állapot szerint, a sorból az adatlapra, ott megtekintett lesz', async ({
  page,
}) => {
  await login(page, 'dr.kovacs@pulse.example')
  await expect(page).toHaveURL(/\/doctor$/)
  const nav = page.getByRole('navigation', { name: 'Menü' })
  const alertsLink = nav.getByRole('link', { name: /Riasztások/ })
  // A jelvény a felelős nélküli nyitott riasztások száma (Varga Béla 2, Szabó János 2).
  await expect(alertsLink).toContainText('4')
  await alertsLink.click()
  await expect(page).toHaveURL(/\/doctor\/alerts$/)
  await expect(page.getByRole('heading', { name: 'Riasztások' })).toBeVisible()

  // Szabó János riasztásai a korábbi adatlap-megnyitáskor megtekintettek lettek,
  // Varga Béláé még újak; felelős még egyiknek sincs.
  await expect(alertFilter(page, 'Mind (4)')).toHaveAttribute('aria-pressed', 'true')
  await expect(alertFilter(page, 'Felelősnél (0)')).toBeVisible()
  await alertFilter(page, 'Megtekintve (2)').click()
  await expect(alertRows(page)).toHaveCount(2)
  for (const row of await alertRows(page).all()) {
    await expect(row).toContainText('Szabó János')
    await expect(row).toContainText('Megtekintve')
    await expect(row).toContainText('Nincs felelős')
  }
  await alertFilter(page, 'Új (2)').click()
  await expect(alertRows(page)).toHaveCount(2)
  // Elöl a súlyosabb: Varga Béla küszöbriasztása.
  const first = alertRows(page).first()
  await expect(first).toContainText('Varga Béla')
  await expect(first).toContainText('Vérnyomás a határ fölött')
  await expect(first).toContainText('Küszöbszabály, 1. verzió · súlyos')

  // A sorból az adatlapra: a felület a két új riasztást megtekintettnek jelöli.
  const seen = page.waitForResponse(
    (r) => r.url().includes('/seen') && r.request().method() === 'POST',
  )
  await first.click()
  await expect(page).toHaveURL(/\/doctor\/patients\//)
  expect((await seen).status()).toBe(200)
  const card = page.getByRole('article', { name: 'Vérnyomás a határ fölött' }).first()
  await expect(card.locator('.pd-step.done')).toHaveCount(2)
  // Mindkét kártyáról eltűnt az „Új” jelölés (mindkét megtekintés beérkezett).
  await expect(page.locator('main article.pd-alert')).toHaveCount(2)
  await expect(page.locator('main .pd-chip')).toHaveCount(0)

  await alertsLink.click()
  await expect(alertFilter(page, 'Új (0)')).toBeVisible()
  await expect(alertFilter(page, 'Megtekintve (4)')).toBeVisible()
})

test('riasztás-életút, orvos: felelőshöz rendelés, lezárás indoklással és betegüzenettel', async ({
  page,
}) => {
  await login(page, 'dr.kovacs@pulse.example')
  await expect(page).toHaveURL(/\/doctor$/)
  await page.getByRole('link', { name: 'Szabó János' }).click()
  const main = page.locator('main')
  const card = main.getByRole('article', { name: 'Vérnyomás a határ fölött' })
  // A megtekintés az első megnyitáskor megtörtént: az életút második lépése kész.
  await expect(card.locator('.pd-step.done')).toHaveCount(2)
  await expect(card.locator('.pd-step.now')).toContainText('Felelőshöz rendelve')

  // Felelőshöz rendelés: a beteg orvosai közül, alapból a belépett orvos.
  await card.getByRole('button', { name: 'Felelőshöz rendelés' }).click()
  const owner = card.getByLabel('Felelős')
  await expect(owner.locator('option:checked')).toHaveText('Dr. Kovács Éva (én)')
  await card.getByRole('button', { name: 'Hozzárendelés' }).click()
  await expect(card).toContainText('Felelős: Dr. Kovács Éva')
  await expect(card.getByRole('button', { name: 'Felelőshöz rendelés' })).toHaveCount(0)
  await expect(card.locator('.pd-step.done')).toHaveCount(3)
  await expect(main.locator('.pd-status')).toContainText('ebből 1 felelősnél')

  // Lezárás: indoklás nélkül hibaüzenet; gyorsválasztó + szöveg, és üzenet a betegnek.
  await card.getByRole('button', { name: 'Lezárás…' }).click()
  const dialog = page.getByRole('dialog', { name: 'Riasztás lezárása' })
  await expect(dialog).toContainText('Vérnyomás a határ fölött · Szabó János')
  await dialog.getByRole('button', { name: 'Lezárás', exact: true }).click()
  await expect(dialog).toContainText('Az indoklás kötelező.')
  const quick = dialog.getByRole('button', { name: 'Telefonon egyeztetve' })
  await quick.click()
  const reason = dialog.getByRole('textbox', { name: /^Indoklás/ })
  await expect(reason).toHaveValue('Telefonon egyeztetve.')
  await expect(quick).toHaveAttribute('aria-pressed', 'true')
  await reason.fill('Telefonon egyeztetve. A gyógyszerelés marad, kontroll két hét múlva.')
  await expect(dialog).toContainText('A beteg a Teendőim oldalon olvassa. Válaszolni nem tud rá.')
  await dialog
    .getByRole('textbox', { name: /^Visszajelzés a betegnek/ })
    .fill('Átnéztem a méréseit, a gyógyszerelés marad. Két hét múlva újra beszélünk.')
  await dialog.getByRole('button', { name: 'Lezárás', exact: true }).click()
  await expect(dialog).toHaveCount(0)

  // A kártya lezárt alakra vált: ki és mikor zárta le, az indoklás, kinyitható történet.
  const closed = main.getByRole('article', { name: 'Vérnyomás a határ fölött, lezárva' })
  await expect(closed).toContainText(/Lezárva .+ · Dr\. Kovács Éva/)
  await expect(closed).toContainText('A gyógyszerelés marad, kontroll két hét múlva.')
  await closed.getByText(/Eseménytörténet/).click()
  const timeline = closed.locator('.pd-timeline')
  await expect(timeline.locator('li').first()).toContainText('Lezárva · Dr. Kovács Éva')
  await expect(timeline.locator('li').first()).toContainText('Indoklás: „Telefonon egyeztetve.')
  await expect(timeline).toContainText('Felelőshöz rendelve · felelős: Dr. Kovács Éva')
  await expect(timeline).toContainText('Megtekintve · Dr. Kovács Éva')

  // A kérdőív-riasztás lezárása közvetlenül a megtekintettből (a lépés kihagyható).
  const other = main.locator('article.pd-alert:not(.closed)')
  await expect(other).toHaveCount(1)
  await other.getByRole('button', { name: 'Lezárás…' }).click()
  await dialog.getByRole('button', { name: 'Nem igényel beavatkozást' }).click()
  await dialog.getByRole('button', { name: 'Lezárás', exact: true }).click()
  await expect(dialog).toHaveCount(0)
  await expect(main.locator('article.pd-alert:not(.closed)')).toHaveCount(0)

  // Lezárás után a státusz Kezelve, amíg megerősítő adat nem érkezik (07-es dokumentum).
  await expect(main.locator('.pd-status')).toContainText('Kezelve')
  const nav = page.getByRole('navigation', { name: 'Menü' })
  await nav.getByRole('link', { name: /Betegeim/ }).click()
  await expect(page).toHaveURL(/\/doctor$/)
  await page.locator('.pulse-prow').first().waitFor()
  const rows = await rowsText(page)
  expect(rows.map((r) => r.split(' ')[0])).toEqual(['Súlyos', 'Adathiány', 'Kezelve', 'Rendben'])
  expect(rows[2]).toContain('Szabó János')
  expect(rows[2]).toContain('Dr. Kovács Éva lezárta, megerősítő adat még nem érkezett')
  // Két lezárás ugyanattól az orvostól: az ok egyszer szerepel.
  expect(rows[2].split('lezárta')).toHaveLength(2)
})

test('a beteg a Teendőim oldalon látja az orvos visszajelzését', async ({ page }) => {
  await login(page, 'szabo.janos@pulse.example')
  await expect(page).toHaveURL(/\/patient$/)
  const feedback = page.getByRole('region', { name: 'Visszajelzések az orvosodtól' })
  await expect(feedback.locator('.pulse-msg')).toHaveCount(1)
  await expect(feedback).toContainText(
    /Dr\. Kovács Éva\s*visszajelzése a\(z\) vérnyomás-riasztás lezárásakor · \S+/,
  )
  await expect(feedback).toContainText(
    'Átnéztem a méréseit, a gyógyszerelés marad. Két hét múlva újra beszélünk.',
  )
  // A belső indoklás nem a betegnek szól.
  await expect(page.locator('main')).not.toContainText('kontroll két hét múlva')
})
