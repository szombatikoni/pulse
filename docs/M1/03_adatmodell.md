# Adatmodell (E-K diagram)

> A diagram Mermaid-formátumú (GitHub megjeleníti); a leadandó változat
> draw.io-ban készül ugyanebből a tartalomból.

```mermaid
erDiagram
    User ||--o| PatientProfile : "profilja"
    User ||--o| DoctorProfile : "profilja"
    DoctorProfile ||--o{ DoctorPatient : "összerendelés"
    PatientProfile ||--o{ DoctorPatient : "összerendelés"

    MeasurementType ||--|{ MeasurementComponent : "komponensei"
    PatientProfile ||--o{ Measurement : "rögzíti"
    Measurement }o--|| MeasurementType : "típusa"
    Measurement ||--|{ MeasurementValue : "értékei"
    Measurement }o--o| Measurement : "javítása (corrected_from)"
    MeasurementValue }o--|| MeasurementComponent : "komponense"

    Rule }o--|| PatientProfile : "betegre vonatkozik"
    Rule ||--|{ RuleVersion : "verziói"
    Rule ||--o{ Alert : "szabálya (deduplikáció)"
    RuleVersion ||--o{ Alert : "megnyitó verzió"
    RuleVersion ||--o{ AlertEvent : "alkalmazott verzió"
    Alert }o--|| PatientProfile : "betege"
    Alert ||--|{ AlertEvent : "eseménytörténet"
    Alert ||--o{ NotificationDelivery : "kézbesítések"

    QuestionnaireTemplate ||--|{ QuestionnaireVersion : "verziói"
    QuestionnaireVersion ||--|{ Question : "kérdései"
    Assignment }o--|| PatientProfile : "betege"
    Assignment }o--o| QuestionnaireTemplate : "kirendelt kérdőív"
    Assignment }o--o| MeasurementType : "előírt mérés"
    Assignment ||--o{ AssignmentOccurrence : "alkalmai"
    AssignmentOccurrence }o--o| QuestionnaireVersion : "rögzített verzió"
    AssignmentOccurrence |o--o| Measurement : "teljesítő mérés"
    AssignmentOccurrence ||--o| Submission : "teljesítő kitöltés"
    Submission }o--|| QuestionnaireVersion : "kitöltött verzió"
    Submission ||--|{ Answer : "válaszai"
    Answer }o--|| Question : "kérdése"

    DoctorProfile ||--o{ Note : "írja"
    Note }o--|| PatientProfile : "betegről"
    User ||--o{ Notification : "értesítései"

    User {
        uuid id PK
        string email
        string password_hash
        enum role "patient|doctor|admin"
        bool is_active
    }
    PatientProfile {
        uuid id PK
        uuid user_id FK
        string name
        date birth_date
    }
    DoctorProfile {
        uuid id PK
        uuid user_id FK
        string name
    }
    DoctorPatient {
        uuid id PK
        uuid doctor_id FK
        uuid patient_id FK
        datetime valid_from
        datetime valid_to "NULL = aktív"
    }
    MeasurementType {
        uuid id PK
        string code "pl. blood_pressure"
        string name
        string unit
    }
    MeasurementComponent {
        uuid id PK
        uuid type_id FK
        string code "pl. systolic"
        string name
        float ref_min
        float ref_max
    }
    Measurement {
        uuid id PK
        uuid patient_id FK
        uuid type_id FK
        datetime measured_at "a beteg szerint, max. 2 napra vissza"
        datetime recorded_at "a rögzítés tényleges ideje"
        uuid corrected_from FK "javítás esetén az eredeti"
    }
    MeasurementValue {
        uuid id PK
        uuid measurement_id FK
        uuid component_id FK
        float value
    }
    Rule {
        uuid id PK
        uuid patient_id FK
        uuid created_by FK
        bool is_active
    }
    RuleVersion {
        uuid id PK
        uuid rule_id FK
        int version_no
        enum rule_type "threshold|window|questionnaire|missing_data"
        json params "immutabilis"
        enum severity
        datetime created_at
        uuid created_by FK
    }
    Alert {
        uuid id PK
        uuid patient_id FK
        uuid rule_id FK "deduplikáció: beteg + szabály"
        uuid rule_version_id FK "a megnyitáskori verzió"
        enum status "new|seen|assigned|closed"
        enum severity "aktuális súlyosság"
        json trigger_data_ids "megnyitáskori kiváltó adatok"
        bool needs_review "kiváltó adat javítva"
        datetime created_at
    }
    AlertEvent {
        uuid id PK
        uuid alert_id FK
        uuid actor_id FK "NULL = rendszer"
        enum event_type "created|seen|assigned|closed|re_triggered|rule_changed|trigger_corrected"
        uuid rule_version_id FK "az eseménykor alkalmazott verzió"
        json trigger_data_ids "az eseményt kiváltó adatok"
        string reason "lezárásnál kötelező"
        datetime created_at
    }
    NotificationDelivery {
        uuid id PK
        uuid alert_id FK
        string recipient
        enum status "pending|sent|failed"
        int attempts
        datetime last_attempt_at
    }
    Note {
        uuid id PK
        uuid doctor_id FK
        uuid patient_id FK
        text content
        datetime created_at
    }
    Notification {
        uuid id PK
        uuid user_id FK
        string title
        text body
        bool is_read
        datetime created_at
    }
    QuestionnaireTemplate {
        uuid id PK
        string name
        uuid created_by FK
        bool is_active
    }
    QuestionnaireVersion {
        uuid id PK
        uuid template_id FK
        int version_no
        json scoring_thresholds "kiértékelési határok, immutabilis"
        datetime created_at
    }
    Question {
        uuid id PK
        uuid version_id FK
        int order_no
        enum question_type "scale|single|multi"
        string text
        int scale_min "skálánál, pl. 1"
        int scale_max "skálánál, pl. 5"
        enum good_end "min|max, skálánál kötelező"
        json options_scores "válasz -> pont tábla"
    }
    Assignment {
        uuid id PK
        uuid patient_id FK
        uuid assigned_by FK
        enum target_kind "questionnaire|measurement"
        uuid questionnaire_template_id FK "0..1"
        uuid measurement_type_id FK "0..1"
        enum frequency "daily|weekly|every_n_days"
        int interval_days "every_n_days esetén"
        time suggested_time "opcionális ajánlott kezdőidő (csak megjelenítés)"
        time due_time "határidő az időszak utolsó napján"
        date start_date
        date end_date "NULL = visszavonásig"
        datetime revoked_at
    }
    AssignmentOccurrence {
        uuid id PK
        uuid assignment_id FK
        datetime period_start "az alkalom időszakának kezdete"
        datetime due_at "határidő; egyedi: assignment + due_at"
        enum status "due|fulfilled|fulfilled_late|missed"
        uuid measurement_id FK "0..1, teljesítő mérés"
        uuid questionnaire_version_id FK "0..1, rögzített verzió"
        datetime fulfilled_at
        datetime created_at
    }
    Submission {
        uuid id PK
        uuid occurrence_id FK "a teljesített alkalom"
        uuid version_id FK "= az alkalomhoz rögzített verzió"
        uuid patient_id FK
        int total_score
        datetime submitted_at
    }
    Answer {
        uuid id PK
        uuid submission_id FK
        uuid question_id FK
        json value
        int score
    }
```

## Tervezési indoklás

**Immutabilis verziók.** A `Rule` és a `QuestionnaireTemplate` csak identitást
hordoz; a tényleges paraméterek a `RuleVersion`, illetve a
`QuestionnaireVersion` + `Question` rekordokban élnek, amelyek létrejöttük
után nem módosulnak — minden változtatás új verziósort szúr be. A riasztás
eseményei a náluk alkalmazott szabályverzióra, a kitöltések az alkalomhoz
rögzített kérdőívverzióra hivatkoznak, így a régi riasztások és kitöltések
jelentése és pontszáma utólag nem változhat.

**Előírás és alkalom.** Az `Assignment` az orvos által beállított, ismétlődő
előírás (mit, milyen gyakran, milyen határidővel és ajánlott kezdőidővel,
mettől meddig). Egyes alkalmai külön `AssignmentOccurrence` sorok, amelyeket
egy ütemezett háttérfolyamat menet közben hoz létre — nem előre, egész
időszakra —, így az előírás módosítása vagy visszavonása nem igényli előre
legyártott sorok törlését. Minden alkalom rögzíti a saját határidejét,
státuszát (esedékes, teljesítve, késve teljesítve, elmulasztva) és a
teljesítő mérést vagy kitöltést; az `(assignment_id, due_at)` egyedi
megkötés garantálja, hogy a háttérfolyamat ismételt futása sem hoz létre
dupla alkalmat. Minden alkalomhoz egy időszak tartozik (`period_start` –
következő alkalom kezdete; napi előírásnál a naptári nap, heti vagy N napos
előírásnál a teljes időköz), a határidő (`due_at`) az időszak utolsó napján
van. A mérés a mérés időpontja (`measured_at`) alapján ahhoz az alkalomhoz
rendelődik, amelynek időszakába esik. Ha a rögzítés (`recorded_at`) a
határidő előtt történik, az alkalom teljesítve, ha utána, késve teljesítve;
mérést legfeljebb két napra visszamenőleg lehet rögzíteni, így az elmulasztott
alkalom az időszaka vége után két napig pótolható. Kérdőívnél nincs
visszadátumozás: a kitöltés a legrégebbi, még pótolható alkalomhoz rendelődik.
A `suggested_time` csak a beteg felületén megjelenő ajánlás, a hozzárendelést
nem befolyásolja.

**Riasztás és szabályverziók.** A deduplikáció a `rule_id` alapján történik
(beteg + szabály), ezért egy szabály módosítása után ugyanaz a nyitott
riasztás folytatódik, új riasztás nem keletkezik. Az `Alert` a megnyitáskori
verziót és kiváltó adatokat őrzi, minden további esemény (`AlertEvent`) a
saját alkalmazott verzióját és kiváltó adatait tárolja; így az
eseménytörténetből minden lépésnél kiolvasható, melyik verzió, milyen adat
alapján mit állapított meg.

**Javított mérés.** A javítás nem írja felül az eredetit: az új `Measurement`
a `corrected_from` mezővel hivatkozik rá. A javítás újrakiértékelést vált ki,
amely `trigger_corrected` eseményként rögzül; ha a feltétel már nem teljesül,
a riasztás nem záródik le automatikusan, hanem `needs_review` jelölést kap,
és az orvos zárja le indoklással.

**Beteg-státusz.** A státusz (Súlyos, Figyelem, Adathiány, Kezelve, Rendben)
számított érték, nem tárolt mező: a nyitott riasztásokból, az alkalmak
teljesítéséből, a friss adat meglétéből és a lezárás utáni megerősítő adatból
áll elő. Adat nélkül (pl. frissen felvett beteg) a státusz Adathiány, nem
Rendben. Előírás nélkül a frissességi határ (alapértelmezés szerint 7 nap)
rendszerszintű beállítás, ezért nem igényel külön mezőt. A számítás szabályait
a működési szabályokat bemutató fejezet írja le példákon.

**Pontozás iránya.** A pontozás egységes: több pont = rosszabb állapot. A
skálás kérdésnél a kérdőív készítője kötelezően megadja, melyik vég jelenti a
jobb állapotot (`good_end`); a rendszer ebből képlettel számítja ki a
válasz → pont táblát (a jobb vég mindig 0 pont), és ezt a verzióban
(`options_scores`) tárolja. Kitöltéskor a pontszám a tárolt táblából
olvasódik ki, így egy későbbi kódmódosítás sem változtathatja meg a régi
kitöltések pontjait.

**Többértékű mérés.** A vérnyomás két értékből áll (szisztolés/diasztolés),
ezért a méréstípus komponensekre bomlik (`MeasurementComponent`), és egy
mérés komponensenként egy-egy `MeasurementValue` sort kap. Ez normalizált
megoldás: a szabálykiértékelés komponens-szinten tud küszöböt vizsgálni, és
új többértékű típus séma­módosítás nélkül vehető fel. Az alternatíva (értékek
JSONB-oszlopban) a dolgozat relációs vs. NoSQL alfejezetében kerül
összevetésre.

**Riasztás-életút és kézbesítés.** Az `Alert` státuszváltásai kizárólag
`AlertEvent` rögzítésével történnek (ki, mikor, mit, lezárásnál indoklás).
Az e-mail-kézbesítést a `NotificationDelivery` külön követi újrapróbálkozási
számlálóval — a riasztás létrejötte tranzakcionális, a küldés ettől független.

**Összerendelés időbeli érvényességgel.** A `DoctorPatient` `valid_from` /
`valid_to` mezőkkel írja le a kapcsolat élettartamát; a jogosultság-szűrés
mindig az aktív (le nem zárt) összerendeléseken alapul.

**UUID elsődleges kulcsok.** Minden tábla azonosítója UUID, nem sorszámozott
egész. Az elsődleges védelem a szerveroldali jogosultság-szűrés; az UUID
pluszréteg (defense in depth): a 2¹²² méretű véletlen tér miatt idegen
rekordok azonosítói végigpróbálgatással (enumerációval) nem találhatók el, és
az azonosító nem szivárogtat mennyiségi információt (pl. hány beteg van a
rendszerben). Ára a nagyobb tárigény (16 bájt) és a szórtabb index — a vállalt
adatmennyiségnél ez nem érdemi hátrány.

**Egész pontszámok.** A kérdőív-pontszámok (`Answer.score`,
`Submission.total_score`) szándékosan egészek: ez a klinikai kérdőívek
konvenciója (pl. PHQ-9), és kizárja a lebegőpontos összehasonlítás hibáit a
szabályhatár-vizsgálatoknál. A számított értékek (pl. trendvizsgálat
átlaga) futásidőben lehetnek törtek, de tárolt pontszám nem.

**Tudatosan elhagyott mezők.** A diagram a szerkezetet mutatja, nem a teljes
mezőlistát. A betegprofil a bemutatáshoz szükséges szűk adattartalommal
marad: az éles rendszerben elvárt további adatok (nem, TAJ-szám, telefonszám,
lakcím) a demonstrációs scope-ból tudatosan kimaradtak, mert kizárólag
mesterséges adatokkal dolgozunk. Utólagos felvételük egy-egy oszlop
hozzáadása (Alembic-migráció), a szerkezetet nem érinti.

**Későbbre halasztva:** általános `AuditLog` tábla az adminisztratív
műveletek naplózására — a két központi modul elsőbbséget élvez.
