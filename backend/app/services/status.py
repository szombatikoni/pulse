"""A beteg státusza (F9; 07_mukodesi_szabalyok.md, 1. rész).

Számított érték, nem tárolt mező. Több feltétel egyidejű fennállásakor a
sorrendben előbb álló érvényes, a felület a többi okot is kiírja:
Súlyos > Figyelem > Adathiány > Kezelve > Rendben.

Az Adathiány okai (M3, A4 2. lépés, a hallgató döntése):
- elmulasztott alkalom: a beteg valamelyik érvényes előírásának legutóbbi
  lezárt (nem esedékes) alkalma elmulasztott ("missed_occurrence"). A késve
  teljesített (pótolt) alkalom nem az. A visszavont, lejárt és még el nem
  kezdett előírás nem számít: az előírás-módosítás (visszavonás + új előírás)
  után a régi elmulasztása nem ragad a betegen;
- még nem érkezett adat: se mérés, se kitöltés ("no_data_yet");
- nincs friss adat ("stale_data"): csak ha a betegnek nincs lezárt alkalma
  érvényes előíráson (nincs előírása, vagy az első határidő még nem járt le).
  Ilyenkor a legutóbbi mérés vagy kitöltés legfeljebb 7 napos lehet
  (rendszerszintű beállítás, data_freshness_days). Ahol már van lezárt
  alkalom, a frissességet az alkalmak teljesítése adja: a havi előírását
  rendben teljesítő beteg 20 napos méréssel is Rendben.

Csak a tárolt alkalom-státuszokat olvassa, lezárást nem futtat: az a
háttérfolyamaté (legfeljebb a futási időköznyi késéssel; a hallgató döntése).
Kezelve státusz még nem fordul elő (a riasztáslezárás az A6-ban jön).
Adat nélkül sosem Rendben a státusz: az adathiány nem ad kedvező jelzést.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    Alert,
    Assignment,
    AssignmentOccurrence,
    AssignmentTarget,
    Measurement,
    OccurrenceStatus,
    PatientProfile,
    QuestionnaireTemplate,
    Severity,
    Submission,
)
from app.services.access import assigned_patients_query
from app.services.alerts import list_patient_alerts
from app.services.occurrences import valid_on


class PatientStatus(StrEnum):
    SEVERE = "severe"  # Súlyos: súlyos nyitott riasztás
    ATTENTION = "attention"  # Figyelem: közepes nyitott riasztás
    NO_DATA = "no_data"  # Adathiány: elmulasztott alkalom, vagy nincs friss adat
    HANDLED = "handled"  # Kezelve: lezárva, megerősítő adatra vár (M3)
    OK = "ok"  # Rendben: friss adat, a fentiek egyike sem


PRIORITY = list(PatientStatus)


@dataclass
class StatusReason:
    status: PatientStatus
    # "open_alert" | "missed_occurrence" | "no_data_yet" | "stale_data" | "fresh_data"
    code: str
    alert: Alert | None = None
    at: datetime | None = None
    # Elmulasztott alkalomnál az alkalom (a felület „Ok" oszlopához).
    occurrence: AssignmentOccurrence | None = None

    @property
    def occurrence_id(self) -> uuid.UUID | None:
        return self.occurrence.id if self.occurrence else None


@dataclass
class PatientStatusResult:
    status: PatientStatus
    reasons: list[StatusReason]
    last_data_at: datetime | None


def last_data_at(db: Session, patient_id: uuid.UUID) -> datetime | None:
    """A legutóbbi adat ideje: mérés (a mérés ideje) vagy kérdőív-kitöltés."""
    measured = db.scalar(
        select(func.max(Measurement.measured_at)).where(Measurement.patient_id == patient_id)
    )
    submitted = db.scalar(
        select(func.max(Submission.submitted_at)).where(Submission.patient_id == patient_id)
    )
    return max((t for t in (measured, submitted) if t is not None), default=None)


def latest_closed_occurrences(
    db: Session, patient_id: uuid.UUID, now: datetime
) -> list[AssignmentOccurrence]:
    """A beteg ma érvényes előírásainak legutóbbi lezárt (nem esedékes)
    alkalma, előírásonként egy, határidő szerint. Inaktív kérdőívre szóló
    előírás nem számít: arra a háttérfolyamat nem nyit alkalmat, így a beteg
    sem teljesíthetné (mint az open_due_occurrences-ben)."""
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
            AssignmentOccurrence.status != OccurrenceStatus.DUE,
        )
        # PostgreSQL DISTINCT ON: előírásonként a legkésőbbi határidejű sor.
        .ext(distinct_on(AssignmentOccurrence.assignment_id))
        .order_by(AssignmentOccurrence.assignment_id, AssignmentOccurrence.due_at.desc())
    ).all()
    return sorted(latest, key=lambda o: (o.due_at, o.id))


def compute_status(
    db: Session, patient_id: uuid.UUID, now: datetime | None = None
) -> PatientStatusResult:
    now = now or datetime.now(UTC)
    reasons: list[StatusReason] = []

    for alert in list_patient_alerts(db, patient_id, open_only=True):
        status = (
            PatientStatus.SEVERE if alert.severity is Severity.SEVERE else PatientStatus.ATTENTION
        )
        reasons.append(StatusReason(status, "open_alert", alert=alert, at=alert.created_at))

    closed = latest_closed_occurrences(db, patient_id, now)
    for occurrence in closed:
        if occurrence.status is OccurrenceStatus.MISSED:
            reasons.append(
                StatusReason(
                    PatientStatus.NO_DATA,
                    "missed_occurrence",
                    at=occurrence.due_at,
                    occurrence=occurrence,
                )
            )

    last = last_data_at(db, patient_id)
    if last is None:
        reasons.append(StatusReason(PatientStatus.NO_DATA, "no_data_yet"))
    elif not closed and last < now - timedelta(days=settings.data_freshness_days):
        # A 7 napos szabály csak lezárt alkalom nélkül él (lásd a modul leírását).
        reasons.append(StatusReason(PatientStatus.NO_DATA, "stale_data", at=last))

    if not reasons:
        reasons.append(StatusReason(PatientStatus.OK, "fresh_data", at=last))

    reasons.sort(key=lambda r: PRIORITY.index(r.status))  # stabil: a sorrend azonos szinten marad
    return PatientStatusResult(reasons[0].status, reasons, last)


def doctor_patient_list(
    db: Session, doctor_id: uuid.UUID, now: datetime | None = None
) -> list[tuple[PatientProfile, PatientStatusResult]]:
    """Az orvos éppen hozzá rendelt betegei státusszal, priorizálva (F9):
    elöl a Súlyos, a végén a Rendben; azonos státuszon belül név szerint."""
    now = now or datetime.now(UTC)
    patients = db.scalars(assigned_patients_query(doctor_id, now)).all()
    rows = [(p, compute_status(db, p.id, now)) for p in patients]
    rows.sort(key=lambda row: (PRIORITY.index(row[1].status), row[0].name))
    return rows
