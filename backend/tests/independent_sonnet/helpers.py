"""Segédfüggvények a független tesztkészlethez.

Szándékosan nem importáljuk a `tests/factories.py`-t (függetlenség), helyette
saját, minimális segédfüggvényeket írunk a specifikációban leírt
`create_user` szolgáltatás köré.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy.orm import Session

from app.models import DoctorPatient, User, UserRole
from app.services.users import create_user

# Legalább PASSWORD_MIN_LENGTH (10) karakter, hogy create_user elfogadja.
DEFAULT_PASSWORD = "Helyes-Jelszo-123"


def make_patient(
    db: Session,
    *,
    email: str,
    password: str = DEFAULT_PASSWORD,
    name: str = "Teszt Elek",
    birth_date: date = date(1990, 1, 1),
) -> User:
    user = create_user(
        db, email=email, password=password, role=UserRole.PATIENT, name=name, birth_date=birth_date
    )
    db.commit()
    return user


def make_doctor(
    db: Session, *, email: str, password: str = DEFAULT_PASSWORD, name: str = "Dr. Teszt"
) -> User:
    user = create_user(db, email=email, password=password, role=UserRole.DOCTOR, name=name)
    db.commit()
    return user


def make_admin(db: Session, *, email: str, password: str = DEFAULT_PASSWORD) -> User:
    user = create_user(db, email=email, password=password, role=UserRole.ADMIN)
    db.commit()
    return user


def assign(
    db: Session,
    *,
    doctor_id: uuid.UUID,
    patient_id: uuid.UUID,
    valid_from,
    valid_to=None,
) -> DoctorPatient:
    link = DoctorPatient(
        doctor_id=doctor_id, patient_id=patient_id, valid_from=valid_from, valid_to=valid_to
    )
    db.add(link)
    db.commit()
    return link
