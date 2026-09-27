# Folyamat- és architektúraábrák

Kiegészítő ábrák az adatmodellhez: a két kulcs-életciklus állapotgépe és a
rendszer architektúrája.

## Riasztás-életút (állapotgép)

Minden átmenet `AlertEvent`-ként rögzül (ki, mikor, mit); a lezárás indoklása
kötelező. A nyitott riasztás melletti új kiváltó adat nem új riasztás, hanem
„ismételt aktiválódás" esemény.

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

A beteg zöld/sárga/piros/szürke státusza a **nyitott** jelzésekből számítódik
— a riasztás lezárása tehát elkülönül a beteg állapotjelzésétől: lezáráskor a
státusz újraszámítódik a fennmaradó nyitott jelzések alapján.

## Kirendelés-életciklus (követési terv eleme)

```mermaid
stateDiagram-v2
    [*] --> Kirendelve : orvos kirendeli<br/>(mit, milyen gyakran, határidő)
    Kirendelve --> Esedékes : esedékességi idő elérve
    Esedékes --> Teljesítve : mérés / kitöltés beérkezik
    Esedékes --> Elmulasztva : határidő lejár adat nélkül
    Elmulasztva --> [*] : „elmaradt adatküldés" szabály aktiválódik<br/>(szürke státusz felé)
    Teljesítve --> [*]
```

## Architektúra

```mermaid
flowchart LR
    B[Böngésző<br/>React + TypeScript SPA] -->|HTTPS / REST + JWT| A[FastAPI backend<br/>szolgáltatásréteg, jogosultság-szűrés]
    A --> R[Szabálymotor<br/>4 szabálytípus, verziózott kiértékelés]
    A --> DB[(PostgreSQL<br/>SQLAlchemy + Alembic)]
    R --> DB
    R -->|riasztás tranzakcióban| DB
    A --> Q[E-mail küldő<br/>retry + kézbesítés-nyilvántartás]
    Q --> M[SMTP<br/>dev: Mailpit]
    subgraph DC[Docker Compose]
        A
        R
        DB
        Q
        M
    end
    CI[GitHub Actions<br/>CI/CD] -.->|build, teszt, deploy| DC
```

A szabálymotor a backend része (nem külön szolgáltatás), de logikailag
elkülönített modul: bemenete a beérkező/javított adat, kimenete riasztás vagy
„ismételt aktiválódás" esemény, mindig adatbázis-tranzakción belül. Az
e-mail-küldés a tranzakción kívül, újrapróbálkozással történik.
