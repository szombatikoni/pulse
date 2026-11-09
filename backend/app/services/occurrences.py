"""Az előírások alkalmai (AssignmentOccurrence; M3, A2-A3).

A szabályok az M1 adatmodelljéből jönnek (docs/M1/03_adatmodell.md, „Előírás és
alkalom"); a beteg teendőlistája (tasks.py) is ezekből a tárolt alkalmakból
dolgozik:

- az időszak napi előírásnál a helyi naptári nap; heti vagy N napos előírásnál a
  kezdőnaptól (start_date) számított teljes időköz; ha az előírás vége
  (end_date) egy időszak belsejébe esik, az utolsó időszak a vég napjával
  zárul (csonka időszak, lásd period_containing);
- a határidő (due_at) az időszak utolsó napján, a due_time időpontban van;
- az alkalmat a háttérfolyamat menet közben nyitja meg (az aktuális és a még
  hiányzó korábbi időszakokét, előre nem), vagy az adat mentése, a teendőlista
  lekérése, illetve az előírás létrehozása hozza létre, ha még nincs;
- a mérés a measured_at, a kitöltés a beküldés ideje szerint kerül az
  időszakába; teljesítve, ha a rögzítés a határidőig történt, különben késve;
- elmulasztva: mérésnél az időszak vége + 48 óra (a visszadátumozás határa,
  MAX_BACKDATE, abszolút időben, lásd catch_up_deadline) után, kérdőívnél az
  időszak vége után azonnal.

A véglegesítést (commit) a hívó végzi, mint a mérésnél és a kitöltésnél.
"""

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import ColumnElement, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.models import (
    Assignment,
    AssignmentOccurrence,
    AssignmentTarget,
    Frequency,
    Measurement,
    OccurrenceStatus,
    QuestionnaireTemplate,
    QuestionnaireVersion,
    Submission,
)
from app.services.measurements import MAX_BACKDATE
from app.services.questionnaires import current_version
from app.services.rules import MissedTarget, evaluate_missed


@dataclass(frozen=True)
class Period:
    """Az előírás egy időszaka: [start, end), a határidő az utolsó napján (a
    lejáró előírás utolsó időszakánál a vég napján, lásd period_containing)."""

    first_day: date
    start: datetime
    end: datetime
    due_at: datetime


@dataclass(frozen=True)
class OccurrenceCheck:
    """Egy ellenőrzés eredménye: hány alkalom nyílt meg és hány zárult elmulasztva."""

    opened: int
    missed: int


def period_days(assignment: Assignment) -> int:
    if assignment.frequency is Frequency.DAILY:
        return 1
    if assignment.frequency is Frequency.WEEKLY:
        return 7
    return assignment.interval_days or 1


def local_midnight(day: date) -> datetime:
    return datetime.combine(day, time(0), tzinfo=settings.tz)


def period_containing(assignment: Assignment, day: date) -> Period:
    """Az előírás azon időszaka, amelybe a (helyi) nap esik. A kezdőnap előtti
    napra a kezdés előtti időszakot adja; azt a hívó szűri ki.

    Az utolsó időszak csonkolása (review K2, a hallgató döntése, 2026-11-01):
    ha az előírás vége (end_date) egy heti vagy N napos időszak belsejébe esik,
    az időszak utolsó napja a vég napja. A határidő így end_date + due_time, az
    időszak vége az end_date-et követő helyi éjfél, és a pótlási ablak is ettől
    számít (catch_up_deadline); a beteg a tényleges végdátumot látja
    határidőként. A vég után kezdődő időszakot nem csonkolja (azt a hívó szűri)."""
    days = period_days(assignment)
    k = (day - assignment.start_date).days // days
    first_day = assignment.start_date + timedelta(days=k * days)
    last_day = first_day + timedelta(days=days - 1)
    end_date = assignment.end_date
    if end_date is not None and first_day <= end_date < last_day:
        last_day = end_date
    return Period(
        first_day=first_day,
        start=local_midnight(first_day),
        end=local_midnight(last_day + timedelta(days=1)),
        due_at=datetime.combine(last_day, assignment.due_time, tzinfo=settings.tz),
    )


def periods_until(assignment: Assignment, last_day: date) -> Iterator[Period]:
    """Az előírás időszakai a kezdőnaptól a last_day-t tartalmazó időszakig
    (azzal együtt)."""
    step = timedelta(days=period_days(assignment))
    first_day = assignment.start_date
    while first_day <= last_day:
        yield period_containing(assignment, first_day)
        first_day += step


def period_end(occurrence: AssignmentOccurrence) -> datetime:
    """Az alkalom időszakának vége: a határidő helyi napját követő éjfél (a
    határidő mindig az utolsó napon van, ezért nem kell külön tárolni)."""
    last_day = occurrence.due_at.astimezone(settings.tz).date()
    return local_midnight(last_day + timedelta(days=1))


def catch_up_deadline(end: datetime) -> datetime:
    """Az időszak (end-ben végződő) pótlási ablakának vége: az időszak vége után
    pontosan 48 óra (MAX_BACKDATE), abszolút időben.

    Az UTC-re váltás szándékos: a helyi idejű datetime-hoz adott timedelta
    falióra szerint számol, így óraátállításkor 47 vagy 49 valós óra lenne,
    a mentés too_old határa (measurements.py: now - MAX_BACKDATE) viszont
    abszolút. Így a két határ mindig összeér, hézag és átfedés nélkül: amíg
    az időszakba eső mérés még rögzíthető, az alkalom nem elmulasztott, utána
    pedig már nem rögzíthető (a hallgató döntése, 2026-11-01; review K1)."""
    return end.astimezone(UTC) + MAX_BACKDATE


def missed_from(occurrence: AssignmentOccurrence) -> datetime:
    """Ettől az időponttól elmulasztott a nem teljesített alkalom. Mérésnél a
    pótlási ablak végéig vár: addig a visszadátumozott mérés még az időszakba
    eshet (ugyanaz a határ, mint a teendőlista „Pótlás" ajánlatánál)."""
    end = period_end(occurrence)
    if occurrence.assignment.target_kind is AssignmentTarget.MEASUREMENT:
        return catch_up_deadline(end)
    return end


def valid_on(day: date) -> list[ColumnElement[bool]]:
    """Az adott napon érvényes előírások feltétele: nincs visszavonva, és a nap
    a kezdet és az (opcionális) vég közé esik."""
    return [
        Assignment.revoked_at.is_(None),
        Assignment.start_date <= day,
        or_(Assignment.end_date.is_(None), Assignment.end_date >= day),
    ]


def _find(db: Session, assignment: Assignment, period: Period) -> AssignmentOccurrence | None:
    return db.scalar(
        select(AssignmentOccurrence).where(
            AssignmentOccurrence.assignment_id == assignment.id,
            AssignmentOccurrence.due_at == period.due_at,
        )
    )


def _ensure(
    db: Session, assignment: Assignment, period: Period
) -> tuple[AssignmentOccurrence, bool]:
    """Az időszak alkalma, ha kell, létrehozva; a második érték: most jött-e létre.

    Az előzetes keresés csak a gyakori esetet (már van alkalom) gyorsítja; a
    beszúrás INSERT … ON CONFLICT DO NOTHING. A háttérfolyamat és a beteg
    mentése ugyanis egyszerre is létrehozhatná ugyanazt az alkalmat, és sima
    beszúrásnál a második ütközési hibával a teljes mentést (a mérést is)
    elveszítené. Így az egyedi kulcs csendben kiszűri a duplát, és utána
    mindkét fél ugyanazt a sort olvassa vissza.
    """
    existing = _find(db, assignment, period)
    if existing is not None:
        return existing, False
    created = _insert(db, assignment, period, _pinned_version_id(db, assignment))
    occurrence = _find(db, assignment, period)
    assert occurrence is not None
    return occurrence, created


def occurrence_for(db: Session, assignment: Assignment, period: Period) -> AssignmentOccurrence:
    """Az időszak alkalma; ha még nincs, itt nyílik meg (idempotens, lásd _ensure)."""
    return _ensure(db, assignment, period)[0]


def _pinned_version_id(db: Session, assignment: Assignment) -> uuid.UUID | None:
    """Kérdőívnél az alkalomhoz rögzítendő verzió: a létrehozáskor aktuális;
    egy későbbi sablonmódosítás nem írja át."""
    if assignment.target_kind is not AssignmentTarget.QUESTIONNAIRE:
        return None
    return current_version(db, assignment.questionnaire_template_id).id


def _insert(
    db: Session, assignment: Assignment, period: Period, version_id: uuid.UUID | None
) -> bool:
    """Az alkalom beszúrása, ütközésnél csendben kihagyva (lásd _ensure).
    Igaz, ha most jött létre."""
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


def _fulfil(occurrence: AssignmentOccurrence, at: datetime) -> bool:
    """Teljesítés a rögzítés idejével. Csak esedékes alkalmat ír át: a már
    teljesítettnél az első adat számít, az elmulasztottat pedig nem fordítja
    vissza csendben egy később beérkező adat."""
    if occurrence.status is not OccurrenceStatus.DUE:
        return False
    late = at > occurrence.due_at
    occurrence.status = OccurrenceStatus.FULFILLED_LATE if late else OccurrenceStatus.FULFILLED
    occurrence.fulfilled_at = at
    return True


def open_due_occurrences(db: Session, now: datetime) -> int:
    """Megnyitja az előírások minden még hiányzó alkalmát a kezdőnaptól az
    aktuális időszakig (a hallgató döntése, 2026-10-30): ha a háttérfolyamat
    egy ideig nem futott (pl. a demóadat múltbeli időszakai), a kimaradt
    időszakok is megkapják az alkalmukat, és a lezárás elmulasztottra zárja
    őket. Az előírás vége (end_date) után kezdődő időszakra nem nyit, jövőbeli
    alkalmat sem hoz létre; ismételt futás nem nyit újat. Visszaadja az
    újonnan megnyitott alkalmak számát."""
    today = now.astimezone(settings.tz).date()
    assignments = list(
        db.scalars(
            select(Assignment)
            .outerjoin(Assignment.template)
            .where(
                # A visszavont előírást egészen kihagyjuk: a visszavonás a nyitott
                # alkalmát is törli (plans.py; A hallgató döntése (2026-11-01)), így a
                # visszavonás előtti, még meg nem nyitott időszakai sem kapnak
                # utólag alkalmat.
                Assignment.revoked_at.is_(None),
                Assignment.start_date <= today,
                # A lejárt előírás is kell: a vége előtti, kimaradt időszakai miatt.
                # Inaktív kérdőívre a teendőlista sem ad feladatot.
                or_(
                    Assignment.target_kind == AssignmentTarget.MEASUREMENT,
                    QuestionnaireTemplate.is_active.is_(True),
                ),
            )
            .order_by(Assignment.id)
        )
    )
    # A meglévő alkalmak egy lekérdezéssel, nem időszakonként külön: a
    # visszamenőleges nyitásnál egy előírásnak sok múltbeli időszaka lehet.
    existing = {
        (assignment_id, due_at)
        for assignment_id, due_at in db.execute(
            select(AssignmentOccurrence.assignment_id, AssignmentOccurrence.due_at).where(
                AssignmentOccurrence.assignment_id.in_([a.id for a in assignments])
            )
        )
    }
    opened = 0
    for assignment in assignments:
        last_day = min(today, assignment.end_date) if assignment.end_date else today
        missing = [
            period
            for period in periods_until(assignment, last_day)
            if (assignment.id, period.due_at) not in existing
        ]
        if not missing:
            continue
        version_id = _pinned_version_id(db, assignment)
        opened += sum(_insert(db, assignment, period, version_id) for period in missing)
    return opened


def close_missed_occurrences(db: Session, now: datetime) -> int:
    """A lejárt, nem teljesített alkalmak elmulasztottra zárása, majd az érintett
    célpontok elmaradt adat szabályainak kiértékelése (rules.evaluate_missed;
    M3, A4). Idempotens: csak esedékes alkalmat zár, és ha semmit nem zárt le,
    nem is értékel. Visszaadja a most lezártak számát."""
    # A határidő mindig az időszak vége előtt van, így az időszak vége nem
    # tárolt oszlop nélkül is jó előszűrés; a pontos határ (missed_from) után.
    candidates = db.scalars(
        select(AssignmentOccurrence)
        .where(
            AssignmentOccurrence.status == OccurrenceStatus.DUE,
            AssignmentOccurrence.due_at <= now,
        )
        .options(joinedload(AssignmentOccurrence.assignment))
    )
    expired = [o for o in candidates if now >= missed_from(o)]
    if not expired:
        return 0
    # Feltételes zárás (review k1): a kijelölés és a zárás között egy egyidejű
    # mentés teljesítheti az alkalmat. Feltétel nélküli UPDATE-nél ez a
    # fulfilled_at CHECK-en integritáshibát adna, és a teljes futás (a most
    # nyitott alkalmakkal együtt) visszagörgetődne; így a közben teljesített
    # sor egyszerűen kimarad. PostgreSQL-ben a zárolásra váró UPDATE a feltételt
    # a másik tranzakció commitja után újraértékeli.
    closed = set(
        db.scalars(
            update(AssignmentOccurrence)
            .where(
                AssignmentOccurrence.id.in_([o.id for o in expired]),
                AssignmentOccurrence.status == OccurrenceStatus.DUE,
            )
            .values(status=OccurrenceStatus.MISSED)
            .returning(AssignmentOccurrence.id)
            .execution_options(synchronize_session=False)
        )
    )
    # Csak a ténylegesen most lezártak célpontjai (a közben teljesítettek nem).
    targets = {
        MissedTarget(
            patient_id=o.assignment.patient_id,
            measurement_type_id=o.assignment.measurement_type_id,
            questionnaire_template_id=o.assignment.questionnaire_template_id,
        )
        for o in expired
        if o.id in closed
    }
    # A betöltött példányok státusza elavult; a következő hozzáférés újraolvassa.
    for occurrence in expired:
        db.expire(occurrence)
    if targets:
        evaluate_missed(db, targets, now=now)
    return len(closed)


def run_occurrence_check(db: Session, now: datetime | None = None) -> OccurrenceCheck:
    """A háttérfolyamat egy futása (és az „ellenőrzés most"): alkalom-nyitás,
    majd az elmulasztottak lezárása, egy tranzakcióban."""
    now = now or datetime.now(UTC)
    opened = open_due_occurrences(db, now)
    return OccurrenceCheck(opened=opened, missed=close_missed_occurrences(db, now))


def fulfil_with_measurement(db: Session, measurement: Measurement) -> list[AssignmentOccurrence]:
    """A mérés hozzárendelése az előírásai alkalmához: a mérés idejének (helyi)
    napja szerinti időszakhoz. Ha az alkalom még nincs meg (a háttérfolyamat
    még nem járt ott), létrehozza. Visszaadja a most teljesített alkalmakat.

    Csak a mérés napján érvényes előírások számítanak (valid_on): a lejáró
    előírás utolsó időszaka a vég napjával zárul (period_containing), így a vég
    utáni mérés már nem tartozhat hozzá, és a vég után kezdődő időszak sem
    nyílik meg."""
    day = measurement.measured_at.astimezone(settings.tz).date()
    assignments = db.scalars(
        select(Assignment)
        .where(
            Assignment.patient_id == measurement.patient_id,
            Assignment.measurement_type_id == measurement.type_id,
            *valid_on(day),
        )
        .order_by(Assignment.start_date, Assignment.id)
    )
    fulfilled = []
    for assignment in assignments:
        occurrence, _ = _ensure(db, assignment, period_containing(assignment, day))
        if _fulfil(occurrence, measurement.recorded_at):
            occurrence.measurement_id = measurement.id
            fulfilled.append(occurrence)
    db.flush()
    return fulfilled


def fulfil_from_existing(
    db: Session, assignment: Assignment, now: datetime
) -> AssignmentOccurrence | None:
    """Új előírásnál (létrehozás, módosítás) az aktuális időszak alkalma, a
    már meglévő adattal teljesítve. Az M1 szerint a mérés a measured_at, a
    kitöltés a beküldés ideje szerint tartozik az időszakába, akkor is, ha az
    előírás később született (pl. a beteg reggel mért, az orvos délben írta
    elő): így nincs hamis „esedékes". A szabályok a mentéskoriak: az első adat
    számít (a rögzítés sorrendjében), a késést a rögzítés ideje és a határidő
    dönti el. A még el nem kezdett előírásra nem nyit alkalmat."""
    today = now.astimezone(settings.tz).date()
    if assignment.start_date > today:
        return None
    period = period_containing(assignment, today)
    occurrence, _ = _ensure(db, assignment, period)
    if assignment.target_kind is AssignmentTarget.MEASUREMENT:
        measurement = db.scalar(
            select(Measurement)
            .where(
                Measurement.patient_id == assignment.patient_id,
                Measurement.type_id == assignment.measurement_type_id,
                Measurement.measured_at >= period.start,
                Measurement.measured_at < period.end,
            )
            .order_by(Measurement.recorded_at, Measurement.id)
            .limit(1)
        )
        if measurement is not None and _fulfil(occurrence, measurement.recorded_at):
            occurrence.measurement_id = measurement.id
    else:
        submission = db.scalar(
            select(Submission)
            .join(QuestionnaireVersion)
            .where(
                Submission.patient_id == assignment.patient_id,
                QuestionnaireVersion.template_id == assignment.questionnaire_template_id,
                Submission.submitted_at >= period.start,
                Submission.submitted_at < period.end,
            )
            .order_by(Submission.submitted_at, Submission.id)
            .limit(1)
        )
        # A kitöltés hivatkozását nem írjuk át: módosításnál a régi előírás
        # (megmaradó) alkalmára mutat, az a története.
        if submission is not None and _fulfil(occurrence, submission.submitted_at):
            submission.occurrence_id = submission.occurrence_id or occurrence.id
    db.flush()
    return occurrence


def _questionnaire_assignments(
    db: Session, patient_id: uuid.UUID, template_id: uuid.UUID, day: date
) -> list[Assignment]:
    """A beteg adott napon érvényes előírásai a kérdőívre, a legrégebbi elöl.
    A kitöltési verzió és a hozzárendelés ugyanebből a sorrendből választ,
    így mindkettő ugyanarra az alkalomra jut."""
    return list(
        db.scalars(
            select(Assignment)
            .where(
                Assignment.patient_id == patient_id,
                Assignment.questionnaire_template_id == template_id,
                *valid_on(day),
            )
            .order_by(Assignment.start_date, Assignment.id)
        )
    )


def fill_version(
    db: Session, patient_id: uuid.UUID, template_id: uuid.UUID, day: date
) -> QuestionnaireVersion:
    """A kitöltendő kérdőívverzió: az aktuális időszak alkalmához rögzített (M1,
    03_adatmodell.md: a kitöltés az alkalom verziójára hivatkozik). Ha az alkalom
    még nincs meg, itt jön létre, az ilyenkor aktuális verzióval; így a kitöltés
    kérdései és a beküldés pontozása akkor is egyezik, ha a sablon közben új
    verziót kap. Érvényes előírás nélkül az aktuális verzió."""
    assignments = _questionnaire_assignments(db, patient_id, template_id, day)
    if not assignments:
        return current_version(db, template_id)
    occurrence, _ = _ensure(db, assignments[0], period_containing(assignments[0], day))
    # Kérdőív-előírás alkalmánál a verzió mindig ki van töltve (_pinned_version_id).
    version = db.get(QuestionnaireVersion, occurrence.questionnaire_version_id)
    assert version is not None
    return version


def fulfil_with_submission(db: Session, submission: Submission) -> AssignmentOccurrence | None:
    """A kitöltés hozzárendelése az aktuális időszak alkalmához (kérdőívnél nincs
    visszadátumozás, így a legrégebbi még teljesíthető alkalom az aktuális).
    A kitöltés occurrence_id-t kap akkor is, ha az alkalmat egy korábbi
    kitöltés már teljesítette: az időszakhoz tartozik, de nem ez teljesítette."""
    day = submission.submitted_at.astimezone(settings.tz).date()
    assignments = _questionnaire_assignments(
        db, submission.patient_id, submission.version.template_id, day
    )
    first = None
    for assignment in assignments:
        occurrence, _ = _ensure(db, assignment, period_containing(assignment, day))
        _fulfil(occurrence, submission.submitted_at)
        # Ugyanarra a kérdőívre két érvényes előírás ritka; a kitöltés a
        # legrégebbi alkalmára hivatkozik, de mindkettőt teljesíti.
        first = first or occurrence
    if first is not None:
        submission.occurrence_id = first.id
    db.flush()
    return first
