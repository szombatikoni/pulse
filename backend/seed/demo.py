"""Demófelhasználók és orvos–beteg összerendelések létrehozása.

Minden név és adat kitalált (mesterséges). A közös jelszó CSAK helyi és
bemutató célra való.
"""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DoctorPatient, User, UserRole
from app.services.users import create_user, get_user_by_email

DEMO_PASSWORD = "pulse-demo-2026"

USERS = [
    {"email": "admin@pulse.example", "role": UserRole.ADMIN},
    {"email": "dr.kovacs@pulse.example", "role": UserRole.DOCTOR, "name": "Dr. Kovács Éva"},
    {"email": "dr.nagy@pulse.example", "role": UserRole.DOCTOR, "name": "Dr. Nagy Péter"},
    {
        "email": "szabo.janos@pulse.example",
        "role": UserRole.PATIENT,
        "name": "Szabó János",
        "birth_date": date(1958, 3, 14),
    },
    {
        "email": "toth.maria@pulse.example",
        "role": UserRole.PATIENT,
        "name": "Tóth Mária",
        "birth_date": date(1962, 11, 2),
    },
]

# Kovács doktor csak Szabó Jánost, Nagy doktor csak Tóth Máriát látja: így a
# bemutatón látszik, hogy az orvos idegen beteg adatát nem éri el.
ASSIGNMENTS = [
    ("dr.kovacs@pulse.example", "szabo.janos@pulse.example"),
    ("dr.nagy@pulse.example", "toth.maria@pulse.example"),
]


def _get(db: Session, email: str) -> User:
    user = get_user_by_email(db, email)
    assert user is not None, email
    return user


def seed_demo_data(db: Session) -> list[str]:
    """Létrehozza a hiányzó demófiókokat és összerendeléseket, a meglévőket
    kihagyja (ismételten futtatható). Visszaadja, mi történt (soronként)."""
    log: list[str] = []
    for spec in USERS:
        if get_user_by_email(db, spec["email"]) is None:
            create_user(db, password=DEMO_PASSWORD, **spec)
            log.append(f"létrehozva: {spec['email']} ({spec['role']})")
        else:
            log.append(f"már létezik: {spec['email']}")

    for doctor_email, patient_email in ASSIGNMENTS:
        doctor = _get(db, doctor_email).doctor_profile
        patient = _get(db, patient_email).patient_profile
        active = db.scalar(
            select(DoctorPatient).where(
                DoctorPatient.doctor_id == doctor.id,
                DoctorPatient.patient_id == patient.id,
                DoctorPatient.valid_to.is_(None),
            )
        )
        if active is None:
            db.add(DoctorPatient(doctor_id=doctor.id, patient_id=patient.id))
            log.append(f"összerendelve: {doctor.name} – {patient.name}")

    db.commit()
    return log
