"""create_user — a 9. jóváhagyott pont.

2026-10-10: a specifikáció módosult (a másik független tesztíró leletei alapján):
create_user mostantól 10-255 karakteres jelszót követel (PASSWORD_MIN_LENGTH /
PASSWORD_MAX_LENGTH), különben ValueError. A korábbi "x"/"y" jelszavak emiatt
mindenhol lecserélve egy megfelelő hosszú, érvényes jelszóra; ahol kifejezetten
a hossz-szabályt teszteljük, azt új tesztek vizsgálják.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH
from app.models import DoctorProfile, PatientProfile, UserRole
from app.services.users import create_user, get_user_by_email

VALID_PASSWORD = "Ervenyes-Jelszo-1"
OTHER_VALID_PASSWORD = "Masik-Ervenyes-Jelszo-2"


def test_create_patient_requires_name_and_birth_date(db: Session) -> None:
    with pytest.raises(ValueError):
        create_user(
            db, email="hianyos-beteg@example.com", password=VALID_PASSWORD, role=UserRole.PATIENT
        )


def test_create_patient_missing_birth_date_only(db: Session) -> None:
    with pytest.raises(ValueError):
        create_user(
            db,
            email="hianyos-beteg2@example.com",
            password=VALID_PASSWORD,
            role=UserRole.PATIENT,
            name="Van Név",
        )


def test_create_doctor_requires_name(db: Session) -> None:
    with pytest.raises(ValueError):
        create_user(
            db, email="hianyos-orvos@example.com", password=VALID_PASSWORD, role=UserRole.DOCTOR
        )


def test_create_patient_creates_patient_profile(db: Session) -> None:
    user = create_user(
        db,
        email="profil-beteg@example.com",
        password=VALID_PASSWORD,
        role=UserRole.PATIENT,
        name="Teszt Panni",
        birth_date=date(1985, 5, 5),
    )
    db.commit()

    assert isinstance(user.patient_profile, PatientProfile)
    assert user.doctor_profile is None
    assert user.patient_profile.name == "Teszt Panni"


def test_create_doctor_creates_doctor_profile(db: Session) -> None:
    user = create_user(
        db,
        email="profil-orvos@example.com",
        password=VALID_PASSWORD,
        role=UserRole.DOCTOR,
        name="Dr. X",
    )
    db.commit()

    assert isinstance(user.doctor_profile, DoctorProfile)
    assert user.patient_profile is None


def test_create_admin_has_no_profile(db: Session) -> None:
    user = create_user(
        db, email="profil-admin@example.com", password=VALID_PASSWORD, role=UserRole.ADMIN
    )
    db.commit()

    assert user.patient_profile is None
    assert user.doctor_profile is None


def test_email_stored_lowercase(db: Session) -> None:
    user = create_user(
        db, email="Nagy.Beteg@Example.COM", password=VALID_PASSWORD, role=UserRole.ADMIN
    )
    db.commit()

    assert user.email == "nagy.beteg@example.com"


def test_email_uniqueness_case_insensitive(db: Session) -> None:
    create_user(db, email="egyedi@example.com", password=VALID_PASSWORD, role=UserRole.ADMIN)
    db.commit()

    with pytest.raises(IntegrityError):
        create_user(
            db, email="EGYEDI@EXAMPLE.COM", password=OTHER_VALID_PASSWORD, role=UserRole.ADMIN
        )
        db.commit()


def test_get_user_by_email_is_case_insensitive(db: Session) -> None:
    create_user(db, email="keresett@example.com", password=VALID_PASSWORD, role=UserRole.ADMIN)
    db.commit()

    found = get_user_by_email(db, "KERESETT@example.com")

    assert found is not None
    assert found.email == "keresett@example.com"


# --- Új tesztek: jelszóhossz-szabály (2026-10-10 specifikációváltozás) ---


def test_password_too_short_raises_value_error(db: Session) -> None:
    short_password = "a" * (PASSWORD_MIN_LENGTH - 1)

    with pytest.raises(ValueError):
        create_user(
            db, email="rovid-jelszo@example.com", password=short_password, role=UserRole.ADMIN
        )


def test_password_too_long_raises_value_error(db: Session) -> None:
    long_password = "a" * (PASSWORD_MAX_LENGTH + 1)

    with pytest.raises(ValueError):
        create_user(
            db, email="hosszu-jelszo@example.com", password=long_password, role=UserRole.ADMIN
        )


def test_password_exactly_min_length_accepted(db: Session) -> None:
    password = "a" * PASSWORD_MIN_LENGTH

    user = create_user(
        db, email="min-hosszu-jelszo@example.com", password=password, role=UserRole.ADMIN
    )
    db.commit()

    assert user.email == "min-hosszu-jelszo@example.com"


def test_password_exactly_max_length_accepted(db: Session) -> None:
    password = "a" * PASSWORD_MAX_LENGTH

    user = create_user(
        db, email="max-hosszu-jelszo@example.com", password=password, role=UserRole.ADMIN
    )
    db.commit()

    assert user.email == "max-hosszu-jelszo@example.com"


def test_db_rejects_mixed_case_email_bypassing_service(db: Session) -> None:
    """2026-10-10: ck_users_email_lowercase — a szolgáltatást megkerülő, vegyes
    betűs e-mail beszúrása az adatbázis szintjén is elutasítva."""
    from app.core.security import hash_password
    from app.models import User

    user = User(
        email="Vegyes.Betu@Example.com",
        password_hash=hash_password(VALID_PASSWORD),
        role=UserRole.ADMIN,
    )
    db.add(user)

    with pytest.raises(IntegrityError):
        db.commit()


def test_password_too_short_does_not_create_user(db: Session) -> None:
    """Hibás jelszónál ne maradjon félig létrehozott felhasználó az adatbázisban."""
    short_password = "a" * (PASSWORD_MIN_LENGTH - 1)

    with pytest.raises(ValueError):
        create_user(
            db, email="nem-johet-letre@example.com", password=short_password, role=UserRole.ADMIN
        )

    assert get_user_by_email(db, "nem-johet-letre@example.com") is None
