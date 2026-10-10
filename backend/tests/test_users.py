from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.security import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH
from app.models import User, UserRole
from app.services.users import create_user
from tests.factories import PASSWORD


def test_patient_needs_name_and_birth_date(db):
    with pytest.raises(ValueError):
        create_user(db, email="b@test.example", password=PASSWORD, role=UserRole.PATIENT, name="B")


def test_doctor_needs_name(db):
    with pytest.raises(ValueError):
        create_user(db, email="o@test.example", password=PASSWORD, role=UserRole.DOCTOR)


def test_profile_matches_role(db):
    patient = create_user(
        db,
        email="p@test.example",
        password=PASSWORD,
        role=UserRole.PATIENT,
        name="P",
        birth_date=date(1970, 5, 5),
    )
    admin = create_user(db, email="a@test.example", password=PASSWORD, role=UserRole.ADMIN)
    assert patient.patient_profile is not None and patient.doctor_profile is None
    assert admin.patient_profile is None and admin.doctor_profile is None


@pytest.mark.parametrize("length", [PASSWORD_MIN_LENGTH - 1, PASSWORD_MAX_LENGTH + 1, 0])
def test_password_length_out_of_range_is_rejected_at_creation(db, length):
    with pytest.raises(ValueError):
        create_user(db, email="h@test.example", password="x" * length, role=UserRole.ADMIN)


@pytest.mark.parametrize("length", [PASSWORD_MIN_LENGTH, PASSWORD_MAX_LENGTH])
def test_password_length_boundaries_are_accepted(db, length):
    user = create_user(db, email="h@test.example", password="x" * length, role=UserRole.ADMIN)
    assert user.id is not None


def test_database_rejects_mixed_case_email_even_without_the_service(db):
    # Védelem mélységben: a szolgáltatást megkerülő beszúrást is elutasítja.
    db.add(User(email="Vegyes@Test.Example", password_hash="x", role=UserRole.ADMIN))
    with pytest.raises(IntegrityError):
        db.flush()
