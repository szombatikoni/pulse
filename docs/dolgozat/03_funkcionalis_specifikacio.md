# Funkcionális specifikáció

A követelményeket az első mérföldkőben rögzítettem, és a témavezetői
visszajelzés alapján pontosítottam. A funkcionális követelmények F1–F20, a
nem funkcionálisak NF1–NF9 azonosítót kaptak (az NF9 az októberi integrációs
iránnyal került be). Ezekre a tesztek és a dokumentáció is hivatkozik.

A táblázatok utolsó két oszlopa a harmadik mérföldkő (M3) közbeni állapotot
mutatja.
**Bemutatható:** elejétől végéig működik, és teszt ellenőrzi. **Részben:** egy
része kész; a cella megnevezi a hiányzó részt és a mérföldkövet, amelyben
elkészül. **Terv:** még nem készült el. A bizonyítékok a backend tesztfájljai
(`backend/tests/`) és a böngészős folyamattesztek (`e2e/`, három fájlban 25
teszt). A táblázatok sorszámai a fő fájlra (`m2_folyamatok.spec.ts`)
hivatkoznak, amely a felületen 17 lépésben viszi végig a folyamatokat; a
kérdőívszerkesztőt (3 teszt) és a NICE-panelt (5 teszt) külön fájl
ellenőrzi. Az első hat lépés a két M2-folyamat: az
orvosi lista (1.), a riasztás magyarázata (2.), idegen beteg adatlapja (3.),
mérés rögzítése (4.), kérdőív kitöltése (5.) és a jelzés az orvosnál (6.). A
többi a követési terv (7–10.), a szabályok (11–12.), a riasztáskezelés
(13–15.) és a mérésjavítás (16–17.).

## Szereplők és használati esetek

A rendszernek három emberi szereplője van, a beteg, az orvos és az admin,
valamint egy rendszerszereplő, az időzítő (@abra:usecase). Minden használati
eset bejelentkezést feltételez, ezért a bejelentkezés külön nem szerepel az
ábrán.

![A PULSE használati esetei](images/use_case.png){#abra:usecase}

A felület oldalait és a köztük lévő átmeneteket szerepkörönként a
@abra:pageflow mutatja, a jelenleg elkészült állapot szerint.

![A felület oldalai és átmenetei szerepkörönként](images/dolgozat_pageflow.png){#abra:pageflow}

**A beteg** méréseket rögzít (például vérnyomást: a szisztolés és a
diasztolés érték egy mérésben), és utólag javíthatja a hibásan rögzített
mérést. Látja a korábbi méréseit, az esedékes teendőit (előírt mérések és
kérdőívek, határidővel), kitölti a neki kirendelt kérdőíveket, és értesítést
kap a teendőiről.

**Az orvos** a hozzá rendelt betegeket priorizált listán látja, ahol minden
beteg mellett egy státusz és egy mondatos indoklás áll. A beteg adatlapján a
riasztásokat magyarázattal, a méréseket és a kitöltéseket grafikonon is
látja. Betegenként szabályokat állít be, kérdőíveket szerkeszt, követési
tervet állít össze, kezeli a riasztásokat (megtekintés, felelőshöz rendelés,
lezárás indoklással), és megjegyzést írhat a beteghez.

**Az admin** a felhasználókat, az orvos–beteg összerendeléseket és a
méréstípus-törzsadatokat kezeli.

**Az időzítő** a háttérfolyamatot jelképezi. Rendszeres időközönként
felhasználói kérés nélkül ellenőrzi a határidőket, így az elmaradt adatot is
felismeri.

A **szabálykiértékelés** önálló használati eset, amelyet több másik magában
foglal («include»): a mérés rögzítése és javítása, a kérdőív kitöltése és a
határidők ellenőrzése. Így minden új vagy megváltozott adatot ugyanaz a
szabálymotor értékel ki, ugyanazokkal a szabályokkal.

## Funkcionális követelmények

### Hitelesítés és hozzáférés

| Az. | Követelmény | Állapot | Mi bizonyítja, mi hiányzik |
|-------|----------------------------|-------------|------------------------------|
| F1 | E-mail és jelszó alapú bejelentkezés (JWT); három szerepkör: beteg, orvos, admin. | bemutatható | `test_auth_api.py`, `test_security.py`; a böngészős teszt minden lépése belépéssel indul |
| F2 | Minden végpont szerveroldalon szűr: a beteg csak a saját adatait, az orvos csak a hozzá rendelt betegekét, az admin az adminisztratív erőforrásokat éri el. | bemutatható | `test_access.py`, `test_patient_api.py`, `test_questionnaire_api.py` (idegen beteg, admin, bejelentkezés nélkül); böngészős teszt 3. |
| F3 | Az orvos–beteg összerendelés időbeli érvényességű; megszűnésekor a hozzáférés azonnal megszűnik, létrejöttekor megnyílik. | bemutatható | `test_access.py`, `test_patient_api.py` (a megszüntetés és a létrehozás azonnal hat); az összerendelés felületét az F20 adja |

### Beteg

| Az. | Követelmény | Állapot | Mi bizonyítja, mi hiányzik |
|-------|----------------------------|-------------|------------------------------|
| F4 | Mérés rögzítése a törzsadatban szereplő típusokhoz, többértékű méréssel. | bemutatható | `test_measurements.py`, `test_patient_api.py` (teljes folyamat a rögzítéstől az orvosi nézetig); böngészős teszt 4. |
| F5 | A korábbi mérések listában és grafikonon, típusonként, időszakszűréssel. | részben | a lista napokra bontva és a típus szerinti szűrés kész (`test_measurements.py`, böngészős teszt 4.); a grafikon 14, 30 vagy 90 napos időszakkal az Előzményeim oldalon elkészült, de teszt még nem ellenőrzi |
| F6 | Az esedékes teendők listája határidővel; a kirendelt kérdőívek kitöltése. | bemutatható | a kitöltés és a határidős teendőlista: mi esedékes, mi kész, mi maradt el, a tárolt alkalmakból (`test_tasks.py`, `test_occurrences.py`, böngészős teszt 4. és 5.) |
| F7 | Hibás mérés javítása újrakiértékeléssel; mérés legfeljebb két napra visszamenőleg; a felület felajánlja a pótolható alkalmat. | bemutatható | a kétnapos határ és a pótolható alkalom felajánlása (`test_measurements.py`, `test_tasks.py`, böngészős teszt 4.); a javítás újrakiértékeléssel (`test_measurement_correction.py`, böngészős teszt 16. és 17.) |
| F8 | Értesítés az esedékes teendőkről (felületen és e-mailben). | részben | a felületen a beteg a teendői között látja az előírás változásait és az orvos visszajelzését (`test_plan_changes.py`, `test_alert_lifecycle.py`, böngészős teszt 8., 10. és 15.); az e-mail: M4 |

### Orvos

| Az. | Követelmény | Állapot | Mi bizonyítja, mi hiányzik |
|-------|----------------------------|-------------|------------------------------|
| F9 | Priorizált beteglista öt státusszal (Súlyos, Figyelem, Adathiány, Kezelve, Rendben), egy mondatos indoklással; sem a lezárás, sem az adathiány nem ad Rendben státuszt. | bemutatható | öt státusz indoklással, státusz szerinti szűréssel, név szerinti kereséssel és a teendők állapotával (`test_status.py`, `test_tasks.py`, `test_alert_lifecycle.py`, böngészős teszt 1., 6. és 14.) |
| F10 | A beteg adatlapja: grafikonok küszöbvonalakkal, mérések, kitöltések, riasztások magyarázattal, megjegyzések. | részben | a riasztások magyarázattal és idővonallal, a teendők teljesítése, a mérések (a riasztást kiváltók jelölve), a kitöltések és a grafikonok a szabályok határvonalaival kész (böngészős teszt 2. és 6.; a grafikont teszt még nem ellenőrzi); a megjegyzések: M3 |
| F11 | Négy, betegenként paraméterezhető szabálytípus: egyszeri küszöbátlépés; időablakos ismétlődés; kérdőív-pontszám határa vagy romló trendje; elmaradt adatküldés. | bemutatható | mind a négy típus és a beállító felület (`test_rules.py`, `test_rule_types.py`, `test_questionnaires.py`, `test_rules_api.py`, böngészős teszt 11. és 12.) |
| F12 | Minden szabálymódosítás új, megváltoztathatatlan verziót hoz létre; a riasztás a keletkezéskori verzióra hivatkozik. | bemutatható | az adatbázisban triggerrel védve (`test_rules.py`); a módosítás a felületről új verziót hoz létre (`test_rules_api.py`, böngészős teszt 11.) |
| F13 | Kérdőívszerkesztő (skálás, egy- és többválasztós kérdések, pontozás, kiértékelési sávok); egységes pontozási irány; minden módosítás új verzió. | bemutatható | a pontozás, a sávok és a verziózás (`test_questionnaires.py`); a szerkesztő új kérdőívvel és új verzióval (`test_questionnaire_editor_api.py`, böngészős teszt: `m3_a5_kerdoivszerkeszto.spec.ts`) |
| F14 | Követési terv: mit, milyen gyakran, milyen határidőre, mettől meddig; az alkalmak külön rögzülnek; a határidőket háttérfolyamat ellenőrzi. | bemutatható | az előírás, a tárolt alkalmak és a háttérfolyamat (`test_tasks.py`, `test_occurrences.py`, `test_worker.py`); az orvosi felület új előírással, módosítással és visszavonással (`test_plans_api.py`, `test_plan_changes.py`, böngészős teszt 7–10.) |
| F15 | Riasztáskezelés: megtekintés, felelőshöz rendelés, lezárás kötelező indoklással; minden váltás eseményként rögzül; lezáráskor rövid, a betegnek szóló visszajelzés küldhető. | bemutatható | `test_alert_lifecycle.py`, `test_alerts_api.py`; böngészős teszt 13–15. |
| F16 | Megjegyzés a beteghez. | terv | M3 |

### Riasztások

| Az. | Követelmény | Állapot | Mi bizonyítja, mi hiányzik |
|-------|----------------------------|-------------|------------------------------|
| F17 | Minden riasztás és esemény tárolja az alkalmazott szabályverziót és a kiváltó adatokat, ebből olvasható magyarázat készül. Szabálymódosítás után ugyanaz a riasztás folytatódik; javított kiváltó adatnál a riasztás megjelölődik, és az orvos zárja le. | bemutatható | a verzió, a kiváltó adat és a magyarázat (`test_rules.py`, böngészős teszt 2.); a módosítás eseménye (`test_rules_api.py`, böngészős teszt 11.) és a javításé (`test_measurement_correction.py`, böngészős teszt 17.) |
| F18 | Deduplikáció: nyitott riasztás mellett az új kiváltó adat „ismételt aktiválódás" esemény, a súlyosság emelkedhet. | bemutatható | `test_rules.py`, `test_questionnaires.py` (ismételt aktiválódás, a súlyosság nem csökken, adatbázisszinten is csak egy nyitott riasztás); böngészős teszt 2. |
| F19 | A riasztás adatbázis-tranzakcióban jön létre, az e-mail ettől elkülönítve, újrapróbálkozással megy ki. | részben | a riasztás a méréssel vagy a kitöltéssel egy tranzakcióban jön létre; az e-mail: M3 |

### Admin

| Az. | Követelmény | Állapot | Mi bizonyítja, mi hiányzik |
|-------|----------------------------|-------------|------------------------------|
| F20 | Felhasználók, orvos–beteg összerendelések és méréstípusok kezelése. | terv | most a demóadat-betöltő hozza létre őket (`test_seed.py`); az admin egyelőre csak az alkalmak ellenőrzését indíthatja el kézzel (`test_admin_api.py`); a többi végpont és a felület: M3 |

## Nem funkcionális követelmények

| Az. | Követelmény | Állapot | Mi bizonyítja, mi hiányzik |
|-------|----------------------------|-------------|------------------------------|
| NF1 | Biztonság: JWT-alapú hitelesítés, hashelt jelszó, szerveroldali jogosultság, célzott tesztekkel. | bemutatható | Argon2-hash; `test_security.py`, `test_auth_api.py`, `test_access.py`, valamint a követelményekből függetlenül írt tesztek (`independent_*`) |
| NF2 | Auditálhatóság: a verziók megváltoztathatatlanok, a riasztásokhoz teljes eseménytörténet tartozik. | bemutatható | a verziók és az események adatbázis-triggerrel védettek (`test_rules.py`, `test_questionnaires.py`); a riasztás-életút minden váltása esemény (`test_alert_lifecycle.py`) |
| NF3 | Tesztelés: pytest, legalább 70% lefedettség, kiemelt határesetekkel. | bemutatható | 710 backend-tesztfüggvény (futáskor 983 eset); a CI 70% alatti lefedettségnél hibát jelez; a böngészős folyamatteszt is a CI-ban fut |
| NF4 | Teljesítmény: a kiértékelés és a fő végpontok ideje mérve, növekvő adatmennyiségnél. | terv | M4 |
| NF5 | Telepíthetőség: Docker, GitHub Actions CI/CD, nyilvános demókörnyezet. | részben | Docker és CI kész (a CI a böngészős tesztet a Dockerben indított rendszeren futtatja); a CD és a demókörnyezet: M4 |
| NF6 | Dokumentáltság: OpenAPI/Swagger, fejlesztői dokumentáció a repóban. | bemutatható | Swagger (`/api/docs`), a README indítási leírása |
| NF7 | Nemzetköziesítés: magyar és angol felület. | részben | a felület szövegei kétnyelvűek; a nyelvváltó: M4 |
| NF8 | Korlátok: demonstrációs rendszer, kizárólag mesterséges adattal, nem orvostechnikai eszköz. | bemutatható | a belépőoldalon és a README-ben kiírva; a demóadat mesterséges |
| NF9 | Szabványos adatcsere és kiértékelés: a mérések és a kérdőívek FHIR R4 formában is kiadhatók (Observation LOINC- és UCUM-kóddal, Questionnaire, QuestionnaireResponse); egy klinikai ajánláson alapuló szabály CQL-ben, meglévő motorral kiértékelhető. | bemutatható | a LOINC- és UCUM-kódok a törzsadatban (`test_measurements.py`); a CQL-próba kész, független kézi számítással ellenőrizve (lásd a Működés fejezetet); a FHIR-kiadás kész (`test_fhir.py`); a CQL-motor külön konténerben fut, a backend egy végpontja hívja, és az eredményét saját számítással veti össze (`test_nice.py`, `test_nice_api.py`, `test_cql_client.py`); az eredményt az orvosi adatlap tájékoztató panelje mutatja, nem tárolódik, és nem hat a státuszra (böngészős teszt: `k2_nice.spec.ts`) |

## Ami nem része a vállalásnak

A rendszer a krónikus betegek otthoni adatainak követésére és az orvosi
figyelem irányítására összpontosít. Tudatosan kimaradt:

- a gyógyszerelés nyilvántartása;
- az időpontfoglalás;
- a kétirányú üzenetküldés orvos és beteg között (továbbfejlesztési
  lehetőség; a tervben csak egyirányú orvosi visszajelzés szerepel a riasztás
  lezárásakor);
- a mérőeszközök automatikus csatlakoztatása (a beteg kézzel rögzít);
- a diagnózis felállítása (a rendszer a kezelés követését segíti);
- az éles használat valódi betegadatokkal;
- a külön mobilalkalmazás (a felület webes).

## A felület képernyői

A képek a futó alkalmazásról készültek, frissen betöltött, mesterséges
demóadatokkal. Először a beteg, utána az orvos felületét mutatom be.

A belépőoldalon (@abra:kep_belepes) e-mail-címmel és jelszóval lehet
belépni. A bemutató fiókok közül egyre kattintva a felület kitölti az
e-mail-címet. Az oldal alján a demonstrációs jellegre figyelmeztető szöveg áll.

![A belépőoldal](images/kepernyo_01_belepes.png){#abra:kep_belepes}

A beteg belépés után a mai teendőit látja (@abra:kep_teendok): előírásonként
egy kártyát a gyakorisággal, a határidővel és az állapottal (esedékes, kész).
Az elmaradt, de még pótolható mérést a kártya külön jelzi, a Pótlás gombbal
rögzíthető. A felső sáv a napi teendők teljesítését mutatja.

![A beteg kezdőoldala az esedékes teendőkkel](images/kepernyo_02_beteg_teendok.png){#abra:kep_teendok}

Előírás nélküli mérésnél a beteg előbb a méréstípust választja ki
(@abra:kep_meres). A vérnyomás két értéke egy mérésben rögzül. A képen
elgépelt szisztolés érték látszik: a szerver elutasítja, a hibaüzenet a mező
alatt jelenik meg, a beírt érték pedig megmarad, hogy javítható legyen. A
mérés ideje alapból az aktuális időpont, a Másik időpont gombbal korábbi is
megadható.

![Vérnyomásmérés rögzítése, a tartományon kívüli érték hibaüzenetével](images/kepernyo_03_meres_rogzites.png){#abra:kep_meres}

Az Előzményeim oldalon (@abra:kep_elozmenyek) a beteg a legutóbbi értékeit
és a méréseit grafikonon látja 14, 30 vagy 90 napra, és táblázatnézetre is
válthat. A vérnyomás egy függőleges szakasz: a felső pont a szisztolés, az
alsó a diasztolés érték. A grafikon értékelés nélkül mutatja a méréseket,
ahogy az oldal felirata is jelzi.

![A beteg előzményei a vérnyomás grafikonjával](images/kepernyo_04_beteg_elozmenyek.png){#abra:kep_elozmenyek}

A kirendelt kérdőív saját oldalon nyílik meg (@abra:kep_kerdoiv). A skálás
kérdéseknél a skála két végének felirata segít, az egyválasztós kérdés
lehetőségei gombként jelennek meg. A Beküldés gomb akkor aktív, ha minden
kérdésre van válasz. A pontszámot és a sávot a beteg nem látja.

![Kérdőív kitöltése a beküldés előtt](images/kepernyo_05_kerdoiv_kitoltes.png){#abra:kep_kerdoiv}

Az orvos kezdőoldala a hozzá rendelt betegek priorizált listája
(@abra:kep_beteglista). A felső kártyák státuszonként számolnak, és szűrőként
is működnek. A sorok csoportokban állnak (Döntésre vár, Figyelendő, Rendben);
minden sorban a státusz, az ok, a teendők állapota és az utolsó adat ideje
látszik. A demóadatban négy státusz fordul elő, Kezelve státuszú beteg nincs.

![Az orvos beteglistája a státuszokkal](images/kepernyo_06_orvos_beteglista.png){#abra:kep_beteglista}

A beteg adatlapjának Áttekintés fülén felül a nyitott riasztások állnak
(@abra:kep_adatlap). A riasztás kártyája megmutatja, melyik szabály melyik
verziója jelzett, mi volt a feltétel, és mely mérések váltották ki. Alatta az
életút lépései látszanak, innen lehet a riasztást felelőshöz rendelni vagy
lezárni. Jobb oldalon a teendők teljesítése és a követési terv áll, ahol új
előírás vehető fel, a meglévő pedig módosítható vagy visszavonható.

![A beteg adatlapja, Áttekintés fül](images/kepernyo_07_adatlap_attekintes.png){#abra:kep_adatlap}

Ugyanezen a fülön lejjebb a NICE-panel és a mérések grafikonjai következnek
(@abra:kep_nice). A panel a Kiértékelés gombra kiszámolja az otthoni
vérnyomásátlagot a CQL-motorral és a saját számítással is, és kiírja, hogy a
kettő egyezik-e. Az eredmény nem tárolódik, a státuszt és a riasztásokat nem
változtatja. A grafikonon a szabályok határai szaggatott vonalként, a
riasztást kiváltó mérések bekarikázva jelennek meg.

![A NICE-panel kiértékelés után és a vérnyomás grafikonja a határvonalakkal](images/kepernyo_08_adatlap_nice_grafikon.png){#abra:kep_nice}

A Riasztások oldal (@abra:kep_riasztasok) az orvos összes betegének nyitott
riasztásait mutatja egy listában, elöl a súlyosabbal, állapot szerint
szűrhetően. A sor a beteget, a szabályt és a verzióját, a kiváltó értéket, az
állapotot, a keletkezés idejét és a felelőst tartalmazza; a sorra kattintva a
beteg adatlapja nyílik meg.

![A Riasztások oldal](images/kepernyo_09_riasztasok.png){#abra:kep_riasztasok}

Egy riasztás kinyitott eseménytörténetét a @abra:kep_riasztas mutatja. A
riasztás három határsértő mérés után keletkezett. A negyedik mérés nem nyitott
újat, hanem ismételt aktiválódásként kapcsolódott hozzá, mert ugyanarra a
szabályra már volt nyitott riasztás. A megtekintés az orvos nevével rögzült.

![Egy riasztás részletei a magyarázattal és az eseménytörténettel](images/kepernyo_10_riasztas_reszletek.png){#abra:kep_riasztas}

A Szabályok fülön (@abra:kep_szabaly) a beteg szabályai a négy típus szerint
csoportosítva állnak, mindegyiknél a súlyosság és az érvényes verzió. A képen
a küszöbszabály szerkesztője látszik mentés előtt: a felső határ 180 helyett
175, az előnézet kiemeli a változott értéket, a gomb pedig jelzi, hogy a
mentés 2. verzióként történik. Alul a szabály verziói állnak.

![A szabályok és a küszöbszabály szerkesztése](images/kepernyo_11_szabalyszerkeszto.png){#abra:kep_szabaly}

A Kérdőívek menüpontból nyíló szerkesztőben (@abra:kep_kerdoivszerk) az orvos
a kérdések típusát (skála, egy válasz, több válasz), szövegét és pontozását
állítja be. Skálás kérdésnél meg kell adni, melyik vég jelenti a jobb
állapotot, a pontokat a felület ebből számolja. Jobb oldalon a három rögzített
sáv két határa állítható, alatta a verziók listája áll. Változtatás nélkül a
mentés nem lehetséges.

![A kérdőívszerkesztő a Közérzet kérdőívvel](images/kepernyo_12_kerdoivszerkeszto.png){#abra:kep_kerdoivszerk}
