# Fontosabb kódrészletek

Ez a fejezet hat helyet mutat be a backendből, ahol a működési szabályok
kóddá válnak. A szabályok tartalmát a Működés fejezet írja le, itt csak azt
mutatom meg, hogyan valósulnak meg, és mire kellett közben figyelni. A
részletek szó szerint a kódból származnak. Ahol rövidítettem, a kihagyott
részt `# …` jelzi; így maradt ki a legtöbb dokumentációs szöveg (docstring)
és néhány mechanikus mezőfelsorolás. Több részlet csak a függvény törzsét
vagy annak egy ágát mutatja, a fejléc és a docstring nélkül; ezeknél a
behúzást egységesen csökkentettem.

## Riasztás nyitása és deduplikáció

A szabálymotor minden szabálytípusnál ugyanazon a függvényen keresztül nyit
riasztást (`backend/app/services/rules.py`, `_raise_alert`). Ez dönti el, hogy
új riasztás keletkezik, vagy a meglévő nyitott riasztás kap „ismételt
aktiválódás" eseményt. A szabályt a Működés fejezet „Riasztás, deduplikáció
és szabálymódosítás" szakasza írja le. A függvény törzse:

```python
alert = open_alert(db, patient_id, rule.id, for_update=True)
if alert is None:
    alert = Alert(
        # …
    )
    db.add(alert)
    db.flush()
    event_type = AlertEventType.CREATED
else:
    if SEVERITY_RANK[version.severity] > SEVERITY_RANK[alert.severity]:
        alert.severity = version.severity
    event_type = AlertEventType.RE_TRIGGERED
db.add(
    AlertEvent(
        alert_id=alert.id,
        event_type=event_type,
        rule_version_id=version.id,
        trigger_data_ids=trigger_ids,
        created_at=now,
    )
)
return alert
```

Az esemény mindkét ágon tárolja az alkalmazott szabályverziót és a kiváltó
adatok azonosítóit; a felület ebből írja ki a magyarázatot. A súlyosság csak
felfelé változik. Ha az orvos egy időszakra olyan szabályt állított be,
amely súlyosan jelzett, akkor azt az állapotot súlyosnak ítélte, és ez akkor
is így marad, ha később enyhébb szabályt vesz fel. Ha egy új szabályverzió
visszavehetné egy nyitott riasztás súlyosságát, az utólag átírná a régi
jelzés jelentését, ezt kritikus hibának tartanám.

Az `open_alert` a beteg és a szabály nem lezárt riasztását keresi, és
`for_update=True` mellett sorzárral (`SELECT … FOR UPDATE`) olvassa. Ha egy
orvos közben épp lezárja a riasztást, a kiértékelés megvárja a lezárást; a
PostgreSQL ekkor a friss soron újraellenőrzi a feltételt, a lezárt riasztás
kiesik, és új riasztás nyílik, nem a lezártba kerül esemény. A
deduplikációt az adatbázis is őrzi: egy részleges egyedi index
(`uq_alerts_open_per_rule`) szerint egy beteg és szabály párosra legfeljebb
egy nem lezárt riasztás lehet. Ismert korlát: ha két rögzítés egyszerre
váltaná ki ugyanazt a még nem létező riasztást, a nem létező sort a zár nem
védi, a második az indexbe ütközik, és a mérése is visszagördül. A javítást
(a beteg szabályainak zárolása a kiértékelés elején) a negyedik mérföldkőre
tettem.

## Az időablakos szabály és a javított mérések

Az új mérés mentésekor az `evaluate_measurement` előbb a küszöbszabályokat,
majd az időablakos szabályokat értékeli ki. Ez utóbbi ága
(`backend/app/services/rules.py`):

```python
for rule, version in _active_rules(db, measurement.patient_id, RuleType.WINDOW):
    params = WindowParams.model_validate(version.params)
    # Csak határsértő új mérés értékel: egy rendben lévő mérés nem nyithat
    # (lezárás után újra) riasztást a még ablakban lévő korábbi értékekből
    # …
    if not threshold_violations(params, measurement):
        continue
    violating = window_violations(db, params, measurement)
    if len(violating) >= params.count:
        trigger_ids = [str(m.id) for m in violating]
        touched.append(
            _raise_alert(db, rule, version, measurement.patient_id, trigger_ids, now)
        )
```

A korai `continue` a lezárás utáni viselkedés miatt kell: ha az orvos lezárt
egy riasztást, egy rendben lévő mérés ne nyissa újra csak azért, mert az
ablakban még ott vannak a régi magas értékek. Az ablakot a
`window_violations` számolja: a beteg azonos típusú méréseit veszi az új mérés
idejéig, `window_days` nappal visszamenőleg, mindkét szélét beleértve. A
riasztás kiváltói az ablak összes határsértő mérése, nem csak az utolsó. A
kód dokumentációja egy ismert korlátot is rögzít: a visszadátumozott mérés
csak a saját időpontjáig látja az ablakot, a nála később mért értékeket nem.

A javított mérés új sor, amely az eredetire hivatkozik
(`corrected_from`), az eredeti pedig megmarad. Hogy melyik mérés érvényes, azt
egyetlen közös feltétel dönti el (`backend/app/models/measurement.py`):

```python
def not_superseded() -> ColumnElement[bool]:
    # …
    correction = aliased(Measurement)
    return ~exists().where(correction.corrected_from == Measurement.id)
```

Érvényes az a mérés, amelyre nem hivatkozik javítás, így a javítási láncból
mindig csak az utolsó elem marad. Ezt a feltételt használja az időablak, a
frissesség, a Kezelve státusz megerősítő adatának vizsgálata, a FHIR-kiadás
és a NICE-kiértékelés.
Az előzménylista és a régi riasztásesemények magyarázata szándékosan nem
használja, mert ott az eredeti értéknek is látszania kell.

## A legutóbbi lezárt alkalom a státuszhoz

A státusz számított érték (lásd a Működés fejezet „A beteg státusza"
szakaszát). Az Adathiányhoz a rendszernek előírásonként a legutóbbi lezárt
alkalmat kell ismernie (`backend/app/services/status.py`,
`latest_closed_occurrences`):

```python
today = now.astimezone(settings.tz).date()
latest = db.scalars(
    select(AssignmentOccurrence)
    .join(Assignment, AssignmentOccurrence.assignment_id == Assignment.id)
    .outerjoin(Assignment.template)
    .where(
        Assignment.patient_id == patient_id,
        *valid_on(today),
        or_(
            Assignment.target_kind == AssignmentTarget.MEASUREMENT,
            QuestionnaireTemplate.is_active.is_(True),
        ),
        or_(
            AssignmentOccurrence.status != OccurrenceStatus.DUE,
            AssignmentOccurrence.due_at < now,
        ),
    )
    # PostgreSQL DISTINCT ON: előírásonként a legkésőbbi határidejű sor.
    .ext(distinct_on(AssignmentOccurrence.assignment_id))
    .order_by(AssignmentOccurrence.assignment_id, AssignmentOccurrence.due_at.desc())
).all()
return sorted(latest, key=lambda o: (o.due_at, o.id))
```

„Lezárt" itt nemcsak a teljesített és az elmulasztott alkalom, hanem az is,
amelyik még esedékes, de a határideje lejárt. Ezért vált a státusz már a
határidőnél Adathiányra, akkor is, ha a mérés még pótolható. Az inaktív
kérdőívre szóló előírás kimarad, mert arra a háttérfolyamat nem nyit
alkalmat, így a beteg sem teljesíthetné. A `DISTINCT ON` egy lekérdezésben
adja vissza előírásonként a legkésőbbi sort. A PostgreSQL adott volt, a
rendszer máshol is a saját lehetőségeire épít, ezért itt is a rövidebb,
PostgreSQL-specifikus megoldást választottam. Adatbázisváltás esetén ezt a
lekérdezést szabványos ablakfüggvényre kellene átírni.

Ha a legutóbbi lejárt időszaknak még nincs tárolt sora (például mert a
háttérfolyamat még nem járt ott), a `lapsed_without_row` függvény pótolja: az
alkalom ilyenkor nem teljesülhetett, mert a teljesítés mindig sort hoz létre.
Így a státusz nem függ attól, hogy a háttérfolyamat mikor futott, és maga sem
ír semmit.

## Alkalmak nyitása ismételhetően

A háttérfolyamat óránként nyitja a soron következő alkalmakat (lásd az
Architektúra fejezetet), de a beteg mérése is megnyithatja a saját időszakának
alkalmát, ha az még nincs meg. A kettő ugyanazt az alkalmat egyszerre is
létrehozhatná. A beszúrás ezért így néz ki
(`backend/app/services/occurrences.py`, `_insert`):

```python
def _insert(
    db: Session, assignment: Assignment, period: Period, version_id: uuid.UUID | None
) -> bool:
    # …
    inserted = db.scalar(
        insert(AssignmentOccurrence)
        .values(
            id=uuid.uuid4(),
            assignment_id=assignment.id,
            period_start=period.start,
            due_at=period.due_at,
            status=OccurrenceStatus.DUE,
            questionnaire_version_id=version_id,
        )
        .on_conflict_do_nothing(index_elements=["assignment_id", "due_at"])
        .returning(AssignmentOccurrence.id)
    )
    return inserted is not None
```

Az `(assignment_id, due_at)` páros egyedi. Sima beszúrásnál a második fél
ütközési hibát kapna, és vele a teljes mentés, a mérés is elveszne; így a
dupla csendben kimarad, és mindkét fél ugyanazt a sort olvassa vissza. Az
ismételhetőséget tehát egy adatbázis-megkötés garantálja, nem a kód
óvatossága. Hogy a sor most jött-e létre, a `RETURNING` mondja meg: az
SQLAlchemy ennél a hívásnál a módosított sorok számára 0-t adott, ezért arra
nem lehetett építeni. Kérdőívnél a `version_id` az alkalom létrejöttekor
aktuális kérdőívverzió; a beteg ezt tölti ki, akkor is, ha közben új verzió
készült.

## Új kérdőívverzió mentése zárolással

A kérdőív módosítása mindig új verziót hoz létre, a régit az adatbázis
triggere védi a módosítás és a törlés ellen
(`backend/app/services/questionnaires.py`, `add_version`):

```python
db.execute(
    select(QuestionnaireTemplate.id)
    .where(QuestionnaireTemplate.id == template.id)
    .with_for_update()
)
last = current_version(db, template.id, required=False)
last_no = last.version_no if last else 0
if base_version_no is not None and base_version_no != last_no:
    raise QuestionnaireError("stale_version", conflict=True, current_version_no=last_no)
version = QuestionnaireVersion(
    template_id=template.id,
    version_no=last_no + 1,
    # …
)
db.add(version)
db.flush()
return version
```

Két védelem van itt. A sablon sorának zárolása a verziószám olvasása előtt
történik, így két egyidejű mentés egymás után fut, és a második már az első
verzióját látja; a `(template_id, version_no)` egyediség nem sérülhet. A
`base_version_no` az a verzió, amelyből a szerkesztés indult. Ha közben valaki
más mentett, a mentés 409-es ütközés lesz, és az orvos nem írja felül tudtán
kívül a kollégája módosítását; a felület ekkor felajánlja a friss változat
betöltését. A szabályverziók mentése (`add_rule_version`) ugyanígy zárol. A
kihagyott rész a kérdéseket és a sávokat másolja a verzióba; a skálás
kérdések válasz → pont táblája ekkor készül el, a Működés fejezet
„Kérdőív-pontozás" szakaszában leírt képlettel.

## Jogosultsági szűrés

Az egy betegre szóló kéréseknél a hozzáférés egy függvényen dől el
(`backend/app/services/access.py`, `can_access_patient`):

```python
def can_access_patient(db: Session, user: User, patient_id: uuid.UUID) -> bool:
    # …
    if not user.is_active:
        return False
    if user.role is UserRole.PATIENT:
        return user.patient_profile is not None and user.patient_profile.id == patient_id
    if user.role is UserRole.DOCTOR:
        return user.doctor_profile is not None and active_assignment_exists(
            db, user.doctor_profile.id, patient_id
        )
    return False
```

A beteg csak a sajátját éri el, az orvos csak azt a beteget, akivel éppen
érvényes összerendelése van, az admin pedig egyetlen beteg adatát sem. Az
utolsó `return False` miatt minden, ami nincs kifejezetten megengedve,
tiltott. Az összerendelés érvényességét az `active_assignment_exists`
minden hívásnál az adatbázisból kérdezi le (`valid_from` legfeljebb most,
`valid_to` üres vagy későbbi), ezért egy összerendelés megszüntetése vagy
létrejötte azonnal hat, nem csak a következő bejelentkezéskor. A végpontok a
`backend/app/api/deps.py` `ensure_patient_access` függvényén át hívják, a
kódban jelenleg kilenc végpontfájl 21 helyén; a riasztásműveleteknél a
riasztás betegére. Ez nem létező betegre is 403-at ad, így a válaszból nem
derül ki, létezik-e az azonosító. A hozzá tartozó teszteket a Tesztelés
fejezet mutatja be.
