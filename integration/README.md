# CQL-integrációs próba (M2)

Ez a mappa a PULSE-tól független próba. Egy szabályt CQL-ben írunk meg,
lefordítjuk ELM-re, majd egy meglévő CQL-motorral lefuttatjuk egy mesterséges
beteg FHIR R4 adatcsomagján. Az eredményt kézi számítással ellenőrizzük.

A szabály az otthoni vérnyomásmérés-sorozat átlaga az első nap méréseinek
elhagyásával (NICE NG136, 1.2.7. ajánlás), összevetve a kezelés követésére
megadott, életkortól függő célértékkel (1.4.22. ajánlás). Forrás:
https://www.nice.org.uk/guidance/ng136/chapter/Recommendations. A NICE-szöveget
a repó nem tartalmazza.

> **Demonstrációs kód, kizárólag mesterséges adattal.** Nem orvosi eszköz, nem
> diagnosztizál, és nem helyettesíti az orvosi döntést. A kezelés követéséhez
> számol átlagot.

## Verziók (rögzítve)

| Elem | Verzió | Hol rögzített |
|---|---|---|
| CQL-fordító | `cqframework/cql-translation-service:v2.8.0`, benne a `cql-to-elm` **4.2.0** (a képben ellenőrizve: `/app/target/libs/cql-to-elm-4.2.0.jar`) | `docker-compose.yml` |
| CQL-motor | `cql-execution` **3.3.2** | `package.json`, `package-lock.json` |
| FHIR-adapter | `cql-exec-fhir` **2.2.0**, `PatientSource.FHIRv401()` | `package.json`, `package-lock.json` |
| Node | `node:24.21.0-alpine3.24` (Node v24.21.0) | `Dockerfile` |
| Adatmodell | FHIR R4 **4.0.1**, `FHIRHelpers` **4.0.1** | a CQL `using`/`include` sora |
| Ellenőrzés | `python:3.12.10-alpine3.21` | `docker-compose.yml` |

A képek digestje (2026-10-12):
- `cql-translation-service@sha256:1c7b19faf07b85cc28bc38a25e0bf766980394e64def73a48b776be4e7656279`
- `node@sha256:ebfe2f90462722a7a4de65e91990e97fe0d401c70e0e762c5b53302f905ec1c1`
- `python@sha256:9c51ecce261773a684c8345b2d4673700055c513b4d54bc0719337d3e4ee552e`

A `cql/FHIRHelpers-4.0.1.cql` változatlan fájl. A fordítókép
`quick-4.2.0.jar`-jából bontottam ki (`org/hl7/fhir/FHIRHelpers-4.0.1.cql`,
sha256 `6748661c…8329591`). Ugyanebből a fájlból oldja fel a fordító a fő
könyvtár `include` sorát is. Licence: Apache-2.0 (a cqframework/clinical_quality_language
repó LICENSE fájlja alapján). A `cql-execution` és a `cql-exec-fhir` szintén Apache-2.0.

## Futtatás

Csak Docker kell (helyi Node és Java nem). Az `integration/` mappából:

```sh
docker compose run --rm forditas    # 1. CQL -> ELM (elm/*.json)
docker compose run --rm motor       # 2. a motor futtatása (eredmeny/eredmeny.json)
docker compose run --rm ellenorzes  # 3. kézi számítás (a motortól független), összevetés
docker compose down                 # a fordítószolgáltatás leállítása
```

- Az ELM a repóban van, ezért a 2. és a 3. lépés fordító nélkül is fut.
- Az első futtatás letölti a képeket, és felépíti a futtató képet (`npm ci`).
- A fordító nem nyit portot a gép felé.
- Helyben, Docker nélkül is fut: `npm ci && node futtatas.mjs`, illetve
  `python -I ellenorzes/kezi_szamitas.py`. Kipróbálva Node 20.20.2-vel is
  (a `package.json` `engines` mezője 24-et ír elő, az `npm ci` csak figyelmeztet);
  a Node-verzió során kívül ugyanazt az eredményt adta.
- Kétszeri tiszta futtatás után az ELM és az eredmény bájtra azonos volt.

## Az adat (mesterséges)

`adat/beteg_hbpm_bundle.json` egy `collection` típusú Bundle. Benne van egy
Patient (`pulse-demo-beteg-01`, született 1958-03-14), és 16 vérnyomás-Observation.
Minden Observation egy leolvasás:
- panel: LOINC 85354-9, komponensek: 8480-6 (szisztolés) és 8462-4 (diasztolés);
- egység: `mm[Hg]` (UCUM), profil: `http://hl7.org/fhir/StructureDefinition/bp`;
- `effectiveDateTime` helyi eltolással (`+02:00`).

Naponta 2 alkalom van (07:30/07:32 és 20:30/20:32), alkalmanként 2 leolvasással.
A mérésazonosító a nap és az időpont, pl. `bp-20261006-0730`.

| Nap | Leolvasások (szisztolés/diasztolés) |
|---|---|
| okt. 5. | 150/95, 148/94, 146/92, 144/92 |
| okt. 6. | 138/86, 136/85, 134/84, 136/86 |
| okt. 7. | 140/88, 138/86, 132/82, 134/84 |
| okt. 8. | 136/86, 134/84, 130/80, 132/82 |

A Bundle-t egy egyszeri szkript írta ki ebből a táblázatból. A HL7-validátorral
**nem ellenőriztem**.

## Várt és kapott eredmény

Kézi számítás (pontos törtekkel), alapértékekkel:
- Az okt. 5. az első nap, ennek 4 mérése kiesik. Marad 12 mérés 3 napról.
- Szisztolés átlag: 1620/12 = **135**. Diasztolés átlag: 1013/12 = **84,41666…**
- A beteg 68 éves, ezért a cél: 135/85 alatt.
- 135 nincs 135 alatt, ezért a cél **nem teljesül** (mindkét átlagnak a határ alatt kell lennie).

A motor eredménye (`eredmeny/eredmeny.json`, „A-alap” forgatókönyv):

```text
excludedFirstDay: 2026-10-05   excludedReadingIds: bp-20261005-0730 … -2032 (4 db)
includedReadingIds: bp-20261006-0730 … bp-20261008-2032 (12 db)   includedDays: 10-06, 10-07, 10-08
meanSystolic: 135   meanDiastolic: 84.41666666666667   ageInYears: 68   target: 135/85
systolicBelowTarget: false   diastolicBelowTarget: true   targetMet: false
```

A futtató ebből egy rövid magyarázatot is ír. Ez bemutató, a végleges szöveg a
PULSE dolga lesz:

> Átlag 135,0/84,4 Hgmm, 12 mérésből (2026-10-06 – 2026-10-08, 3 nap); a
> 2026-10-05-i 4 mérés első napként kiesett; célérték: 135/85 Hgmm alatt (68
> éves; mindkét átlagnak a határ alatt kell lennie): a cél NEM teljesül.

Ugyanez az adat más paraméterekkel. Ezek a kétértelmű pontok hatását mutatják:

| Forgatókönyv | Paraméter | n | Átlag | Cél | `targetMet` |
|---|---|---|---|---|---|
| A-alap | alapértékek | 12 | 135 / 84,42 | 135/85 | false |
| B-elso-nap-nelkul | `Exclude First Day` = false | 16 | 138 / 86,625 | 135/85 | false |
| C-eleg-az-egyik | `Both Components Must Be Below Target` = false | 12 | 135 / 84,42 | 135/85 | **true** |
| D-kerekites-egeszre | `Comparison Rounding Precision` = 0 (135 / 84) | 12 | 135 / 84,42 | 135/85 | false |
| E-min-4-nap | `Min Included Days` = 4 | 12 | 135 / 84,42 | 135/85 | **null** (nincs elég adat) |
| F-80-ev-feletti | születési dátum 1944-03-14 (82 éves; csak a memóriában átírva) | 12 | 135 / 84,42 | 145/85 | **true** |
| G-kirendeles-kezdonapja | `First Day Definition` = 'PeriodStartDay', a sorozat okt. 4-én indul | 16 | 138 / 86,625 | 135/85 | false |

**Ellenőrzés:** az `ellenorzes/kezi_szamitas.py` nem használja sem a CQL-t, sem
a motort. A fenti táblázatból `fractions`-szel számol, és mind a 7
forgatókönyvben összeveti a saját eredményét a motoréval: átlagok, mérésszám,
napok, a kizárt nap, a figyelembe vett és a kizárt **mérésazonosítók**,
életkor, célérték és `targetMet`. Előtte azt is ellenőrzi, hogy a FHIR-csomag
egyezik-e a táblázattal. Eredmény: **minden egyezik**. Az egyetlen eltérés a
számábrázolásé: a motor 84.41666666666667-et ad (64 bites lebegőpontos szám),
a pontos érték 1013/12. Az összevetés tűréshatára 10⁻⁹.

## Akadályok és kerülőutak (a próba alatt derültek ki)

1. **Paraméter alapérték nélkül (motorhiba, kerülőúttal megoldva).** A
   `cql-execution` 3.3.2-ben egy alapérték nélküli, meg nem adott paraméter nem
   `null`-t ad, hanem magát a paraméter-definíciót. A hiba helye:
   `lib/elm/parameters.js`, `ParameterDef.exec`, 19–21. sor. Emiatt az
   `is null` hamis lett, a `Round` NaN-t adott, a `NaN < 85` pedig `false`-t
   (nem `null`-t). Az első futásban ezért lett hamisan „nem a határ alatt” a
   84,42-es diasztolés átlag. Egy külön mini-könyvtárral is igazoltam. A
   kerülőút: `default null` a CQL-ben. Ugyanez jó, ha a hívó explicit
   `null`-t ad át.
2. **A query `return` záradéka alapból `distinct`** (CQL-szemantika, a motor
   is így valósítja meg: `lib/elm/query.js`). `return all` nélkül az ismétlődő
   értékek csak egyszer számítanának. Kipróbáltam: a diasztolés átlag ekkor
   84,17 lett volna 84,42 helyett. A kutatás CQL-vázlata ezt még nem
   tartalmazta.
3. **Időzóna.** A `date from` a tárolt eltolás szerinti napot adja
   (`DateTime.getDate()`). Kipróbálva: egy okt. 6-i 00:30-as mérés
   `+02:00`-val helyesen okt. 6-ra esik. `Z`-vel (UTC, `2026-10-05T22:30:00Z`)
   viszont okt. 5-re csúszik, és első napként kiesik. **A PULSE-exportnak
   helyi eltolással kell írnia.**
4. **Túlterhelt függvények.** A fordító figyelmeztetett, hogy szignatúra
   nélkül a túlterhelt FHIRHelpers-függvények futásidőben kétértelműek
   lehetnek. Ezért a fordítás `signatures=Overloads` kapcsolóval megy. A
   3.3.2 ezt nem olvassa: futásidőben típus szerint választ, több találatnál
   az utolsót (`lib/elm/reusable.js`). A szabály csak egyértelmű
   FHIRHelpers-függvényeket hív (`ToQuantity`, `ToConcept`), és a
   `status`/`id` mezőt `.value`-val olvassa. A maradék 3 figyelmeztetés
   („operand identifier … hiding”) a FHIRHelpers saját kódjából jön.
5. **Lebegőpontos átlag.** A 3.x `Number`-rel számol (lásd fent). Ennél az
   adatnál ez nem változtat az eredményen, de a határ közeli esetekhez és a
   kerekítéshez döntés kell (lásd a feltételezéseket).
6. Egyebek, gond nélkül: a fordítás elsőre sikerült, nem támogatott CQL-elem
   nem kellett.

## A próba feltételezései (nem végleges döntések)

Az alapértékek a kutatás javaslatai. A végleges döntés a hallgatóé. Ahol lehetett,
CQL-paraméter lett belőlük (`cql/PulseHbpmAverage.cql`).

| # | Kérdés | A próbában | Paraméter? |
|---|---|---|---|
| 1 | Kiessen-e az első nap a követésnél is? | igen | `Exclude First Day` (true) |
| 2 | Mi az „első nap”? | az első érvényes mérést tartalmazó naptári nap; a másik lehetőség a sorozat (kirendelés) kezdőnapja, lásd G | `First Day Definition` ('FirstReadingDay') |
| 3 | Melyik időzóna szerinti nap? | a mérés tárolt eltolása szerinti (helyi) nap | nem |
| 4 | Leolvasások vagy alkalmak átlaga? | minden leolvasás egyszerű átlaga (minden Observation egy leolvasás); alkalmankénti párátlag nincs megvalósítva (teljes pároknál ugyanazt adja) | nem |
| 5 | Napi 2 alkalom, reggel/este, ≥1 perc, ülő helyzet | nem ellenőrzi | nem |
| 6 | ÉS vagy VAGY a célértéknél? | mindkét átlagnak a határ alatt kell lennie | `Both Components Must Be Below Target` (true) |
| 7 | Minimum hány nap? | 3 értékelhető nap (az első nappal együtt 4) | `Min Included Days` (3) |
| 8 | Minimum mérésszám? | nincs | nem |
| 9 | Kerekítés az összevetés előtt? | nincs | `Comparison Rounding Precision` (null) |
| 10 | Életkorhatár és célértékek | 80 év; 135/85 alatta, 145/85 felette | `Age Threshold Years`, `Target …` (4 db) |
| 11 | Melyik napon számít az életkor? | a sorozat utolsó napján (ha nincs időszak: a kiértékelés napján) | nem |
| 12 | Mely mérések tartoznak a sorozatba? | a hívó adja meg az időszakot (`Series Period`, a próbában okt. 5. 0:00 – okt. 9. 0:00, felül nyitott); ha nincs megadva, minden mérés | `Series Period` (null) |
| 13 | Mely státusz számít? | `final`, `amended`, `corrected` (a javított adat kezelése az M3 témája) | nem |
| 14 | Hiányos mérés (pl. csak szisztolés, vagy nem `mm[Hg]`) | teljesen kimarad, az azonosítója az `incompleteReadingIds` listába kerül | nem |
| 15 | Nincs elég adat | `targetMet` = null, ami soha nem kedvező eredmény (a PULSE-ban: szürke státusz) | nem |
| 16 | A csomag | `collection` Bundle, egy beteg; a `cql-exec-fhir` nem szűr `subject` szerint | nem |

## Nem ellenőrzött

- A Bundle profilmegfelelése: a HL7-validátort nem futtattam.
- Más fordító- és motorverzió (pl. fordító 4.7.0 vagy 5.4.0, `cql-execution` 4.0-béta).
- A LOINC-licencmegjegyzés pontos szövege. A fájlok LOINC-kódokat és angol
  LOINC-neveket tartalmaznak; a szükséges megjegyzést a loinc.org/license
  alapján kell majd felvenni.
- A NICE-ajánlások értelmezése (lásd a feltételezéseket).

## Fájlok

| Fájl | Tartalom |
|---|---|
| `cql/PulseHbpmAverage.cql` | a szabály (`library PulseHbpmAverage version '0.1.0'`) |
| `cql/FHIRHelpers-4.0.1.cql` | segédkönyvtár, változatlan (lásd fent) |
| `elm/*.json` | a lefordított ELM (a fordító nélküli futtatáshoz) |
| `adat/beteg_hbpm_bundle.json` | a mesterséges beteg FHIR R4 csomagja |
| `forditas.mjs` | fordítókliens (CQL -> ELM a fordítószolgáltatással) |
| `futtatas.mjs` | a motor futtatása, a forgatókönyvek, JSON-kimenet |
| `eredmeny/eredmeny.json` | a motor kimenete (verziók, sha256, 7 forgatókönyv) |
| `ellenorzes/kezi_szamitas.py` | a motortól független, azonos feltevésekkel végzett kézi számítás és összevetés |
| `docker-compose.yml`, `Dockerfile`, `package*.json` | a futtatókörnyezet rögzítése |
| `.gitattributes` | LF sorvég, hogy a rögzített sha256 egy friss klónban is egyezzen |
