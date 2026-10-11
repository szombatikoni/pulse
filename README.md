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

# Mesterséges demóadatok (felhasználók, orvos–beteg összerendelések);
# ismételten is futtatható
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
| Orvos | `dr.kovacs@pulse.example` | Szabó János kezelőorvosa |
| Orvos | `dr.nagy@pulse.example` | Tóth Mária kezelőorvosa |
| Beteg | `szabo.janos@pulse.example` | |
| Beteg | `toth.maria@pulse.example` | |
| Admin | `admin@pulse.example` | betegadatot nem lát |

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

A CI (GitHub Actions) minden pushkor ugyanezeket futtatja: `.github/workflows/ci.yml`.

## Fontos megjegyzés

Demonstrációs célú szakdolgozati rendszer, amely kizárólag mesterséges
(szintetikus) adatokkal működik. Nem orvostechnikai eszköz, és nem helyettesíti
az orvosi döntést.
