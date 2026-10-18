# pulse
PULSE — Patient Understanding through Limits, Signals and Evaluation. Chronic care remote patient monitoring with rule-based, explainable alerting.
[Módosított terv](Modositott_terv.docx) · [M1 leadandók](docs/M1/)

## Mérföldkövek

| # | Tartalom | Határidő |
|---|---|---|
| M1 | Feladatkiírás, követelmények, adatmodell, képernyővázlatok, ütemterv | 2026. szept. 27. |
| M2 | Technikai próba: 1 mérés + 1 kérdőív teljes folyamata Dockerrel | 2026. okt. 18. |
| M3 | Szabálymotor + kérdőívmodul verziózással, riasztás-életút, jogosultság, tesztek | 2026. nov. 22. |
| M4 | Kiértékelés mérésekkel, teljes tesztkészlet, CI/CD + demó, dolgozat | 2026. dec. 12. |

## Szakdolgozat 1 – a pótolt leadandók

| Leadandó | Hol található |
|---|---|
| Feladatkiírás | [PULSE_M1.pdf](docs/M1/PULSE_M1.pdf), 1. fejezet (forrás: [01_feladatkiiras.md](docs/M1/01_feladatkiiras.md)) |
| Funkcionális specifikáció | [PULSE_M1.pdf](docs/M1/PULSE_M1.pdf), 2–6. fejezet: követelmények, adatmodell, működési szabályok, folyamatábrák, képernyővázlatok; a use-case ábra a kezdeti dolgozat 3. fejezetében ([images/use_case.png](images/use_case.png)) |
| Kezdeti dolgozat | PDF: [Google Drive-mappa](https://drive.google.com/drive/folders/1P885HulHbnjETtmCZZ-CA2U3vybnIm5e?usp=sharing); forrás: [docs/dolgozat/](docs/dolgozat/) |
| PoC (működő prototípus) | a kód az [`m2` címkénél](https://github.com/szombatikoni/pulse/tree/m2); indítás: lásd lent; bemutató videó: [Google Drive-mappa](https://drive.google.com/drive/folders/1P885HulHbnjETtmCZZ-CA2U3vybnIm5e?usp=sharing); integrációs próba: [integration/](integration/) |

## Indítás Dockerrel

A teljes rendszer (adatbázis, backend, webes felület) egyetlen paranccsal
indul. Pythont, Node.js-t vagy PostgreSQL-t nem kell telepíteni, ezek a
konténerekben futnak.

### Előfeltételek

- **Docker Desktop** (Windows, macOS) vagy Docker Engine + Compose (Linux):
  https://docs.docker.com/get-docker/
- **Windowson** a Docker Desktop a WSL2-re épül. Ha még nincs telepítve, egy
  rendszergazdai PowerShellben: `wsl --install --no-distribution`, majd
  újraindítás.
- A Docker Desktop fusson (a tálcán a bálna ikon, „Engine running").

### Indítás

```bash
git clone https://github.com/szombatikoni/pulse.git
cd pulse

# Az image-ek felépítése és a konténerek indítása a háttérben
# (az első indítás a letöltések miatt néhány percig tart)
docker compose up --build -d

# Mesterséges demóadatok (méréstípusok, felhasználók, összerendelések,
# szabályok, mérések, a „Közérzet" kérdőív kitöltésekkel); ismételten is futtatható
docker compose exec api python -m seed
```

Ezután:

| Mi | Cím |
|---|---|
| Webes felület | http://localhost:8080 |
| API-dokumentáció (Swagger) | http://localhost:8000/api/docs |

### Demófiókok

Mind mesterséges; a közös jelszó: **`pulse-demo-2026`**.

| Szerepkör | E-mail | Megjegyzés |
|---|---|---|
| Orvos | `dr.kovacs@pulse.example` | négy beteg, mindegyik más státuszban |
| Orvos | `dr.nagy@pulse.example` | Tóth Mária kezelőorvosa |
| Beteg | `varga.bela@pulse.example` | Súlyos: egy mérése 180 Hgmm felett |
| Beteg | `szabo.janos@pulse.example` | Figyelem: két 140 feletti mérés, és a kérdőíve a figyelmeztető sávban |
| Beteg | `kiss.ilona@pulse.example` | Adathiány: 12 napja nem mért |
| Beteg | `molnar.katalin@pulse.example` | Rendben |
| Beteg | `toth.maria@pulse.example` | Rendben (Nagy doktor betege) |
| Admin | `admin@pulse.example` | betegadatot nem lát |

A mérések időpontjai a seed futtatásához képest relatívak (az utolsó mérés
a legutóbbi reggel 7:30-as, magyar idő szerint). Mivel 7 napnál régebbi adat
már nem számít frissnek, **a demó a seed után kb. egy hétig mutatja a fenti
státuszokat**; utána (vagy bemutató előtt) érdemes tisztán újrakezdeni:
`docker compose down -v`, majd újra az indítás és a seed.

### Leállítás

```bash
docker compose down        # leállítás, az adatok megmaradnak
docker compose down -v     # leállítás ÉS az adatbázis törlése (tiszta újrakezdés)
```

### Beállítások (nem kötelező)

Az alapértékek helyi kipróbálásra valók. Eltérő jelszóhoz vagy aláírókulcshoz
másold a `.env.example` fájlt `.env` néven, és írd át. A compose
automatikusan beolvassa. Nyilvános környezetben a `JWT_SECRET_KEY`-t
kötelező lecserélni.

A portok (8080, 8000, 5432) csak a saját gépről érhetők el.

## Fejlesztés

| Feladat | Parancs (a megadott mappában) |
|---|---|
| Csak az adatbázis indítása | `docker compose up -d db` (gyökér) |
| Backend helyben (Python 3.12, [uv](https://docs.astral.sh/uv/)) | `uv sync`, majd `uv run uvicorn app.main:app --reload` (`backend/`) |
| Backend-tesztek | `uv run pytest` (`backend/`; futó adatbázis kell) |
| Frontend helyben (Node.js 24) | `npm install`, majd `npm run dev` → http://localhost:5173 (`frontend/`) |
| Kódellenőrzés | `uv run ruff check .` (`backend/`), `npm run lint` (`frontend/`) |
| Böngészős folyamatteszt ([Playwright](https://playwright.dev/)) | `npm ci`, `npx playwright install chromium`, majd `npx playwright test` (`e2e/`; lásd lent) |

A CI (GitHub Actions) minden pushkor ugyanezeket futtatja: `.github/workflows/ci.yml`.

### Böngészős folyamatteszt

Az `e2e/` teszt a két M2-folyamatot a felületen viszi végig: a beteg mér és
kérdőívet tölt ki, az orvos a listán és az adatlapon látja a jelzést, idegen
beteg adatlapját pedig nem nyithatja meg. Futó rendszert és **frissen seedelt**
adatbázist vár, és **módosítja az adatokat**. Hogy a saját demóadataid
megmaradjanak, külön példányon érdemes futtatni (a fő példány leállítása után,
mert ugyanazokat a portokat használja):

```bash
docker compose -p pulse-e2e up --build -d --wait
docker compose -p pulse-e2e exec api python -m seed
cd e2e && npx playwright test && cd ..
docker compose -p pulse-e2e down -v   # a tesztpéldány és az adatbázisa törlése
```

## Integrációs próba (CQL + FHIR)

Az `integration/` mappa egy önálló próba: egy mesterséges beteg FHIR R4
adatcsomagján lefuttatja a NICE NG136 otthoni vérnyomásmérés-összesítéséből
készült, ELM-re lefordított CQL-szabályt a `cql-execution` motorral, és az
eredményt egy a motortól független kézi számítással veti össze (a fordítás
külön lépésként megismételhető). Csak Docker kell hozzá;
a leírás és a parancsok: [integration/README.md](integration/README.md).

## Kódrendszerek

A méréstípusok jelentését LOINC-kód, a mértékegységet UCUM-kód rögzíti.

This material contains content from LOINC (http://loinc.org). LOINC is
copyright © 1995+, Regenstrief Institute, Inc. and the Logical Observation
Identifiers Names and Codes (LOINC) Committee and is available at no cost
under the license at http://loinc.org/license. LOINC® is a registered United
States trademark of Regenstrief Institute, Inc.

## Fontos megjegyzés

Demonstrációs célú szakdolgozati rendszer, amely kizárólag mesterséges
(szintetikus) adatokkal működik. Nem orvostechnikai eszköz, és nem helyettesíti
az orvosi döntést.
