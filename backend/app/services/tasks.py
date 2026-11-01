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
  kérdőívnél nincs pótlás (a hallgató döntése, 2026-10-15).
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum

from sqlalchemy import select
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
from app.services.measurements import MAX_BACKDATE
from app.services.occurrences import (
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


def _active_assignments(db: Session, patient_id: uuid.UUID, today: date) -> list[Assignment]:
    """Az éppen érvényes előírások (ugyanaz a szűrés, mint a kirendelt kérdőíveknél)."""
    return list(
        db.scalars(
            select(Assignment)
            .where(Assignment.patient_id == patient_id, *valid_on(today))
            .order_by(Assignment.start_date, Assignment.id)
        )
    )


_DONE = {OccurrenceStatus.FULFILLED, OccurrenceStatus.FULFILLED_LATE}


def _done_at(db: Session, occurrence: AssignmentOccurrence) -> datetime | None:
    """Mikor készült a teljesítő adat: mérésnél a mérés ideje (measured_at), mert
    a beteg ezt adta meg; kitöltésnél a beküldés ideje (= fulfilled_at)."""
    if occurrence.status not in _DONE:
        return None
    if occurrence.measurement_id is not None:
        measurement = db.get(Measurement, occurrence.measurement_id)
        if measurement is not None:
            return measurement.measured_at
    return occurrence.fulfilled_at


def _task(db: Session, assignment: Assignment, now: datetime) -> PatientTask | None:
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
    current = occurrence_for(db, assignment, period)
    if current.status in _DONE:
        state = TaskState.DONE
    else:
        state = TaskState.LATE if now > current.due_at else TaskState.DUE

    # Az előző időszak: csak ha az előírás már akkor is érvényes volt. Elmaradt,
    # ha az alkalma nem teljesült (még esedékes, vagy a háttérfolyamat már
    # elmulasztottra zárta).
    previous_missed = False
    catch_up_until = catch_up_suggested_at = None
    if period.first_day > assignment.start_date:
        previous = occurrence_for(
            db, assignment, period_containing(assignment, period.first_day - timedelta(days=1))
        )
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
    now = now or datetime.now(UTC)
    today = now.astimezone(settings.tz).date()
    tasks = [t for a in _active_assignments(db, patient_id, today) if (t := _task(db, a, now))]

    def rank(task: PatientTask) -> int:
        if task.state is TaskState.LATE:
            return 0
        if task.state is TaskState.DUE:
            return 1
        return 2 if task.catch_up_until else 3

    tasks.sort(key=lambda t: (rank(t), t.due_at))
    db.flush()
    return tasks
