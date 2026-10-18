"""A seed (mesterséges demóadat, M2-leadandó) gépi ellenőrzése."""

from sqlalchemy import func, select

from app.models import (
    Alert,
    Assignment,
    DoctorPatient,
    Measurement,
    QuestionnaireTemplate,
    Rule,
    Submission,
    User,
)
from app.services.access import can_access_patient
from app.services.status import PatientStatus, doctor_patient_list
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
    models = (
        User,
        DoctorPatient,
        Rule,
        Measurement,
        Alert,
        QuestionnaireTemplate,
        Assignment,
        Submission,
    )
    before = [count(db, m) for m in models]
    second_run = seed_demo_data(db)
    assert [count(db, m) for m in models] == before
    created = (
        "létrehozva",
        "összerendelve",
        "méréstípus",
        "szabályok",
        "mérések",
        "kérdőív",
        "kirendelés",
        "kitöltések",
    )
    assert not any(line.startswith(created) for line in second_run)


def test_seeded_doctor_list_shows_every_m2_status(db):
    # A bemutatóhoz: Kovács doktor listáján minden M2-beli státusz megjelenik,
    # a valódi szabálykiértékelés eredményeként, priorizálva.
    seed_demo_data(db)
    kovacs = get_user_by_email(db, "dr.kovacs@pulse.example")
    rows = doctor_patient_list(db, kovacs.doctor_profile.id)
    assert [(p.name, r.status) for p, r in rows] == [
        ("Varga Béla", PatientStatus.SEVERE),
        ("Szabó János", PatientStatus.ATTENTION),
        ("Kiss Ilona", PatientStatus.NO_DATA),
        ("Molnár Katalin", PatientStatus.OK),
    ]


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
