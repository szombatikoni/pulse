# Architektúra

A PULSE háromrétegű webalkalmazás. A böngészőben futó felület REST-interfészen
keresztül éri el a backendet, és az adatbázishoz kizárólag a backend fér hozzá.
Minden komponens külön Docker-konténerben fut, a teljes rendszert egyetlen
`docker compose up` parancs indítja el. A @abra:architektura a harmadik
mérföldkő állapotát mutatja: folytonos kerettel az elkészült részeket (felület,
backend, adatbázis, háttérfolyamat és a külön konténerben futó
CQL-szolgáltatás), szaggatottal a tervezetteket. Az e-mail-küldés a
fejlesztői levelezővel (Mailpit) még nem készült el, a folyamatos telepítés
(CD) a negyedik mérföldkőben kerül be.

![A PULSE architektúrája](images/dolgozat_architektura_m3.png){#abra:architektura}

## A komponensek

A @abra:komponens egy szinttel mélyebbre megy: a konténereken belüli fő
modulokat és a köztük lévő függéseket mutatja, a kód importjai szerint.

![A PULSE komponensei](images/dolgozat_komponens.png){#abra:komponens}

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
a szolgáltatást hívják a tesztek, a demóadat-betöltő és a háttérfolyamat is.
Így a mesterséges demóadatok is a valódi rögzítési és
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
Bemenete egy új mérés vagy kérdőív-kitöltés, egy javított adat vagy egy
elmulasztott alkalom; kimenete egy riasztás vagy egy riasztási esemény. A
kiértékelés ugyanabban az adatbázis-tranzakcióban fut, mint a rögzítés: a
mérés és az általa kiváltott riasztás együtt mentődik, vagy egyik sem. Így nem
fordulhat elő, hogy a mérés bekerül, a riasztása viszont elvész.

Külön szolgáltatás esetén a kettő közé üzenetküldés kerülne, és a
konzisztenciát külön kellene biztosítani. Ekkora rendszernél ez csak
bonyolultabbá tenné a működést, haszon nélkül.

## Háttérfolyamat és értesítés

A háttérfolyamat elkészült; az e-mail-küldés még terv, a harmadik
mérföldkő végére készül el.

Az elmaradt adatot a rendszernek akkor is fel kell ismernie, ha semmilyen
kérés nem érkezik. Ezt egy külön konténerben futó háttérfolyamat végzi,
amely ugyanazt a backend-kódot használja. Beállítható időközönként (alapértelmezés
szerint óránként) létrehozza a soron következő alkalmakat, és
elmulasztottnak jelöli a lejártakat. Az ellenőrzés egyetlen függvény, amely
ismételt futtatásra sem hoz létre dupla alkalmat vagy riasztást. Ugyanezt a
függvényt hívják a tesztek szimulált idővel, a bemutatón pedig egy kézi
indítás. A külön konténer miatt a háttérfolyamat működését nem befolyásolja,
ha a webszervert újraindítják, vagy több példányban fut.

Az első tervben 15 perces ütem szerepelt. A megvalósításkor óránkéntire
váltottam, mert a határidők napi léptékűek, a sűrűbb futás pedig egyetlen
követelményből sem következett. Az eredmény helyességét nem az ütem adja,
hanem az, hogy az ellenőrzés ismételhető, és kézzel bármikor elindítható.

Az e-mail-értesítés a terv szerint a riasztástól elválasztva működik majd. A
riasztás a tranzakción belül jön létre, a levél küldése utána,
újrapróbálkozással történik, és a kézbesítés állapotát külön tábla követi
majd. Ha a levél nem megy ki, a riasztás attól még megvan az adatbázisban.
Fejlesztés közben a leveleket egy Mailpit-postafiók fogja el, valódi címre
semmi nem megy ki.

## Futtatókörnyezet és CI

A `docker-compose.yml` öt szolgáltatást ír le: az adatbázist, a backendet, a
háttérfolyamatot, a CQL-szolgáltatást és a felületet. A portok csak a saját
gépről érhetők el (`127.0.0.1`); a háttérfolyamat és a CQL-szolgáltatás kifelé
nem nyit portot. Az adatbázis tartalma elnevezett kötetben marad meg
újraindítás után is. A titkok (adatbázis-jelszó, a tokenek aláírókulcsa)
környezeti változóból jönnek; a fájlban lévő alapértékek csak helyi
fejlesztésre valók.

A GitHub Actions minden, a `develop` vagy a `main` ágra kerülő változtatásnál
négy ellenőrzést futtat:

- a backendnél kódellenőrzést, a migrációk lefutását és egyezését a
  modellekkel, valamint a teszteket legalább 70%-os lefedettséggel;
- a felületnél kódellenőrzést, formázás-ellenőrzést, típusellenőrzést és
  fordítást;
- a CQL-szolgáltatás saját tesztjeit;
- a Docker-image-ek felépítését, majd az elindított rendszeren a demóadat
  betöltését, az ajánlás szerinti kiértékelést a valódi CQL-motorral és a
  böngészős folyamattesztet.

## Időkezelés

Az adatbázis minden időpontot UTC-ben tárol. A „helyi nap", például hogy egy
kirendelés mettől érvényes, egy rendszerszintű időzóna (`Europe/Budapest`)
szerint számítódik. Így az óraátállítás sem csúsztatja el a napokat. A
mérésenkénti időzóna később erre ráépíthető, de egy magyar rendszernél nincs
rá szükség.

## Kapcsolat szabványos egészségügyi formátumokkal

A rendszer saját adatmodellje marad az elsődleges, de a beteg adatai egy
végponton szabványos formában is kiadhatók: FHIR R4 Observation (LOINC- és
UCUM-kóddal), Questionnaire és QuestionnaireResponse. A méréstípusok LOINC- és
UCUM-kódja az adatbázisban van. Egy klinikai ajánláson alapuló szabályt CQL-ben is
megírtunk, és egy meglévő motorral külön próbában futtattuk; a próbát a
Működés fejezet utolsó alfejezete írja le. A harmadik mérföldkőben a motor
külön konténerbe került, a backend belső HTTP-hívással éri el. Egy végpont a
beteg utolsó hét lezárt napjának vérnyomásméréseit értékelteti ki vele, és az
eredményt saját, törtekkel végzett számítással veti össze; ha a motor nem
érhető el, csak ez a végpont ad hibát. Az eredményt az orvosi adatlap
tájékoztató panelje mutatja; nem tárolódik, és nem hat a státuszra és a
riasztásokra.

## Döntések és elvetett alternatívák

| Döntés | Elvetett alternatíva | Indoklás |
|--------------|---------------|-------------------------------|
| FastAPI | Django, Flask | Típusjelölésekből validál és OpenAPI-leírást készít. A Django sok olyat hoz, ami itt nem kell (sablonok, admin), a Flaskhoz sok kiegészítő kellene. |
| Szinkron SQLAlchemy | Aszinkron SQLAlchemy | A FastAPI a szinkron végpontokat szálkészletben futtatja, ami ekkora rendszerhez elég; a szinkron kód egyszerűbb és könnyebben tesztelhető. A negyedik mérföldkő teljesítménymérése ezt számokkal is ellenőrzi majd. |
| PostgreSQL | Dokumentum-adatbázis | Az adatok erősen kapcsolódnak, és tranzakció kell; részletesen lásd az Adatmodell fejezetet. |
| JWT a kérés fejlécében | Szerveroldali munkamenet, sütiben | Szabványos és állapotmentes. A lejárat előtti visszavonhatatlanságot ellensúlyozza, hogy a felhasználót minden kérésnél az adatbázisból töltöm be, így a letiltás azonnal hat; részletesen a Biztonság fejezet írja le. |
| Statikus build nginx-szel | Fejlesztői szerver a konténerben | Éles környezetben is így futna; egyetlen cím, nincs CORS. |
| Háttérfolyamat külön konténerben | Időzítő a webszerver folyamatában | Független a webszerver újraindításától és példányszámától. |
| uv | pip és `requirements.txt` | A lockfájl minden csomag pontos verzióját rögzíti, így a telepítés bárhol ugyanaz. |
| Mantine | MUI | A lekerekítés egy beállítással kikapcsolható, a sötét téma beépített. A grafikonok végül saját SVG-rajzok lettek, a Mantine Recharts-alapú grafikonjai helyett. |
