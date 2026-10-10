"""Spec 12 + F2/F3 HTTP-n: require_roles és egy betegadat-mintavégpont a próba-alkalmazáson."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.models import UserRole
from tests.independent_fable.helpers import (
    assign,
    bearer,
    forge_token,
    login_token,
    make_admin,
    make_doctor,
    make_patient,
    standard_payload,
)

# --- 12. require_roles ------------------------------------------------------------


def test_doctor_only_allows_doctor(client, probe, db: Session):
    doctor = make_doctor(db)
    response = probe.get("/doctor-only", headers=bearer(login_token(client, doctor)))
    assert response.status_code == 200
    assert response.json() == {"id": str(doctor.user.id), "role": "doctor"}


@pytest.mark.parametrize("factory", [make_patient, make_admin])
def test_doctor_only_forbids_other_roles(client, probe, db: Session, factory):
    account = factory(db)
    response = probe.get("/doctor-only", headers=bearer(login_token(client, account)))
    assert response.status_code == 403
    assert "doctor" not in response.text.lower()


def test_admin_only(client, probe, db: Session):
    admin = make_admin(db)
    doctor = make_doctor(db)
    patient = make_patient(db)
    assert probe.get("/admin-only", headers=bearer(login_token(client, admin))).status_code == 200
    assert probe.get("/admin-only", headers=bearer(login_token(client, doctor))).status_code == 403
    assert probe.get("/admin-only", headers=bearer(login_token(client, patient))).status_code == 403


def test_multi_role_dependency(client, probe, db: Session):
    admin = make_admin(db)
    doctor = make_doctor(db)
    patient = make_patient(db)
    url = "/patient-or-doctor"
    assert probe.get(url, headers=bearer(login_token(client, patient))).status_code == 200
    assert probe.get(url, headers=bearer(login_token(client, doctor))).status_code == 200
    assert probe.get(url, headers=bearer(login_token(client, admin))).status_code == 403


def test_empty_role_list_forbids_everyone(client, probe, db: Session):
    admin = make_admin(db)
    assert (
        probe.get("/no-role-allowed", headers=bearer(login_token(client, admin))).status_code == 403
    )


def test_role_endpoint_without_token_is_401_not_403(client, probe, db: Session):
    """Hitelesítés nélkül 401 (+ WWW-Authenticate), nem 403: a jogosultságot
    csak azonosított felhasználónál vizsgáljuk."""
    response = probe.get("/doctor-only")
    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == "Bearer"


def test_role_endpoint_disabled_doctor_is_401(client, probe, db: Session):
    doctor = make_doctor(db)
    token = login_token(client, doctor)
    doctor.user.is_active = False
    db.flush()
    response = probe.get("/doctor-only", headers=bearer(token))
    assert response.status_code == 401


def test_role_endpoint_uses_db_role_not_token_claim(client, probe, db: Session):
    """Aláírt token hamis role igénnyel: 403 marad, ha az adatbázisban beteg."""
    patient = make_patient(db)
    payload = standard_payload(patient.user.id)
    payload["role"] = "doctor"
    assert probe.get("/doctor-only", headers=bearer(forge_token(payload))).status_code == 403


def test_role_demotion_takes_effect_with_live_token(client, probe, db: Session):
    doctor = make_doctor(db)
    token = login_token(client, doctor)
    assert probe.get("/doctor-only", headers=bearer(token)).status_code == 200
    doctor.user.role = UserRole.PATIENT
    db.flush()
    assert probe.get("/doctor-only", headers=bearer(token)).status_code == 403


def test_role_promotion_takes_effect_with_live_token(client, probe, db: Session):
    account = make_admin(db)
    token = login_token(client, account)
    assert probe.get("/doctor-only", headers=bearer(token)).status_code == 403
    account.user.role = UserRole.DOCTOR
    db.flush()
    assert probe.get("/doctor-only", headers=bearer(token)).status_code == 200


# --- F2/F3 HTTP-n: betegadat-mintavégpont -----------------------------------------


def _data_url(account) -> str:
    return f"/patients/{account.user.patient_profile.id}/data"


def test_patient_reads_own_data(client, probe, db: Session):
    patient = make_patient(db)
    response = probe.get(_data_url(patient), headers=bearer(login_token(client, patient)))
    assert response.status_code == 200
    assert response.json()["patient_id"] == str(patient.user.patient_profile.id)


def test_patient_cannot_read_other_patients_data(client, probe, db: Session):
    a = make_patient(db)
    b = make_patient(db)
    assert probe.get(_data_url(b), headers=bearer(login_token(client, a))).status_code == 403


def test_doctor_reads_assigned_patient_only(client, probe, db: Session):
    doctor = make_doctor(db)
    mine = make_patient(db)
    other = make_patient(db)
    assign(db, doctor, mine)
    token = login_token(client, doctor)
    assert probe.get(_data_url(mine), headers=bearer(token)).status_code == 200
    assert probe.get(_data_url(other), headers=bearer(token)).status_code == 403


def test_admin_cannot_read_patient_data(client, probe, db: Session):
    admin = make_admin(db)
    patient = make_patient(db)
    assert (
        probe.get(_data_url(patient), headers=bearer(login_token(client, admin))).status_code == 403
    )


def test_revocation_closes_http_access_with_live_token(client, probe, db: Session):
    doctor = make_doctor(db)
    patient = make_patient(db)
    link = assign(db, doctor, patient)
    token = login_token(client, doctor)
    assert probe.get(_data_url(patient), headers=bearer(token)).status_code == 200
    link.valid_to = datetime.now(UTC)
    db.flush()
    assert probe.get(_data_url(patient), headers=bearer(token)).status_code == 403


def test_new_assignment_opens_http_access_with_live_token(client, probe, db: Session):
    doctor = make_doctor(db)
    patient = make_patient(db)
    token = login_token(client, doctor)
    assert probe.get(_data_url(patient), headers=bearer(token)).status_code == 403
    assign(db, doctor, patient)
    assert probe.get(_data_url(patient), headers=bearer(token)).status_code == 200


def test_future_assignment_does_not_open_http_access(client, probe, db: Session):
    doctor = make_doctor(db)
    patient = make_patient(db)
    assign(db, doctor, patient, valid_from=datetime.now(UTC) + timedelta(hours=1))
    token = login_token(client, doctor)
    assert probe.get(_data_url(patient), headers=bearer(token)).status_code == 403


def test_patient_data_without_token_is_401(client, probe, db: Session):
    patient = make_patient(db)
    response = probe.get(_data_url(patient))
    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == "Bearer"


def test_disabled_patient_cannot_read_own_data_with_live_token(client, probe, db: Session):
    patient = make_patient(db)
    token = login_token(client, patient)
    patient.user.is_active = False
    db.flush()
    assert probe.get(_data_url(patient), headers=bearer(token)).status_code == 401


def test_patient_data_with_non_uuid_id_is_not_200(client, probe, db: Session):
    patient = make_patient(db)
    token = login_token(client, patient)
    assert probe.get("/patients/nem-uuid/data", headers=bearer(token)).status_code in (
        403,
        404,
        422,
    )
