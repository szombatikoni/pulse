# Felhasznált technológiák

Ez a fejezet a ténylegesen használt eszközöket és a választásuk okát írja le.
Az, hogy melyik komponens hol helyezkedik el a rendszerben, az Architektúra
fejezetben szerepel. Az ottani döntéstábla már indokolja a FastAPI, a szinkron
SQLAlchemy, a PostgreSQL, a fejlécben küldött JWT, az nginx, a külön
háttérfolyamat, az uv és a Mantine választását; ezeket itt nem ismétlem meg.
A verziók a zárolt állapotot mutatják: a Python-csomagokét a
`backend/uv.lock`, az npm-csomagokét a `package-lock.json` fájlok rögzítik.
A futtatókörnyezetek főverzióját a Dockerfile-ok és a `docker-compose.yml`
adják meg (pontos javítóverzióval csak a CQL-szolgáltatás Node-ja rögzített).

| Terület | Eszköz | Verzió |
|-----------|---------------------------------|-------------|
| Felület | React | 19.3.0 |
| | TypeScript | 6.0.3 |
| | Vite | 8.3.2 |
| | Mantine | 9.6.3 |
| | TanStack React Query | 5.104.0 |
| | React Router | 7.18.4 |
| | i18next | 26.4.2 |
| Backend | Python | 3.12 |
| | FastAPI (uvicorn szerverrel) | 0.142.2 (0.54.0) |
| | Pydantic | 2.13.5 |
| | SQLAlchemy | 2.1.1 |
| | Alembic | 1.20.0 |
| | psycopg | 3.3.6 |
| | PyJWT, pwdlib (Argon2) | 2.15.1, 0.3.1 |
| Adatbázis | PostgreSQL | 17 |
| CQL-szolgáltatás | Node.js | 24.21.0 |
| | cql-execution, cql-exec-fhir | 3.3.2, 2.2.0 |
| Tesztelés, kódminőség | pytest | 9.1.1 |
| | Playwright | 1.64.1 |
| | ruff | 0.16.10 |
| | ESLint, Prettier | |
| Futtatás | Docker Compose, GitHub Actions | |

## Felület

A React és a TypeScript már a feladatkiírásban szerepelt. Korábban Angularral
és Reacttel is dolgoztam, a Vue-val nincs tapasztalatom. Az Angular is
alkalmas lett volna, de a Reactet szabadabbnak éreztem, és sok kész könyvtár
érhető el hozzá, ezért ezt választottam. A TypeScript szigorú módban
(`strict`) fut, így a típushibák egy része már fordításkor kiderül. A fordítást
a Vite végzi: fejlesztés közben azonnal frissülő fejlesztői szervert ad, a
telepítéshez pedig statikus fájlokat készít. A `build` parancs előbb a
TypeScript-fordítót futtatja típusellenőrzésre, és csak utána a Vite-ot, ezért
típushibás kód nem fordul le, a CI-ban sem.

A szerverről érkező adatokat a React Query kezeli, az okát az Architektúra
fejezet írja le. Az oldalak közötti navigációt a React Router végzi; mivel az
alkalmazás egyoldalas, az nginx minden ismeretlen útvonalra az `index.html`-t
adja vissza, és az útvonalat a böngészőben a React Router oldja fel.

A felület szövegei az i18next fordítási fájljaiban vannak, magyarul és
angolul. Az angol fordítás típusa a magyaréból
származik, így ha egy kulcs az egyikből hiányzik, a fordítás hibát jelez. Az
alapnyelv a magyar; a nyelvváltó a negyedik mérföldkőben kerül a felületre.

A grafikonok nem külső könyvtárral, hanem saját SVG-rajzzal készültek (lásd az
Architektúra fejezet döntéstábláját). Az ikonokat a Phosphor csomag adja, a
két betűtípust (Source Serif 4 és Instrument Sans) pedig npm-csomagként
telepítettem, így ezeket nem külső betűszolgáltatásból tölti le a böngésző.

## Backend

A backend Python 3.12-ben készült. A Pythont azért választottam, mert könnyen
olvasható, folyamatosan fejlődő nyelv, sok könyvtár érhető el hozzá, és az
AI-asszisztált fejlesztés is jól támogatja. A bemenet ellenőrzését a Pydantic
végzi: a végpontok sémái típusjelölésekből állnak, a hibás kérés 422-es választ
kap, mielőtt az üzleti logikához érne. A beállításokat (adatbázis-cím,
aláírókulcs, időközök) a pydantic-settings olvassa be környezeti változókból,
ugyanazzal a típusellenőrzéssel.

Az adatbázist az SQLAlchemy 2 ORM-en keresztül érem el, a PostgreSQL-hez a
psycopg 3 meghajtóval. A séma változásait Alembic-migrációk rögzítik. Az
Alembic az SQLAlchemy készítőitől származik, és a modellek alapján
migrációtervezetet tud generálni, amelyet átnézés után veszek fel a repóba. A CI külön ellenőrzi, hogy a migrációk végén kapott séma egyezik
a modellekkel (`alembic check`), így nem maradhat ki egy modellváltozás
migrációja.

A tokenek kezelésére a PyJWT, a jelszavak hashelésére a pwdlib csomagot
használom Argon2 algoritmussal. A jelszókezelés és a token részleteit a Biztonság fejezet írja le.

## A CQL-motor

A klinikai ajánláson alapuló szabályt a cql-execution motor futtatja
[@cql-execution], a FHIR-adatokat a cql-exec-fhir adapter adja át neki
[@cql-exec-fhir]. Ez JavaScript-könyvtár, ezért Node.js-en fut, és a CQL-ből
előre lefordított ELM-et értelmezi. Ezt a láncot a témavezető javasolta
irányként, a próbát a Működés fejezet írja le.

A beépítésnél három út jött szóba: a backend minden kiértékelésnél külön
Node-folyamatot indít; egy Java-alapú motort használok; vagy a motor külön
szolgáltatásként fut, és a backend HTTP-n hívja. A Java-motorhoz JDK 17-es
futtatókörnyezet kellett volna. Az első próba még egyszer lefutó parancsokkal
dolgozott; a beépítésnél a témavezető javaslatát elfogadva a harmadik utat
választottam. A szolgáltatás induláskor egyszer tölti be az ELM-et, és utána memóriában tartja,
így a kérésenkénti indítás költsége elmarad. A HTTP-felületet a Node beépített
`http` modulja adja, új függőség nélkül, és a backend oldalon is a Python
standard könyvtárának HTTP-kliense hívja.

## Tesztelés és kódminőség

A backend tesztjei pytesttel, valódi PostgreSQL-adatbázison futnak, a
lefedettséget a pytest-cov méri. A felület és a teljes lánc ellenőrzésére
Playwrightot használok: valódi Chromium böngészőt vezérel, és a felületen
kattintja végig a folyamatokat, az nginxen és az API-n át egészen az
adatbázisig. A verziója pontosan rögzített (1.64.1): ahol lehet, azonos
verziókat használok helyben és a CI-ban, hogy elkerüljem az eltérő verziókból
adódó összeférhetetlenséget. Alternatívaként a Cypresst néztem meg. A
választás előtt mások tapasztalatait olvastam el, és a legtöbben a
Playwrightot ajánlották: több böngészőmotort kezel, gyorsabban futtatja a
teszteket, és kevesebb kiegészítő kell hozzá. A tesztek felépítését és
eredményeit a
Tesztelés fejezet mutatja be.

A kódstílust a backendben a ruff ellenőrzi és formázza; egyetlen eszközként
váltja ki a korábban szokásos flake8, isort és black hármast. A felületen az
ESLint és a Prettier végzi ugyanezt.

## Futtatás és folyamatos integráció

Minden komponens Docker-konténerben fut, és a Docker Compose egyetlen
paranccsal indítja a teljes rendszert, így a kipróbáláshoz nem kell Pythont,
Node.js-t vagy PostgreSQL-t telepíteni. Az ellenőrzéseket a GitHub Actions
futtatja a `develop` és a `main` ágra kerülő minden változtatásnál.
Ez volt a legkézenfekvőbb választás: a munkahelyemen Azure DevOpsot
használok, de itt a nyilvános GitHub-repó adott volt, és a GitHub Actions
ehhez külön szolgáltatás nélkül, egyszerűen használható. Mindkettő
részleteit a DevOps fejezet írja le.
