# Funkcionális specifikáció

A követelményeket az első mérföldkőben rögzítettem, és a témavezetői
visszajelzés alapján pontosítottam. A funkcionális követelmények F1–F20, a
nem funkcionálisak NF1–NF9 azonosítót kaptak (az NF9 az októberi integrációs
iránnyal került be). Ezekre a tesztek és a dokumentáció is hivatkozik.

A táblázatok utolsó két oszlopa a második mérföldkő (M2) állapotát mutatja.
**Bemutatható:** elejétől végéig működik, és teszt ellenőrzi. **Részben:** egy
része kész; a cella megnevezi a hiányzó részt és a mérföldkövet, amelyben
elkészül. **Terv:** még nem készült el. A bizonyítékok a backend tesztfájljai
(`backend/tests/`) és a böngészős folyamatteszt (`e2e/`). Ez utóbbi a felületen
viszi végig a két M2-folyamatot hat lépésben: az orvosi lista (1.), a riasztás
magyarázata (2.), idegen beteg adatlapja (3.), mérés rögzítése (4.), kérdőív
kitöltése (5.) és a jelzés az orvosnál (6.).

## Szereplők és használati esetek

A rendszernek három emberi szereplője van, a beteg, az orvos és az admin,
valamint egy rendszerszereplő, az időzítő (@abra:usecase). Minden használati
eset bejelentkezést feltételez, ezért a bejelentkezés külön nem szerepel az
ábrán.

![A PULSE használati esetei](images/use_case.png){#abra:usecase}

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
| F5 | A korábbi mérések listában és grafikonon, típusonként, időszakszűréssel. | részben | a lista napokra bontva és a típus szerinti szűrés kész (`test_measurements.py`, böngészős teszt 4.), típusonként egy kis görbe az utolsó mérésekről; a teljes grafikon és az időszakszűrés: M3 |
| F6 | Az esedékes teendők listája határidővel; a kirendelt kérdőívek kitöltése. | részben | a kitöltés és a határidős teendőlista kész: mi esedékes, mi kész, mi maradt el, az előírásokból számolva (`test_tasks.py`, böngészős teszt 4. és 5.); az alkalmak tárolása: M3 |
| F7 | Hibás mérés javítása újrakiértékeléssel; mérés legfeljebb két napra visszamenőleg; a felület felajánlja a pótolható alkalmat. | részben | a kétnapos határ és a pótolható alkalom felajánlása kész (`test_measurements.py`, `test_tasks.py`, böngészős teszt 4.); a javítás: M3 |
| F8 | Értesítés az esedékes teendőkről (felületen és e-mailben). | terv | M3 |

### Orvos

| Az. | Követelmény | Állapot | Mi bizonyítja, mi hiányzik |
|-------|----------------------------|-------------|------------------------------|
| F9 | Priorizált beteglista öt státusszal (Súlyos, Figyelem, Adathiány, Kezelve, Rendben), egy mondatos indoklással; sem a lezárás, sem az adathiány nem ad Rendben státuszt. | részben | négy státusz indoklással, státusz szerinti szűréssel, név szerinti kereséssel és a teendők állapotával kész (`test_status.py`, `test_tasks.py`, böngészős teszt 1. és 6.); a Kezelve a riasztáslezárással: M3 |
| F10 | A beteg adatlapja: grafikonok küszöbvonalakkal, mérések, kitöltések, riasztások magyarázattal, megjegyzések. | részben | a riasztások magyarázattal és idővonallal, a teendők teljesítése, a mérések (a riasztást kiváltók jelölve) és a kitöltések kész (böngészős teszt 2. és 6.); a grafikonok küszöbvonallal és a megjegyzések: M3 |
| F11 | Négy, betegenként paraméterezhető szabálytípus: egyszeri küszöbátlépés; időablakos ismétlődés; kérdőív-pontszám határa vagy romló trendje; elmaradt adatküldés. | részben | a küszöbszabály és a kérdőív-sáv kész (`test_rules.py`, `test_questionnaires.py`); az időablakos ismétlődés, a romló trend, az elmaradt adat és a beállító felület: M3 |
| F12 | Minden szabálymódosítás új, megváltoztathatatlan verziót hoz létre; a riasztás a keletkezéskori verzióra hivatkozik. | részben | az adatbázisban kész, triggerrel védve (`test_rules.py`); a módosító felület: M3 |
| F13 | Kérdőívszerkesztő (skálás, egy- és többválasztós kérdések, pontozás, kiértékelési sávok); egységes pontozási irány; minden módosítás új verzió. | részben | a pontozás, a sávok és a verziózás kész (`test_questionnaires.py`); a szerkesztő: M3 |
| F14 | Követési terv: mit, milyen gyakran, milyen határidőre, mettől meddig; az alkalmak külön rögzülnek; a határidőket háttérfolyamat ellenőrzi. | részben | az előírás táblája kész, az időszak és a határidő ebből számolódik, a kérdőív csak kirendelés alapján tölthető ki (`test_tasks.py`, `test_questionnaires.py`); az alkalmak tárolása, a háttérfolyamat és az orvosi felület: M3 |
| F15 | Riasztáskezelés: megtekintés, felelőshöz rendelés, lezárás kötelező indoklással; minden váltás eseményként rögzül; lezáráskor rövid, a betegnek szóló visszajelzés küldhető. | terv | M3 |
| F16 | Megjegyzés a beteghez. | terv | M3 |

### Riasztások

| Az. | Követelmény | Állapot | Mi bizonyítja, mi hiányzik |
|-------|----------------------------|-------------|------------------------------|
| F17 | Minden riasztás és esemény tárolja az alkalmazott szabályverziót és a kiváltó adatokat, ebből olvasható magyarázat készül. Szabálymódosítás után ugyanaz a riasztás folytatódik; javított kiváltó adatnál a riasztás megjelölődik, és az orvos zárja le. | részben | a verzió, a kiváltó adat és a magyarázat kész (`test_rules.py`, böngészős teszt 2.); a módosítás- és a javítás-esemény: M3 |
| F18 | Deduplikáció: nyitott riasztás mellett az új kiváltó adat „ismételt aktiválódás" esemény, a súlyosság emelkedhet. | bemutatható | `test_rules.py`, `test_questionnaires.py` (ismételt aktiválódás, a súlyosság nem csökken, adatbázisszinten is csak egy nyitott riasztás); böngészős teszt 2. |
| F19 | A riasztás adatbázis-tranzakcióban jön létre, az e-mail ettől elkülönítve, újrapróbálkozással megy ki. | részben | a riasztás a méréssel vagy a kitöltéssel egy tranzakcióban jön létre; az e-mail: M3 |

### Admin

| Az. | Követelmény | Állapot | Mi bizonyítja, mi hiányzik |
|-------|----------------------------|-------------|------------------------------|
| F20 | Felhasználók, orvos–beteg összerendelések és méréstípusok kezelése. | terv | most a demóadat-betöltő hozza létre őket (`test_seed.py`); a végpontok és a felület: M3 |

## Nem funkcionális követelmények

| Az. | Követelmény | Állapot | Mi bizonyítja, mi hiányzik |
|-------|----------------------------|-------------|------------------------------|
| NF1 | Biztonság: JWT-alapú hitelesítés, hashelt jelszó, szerveroldali jogosultság, célzott tesztekkel. | bemutatható | Argon2-hash; `test_security.py`, `test_auth_api.py`, `test_access.py`, valamint a követelményekből függetlenül írt tesztek (`independent_*`) |
| NF2 | Auditálhatóság: a verziók megváltoztathatatlanok, a riasztásokhoz teljes eseménytörténet tartozik. | részben | a verziók és az események adatbázis-triggerrel védettek (`test_rules.py`, `test_questionnaires.py`); a riasztás-életút eseményei: M3 |
| NF3 | Tesztelés: pytest, legalább 70% lefedettség, kiemelt határesetekkel. | bemutatható | 430 backend-teszt, 98% lefedettség; a CI 70% alatt hibát jelez; a böngészős folyamatteszt is a CI-ban fut |
| NF4 | Teljesítmény: a kiértékelés és a fő végpontok ideje mérve, növekvő adatmennyiségnél. | terv | M4 |
| NF5 | Telepíthetőség: Docker, GitHub Actions CI/CD, nyilvános demókörnyezet. | részben | Docker és CI kész (a CI a böngészős tesztet a Dockerben indított rendszeren futtatja); a CD és a demókörnyezet: M4 |
| NF6 | Dokumentáltság: OpenAPI/Swagger, fejlesztői dokumentáció a repóban. | bemutatható | Swagger (`/api/docs`), a README indítási leírása |
| NF7 | Nemzetköziesítés: magyar és angol felület. | részben | a felület szövegei kétnyelvűek; a nyelvváltó: M3 |
| NF8 | Korlátok: demonstrációs rendszer, kizárólag mesterséges adattal, nem orvostechnikai eszköz. | bemutatható | a belépőoldalon és a README-ben kiírva; a demóadat mesterséges |
| NF9 | Szabványos adatcsere és kiértékelés: a mérések és a kérdőívek FHIR R4 formában is kiadhatók (Observation LOINC- és UCUM-kóddal, Questionnaire, QuestionnaireResponse); egy klinikai ajánláson alapuló szabály CQL-ben, meglévő motorral kiértékelhető. | részben | a LOINC- és UCUM-kódok a törzsadatban (`test_measurements.py`); a CQL-próba kész, független kézi számítással ellenőrizve (lásd a Működés fejezetet); a FHIR-kiadás és a beépítés: M3 |

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
