# DevOps

A futtatókörnyezet áttekintését az Architektúra fejezet adja. Ez a fejezet azt
írja le részletesebben, hogyan épülnek fel a konténerek, milyen sorrendben
indulnak, hogyan kerül adat a rendszerbe, és mit ellenőriz a folyamatos
integráció (CI).

## A konténerek

A `docker-compose.yml` öt szolgáltatást ír le. A backend és a háttérfolyamat
ugyanabból az image-ből épül, csak más paranccsal indul.

| Szolgáltatás | Image | Indítóparancs | Mikor indul | Állapotellenőrzés |
|-----------|-----------------|-------------------|-------------|---------------|
| `db` | `postgres:17` | az image saját parancsa | elsőként | `pg_isready` |
| `api` | `backend/Dockerfile` (`python:3.12-slim`) | migrációk, majd `uvicorn` | ha a `db` egészséges | `/api/health` |
| `worker` | ugyanaz, mint az `api`-é | `python -m app.worker` | ha az `api` egészséges | nincs |
| `cql` | `integration/Dockerfile`, `szolgaltatas` cél (`node:24.21.0-alpine3.24`) | `node szolgaltatas.mjs` | önállóan | `/health` |
| `frontend` | `frontend/Dockerfile` (`node:24-alpine`, majd `nginx:alpine`) | nginx | az `api` után | nincs |

A Dockerfile-ok mindhárom esetben előbb csak a függőségek listáját másolják be
(`pyproject.toml` és `uv.lock`, illetve `package.json` és
`package-lock.json`), telepítik a zárolt verziókat, és csak utána a kódot. Így
ha csak a kód változik, a Docker a függőségek rétegét a gyorsítótárból veszi.
A backend image-be a uv a hivatalos uv-image-ből kerül, és a fejlesztői
csomagok (pytest, ruff) nélkül települ. A felület kétlépcsős: az első image a
Node-dal lefordítja a kódot, a második már csak a statikus fájlokat és az
nginxet tartalmazza. A CQL-szolgáltatás image-ében az előre lefordított ELM és
a szolgáltatás kódja van, és a folyamat nem rendszergazdaként, hanem a `node`
felhasználóval fut. Ha a folyamat hibával kilép, a Docker újraindítja.

## Indítási sorrend és migrációk

Az `api` konténer induláskor előbb lefuttatja a hiányzó migrációkat
(`alembic upgrade head`), és csak utána indítja a webszervert. Az
állapotellenőrzése ezért csak akkor sikeres, ha a séma már naprakész, és a
háttérfolyamat erre vár: így nem futhat régi sémán. Az `api` szándékosan nem
függ a `cql` szolgáltatástól. Ha a CQL-motor nem fut, a rendszer elindul, a
riasztás működik, és csak a NICE-kiértékelés végpontja ad hibát. Az adatbázis
első indulásakor egy induló szkript a tesztek adatbázisát (`pulse_test`) is
létrehozza.

## Demóadatok

A mesterséges demóadatokat külön parancs tölti be (`python -m seed` az `api`
konténerben), nem az indulás. A betöltő ismételten is futtatható, és a valódi
rögzítési úton dolgozik (lásd az Architektúra fejezetet). A mérések időpontjai a betöltés idejéhez igazodnak.
Mivel a betegeknél legkésőbb a betöltés utáni napon 10:00-kor lejár egy
határidő, és a Rendben beteg Adathiány státuszba kerül (lásd a Működés
fejezetet), bemutató előtt az adatbázist törlöm, és újra betöltöm az adatokat.

## Telepítés

A kipróbáláshoz csak Docker kell (Windowson a Docker Desktop). A dolgozat a
`develop` ág állapotát írja le, a `main` az utolsó lezárt mérföldkőé. A
letöltés és az indítás (a demófiókokat a repó README-je sorolja fel):

```bash
git clone --branch develop https://github.com/szombatikoni/pulse.git
cd pulse
docker compose up --build -d          # az image-ek építése és indítás
docker compose exec api python -m seed  # mesterséges demóadatok
```

Ezután a felület a `http://localhost:8080`, az API-leírás a
`http://localhost:8000/api/docs` címen érhető el. A `docker compose down`
leállít, a `docker compose down -v` az adatbázist is törli. A jelszavak és az
aláírókulcs alapértékei csak helyi használatra valók; eltérő értékhez a
`.env.example` fájlt kell `.env` néven lemásolni és átírni.

## Folyamatos integráció

A GitHub Actions minden, a `develop` vagy a `main` ágra küldött változtatásnál,
és minden, a `main` ágra nyitott pull requestnél lefut. Négy feladatból (job)
áll:

| Feladat | Mit ellenőriz |
|------------|------------------------------------------------------------|
| Backend | ruff (hibák és formázás); a migrációk lefutnak egy PostgreSQL 17 adatbázison, és egyeznek a modellekkel (`alembic check`); a pytest legalább 70%-os lefedettséggel |
| Frontend | ESLint, Prettier, majd típusellenőrzés és fordítás |
| CQL-szolgáltatás | a szolgáltatás saját tesztjei (`node --test`) |
| Docker | a teljes rendszer felépítése és indítása, a demóadatok betöltése, a NICE-kiértékelés a valódi CQL-motorral és a böngészős tesztek Playwrighttal |

Az első három párhuzamosan fut, a Docker-feladat csak a backend és a frontend
sikere után indul. A pytest a CQL-motort helyettesítővel hívja, ezért a valódi
láncot (adatbázis, FHIR-csomag, CQL-motor, összevetés a saját számítással) itt,
egy betöltött betegen futtatom le. Hiba esetén a Playwright képernyőképei és
nyomkövetése hét napig letölthető, a konténerek naplója pedig a futás
kimenetébe kerül.

## Ágmodell

A napi munka a `develop` ágon folyik, és minden push után lefut a CI. A `main`
ág csak pull requesttel kap változást, mérföldkövenként; ilyenkor a
mérföldkő commitja címkét kap (a második mérföldkőé `m2`).

## Demókörnyezet és folyamatos telepítés (terv)

A nyilvános demókörnyezet és a folyamatos telepítés (CD) a negyedik mérföldkő
feladata, jelenleg egyik sincs meg. A rendszer most csak helyben fut, a portok
csak a saját gépről érhetők el. A demó helyéről és a telepítés
indításáról a negyedik mérföldkőben döntök. A nyilvános példányhoz
a jelszavakat és az aláírókulcsot le kell cserélni, és a demóadatokat
rendszeresen frissíteni kell, mert különben a betegek Adathiány státuszba
kerülnek. Az e-mail-küldés és vele a fejlesztői levelező (Mailpit) még nincs a
compose-ban. Az orvosnak szóló értesítés a harmadik mérföldkő hátralévő
része, a betegnek szóló a negyediké.
