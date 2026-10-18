"""A mérés-folyamat végpontjai: jogosultság végpontszinten (F2, F3, NF1) és a
teljes folyamat a beteg rögzítésétől az orvosi megjelenítésig (M2)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.core.security import create_access_token
from app.models import Severity
from tests.factories import (
    PASSWORD,
    assign,
    make_admin,
    make_doctor,
    make_patient,
    make_threshold_rule,
)


def auth(user):
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def bp(systolic=128, diastolic=82, measured_at=None):
    measured_at = measured_at or datetime.now(UTC) - timedelta(minutes=1)
    return {
        "type_code": "blood_pressure",
        "measured_at": measured_at.isoformat(),
        "values": {"systolic": systolic, "diastolic": diastolic},
    }


@pytest.fixture
def setup(db, measurement_types):
    """Egy orvos a saját betegével, egy idegen beteg és egy admin."""
    doctor = make_doctor(db)
    patient = make_patient(db)
    foreign = make_patient(db, email="idegen@test.example", name="Idegen Beteg")
    link = assign(db, doctor, patient)
    make_threshold_rule(db, patient, doctor)
    return {
        "doctor": doctor,
        "patient": patient,
        "foreign": foreign,
        "admin": make_admin(db),
        "link": link,
    }


def pid(user) -> str:
    return str(user.patient_profile.id)


# --- Rögzítés ----------------------------------------------------------------


def test_patient_records_own_measurement(client, setup):
    patient = setup["patient"]
    response = client.post(
        f"/api/patients/{pid(patient)}/measurements", json=bp(131, 84), headers=auth(patient)
    )
    assert response.status_code == 201
    body = response.json()
    assert body["type_code"] == "blood_pressure"
    assert body["values"] == [
        {"component": "systolic", "value": 131, "unit": "mm[Hg]"},
        {"component": "diastolic", "value": 84, "unit": "mm[Hg]"},
    ]


def test_patient_cannot_record_for_another_patient(client, setup):
    response = client.post(
        f"/api/patients/{pid(setup['foreign'])}/measurements",
        json=bp(),
        headers=auth(setup["patient"]),
    )
    assert response.status_code == 403


@pytest.mark.parametrize("role", ["doctor", "admin"])
def test_only_patients_can_record(client, setup, role):
    response = client.post(
        f"/api/patients/{pid(setup['patient'])}/measurements", json=bp(), headers=auth(setup[role])
    )
    assert response.status_code == 403


def test_recording_requires_login(client, setup):
    response = client.post(f"/api/patients/{pid(setup['patient'])}/measurements", json=bp())
    assert response.status_code == 401


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        (bp(measured_at=datetime.now(UTC) - timedelta(days=3)), "too_old"),
        (bp(systolic=1400), "out_of_range"),
        ({**bp(), "type_code": "cholesterol"}, "unknown_type"),
    ],
)
def test_invalid_measurement_gives_422_with_reason_code(client, setup, payload, code):
    patient = setup["patient"]
    response = client.post(
        f"/api/patients/{pid(patient)}/measurements", json=payload, headers=auth(patient)
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == code


def test_measured_at_without_timezone_is_rejected(client, setup):
    patient = setup["patient"]
    payload = {**bp(), "measured_at": "2026-10-12T07:30:00"}
    response = client.post(
        f"/api/patients/{pid(patient)}/measurements", json=payload, headers=auth(patient)
    )
    assert response.status_code == 422


# --- Lekérdezés: ki mit láthat ----------------------------------------------


def test_doctor_and_patient_see_the_patients_measurements(client, setup):
    patient = setup["patient"]
    client.post(f"/api/patients/{pid(patient)}/measurements", json=bp(), headers=auth(patient))
    for user in (patient, setup["doctor"]):
        response = client.get(f"/api/patients/{pid(patient)}/measurements", headers=auth(user))
        assert response.status_code == 200
        assert len(response.json()) == 1


@pytest.mark.parametrize(
    "path",
    [
        "/api/patients/{id}/measurements",
        "/api/patients/{id}",
        "/api/patients/{id}/alerts",
    ],
)
def test_doctor_cannot_read_foreign_patient(client, setup, path):
    url = path.format(id=pid(setup["foreign"]))
    assert client.get(url, headers=auth(setup["doctor"])).status_code == 403


@pytest.mark.parametrize(
    "path",
    [
        "/api/patients/{id}/measurements",
        "/api/patients/{id}",
        "/api/patients/{id}/alerts",
    ],
)
def test_admin_cannot_read_patient_data(client, setup, path):
    url = path.format(id=pid(setup["patient"]))
    assert client.get(url, headers=auth(setup["admin"])).status_code == 403


def test_unknown_patient_id_is_403_not_404(client, setup):
    # A válaszból nem derülhet ki, létezik-e az azonosító.
    url = f"/api/patients/{uuid.uuid4()}/measurements"
    assert client.get(url, headers=auth(setup["doctor"])).status_code == 403


def test_patient_cannot_read_another_patients_measurements(client, setup):
    url = f"/api/patients/{pid(setup['foreign'])}/measurements"
    assert client.get(url, headers=auth(setup["patient"])).status_code == 403


@pytest.mark.parametrize("path", ["/api/patients/{id}", "/api/patients/{id}/alerts"])
def test_alerts_and_status_are_for_doctors_only(client, setup, path):
    url = path.format(id=pid(setup["patient"]))
    assert client.get(url, headers=auth(setup["patient"])).status_code == 403


@pytest.mark.parametrize("role", ["patient", "admin"])
def test_patient_list_is_for_doctors_only(client, setup, role):
    assert client.get("/api/doctor/patients", headers=auth(setup[role])).status_code == 403


def test_ending_assignment_revokes_endpoint_access_immediately(client, db, setup):
    url = f"/api/patients/{pid(setup['patient'])}/measurements"
    doctor = setup["doctor"]
    assert client.get(url, headers=auth(doctor)).status_code == 200
    setup["link"].valid_to = datetime.now(UTC)
    db.flush()
    assert client.get(url, headers=auth(doctor)).status_code == 403
    assert client.get("/api/doctor/patients", headers=auth(doctor)).json() == []


def test_new_assignment_grants_endpoint_access_immediately(client, db, setup):
    url = f"/api/patients/{pid(setup['foreign'])}/measurements"
    doctor = setup["doctor"]
    assert client.get(url, headers=auth(doctor)).status_code == 403
    assign(db, doctor, setup["foreign"])
    assert client.get(url, headers=auth(doctor)).status_code == 200


def test_doctor_sees_patient_header_with_status(client, setup):
    patient = setup["patient"]
    client.post(
        f"/api/patients/{pid(patient)}/measurements", json=bp(125, 80), headers=auth(patient)
    )
    response = client.get(f"/api/patients/{pid(patient)}", headers=auth(setup["doctor"]))
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Teszt Beteg"
    assert body["status"] == "ok"
    assert [r["code"] for r in body["reasons"]] == ["fresh_data"]


def test_measurement_types_are_listed_with_codes(client, setup):
    response = client.get("/api/measurement-types", headers=auth(setup["patient"]))
    assert response.status_code == 200
    by_code = {t["code"]: t for t in response.json()}
    assert by_code["blood_pressure"]["loinc_code"] == "85354-9"
    assert [c["code"] for c in by_code["blood_pressure"]["components"]] == [
        "systolic",
        "diastolic",
    ]


def test_me_returns_patient_id_for_patients_only(client, setup):
    me = client.get("/api/auth/me", headers=auth(setup["patient"])).json()
    assert me["patient_id"] == pid(setup["patient"])
    me = client.get("/api/auth/me", headers=auth(setup["doctor"])).json()
    assert me["patient_id"] is None


# --- A teljes folyamat -------------------------------------------------------


def test_full_flow_from_patient_entry_to_doctor_view(client, db, measurement_types):
    """A beteg belép és rögzít egy magas értéket → a szabály kiértékeli →
    riasztás keletkezik → az orvos a listáján Figyelem státusszal, okkal látja,
    és a riasztás magyarázata megmondja, melyik szabályverzió, melyik mérés,
    melyik határ."""
    doctor = make_doctor(db, email="flow.orvos@test.example")
    patient = make_patient(db, email="flow.beteg@test.example", name="Folyamat Beteg")
    assign(db, doctor, patient)
    make_threshold_rule(db, patient, doctor, severity=Severity.MODERATE)

    def login(email):
        response = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    patient_headers = login("flow.beteg@test.example")
    me = client.get("/api/auth/me", headers=patient_headers).json()
    created = client.post(
        f"/api/patients/{me['patient_id']}/measurements",
        json=bp(152, 95),
        headers=patient_headers,
    )
    assert created.status_code == 201
    measurement_id = created.json()["id"]

    doctor_headers = login("flow.orvos@test.example")
    [row] = client.get("/api/doctor/patients", headers=doctor_headers).json()
    assert row["name"] == "Folyamat Beteg"
    assert row["status"] == "attention"
    reason = row["reasons"][0]
    assert reason["code"] == "open_alert"
    assert reason["severity"] == "moderate"
    assert reason["trigger"]["measurement"]["id"] == measurement_id
    assert reason["trigger"]["violations"] == [
        {"component": "systolic", "value": 152, "bound": "max", "limit": 140},
        {"component": "diastolic", "value": 95, "bound": "max", "limit": 90},
    ]

    [alert] = client.get(f"/api/patients/{me['patient_id']}/alerts", headers=doctor_headers).json()
    assert alert["status"] == "new"
    assert alert["rule_version"]["version_no"] == 1
    assert alert["rule_version"]["params"]["limits"]["systolic"] == {"max": 140}
    [event] = alert["events"]
    assert event["event_type"] == "created"
    assert event["triggers"][0]["measurement"]["id"] == measurement_id


@pytest.mark.parametrize(
    "path", ["/api/measurement-types", "/api/doctor/patients", "/api/patients/{id}/alerts"]
)
def test_endpoints_require_login(client, setup, path):
    response = client.get(path.format(id=pid(setup["patient"])))
    assert response.status_code == 401


def test_closed_alerts_are_listed_only_on_request(client, db, setup):
    patient = setup["patient"]
    client.post(
        f"/api/patients/{pid(patient)}/measurements", json=bp(150, 95), headers=auth(patient)
    )
    url = f"/api/patients/{pid(patient)}/alerts"
    [alert] = client.get(url, headers=auth(setup["doctor"])).json()
    db.execute(
        text("UPDATE alerts SET status = 'closed' WHERE id = :id"), {"id": alert["id"]}
    )  # a lezárás folyamata az M3-ban jön
    assert client.get(url, headers=auth(setup["doctor"])).json() == []
    closed = client.get(url + "?include_closed=true", headers=auth(setup["doctor"])).json()
    assert [a["status"] for a in closed] == ["closed"]
