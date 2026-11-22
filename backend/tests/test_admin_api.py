"""Az „ellenőrzés most" végpont (M3, A2): csak az admin indíthatja, és ugyanazt
futtatja, mint a háttérfolyamat."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.security import create_access_token
from app.models import AssignmentOccurrence, OccurrenceStatus
from app.services.measurements import get_type_by_code
from app.services.tasks import assign_measurement
from tests.factories import assign, make_admin, make_doctor, make_measurement_types, make_patient

URL = "/api/admin/occurrence-check"


def auth(user):
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


@pytest.fixture
def setup(db):
    make_measurement_types(db)
    doctor = make_doctor(db)
    patient = make_patient(db)
    assign(db, doctor, patient)
    # Három napja kezdődő napi mérés: a háromnapos időszak pótlási ideje már lejárt.
    today = datetime.now(settings.tz).date()
    assign_measurement(
        db,
        patient_id=patient.patient_profile.id,
        measurement_type=get_type_by_code(db, "blood_pressure"),
        assigned_by=doctor.id,
        start_date=today - timedelta(days=3),
    )
    return {"doctor": doctor, "patient": patient, "admin": make_admin(db)}


def test_admin_runs_the_check_and_gets_the_result(client, db, setup):
    response = client.post(URL, headers=auth(setup["admin"]))
    assert response.status_code == 200
    # Négy időszak (3 napja … ma), ebből a legrégebbi elmulasztva.
    assert response.json() == {"opened": 4, "missed": 1}
    statuses = sorted(o.status for o in db.scalars(select(AssignmentOccurrence)))
    assert statuses == sorted([OccurrenceStatus.MISSED] + [OccurrenceStatus.DUE] * 3)

    # Ismételt hívás nem változtat semmin (idempotens).
    again = client.post(URL, headers=auth(setup["admin"]))
    assert again.json() == {"opened": 0, "missed": 0}


@pytest.mark.parametrize("role", ["patient", "doctor"])
def test_only_the_admin_may_run_the_check(client, db, setup, role):
    response = client.post(URL, headers=auth(setup[role]))
    assert response.status_code == 403
    assert db.scalars(select(AssignmentOccurrence)).all() == []


def test_the_check_requires_login(client, db, setup):
    assert client.post(URL).status_code == 401
    assert db.scalars(select(AssignmentOccurrence)).all() == []
