"""A beteg teendői: az előírások aktuális és előző időszaka (F6, F14).

Számított előnézet: az alkalmakat nem tárolja, hanem minden lekérdezéskor az
előírásból és a beérkezett adatokból számolja ki. A szabályok az M1
adatmodelljéből jönnek (docs/M1/03_adatmodell.md, „Előírás és alkalom"):

- az időszak napi előírásnál a helyi naptári nap; heti vagy N napos előírásnál a
  kezdőnaptól (start_date) számított teljes időköz (7, illetve interval_days nap);
- a határidő (due_at) az időszak utolsó napján, a due_time időpontban van;
- a mérés a mérés ideje (measured_at), a kitöltés a beküldés ideje szerint
  kerül az időszakába;
- az elmaradt mérés az időszak vége után két napig pótolható (MAX_BACKDATE);
  kérdőívnél nincs pótlás (a hallgató döntése, 2026-10-15).

Az M3-ban az alkalmak (AssignmentOccurrence) ugyanezzel a szabállyal
tárolódnak, és azokra épül a késés rögzítése és az elmaradt adat jelzése.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    Assignment,
    AssignmentTarget,
    Frequency,
    Measurement,
    MeasurementType,
    QuestionnaireTemplate,
    QuestionnaireVersion,
    Submission,
)
from app.services.measurements import MAX_BACKDATE

# A „Pótlás" javasolt időpontja ennyivel a legkorábbi rögzíthető idő után van,
# hogy a mentésig eltelt idő miatt se essen ki a két napos ablakból.
CATCH_UP_MARGIN = timedelta(minutes=5)


class TaskState(StrEnum):
    DONE = "done"  # az aktuális időszakban már érkezett adat
    DUE = "due"  # még nem érkezett, a határidő még nem járt le
    LATE = "late"  # a határidő lejárt, de az időszak még tart (késve teljesíthető)


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
    """Mérés előírása a betegnek (F14). Az alkalmak tárolása az M3-ban jön."""
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


def _period_days(assignment: Assignment) -> int:
    if assignment.frequency is Frequency.DAILY:
        return 1
    if assignment.frequency is Frequency.WEEKLY:
        return 7
    return assignment.interval_days or 1


def _local_midnight(day: date) -> datetime:
    return datetime.combine(day, time(0), tzinfo=settings.tz)


def _last_data_at(
    db: Session, assignment: Assignment, start: datetime, end: datetime
) -> datetime | None:
    """A legutóbbi adat ideje az előírás [start, end) időszakában."""
    if assignment.target_kind is AssignmentTarget.MEASUREMENT:
        return db.scalar(
            select(func.max(Measurement.measured_at)).where(
                Measurement.patient_id == assignment.patient_id,
                Measurement.type_id == assignment.measurement_type_id,
                Measurement.measured_at >= start,
                Measurement.measured_at < end,
            )
        )
    return db.scalar(
        select(func.max(Submission.submitted_at))
        .join(QuestionnaireVersion)
        .where(
            Submission.patient_id == assignment.patient_id,
            QuestionnaireVersion.template_id == assignment.questionnaire_template_id,
            Submission.submitted_at >= start,
            Submission.submitted_at < end,
        )
    )


def _active_assignments(db: Session, patient_id: uuid.UUID, today: date) -> list[Assignment]:
    """Az éppen érvényes előírások (ugyanaz a szűrés, mint a kirendelt kérdőíveknél)."""
    return list(
        db.scalars(
            select(Assignment)
            .where(
                Assignment.patient_id == patient_id,
                Assignment.revoked_at.is_(None),
                Assignment.start_date <= today,
                or_(Assignment.end_date.is_(None), Assignment.end_date >= today),
            )
            .order_by(Assignment.start_date, Assignment.id)
        )
    )


def _task(db: Session, assignment: Assignment, now: datetime) -> PatientTask | None:
    today = now.astimezone(settings.tz).date()
    days = _period_days(assignment)
    k = (today - assignment.start_date).days // days
    first_day = assignment.start_date + timedelta(days=k * days)
    start = _local_midnight(first_day)
    end = _local_midnight(first_day + timedelta(days=days))
    due_at = datetime.combine(
        first_day + timedelta(days=days - 1), assignment.due_time, tzinfo=settings.tz
    )

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

    done_at = _last_data_at(db, assignment, start, end)
    if done_at is not None:
        state = TaskState.DONE
    else:
        state = TaskState.LATE if now > due_at else TaskState.DUE

    # Az előző időszak: csak ha az előírás már akkor is érvényes volt.
    previous_missed = False
    catch_up_until = catch_up_suggested_at = None
    if k > 0:
        prev_first_day = first_day - timedelta(days=days)
        prev_start = _local_midnight(prev_first_day)
        if _last_data_at(db, assignment, prev_start, start) is None:
            previous_missed = True
            if (
                assignment.target_kind is AssignmentTarget.MEASUREMENT
                and now < start + MAX_BACKDATE
            ):
                prev_due = datetime.combine(
                    first_day - timedelta(days=1), assignment.due_time, tzinfo=settings.tz
                )
                suggested = max(prev_due, now - MAX_BACKDATE + CATCH_UP_MARGIN)
                if suggested < start:
                    catch_up_until = start + MAX_BACKDATE
                    catch_up_suggested_at = suggested

    return PatientTask(
        assignment=assignment,
        code=code,
        name=name,
        period_start=start,
        period_end=end,
        due_at=due_at,
        state=state,
        done_at=done_at,
        previous_missed=previous_missed,
        catch_up_until=catch_up_until,
        catch_up_suggested_at=catch_up_suggested_at,
    )


def patient_tasks(
    db: Session, patient_id: uuid.UUID, now: datetime | None = None
) -> list[PatientTask]:
    """A beteg teendői az érvényes előírásai szerint. Sorrend: előbb ami még
    hiányzik (lejárt, esedékes), aztán a pótolható, végül a kész."""
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
    return tasks
