# Architektúra

A PULSE háromrétegű webalkalmazás. A böngészőben futó felület REST-interfészen
keresztül éri el a backendet, és az adatbázishoz kizárólag a backend fér hozzá.
Minden komponens külön Docker-konténerben fut, a teljes rendszert egyetlen
`docker compose up` parancs indítja el. A @abra:architektura a jelenlegi
felépítést mutatja: folytonos kerettel a második mérföldkőig elkészült részeket
(felület, backend, adatbázis), szaggatottal a tervezetteket: a háttérfolyamat és
az e-mail-küldés a fejlesztői levelezővel (Mailpit) a követési tervekkel együtt,
a folyamatos telepítés (CD) pedig a negyedik mérföldkőben kerül be.

![A PULSE architektúrája](images/dolgozat_architektura.png){#abra:architektura}

## A komponensek

### Felület

A felület React-alapú, TypeScriptben írt egyoldalas alkalmazás (SPA), amelyet
a Vite fordít. A komponenseket a Mantine könyvtár adja. A szerverről érkező
adatokat a React Query kezeli: gyorsítótáraz, és kezeli a betöltési és a
hibaállapotot, így ezt nem kell oldalanként kézzel megírni. A szövegek
i18next-tel magyarul és angolul is elérhetők.

Telepített formában a felület lefordított, statikus fájlokból áll, ezeket egy
nginx-webszerver szolgálja ki. Az nginx a `/api/` kezdetű kéréseket továbbítja
a backendnek, így a böngésző egyetlen címmel beszél, és nincs szükség
CORS-beállításra. Fejlesztés közben ugyanezt a Vite fejlesztői szervere végzi.

A felület jogosultsági döntést nem hoz. Azt jeleníti meg, amit a backend
visszaad; ha egy gomb vagy menüpont rejtve marad, az csak kényelmi funkció, a
védelmet a szerver adja.

### Backend

A backend Python 3.12-ben, FastAPI-keretrendszerrel készült, és három rétegre
tagolódik:

- **végpontok** (`app/api`): átveszik a kérést, Pydantic-sémákkal ellenőrzik a
  bemenetet, és függőségként vizsgálják a bejelentkezést és a szerepkört;
- **szolgáltatások** (`app/services`): itt van az üzleti logika, például a
  mérésrögzítés, a kérdőívkitöltés, a szabálykiértékelés, a státuszszámítás és
  a hozzáférés-ellenőrzés;
- **modellek** (`app/models`): az adatbázistáblák SQLAlchemy 2-osztályai.

A végpont nem ír közvetlenül az adatbázisba, hanem szolgáltatást hív. Ugyanezt
a szolgáltatást hívják a tesztek és a demóadat-betöltő is, később pedig a
háttérfolyamat. Így a mesterséges demóadatok is a valódi rögzítési és
kiértékelési úton kerülnek be. A FastAPI a végpontokból automatikusan
OpenAPI-leírást és Swagger-felületet készít (`/api/docs`).

### Adatbázis

Az adatbázis PostgreSQL 17. A séma változásait Alembic-migrációk rögzítik, a
backend induláskor lefuttatja a hiányzókat. A tesztek külön adatbázison
(`pulse_test`) futnak, valódi PostgreSQL-lel. Erre azért van szükség, mert
több védelem az adatbázisban van (CHECK-megszorítások, triggerek, részleges
egyedi index), és ezeket egy memóriabeli helyettesítő nem ellenőrizné.

## A szabálykiértékelés helye

A szabálymotor nem külön szolgáltatás, hanem a backend elkülönített modulja.
Bemenete egy új mérés vagy kérdőív-kitöltés, később egy javított adat vagy egy
elmulasztott alkalom; kimenete egy riasztás vagy egy riasztási esemény. A
kiértékelés ugyanabban az adatbázis-tranzakcióban fut, mint a rögzítés: a
mérés és az általa kiváltott riasztás együtt mentődik, vagy egyik sem. Így nem
fordulhat elő, hogy a mérés bekerül, a riasztása viszont elvész.

Külön szolgáltatás esetén a kettő közé üzenetküldés kerülne, és a
konzisztenciát külön kellene biztosítani. Ekkora rendszernél ez csak
bonyolultabbá tenné a működést, haszon nélkül.

## Háttérfolyamat és értesítés

Ez a rész a tervet írja le; a háttérfolyamat és az e-mail-küldés a harmadik
mérföldkőben készül el.

Az elmaradt adatot a rendszernek akkor is fel kell ismernie, ha semmilyen
kérés nem érkezik. Ezt egy külön konténerben futó háttérfolyamat fogja végezni,
amely ugyanazt a backend-kódot használja. Beállítható időközönként (alapértelmezés
szerint 15 percenként) létrehozza a soron következő alkalmakat, és
elmulasztottnak jelöli a lejártakat. Az ellenőrzés egyetlen függvény, amely
ismételt futtatásra sem hoz létre dupla alkalmat vagy riasztást. Ugyanezt a
függvényt hívják majd a tesztek szimulált idővel, a bemutatón pedig egy kézi
indítás. A külön konténer miatt a háttérfolyamat működését nem befolyásolja,
ha a webszervert újraindítják, vagy több példányban fut.

Az e-mail-értesítés a riasztástól elválasztva működik. A riasztás a
tranzakción belül jön létre, a levél küldése utána, újrapróbálkozással
történik, és a kézbesítés állapotát külön tábla követi. Ha a levél nem
megy ki, a riasztás attól még megvan az adatbázisban. Fejlesztés közben a leveleket egy
Mailpit-postafiók fogja el, valódi címre semmi nem megy ki.

## Futtatókörnyezet és CI

A `docker-compose.yml` jelenleg három szolgáltatást ír le: az adatbázist, a
backendet és a felületet. A portok csak a saját gépről érhetők el
(`127.0.0.1`). Az adatbázis tartalma elnevezett kötetben marad meg
újraindítás után is. A titkok (adatbázis-jelszó, a tokenek aláírókulcsa)
környezeti változóból jönnek; a fájlban lévő alapértékek csak helyi
fejlesztésre valók.

A GitHub Actions minden, a `develop` vagy a `main` ágra kerülő változtatásnál
három ellenőrzést futtat:

- a backendnél kódellenőrzést, a migrációk lefutását és egyezését a
  modellekkel, valamint a teszteket legalább 70%-os lefedettséggel;
- a felületnél kódellenőrzést, formázás-ellenőrzést, típusellenőrzést és
  fordítást;
- a Docker-image-ek felépítését.

## Időkezelés

Az adatbázis minden időpontot UTC-ben tárol. A „helyi nap", például hogy egy
kirendelés mettől érvényes, egy rendszerszintű időzóna (`Europe/Budapest`)
szerint számítódik. Így az óraátállítás sem csúsztatja el a napokat. A
mérésenkénti időzóna később erre ráépíthető, de egy magyar rendszernél nincs
rá szükség.

## Kapcsolat szabványos egészségügyi formátumokkal

A rendszer saját adatmodellje marad az elsődleges, de az adatok a jövőben
szabványos formában is kiadhatók: FHIR R4 Observation (LOINC- és UCUM-kóddal),
Questionnaire és QuestionnaireResponse. A méréstípusok LOINC- és UCUM-kódja
már most az adatbázisban van. Egy klinikai ajánláson alapuló szabályt CQL-ben is
megírtunk, és egy meglévő motorral külön próbában futtattuk; a próbát a
Működés fejezet utolsó alfejezete írja le. Hogy a CQL-kiértékelés hogyan
kapcsolódik a backendhez (például külön Node.js-folyamatként), a harmadik
mérföldkő tervezésekor dől el.

## Döntések és elvetett alternatívák

| Döntés | Elvetett alternatíva | Indoklás |
|--------------|---------------|-------------------------------|
| FastAPI | Django, Flask | Típusjelölésekből validál és OpenAPI-leírást készít. A Django sok olyat hoz, ami itt nem kell (sablonok, admin), a Flaskhoz sok kiegészítő kellene. |
| Szinkron SQLAlchemy | Aszinkron SQLAlchemy | A FastAPI a szinkron végpontokat szálkészletben futtatja, ami ekkora rendszerhez elég; a szinkron kód egyszerűbb és könnyebben tesztelhető. A teljesítménymérés ezt számokkal is ellenőrzi. |
| PostgreSQL | Dokumentum-adatbázis | Az adatok erősen kapcsolódnak, és tranzakció kell; részletesen lásd az Adatmodell fejezetet. |
| JWT a kérés fejlécében | Szerveroldali munkamenet, sütiben | Szabványos és állapotmentes. A lejárat előtti visszavonhatatlanságot ellensúlyozza, hogy a felhasználót minden kérésnél az adatbázisból töltöm be, így a letiltás azonnal hat; részletesen a később elkészülő Biztonság fejezet írja le. |
| Statikus build nginx-szel | Fejlesztői szerver a konténerben | Éles környezetben is így futna; egyetlen cím, nincs CORS. |
| Háttérfolyamat külön konténerben | Időzítő a webszerver folyamatában | Független a webszerver újraindításától és példányszámától. |
| uv | pip és `requirements.txt` | A lockfájl minden csomag pontos verzióját rögzíti, így a telepítés bárhol ugyanaz. |
| Mantine | MUI | A lekerekítés egy beállítással kikapcsolható, a sötét téma beépített, a grafikonjai Recharts-alapúak. |
