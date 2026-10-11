"""A seed (mesterséges demóadat, M2-leadandó) gépi ellenőrzése."""

from sqlalchemy import func, select

from app.models import DoctorPatient, User
from app.services.access import can_access_patient
from app.services.users import get_user_by_email
from seed.demo import ASSIGNMENTS, DEMO_PASSWORD, USERS, seed_demo_data


def count(db, model):
    return db.scalar(select(func.count()).select_from(model))


def test_seed_creates_demo_accounts_and_assignments(db):
    users_before, links_before = count(db, User), count(db, DoctorPatient)
    seed_demo_data(db)
    assert count(db, User) == users_before + len(USERS)
    assert count(db, DoctorPatient) == links_before + len(ASSIGNMENTS)


def test_seed_is_idempotent(db):
    seed_demo_data(db)
    users, links = count(db, User), count(db, DoctorPatient)
    second_run = seed_demo_data(db)
    assert count(db, User) == users
    assert count(db, DoctorPatient) == links
    assert not any(line.startswith(("létrehozva", "összerendelve")) for line in second_run)


def test_seeded_doctor_sees_only_own_patient(db):
    seed_demo_data(db)
    kovacs = get_user_by_email(db, "dr.kovacs@pulse.example")
    szabo = get_user_by_email(db, "szabo.janos@pulse.example")
    toth = get_user_by_email(db, "toth.maria@pulse.example")
    assert can_access_patient(db, kovacs, szabo.patient_profile.id)
    assert not can_access_patient(db, kovacs, toth.patient_profile.id)


def test_seeded_accounts_can_log_in(client, db):
    seed_demo_data(db)
    for spec in USERS:
        response = client.post(
            "/api/auth/login", json={"email": spec["email"], "password": DEMO_PASSWORD}
        )
        assert response.status_code == 200, spec["email"]
