"""A beteg teendői: az előírások aktuális és előző időszaka (F6, F14; M3, A3).

A teendőlista a tárolt alkalmakból (AssignmentOccurrence, occurrences.py)
dolgozik, nem számol külön: ami az alkalomnál teljesített, az kész; ami
esedékes, az a határidőig esedékes, utána lejárt. Az aktuális és az előző
időszak alkalmát a lekérés megnyitja, ha még nincs (ugyanaz az idempotens út,
mint a mentésnél), így a háttérfolyamat ütemétől nem függ. A szabályok az M1
adatmodelljéből jönnek (docs/M1/03_adatmodell.md, „Előírás és alkalom"):

- az időszak és a határidő az occurrences.py szerint;
- az elmaradt mérés az időszak vége után 48 óráig pótolható (MAX_BACKDATE,
  ugyanaz a határ, mint a háttérfolyamat zárásánál: occurrences.catch_up_deadline);
  kérdőívnél nincs pótlás (a hallgató döntése, 2026-10-15);
- letiltott betegnek nincs teendője (a lekérés alkalmat sem nyit nála), és
  visszaengedélyezés után a letiltott időszakba eső határidejű időszak nem
  jelenik meg teendőként, késésben vagy pótolhatóként sem (M3, A1;
  services/disabled.py).
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    Assignment,
    AssignmentOccurrence,
    AssignmentTarget,
    Frequency,
    Measurement,
    MeasurementType,
    OccurrenceStatus,
    QuestionnaireTemplate,
)
from app.services.disabled import (
    DisabledPeriod,
    disabled_periods_by_patient,
    inactive_patients,
    is_excused,
)
from app.services.measurements import MAX_BACKDATE
from app.services.occurrences import (
    Period,
    catch_up_deadline,
    occurrence_for,
    period_containing,
    period_end,
    valid_on,
)

# A „Pótlás" javasolt időpontja ennyivel a legkorábbi rögzíthető idő után van,
# hogy a mentésig eltelt idő miatt se essen ki a két napos ablakból.
CATCH_UP_MARGIN = timedelta(minutes=5)


class TaskState(StrEnum):
    DONE = "done"  # az aktuális alkalom teljesítve (időben vagy késve)
    DUE = "due"  # esedékes, a határidő még nem járt le
    LATE = "late"  # esedékes, a határidő lejárt, de az időszak még tart (késve teljesíthető)


@dataclass
class PatientTask:
    assignment: Assignment
    code: str  # a méréstípus vagy a kérdőív kódja
    name: str
    period_start: datetime
    period_end: datetime
    due_at: datetime
    state: TaskState
    done_at: datetime | None
    previous_missed: bool
    # Csak mérésnél, és csak amíg az előző időszak még pótolható.
    catch_up_until: datetime | None
    catch_up_suggested_at: datetime | None


def assign_measurement(
    db: Session,
    *,
    patient_id: uuid.UUID,
    measurement_type: MeasurementType,
    assigned_by: uuid.UUID,
    start_date: date,
    frequency: Frequency = Frequency.DAILY,
    due_time: time = time(10, 0),
    suggested_time: time | None = None,
    interval_days: int | None = None,
) -> Assignment:
    """Mérés előírása a betegnek (F14), ellenőrzések nélkül: a demóadathoz és a
    tesztekhez. Az orvosi felület útja a plans.create()."""
    assignment = Assignment(
        patient_id=patient_id,
        assigned_by=assigned_by,
        target_kind=AssignmentTarget.MEASUREMENT,
        measurement_type_id=measurement_type.id,
        frequency=frequency,
        interval_days=interval_days,
        due_time=due_time,
        suggested_time=suggested_time,
        start_date=start_date,
    )
    db.add(assignment)
    db.flush()
    return assignment


def _active_assignments(
    db: Session, patient_ids: list[uuid.UUID], today: date
) -> dict[uuid.UUID, list[Assignment]]:
    """Az éppen érvényes előírások betegenként (ugyanaz a szűrés, mint a
    kirendelt kérdőíveknél), egy lekérdezéssel."""
    result: dict[uuid.UUID, list[Assignment]] = {}
    if not patient_ids:
        return result
    for assignment in db.scalars(
        select(Assignment)
        .where(Assignment.patient_id.in_(patient_ids), *valid_on(today))
        .order_by(Assignment.start_date, Assignment.id)
    ):
        result.setdefault(assignment.patient_id, []).append(assignment)
    return result


# Az előre betöltött alkalmak (előírás, határidő UTC-ben) szerint; lásd _Prefetch.
Known = dict[tuple[uuid.UUID, datetime], AssignmentOccurrence]


def _key(assignment_id: uuid.UUID, due_at: datetime) -> tuple[uuid.UUID, datetime]:
    """A known kulcsa. A határidő UTC-re váltva: az adatbázis UTC-ben adja, az
    időszaké helyi idő, és az óraátállítás napján (kétszer meglévő vagy
    kimaradó helyi idő) a két alak Pythonban nem egyenlő (PEP 495), így a
    keresés tévesen nem találná a meglévő alkalmat."""
    return assignment_id, due_at.astimezone(UTC)


@dataclass
class _Prefetch:
    """A teendők számolásához előre, egyszerre betöltött sorok (a beteglistán
    minden betegre egy-egy lekérdezéssel). A known az aktuális és az előző
    időszak már meglévő alkalmai; amelyik nincs benne, az még nem létezik, és
    az occurrence_for nyitja meg. A többi lista csak azért van itt, hogy a
    betöltött objektumok a számolás végéig a sessionben maradjanak (így a
    db.get nem kérdez újra)."""

    known: Known
    keep: list[object]


def _periods(assignment: Assignment, today: date) -> list[Period]:
    """Az előírás aktuális és (ha van) előző időszaka: a teendő csak ezeket nézi."""
    period = period_containing(assignment, today)
    if period.first_day <= assignment.start_date:
        return [period]
    return [period, period_containing(assignment, period.first_day - timedelta(days=1))]


def _prefetch(db: Session, assignments: list[Assignment], today: date) -> _Prefetch:
    keys = [(a.id, p.due_at) for a in assignments for p in _periods(a, today)]
    key = tuple_(AssignmentOccurrence.assignment_id, AssignmentOccurrence.due_at)
    known: Known = {}
    if keys:
        for occurrence in db.scalars(select(AssignmentOccurrence).where(key.in_(keys))):
            known[_key(occurrence.assignment_id, occurrence.due_at)] = occurrence
    keep: list[object] = []
    type_ids = {a.measurement_type_id for a in assignments} - {None}
    if type_ids:
        keep += db.scalars(select(MeasurementType).where(MeasurementType.id.in_(type_ids)))
    template_ids = {a.questionnaire_template_id for a in assignments} - {None}
    if template_ids:
        keep += db.scalars(
            select(QuestionnaireTemplate).where(QuestionnaireTemplate.id.in_(template_ids))
        )
    measurement_ids = {
        o.measurement_id for o in known.values() if o.status in _DONE and o.measurement_id
    }
    if measurement_ids:
        keep += db.scalars(select(Measurement).where(Measurement.id.in_(measurement_ids)))
    return _Prefetch(known, keep)


def _existing(
    db: Session, known: Known | None, assignment: Assignment, period: Period
) -> AssignmentOccurrence | None:
    """Az időszak már meglévő alkalma (nem nyit újat)."""
    if known is not None:
        return known.get(_key(assignment.id, period.due_at))
    return db.scalar(
        select(AssignmentOccurrence).where(
            AssignmentOccurrence.assignment_id == assignment.id,
            AssignmentOccurrence.due_at == period.due_at,
        )
    )


def _occurrence(
    db: Session, known: Known | None, assignment: Assignment, period: Period
) -> AssignmentOccurrence:
    """Az időszak alkalma: az előre betöltött, vagy ha még nincs, az
    occurrence_for nyitja meg (ugyanaz az idempotens út)."""
    hit = known.get(_key(assignment.id, period.due_at)) if known is not None else None
    return hit if hit is not None else occurrence_for(db, assignment, period)


_DONE = {OccurrenceStatus.FULFILLED, OccurrenceStatus.FULFILLED_LATE}


def _done_at(db: Session, occurrence: AssignmentOccurrence) -> datetime | None:
    """Mikor készült a teljesítő adat: mérésnél a mérés ideje (measured_at), mert
    a beteg ezt adta meg; kitöltésnél a beküldés ideje (= fulfilled_at).

    Az alkalom az eredeti mérésre mutat akkor is, ha azt később javították (A7):
    szűrés itt nem kell, mert a javítás a mérési időt nem változtatja (D1)."""
    if occurrence.status not in _DONE:
        return None
    if occurrence.measurement_id is not None:
        measurement = db.get(Measurement, occurrence.measurement_id)
        if measurement is not None:
            return measurement.measured_at
    return occurrence.fulfilled_at


def _catch_up_only(
    db: Session,
    assignment: Assignment,
    code: str,
    name: str,
    period: Period,
    now: datetime,
    excused: list[DisabledPeriod],
    known: Known | None = None,
) -> PatientTask | None:
    """Visszaengedélyezés napja, ha a mai határidő a letiltás alatt telt le és a
    mai alkalom nem teljesült (A1): a mai alkalom nem teendő. Ha viszont az előző
    időszak határideje a letiltás előtt volt (számít), még nem teljesült és még
    pótolható, akkor az előző időszak a pótlás ajánlatával; így a letiltás előtti
    pótlás lehetősége nem vész el. Ezt a teendőt a pótlási ajánlat és a hiányzó
    „előző elmaradt" jelzés (previous_missed=False) különbözteti meg; a beteg
    felülete ilyenkor csak a pótlást mutatja (TaskList.tsx), állapotsor és a mai
    időszakra mentő fő gomb nélkül. Egyébként nincs teendő (a következő időszak a
    kezdetétől látszik)."""
    if assignment.target_kind is not AssignmentTarget.MEASUREMENT:
        return None
    if period.first_day <= assignment.start_date:
        return None
    previous_period = period_containing(assignment, period.first_day - timedelta(days=1))
    if is_excused(excused, previous_period.due_at):
        return None
    deadline = catch_up_deadline(previous_period.end)
    suggested = max(previous_period.due_at, now - MAX_BACKDATE + CATCH_UP_MARGIN)
    if now >= deadline or suggested >= previous_period.end:
        return None
    previous = _occurrence(db, known, assignment, previous_period)
    if previous.status is not OccurrenceStatus.DUE:
        return None
    return PatientTask(
        assignment=assignment,
        code=code,
        name=name,
        period_start=previous.period_start,
        period_end=previous_period.end,
        due_at=previous.due_at,
        state=TaskState.LATE,
        done_at=None,
        previous_missed=False,
        catch_up_until=deadline,
        catch_up_suggested_at=suggested,
    )


def _task(
    db: Session,
    assignment: Assignment,
    now: datetime,
    excused: list[DisabledPeriod],
    known: Known | None = None,
) -> PatientTask | None:
    if assignment.target_kind is AssignmentTarget.MEASUREMENT:
        mtype = db.get(MeasurementType, assignment.measurement_type_id)
        if mtype is None:
            return None
        code, name = mtype.code, mtype.name
    else:
        template = db.get(QuestionnaireTemplate, assignment.questionnaire_template_id)
        if template is None or not template.is_active:
            return None
        code, name = template.code, template.name

    period = period_containing(assignment, now.astimezone(settings.tz).date())
    if is_excused(excused, period.due_at):
        # A határidő a letiltás alatt telt le (A1): ez az alkalom nem esedékes és nem
        # késésben, sort sem nyitunk rá. Ha már teljesült, kész teendőként látszik;
        # ha nem, de az előző (számító) időszak még pótolható, az látszik.
        existing = _existing(db, known, assignment, period)
        if existing is None or existing.status not in _DONE:
            return _catch_up_only(db, assignment, code, name, period, now, excused, known)
        current = existing
    else:
        current = _occurrence(db, known, assignment, period)
    if current.status in _DONE:
        state = TaskState.DONE
    else:
        state = TaskState.LATE if now > current.due_at else TaskState.DUE

    # Az előző időszak: csak ha az előírás már akkor is érvényes volt. Elmaradt,
    # ha az alkalma nem teljesült (még esedékes, vagy a háttérfolyamat már
    # elmulasztottra zárta).
    previous_missed = False
    catch_up_until = catch_up_suggested_at = None
    previous_period = (
        period_containing(assignment, period.first_day - timedelta(days=1))
        if period.first_day > assignment.start_date
        else None
    )
    # A letiltott időszakba eső határidejű előző időszak nem elmaradt (A1).
    if previous_period is not None and not is_excused(excused, previous_period.due_at):
        previous = _occurrence(db, known, assignment, previous_period)
        if previous.status not in _DONE:
            previous_missed = True
            # Az előző időszak vége az aktuális kezdete; a pótlás határa ugyanabból
            # a képletből jön, mint a worker zárásáé (abszolút 48 óra).
            deadline = catch_up_deadline(period.start)
            if assignment.target_kind is AssignmentTarget.MEASUREMENT and now < deadline:
                suggested = max(previous.due_at, now - MAX_BACKDATE + CATCH_UP_MARGIN)
                if suggested < period.start:
                    catch_up_until = deadline
                    catch_up_suggested_at = suggested

    return PatientTask(
        assignment=assignment,
        code=code,
        name=name,
        period_start=current.period_start,
        period_end=period_end(current),
        due_at=current.due_at,
        state=state,
        done_at=_done_at(db, current),
        previous_missed=previous_missed,
        catch_up_until=catch_up_until,
        catch_up_suggested_at=catch_up_suggested_at,
    )


def patient_tasks(
    db: Session, patient_id: uuid.UUID, now: datetime | None = None
) -> list[PatientTask]:
    """A beteg teendői az érvényes előírásai szerint. Sorrend: előbb ami még
    hiányzik (lejárt, esedékes), aztán a pótolható, végül a kész. A hiányzó
    alkalmakat megnyitja; a véglegesítést (commit) a hívó végzi."""
    return tasks_by_patient(db, [patient_id], now)[patient_id]


def tasks_by_patient(
    db: Session, patient_ids: list[uuid.UUID], now: datetime | None = None
) -> dict[uuid.UUID, list[PatientTask]]:
    """A patient_tasks több betegre (a beteglistához): az előírások, a letiltott
    időszakok és a meglévő alkalmak fajtánként egy lekérdezéssel jönnek, a
    számolás betegenként ugyanaz. Lekérdezés csak a még hiányzó alkalom
    megnyitásakor fut külön (occurrence_for)."""
    now = now or datetime.now(UTC)
    inactive = inactive_patients(db, patient_ids)  # letiltott: nincs teendő, alkalmat sem nyit (A1)
    active = [p for p in patient_ids if p not in inactive]
    today = now.astimezone(settings.tz).date()
    excused = disabled_periods_by_patient(db, active)
    assignments = _active_assignments(db, active, today)
    prefetch = _prefetch(db, [a for rows in assignments.values() for a in rows], today)

    def rank(task: PatientTask) -> int:
        if task.state is TaskState.LATE:
            return 0
        if task.state is TaskState.DUE:
            return 1
        return 2 if task.catch_up_until else 3

    result: dict[uuid.UUID, list[PatientTask]] = {}
    for patient_id in patient_ids:
        periods = excused.get(patient_id, [])
        tasks = [
            t
            for a in assignments.get(patient_id, [])
            if (t := _task(db, a, now, periods, prefetch.known))
        ]
        tasks.sort(key=lambda t: (rank(t), t.due_at))
        result[patient_id] = tasks
    db.flush()
    return result
