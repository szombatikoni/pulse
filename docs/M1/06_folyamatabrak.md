# Folyamat- és architektúraábrák

Kiegészítő ábrák az adatmodellhez: a riasztás és az alkalom életciklusa, a
beteg-státusz előállítása és a rendszer architektúrája. A működési
szabályokat példákon a `07_mukodesi_szabalyok.md` mutatja be.

## Riasztás-életút (állapotgép)

Minden átmenet `AlertEvent`-ként rögzül (ki, mikor, mit, melyik
szabályverzió, milyen kiváltó adat); a lezárás indoklása kötelező. A nyitott
riasztás melletti új kiváltó adat nem új riasztás, hanem „ismételt
aktiválódás” esemény. A szabály módosítása és a kiváltó adat javítása szintén
eseményként rögzül, állapotváltás nélkül; javítás után a riasztás
„kiváltó adat javítva” jelölést kap, és csak az orvos zárhatja le.

```mermaid
stateDiagram-v2
    [*] --> Keletkezett : szabály aktiválódik
    Keletkezett --> Megtekintett : orvos megnyitja
    Megtekintett --> FelelőshözRendelt : felelős kijelölése
    Keletkezett --> FelelőshözRendelt : felelős kijelölése
    Megtekintett --> Lezárt : lezárás (indoklás kötelező)
    FelelőshözRendelt --> Lezárt : lezárás (indoklás kötelező)
    Keletkezett --> Keletkezett : ismételt aktiválódás<br/>(súlyosság emelkedhet)
    Megtekintett --> Megtekintett : ismételt aktiválódás
    FelelőshözRendelt --> FelelőshözRendelt : ismételt aktiválódás
    Lezárt --> [*]
```

## Alkalom-életciklus (egy előírás egy alkalma)

Az alkalmakat az ütemezett háttérfolyamat hozza létre az előírás szerint, és
ugyanez a folyamat jelöli elmulasztottnak a lejárt, teljesítetlen alkalmakat
— akkor is, ha semmilyen adat nem érkezik. Mérés rögzítésekor a rendszer
előbb ugyanezt az ellenőrzést futtatja, így a határidő után rögzített mérés
mindig már elmulasztott alkalomhoz kerül, és azt késve teljesíti.

```mermaid
stateDiagram-v2
    [*] --> Esedékes : a háttérfolyamat létrehozza<br/>(az előírás szerint)
    Esedékes --> Teljesítve : rögzítés a határidőig
    Esedékes --> Elmulasztva : a határidő rögzítés nélkül lejár<br/>(ellenőrzés 15 percenként)
    Elmulasztva --> KésveTeljesítve : pótlás: az időszakba eső mérés,<br/>legfeljebb 2 napra visszamenőleg
    Teljesítve --> [*]
    KésveTeljesítve --> [*]
    Elmulasztva --> [*] : az időszak vége után<br/>2 nappal végleges
```

Az elmulasztás a beteg státuszát Adathiányra állítja; az „elmaradt
adatküldés” szabály a beállított számú elmulasztás után riasztást nyit.

## A beteg-státusz előállítása

Friss adat: ahol már lejárt alkalom van, a frissességet az alkalmak
teljesítése adja (ezt a „Legutóbbi alkalom elmaradt?” pont vizsgálja). Előírás
nélkül, illetve az első határidő előtt a legutóbbi mérés vagy kitöltés
legfeljebb 7 napos (rendszerszintű beállítás). Adat nélküli, frissen felvett
beteg így Adathiány.

```mermaid
flowchart TD
    A{Súlyos nyitott<br/>riasztás?} -- igen --> S[Súlyos]
    A -- nem --> B{Közepes nyitott<br/>riasztás?}
    B -- igen --> F[Figyelem]
    B -- nem --> C{Legutóbbi alkalom<br/>elmaradt, pótlás nélkül?}
    C -- igen --> D[Adathiány]
    C -- nem --> G{Van friss adat?}
    G -- nem --> D
    G -- igen --> E{Lezárt riasztás óta<br/>jött rendben lévő adat?}
    E -- nem --> K[Kezelve]
    E -- igen / nem volt lezárás --> R[Rendben]
```

## Architektúra

```mermaid
flowchart LR
    B[Böngésző<br/>React + TypeScript SPA] -->|HTTPS / REST + JWT| A[FastAPI backend<br/>szolgáltatásréteg, jogosultság-szűrés]
    A --> R[Szabálymotor<br/>4 szabálytípus, verziózott kiértékelés]
    A --> DB[(PostgreSQL<br/>SQLAlchemy + Alembic)]
    R -->|riasztás tranzakcióban| DB
    W[Háttérfolyamat<br/>alkalmak, határidő-ellenőrzés<br/>15 percenként] --> R
    W --> DB
    A --> Q[E-mail küldő<br/>retry + kézbesítés-nyilvántartás]
    Q --> M[SMTP<br/>dev: Mailpit]
    subgraph DC[Docker Compose]
        A
        R
        W
        DB
        Q
        M
    end
    CI[GitHub Actions<br/>CI/CD] -.->|build, teszt, deploy| DC
```

A szabálymotor a backend része (nem külön szolgáltatás), de logikailag
elkülönített modul: bemenete a beérkező vagy javított adat, illetve egy
elmulasztott alkalom, kimenete riasztás vagy riasztási esemény, mindig
adatbázis-tranzakción belül. A háttérfolyamat ugyanazt a backend-kódot
futtatja külön konténerben: létrehozza az esedékes alkalmakat, és
elmulasztottnak jelöli a lejártakat. Az ellenőrzés egyetlen, ismételten is
biztonságosan futtatható függvény, amelyet a tesztek szimulált idővel, a
bemutató pedig kézi indítással is meghívhat. Az e-mail-küldés a tranzakción
kívül, újrapróbálkozással történik.
