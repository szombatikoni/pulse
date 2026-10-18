"""Segédfüggvények a tesztadatok gyors létrehozásához."""

from datetime import UTC, date, datetime

from sqlalchemy.orm import Session

from app.models import Alert, DoctorPatient, Measurement, Rule, RuleType, Severity, User, UserRole
from app.services.measurements import record_measurement
from app.services.rules import create_rule
from app.services.users import create_user
from seed.reference import seed_measurement_types

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


def make_measurement_types(db: Session) -> None:
    """A valódi törzsadatok (vérnyomás, pulzus, testsúly, vércukor)."""
    seed_measurement_types(db)


def make_threshold_rule(
    db: Session,
    patient: User,
    created_by: User,
    limits: dict | None = None,
    severity: Severity = Severity.MODERATE,
    measurement_type: str = "blood_pressure",
) -> Rule:
    """Küszöbszabály; alapból: szisztolés > 140 vagy diasztolés > 90, közepes."""
    return create_rule(
        db,
        patient_id=patient.patient_profile.id,
        created_by=created_by.id,
        rule_type=RuleType.THRESHOLD,
        params={
            "measurement_type": measurement_type,
            "limits": limits
            if limits is not None
            else {"systolic": {"max": 140}, "diastolic": {"max": 90}},
        },
        severity=severity,
    )


def record_bp(
    db: Session, patient: User, systolic: float, diastolic: float, at: datetime | None = None
) -> tuple[Measurement, list[Alert]]:
    """Vérnyomásmérés rögzítése a valódi úton (rögzítés + kiértékelés)."""
    at = at or datetime.now(UTC)
    return record_measurement(
        db,
        patient_id=patient.patient_profile.id,
        type_code="blood_pressure",
        values={"systolic": systolic, "diastolic": diastolic},
        measured_at=at,
        now=at,
    )
