"""A kérdőív-folyamat végpontjai: jogosultság (F2, F3) és a teljes folyamat a
beteg kitöltésétől az orvosi megjelenítésig (M2)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.core.security import create_access_token
from app.models import RuleType, Severity
from app.services.questionnaires import assign_questionnaire, create_template
from app.services.rules import create_rule
from seed.questionnaires import WELLBEING_CODE, WELLBEING_NAME, WELLBEING_V1
from tests.factories import PASSWORD, assign, make_admin, make_doctor, make_patient


def auth(user):
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def pid(user) -> str:
    return str(user.patient_profile.id)


@pytest.fixture
def setup(db):
    doctor = make_doctor(db)
    patient = make_patient(db)
    foreign = make_patient(db, email="idegen@test.example", name="Idegen Beteg")
    assign(db, doctor, patient)
    template = create_template(
        db, code=WELLBEING_CODE, name=WELLBEING_NAME, created_by=doctor.id, spec=WELLBEING_V1
    )
    for p in (patient, foreign):
        assign_questionnaire(
            db,
            patient_id=p.patient_profile.id,
            template=template,
            assigned_by=doctor.id,
            start_date=(datetime.now(UTC) - timedelta(days=7)).date(),
        )
    create_rule(
        db,
        patient_id=patient.patient_profile.id,
        created_by=doctor.id,
        rule_type=RuleType.QUESTIONNAIRE,
        params={"questionnaire": WELLBEING_CODE, "bands": ["warning", "critical"]},
        severity=Severity.MODERATE,
    )
    return {"doctor": doctor, "patient": patient, "foreign": foreign, "admin": make_admin(db)}


def answers(client, user, patient, sleep, fatigue, dizziness):
    """A kérdőív kérdéseit a végpontról kéri le, ahogy a felület is."""
    [questionnaire] = client.get(
        f"/api/patients/{pid(patient)}/questionnaires", headers=auth(user)
    ).json()
    q1, q2, q3 = questionnaire["questions"]
    return {
        "questionnaire_code": WELLBEING_CODE,
        "answers": {q1["id"]: sleep, q2["id"]: fatigue, q3["id"]: dizziness},
    }


def test_patient_sees_assigned_questionnaire_without_scores(client, setup):
    patient = setup["patient"]
    response = client.get(f"/api/patients/{pid(patient)}/questionnaires", headers=auth(patient))
    assert response.status_code == 200
    [questionnaire] = response.json()
    assert questionnaire["code"] == WELLBEING_CODE
    assert questionnaire["version_no"] == 1
    assert [q["question_type"] for q in questionnaire["questions"]] == ["scale", "scale", "single"]
    # A pontozási tábla a betegnek nem megy ki, csak a válaszlehetőségek.
    options = questionnaire["questions"][2]["options"]
    assert options[0] == {"value": "never", "label": "Nem"}
    assert "score" not in str(questionnaire)


def test_patient_submits_and_gets_a_receipt_only(client, setup):
    patient = setup["patient"]
    body = answers(client, patient, patient, 4, 4, "rarely")
    response = client.post(
        f"/api/patients/{pid(patient)}/submissions", json=body, headers=auth(patient)
    )
    assert response.status_code == 201
    assert set(response.json()) == {"id", "questionnaire_code", "submitted_at"}


def test_patient_cannot_submit_for_another_patient(client, setup):
    body = answers(client, setup["foreign"], setup["foreign"], 3, 3, "never")
    response = client.post(
        f"/api/patients/{pid(setup['foreign'])}/submissions",
        json=body,
        headers=auth(setup["patient"]),
    )
    assert response.status_code == 403


@pytest.mark.parametrize("role", ["doctor", "admin"])
def test_only_patients_can_submit(client, setup, role):
    patient = setup["patient"]
    body = answers(client, patient, patient, 3, 3, "never")
    response = client.post(
        f"/api/patients/{pid(patient)}/submissions", json=body, headers=auth(setup[role])
    )
    assert response.status_code == 403


def test_invalid_answer_gives_422_with_reason_code(client, setup):
    patient = setup["patient"]
    body = answers(client, patient, patient, 9, 3, "never")
    response = client.post(
        f"/api/patients/{pid(patient)}/submissions", json=body, headers=auth(patient)
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_answer"


def test_submission_list_is_for_the_doctor_only(client, setup):
    url = f"/api/patients/{pid(setup['patient'])}/submissions"
    assert client.get(url, headers=auth(setup["patient"])).status_code == 403
    assert client.get(url, headers=auth(setup["admin"])).status_code == 403
    assert client.get(url, headers=auth(setup["doctor"])).status_code == 200


@pytest.mark.parametrize("path", ["questionnaires", "submissions"])
def test_doctor_cannot_read_foreign_patients_questionnaires(client, setup, path):
    url = f"/api/patients/{pid(setup['foreign'])}/{path}"
    assert client.get(url, headers=auth(setup["doctor"])).status_code == 403


def test_full_questionnaire_flow_from_patient_to_doctor(client, db, setup):
    """A beteg belép és kitölti a kérdőívet (alvás 4, fáradtság 4, szédülés
    „Ritkán" = 1 + 3 + 2 = 6 pont) → a kérdőívszabály kiértékeli (figyelmeztető
    sáv) → riasztás → az orvos a listán Figyelem státusszal, a kitöltés
    pontszámával és sávjával látja."""

    def login(email):
        response = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    patient_headers = login(setup["patient"].email)
    me = client.get("/api/auth/me", headers=patient_headers).json()
    [questionnaire] = client.get(
        f"/api/patients/{me['patient_id']}/questionnaires", headers=patient_headers
    ).json()
    q1, q2, q3 = questionnaire["questions"]
    created = client.post(
        f"/api/patients/{me['patient_id']}/submissions",
        json={
            "questionnaire_code": WELLBEING_CODE,
            "answers": {q1["id"]: "4", q2["id"]: "4", q3["id"]: "rarely"},
        },
        headers=patient_headers,
    )
    assert created.status_code == 201

    doctor_headers = login(setup["doctor"].email)
    [row] = client.get("/api/doctor/patients", headers=doctor_headers).json()
    assert row["status"] == "attention"
    trigger = row["reasons"][0]["trigger"]
    assert trigger["band"] == "warning"
    assert trigger["submission"]["total_score"] == 6
    assert trigger["submission"]["max_score"] == 13
    assert [a["score"] for a in trigger["submission"]["answers"]] == [1, 3, 2]

    [submission] = client.get(
        f"/api/patients/{me['patient_id']}/submissions", headers=doctor_headers
    ).json()
    assert submission["id"] == created.json()["id"]
    assert (submission["total_score"], submission["band"]) == (6, "warning")

    [alert] = client.get(f"/api/patients/{me['patient_id']}/alerts", headers=doctor_headers).json()
    assert alert["rule_version"]["rule_type"] == "questionnaire"
    assert alert["events"][0]["triggers"][0]["submission"]["id"] == created.json()["id"]


@pytest.mark.parametrize("role", ["patient", "admin"])
def test_others_cannot_list_a_patients_questionnaires(client, setup, role):
    url = f"/api/patients/{pid(setup['foreign'])}/questionnaires"
    assert client.get(url, headers=auth(setup[role])).status_code == 403


@pytest.mark.parametrize("path", ["questionnaires", "submissions"])
def test_questionnaire_endpoints_require_login(client, setup, path):
    url = f"/api/patients/{pid(setup['patient'])}/{path}"
    assert client.get(url).status_code == 401
