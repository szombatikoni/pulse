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
    MeasurementValue }o--|| MeasurementComponent : "komponense"

    Rule }o--|| PatientProfile : "betegre vonatkozik"
    Rule ||--|{ RuleVersion : "verziói"
    RuleVersion ||--o{ Alert : "kiváltotta"
    Alert }o--|| PatientProfile : "betege"
    Alert ||--|{ AlertEvent : "eseménytörténet"
    Alert ||--o{ NotificationDelivery : "kézbesítések"

    QuestionnaireTemplate ||--|{ QuestionnaireVersion : "verziói"
    QuestionnaireVersion ||--|{ Question : "kérdései"
    Assignment }o--|| PatientProfile : "betege"
    Assignment }o--o| QuestionnaireVersion : "kirendelt kérdőív"
    Assignment }o--o| MeasurementType : "előírt mérés"
    Assignment ||--o{ Submission : "teljesítései"
    Submission }o--|| QuestionnaireVersion : "kitöltéskori verzió"
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
        datetime measured_at
        datetime recorded_at
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
        uuid rule_version_id FK
        enum status "new|seen|assigned|closed"
        enum severity
        json trigger_data_ids "kiváltó adatok azonosítói"
        datetime created_at
    }
    AlertEvent {
        uuid id PK
        uuid alert_id FK
        uuid actor_id FK
        enum event_type "created|seen|assigned|closed|re_triggered|re_evaluated"
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
        json scoring_thresholds "immutabilis"
        datetime created_at
    }
    Question {
        uuid id PK
        uuid version_id FK
        int order_no
        enum question_type "scale_1_5|scale_1_10|single|multi"
        string text
        json options_scores "válaszlehetőségek és pontszámok"
    }
    Assignment {
        uuid id PK
        uuid patient_id FK
        uuid assigned_by FK
        enum target_kind "questionnaire|measurement"
        uuid questionnaire_version_id FK "0..1, kérdőív-kirendelésnél"
        uuid measurement_type_id FK "0..1, mérés-előírásnál"
        string frequency "pl. naponta, hetente"
        datetime due_at
        enum status "assigned|due|completed|missed"
    }
    Submission {
        uuid id PK
        uuid assignment_id FK
        uuid version_id FK
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
után nem módosulnak — minden változtatás új verziósort szúr be. Az `Alert` a
kiváltó szabályverzióra, a `Submission` a kitöltéskori kérdőívverzióra
hivatkozik, így a régi riasztások és kitöltések jelentése és pontszáma utólag
nem változhat.

**Többértékű mérés.** A vérnyomás két értékből áll (szisztolés/diasztolés),
ezért a méréstípus komponensekre bomlik (`MeasurementComponent`), és egy
mérés komponensenként egy-egy `MeasurementValue` sort kap. Ez normalizált
megoldás: a szabálykiértékelés komponens-szinten tud küszöböt vizsgálni, és
új többértékű típus séma­módosítás nélkül vehető fel. Az alternatíva (értékek
JSONB-oszlopban) a dolgozat relációs vs. NoSQL alfejezetében kerül
összevetésre.

**Javított mérés.** A javítás nem írja felül az eredetit: az új `Measurement`
a `corrected_from` mezővel hivatkozik rá. A javítás újrakiértékelést vált ki,
amely `re_evaluated` eseményként rögzül az érintett riasztás történetében.

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
szabályhatár-vizsgálatoknál. A szerkesztő kérdésenként csak egész pontot enged
felvenni, így az összeg sem lehet tört; a számított értékek (pl. trendvizsgálat
átlaga) futásidőben lehetnek törtek, de tárolt pontszám nem.

**Tudatosan elhagyott mezők.** A diagram a szerkezetet mutatja, nem a teljes
mezőlistát: a betegprofilban éles rendszerben elvárt további adatok — nem
(orvosilag releváns, pl. referenciatartományoknál), TAJ-szám, telefonszám,
lakcím — a demonstrációs scope-ból tudatosan kimaradtak, mert kizárólag
mesterséges adatokkal dolgozunk, és minden további mező karbantartó felületet
és tesztet is igényelne. Utólagos felvételük egy-egy oszlop hozzáadása
(Alembic-migráció), a szerkezetet nem érinti. *Konzultációs kérdés: elegendő-e
így, vagy kerüljön be 1–2 további mező (pl. nem)?*

**Megfontolás alatt:** `AuditLog` tábla az adminisztratív műveletek
naplózására — az M2 tapasztalatai alapján dől el, bekerül-e a scope-ba.
