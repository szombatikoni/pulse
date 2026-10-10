"""Segédfüggvények a tesztadatok gyors létrehozásához."""

from datetime import date, datetime

from sqlalchemy.orm import Session

from app.models import DoctorPatient, User, UserRole
from app.services.users import create_user

PASSWORD = "correct-horse-battery"


def make_patient(db: Session, email: str = "beteg@test.example", name: str = "Teszt Beteg") -> User:
    return create_user(
        db,
        email=email,
        password=PASSWORD,
        role=UserRole.PATIENT,
        name=name,
        birth_date=date(1960, 1, 1),
    )


def make_doctor(db: Session, email: str = "orvos@test.example", name: str = "Dr. Teszt") -> User:
    return create_user(db, email=email, password=PASSWORD, role=UserRole.DOCTOR, name=name)


def make_admin(db: Session, email: str = "admin@test.example") -> User:
    return create_user(db, email=email, password=PASSWORD, role=UserRole.ADMIN)


def assign(
    db: Session,
    doctor: User,
    patient: User,
    valid_from: datetime | None = None,
    valid_to: datetime | None = None,
) -> DoctorPatient:
    link = DoctorPatient(
        doctor_id=doctor.doctor_profile.id,
        patient_id=patient.patient_profile.id,
        valid_to=valid_to,
    )
    if valid_from is not None:
        link.valid_from = valid_from
    db.add(link)
    db.flush()
    return link
