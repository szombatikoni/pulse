"""A beteg státusza (F9; 07_mukodesi_szabalyok.md, 1. rész).

Számított érték, nem tárolt mező. Több feltétel egyidejű fennállásakor a
sorrendben előbb álló érvényes, a felület a többi okot is kiírja:
Súlyos > Figyelem > Adathiány > Kezelve > Rendben.

Az M2-ben még nincs előírás (alkalom) és riasztáslezárás, ezért:
- az Adathiány oka csak az lehet, hogy nincs friss adat — se mérés, se
  kérdőív-kitöltés (előírás nélkül a frissességi határ rendszerszintű
  beállítás, alapértelmezés szerint 7 nap);
- Kezelve státusz még nem fordul elő.
Adat nélkül sosem Rendben a státusz: az adathiány nem ad kedvező jelzést.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Alert, Measurement, PatientProfile, Severity, Submission
from app.services.access import assigned_patients_query
from app.services.alerts import list_patient_alerts


class PatientStatus(StrEnum):
    SEVERE = "severe"  # Súlyos: súlyos nyitott riasztás
    ATTENTION = "attention"  # Figyelem: közepes nyitott riasztás
    NO_DATA = "no_data"  # Adathiány: nincs friss adat
    HANDLED = "handled"  # Kezelve: lezárva, megerősítő adatra vár (M3)
    OK = "ok"  # Rendben: friss adat, a fentiek egyike sem


PRIORITY = list(PatientStatus)


@dataclass
class StatusReason:
    status: PatientStatus
    # "open_alert" | "no_data_yet" | "stale_data" | "fresh_data"
    code: str
    alert: Alert | None = None
    at: datetime | None = None


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

    last = last_data_at(db, patient_id)
    if last is None:
        reasons.append(StatusReason(PatientStatus.NO_DATA, "no_data_yet"))
    elif last < now - timedelta(days=settings.data_freshness_days):
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
