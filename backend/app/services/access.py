"""Hozzáférés a betegadatokhoz (F2, F3).

Minden betegadatot érintő végpont ezen keresztül ellenőriz:
- beteg: csak a saját adatait látja;
- orvos: csak azokat a betegeket, akikkel ÉPPEN érvényes összerendelése van;
- admin: betegadatot nem lát, csak adminisztratív erőforrásokat (F2).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import ColumnElement, Select, and_, exists, or_, select
from sqlalchemy.orm import Session

from app.models import DoctorPatient, PatientProfile, User, UserRole


def _valid_at(at: datetime) -> ColumnElement[bool]:
    """Az összerendelés érvényes az adott pillanatban: valid_from <= at, és
    valid_to üres vagy későbbi."""
    return and_(
        DoctorPatient.valid_from <= at,
        or_(DoctorPatient.valid_to.is_(None), DoctorPatient.valid_to > at),
    )


def active_assignment_exists(
    db: Session, doctor_id: uuid.UUID, patient_id: uuid.UUID, at: datetime | None = None
) -> bool:
    """Van-e az adott pillanatban érvényes orvos–beteg összerendelés."""
    at = at or datetime.now(UTC)
    query = select(
        exists().where(
            DoctorPatient.doctor_id == doctor_id,
            DoctorPatient.patient_id == patient_id,
            _valid_at(at),
        )
    )
    return bool(db.scalar(query))


def assigned_patients_query(doctor_id: uuid.UUID, at: datetime) -> Select[tuple[PatientProfile]]:
    """Az orvoshoz az adott pillanatban rendelt betegek (a beteglistához)."""
    return (
        select(PatientProfile)
        .join(DoctorPatient, DoctorPatient.patient_id == PatientProfile.id)
        .where(DoctorPatient.doctor_id == doctor_id, _valid_at(at))
    )


def can_access_patient(db: Session, user: User, patient_id: uuid.UUID) -> bool:
    """Hozzáférhet-e a felhasználó az adott beteg (PatientProfile.id) adataihoz.
    Minden hívásnál az adatbázisból dönt, így az összerendelés megszüntetése
    vagy létrejötte azonnal hat (F3)."""
    if not user.is_active:
        return False
    if user.role is UserRole.PATIENT:
        return user.patient_profile is not None and user.patient_profile.id == patient_id
    if user.role is UserRole.DOCTOR:
        return user.doctor_profile is not None and active_assignment_exists(
            db, user.doctor_profile.id, patient_id
        )
    return False
