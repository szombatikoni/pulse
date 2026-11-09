"""Szabály-API (M3, A4 2. lépés): jogosultság, létrehozás és módosítás mint új
verzió, a hibakódok, valamint az időablakos és az elmaradt adat riasztás
magyarázata a végpontokon át."""

import uuid
from datetime import UTC, datetime, time, timedelta

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.core.security import create_access_token
from app.models import AlertEventType, Frequency, QuestionnaireTemplate, Rule, RuleVersion
from app.services.measurements import get_type_by_code
from app.services.occurrences import run_occurrence_check
from app.services.questionnaires import assign_questionnaire, create_template
from app.services.tasks import assign_measurement
from seed.questionnaires import WELLBEING_CODE, WELLBEING_NAME, WELLBEING_V1
from tests.factories import assign, make_admin, make_doctor, make_patient, record_bp


def auth(user):
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


@pytest.fixture
def setup(db, measurement_types):
    """Orvos a saját betegével, egy idegen orvos, egy admin és a „Közérzet"."""
    doctor = make_doctor(db)
    patient = make_patient(db)
    link = assign(db, doctor, patient, valid_from=datetime.now(UTC) - timedelta(days=30))
    create_template(
        db, code=WELLBEING_CODE, name=WELLBEING_NAME, created_by=doctor.id, spec=WELLBEING_V1
    )
    return {
        "doctor": doctor,
        "patient": patient,
        "other_doctor": make_doctor(db, email="masik@test.example", name="Dr. Másik"),
        "admin": make_admin(db),
        "pid": patient.patient_profile.id,
        "link": link,
    }


WINDOW = {
    "rule_type": "window",
    "severity": "moderate",
    "params": {
        "measurement_type": "blood_pressure",
        "limits": {"systolic": {"max": 140}, "diastolic": {"max": 90}},
        "count": 3,
        "window_days": 7,
    },
}
MISSING = {
    "rule_type": "missing_data",
    "severity": "moderate",
    "params": {"measurement_type": "blood_pressure", "consecutive_missed": 2},
}


def rules_url(setup):
    return f"/api/patients/{setup['pid']}/rules"


def create(client, setup, body=WINDOW, user="doctor"):
    return client.post(rules_url(setup), json=body, headers=auth(setup[user]))


# --- Jogosultság -----------------------------------------------------------------------


def test_doctor_lists_rules_of_assigned_patient(client, setup):
    response = client.get(rules_url(setup), headers=auth(setup["doctor"]))
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize("user", ["other_doctor", "patient", "admin"])
def test_others_cannot_list_or_create_rules(client, db, setup, user):
    assert client.get(rules_url(setup), headers=auth(setup[user])).status_code == 403
    assert create(client, setup, user=user).status_code == 403
    assert db.scalar(select(func.count()).select_from(Rule)) == 0


@pytest.mark.parametrize("user", ["other_doctor", "patient", "admin"])
def test_others_cannot_add_a_version(client, setup, user):
    rule_id = create(client, setup).json()["id"]
    response = client.post(
        f"/api/rules/{rule_id}/versions",
        json={"params": WINDOW["params"], "severity": "severe"},
        headers=auth(setup[user]),
    )
    assert response.status_code == 403


def test_unknown_rule_gives_403_not_404(client, setup):
    response = client.post(
        f"/api/rules/{uuid.uuid4()}/versions",
        json={"params": WINDOW["params"], "severity": "severe"},
        headers=auth(setup["doctor"]),
    )
    assert response.status_code == 403


def test_ended_assignment_closes_rule_access(client, db, setup):
    # Az összerendelés megszűnésével a szabályokhoz való hozzáférés is azonnal megszűnik.
    rule_id = create(client, setup).json()["id"]
    setup["link"].valid_to = datetime.now(UTC)
    db.flush()
    assert client.get(rules_url(setup), headers=auth(setup["doctor"])).status_code == 403
    response = client.post(
        f"/api/rules/{rule_id}/versions",
        json={"params": WINDOW["params"], "severity": "severe"},
        headers=auth(setup["doctor"]),
    )
    assert response.status_code == 403


# --- Létrehozás és módosítás -----------------------------------------------------------


def test_create_then_modify_gives_version_list(client, setup):
    created = create(client, setup)
    assert created.status_code == 201
    rule = created.json()
    assert rule["rule_type"] == "window"
    assert rule["is_active"] is True
    assert rule["open_alerts"] == 0
    assert rule["current"]["version_no"] == 1
    assert rule["current"]["params"] == WINDOW["params"]
    assert rule["current"]["created_by"] == "Dr. Teszt"
    assert [v["version_no"] for v in rule["versions"]] == [1]

    stricter = {**WINDOW["params"], "limits": {"systolic": {"max": 135}}}
    response = client.post(
        f"/api/rules/{rule['id']}/versions",
        json={"params": stricter, "severity": "severe"},
        headers=auth(setup["doctor"]),
    )
    assert response.status_code == 201
    modified = response.json()
    assert modified["id"] == rule["id"]
    assert [v["version_no"] for v in modified["versions"]] == [1, 2]
    assert modified["current"]["severity"] == "severe"
    assert modified["current"]["params"]["limits"] == {"systolic": {"max": 135}}
    # A régi verzió változatlan (immutabilis).
    assert modified["versions"][0]["params"] == WINDOW["params"]

    listed = client.get(rules_url(setup), headers=auth(setup["doctor"])).json()
    assert [r["current"]["version_no"] for r in listed] == [2]


def test_same_rule_type_may_be_sent_with_the_version(client, setup):
    rule_id = create(client, setup).json()["id"]
    response = client.post(
        f"/api/rules/{rule_id}/versions",
        json={**WINDOW, "severity": "severe"},
        headers=auth(setup["doctor"]),
    )
    assert response.status_code == 201


def test_rule_type_change_is_rejected(client, db, setup):
    rule_id = create(client, setup).json()["id"]
    response = client.post(
        f"/api/rules/{rule_id}/versions",
        json={**MISSING},
        headers=auth(setup["doctor"]),
    )
    assert response.status_code == 422
    assert response.json()["detail"] == {"code": "rule_type_locked"}
    assert db.scalar(select(func.count()).select_from(RuleVersion)) == 1


def test_open_alert_count_and_rule_changed_event(client, db, setup):
    rule_id = create(client, setup).json()["id"]
    now = datetime.now(UTC)
    for days in (2, 1, 0):
        record_bp(db, setup["patient"], 150, 95, at=now - timedelta(days=days, minutes=5))
    [rule] = client.get(rules_url(setup), headers=auth(setup["doctor"])).json()
    assert rule["open_alerts"] == 1

    client.post(
        f"/api/rules/{rule_id}/versions",
        json={"params": WINDOW["params"], "severity": "severe"},
        headers=auth(setup["doctor"]),
    )
    [alert] = client.get(
        f"/api/patients/{setup['pid']}/alerts", headers=auth(setup["doctor"])
    ).json()
    assert [e["event_type"] for e in alert["events"]] == [
        AlertEventType.CREATED,
        AlertEventType.RULE_CHANGED,
    ]


# --- Hibakódok -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("body", "code"),
    [
        (
            {
                "rule_type": "missing_data",
                "severity": "moderate",
                "params": {"measurement_type": "blood_presure", "consecutive_missed": 2},
            },
            "unknown_measurement_type",
        ),
        # Küszöb- és időablakos szabálynál is: elgépelt méréstípus vagy komponens
        # mellett a szabály csendben sosem riasztana.
        (
            {
                "rule_type": "threshold",
                "severity": "severe",
                "params": {"measurement_type": "blood_presure", "limits": {"systolic": {"max": 1}}},
            },
            "unknown_measurement_type",
        ),
        (
            {
                "rule_type": "window",
                "severity": "moderate",
                "params": {
                    "measurement_type": "blood_pressure",
                    "limits": {"sytolic": {"max": 140}},
                    "count": 3,
                    "window_days": 7,
                },
            },
            "unknown_component",
        ),
        (
            {
                "rule_type": "questionnaire",
                "severity": "moderate",
                "params": {"questionnaire": "nincs_ilyen", "bands": ["warning"]},
            },
            "unknown_questionnaire",
        ),
        (
            {
                "rule_type": "questionnaire",
                "severity": "moderate",
                "params": {"questionnaire": WELLBEING_CODE, "bands": ["warnin"]},
            },
            "unknown_band",
        ),
    ],
)
def test_service_errors_map_to_codes(client, db, setup, body, code):
    response = create(client, setup, body=body)
    assert response.status_code == 422
    assert response.json()["detail"] == {"code": code}
    # A mentési pont miatt a félig létrehozott szabály sem marad meg.
    assert db.scalar(select(func.count()).select_from(Rule)) == 0


@pytest.mark.parametrize(
    ("params", "fields"),
    [
        # Pontosan egy feltétel kell (sáv VAGY trend): modell-szintű hiba.
        (
            {"questionnaire": WELLBEING_CODE, "bands": ["warning"], "trend_count": 3},
            ["params"],
        ),
        ({"measurement_type": "blood_pressure", "limits": {"systolic": {}}}, None),
    ],
)
def test_invalid_params_give_invalid_params(client, setup, params, fields):
    rule_type = "questionnaire" if "questionnaire" in params else "threshold"
    response = create(
        client, setup, body={"rule_type": rule_type, "severity": "moderate", "params": params}
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "invalid_params"
    if fields is not None:
        assert detail["fields"] == fields
    else:
        assert detail["fields"] == ["limits.systolic"]


def test_invalid_window_count_in_new_version(client, setup):
    rule_id = create(client, setup).json()["id"]
    response = client.post(
        f"/api/rules/{rule_id}/versions",
        json={"params": {**WINDOW["params"], "count": 1}, "severity": "moderate"},
        headers=auth(setup["doctor"]),
    )
    assert response.status_code == 422
    assert response.json()["detail"] == {"code": "invalid_params", "fields": ["count"]}


def test_unknown_rule_type_is_a_schema_error(client, setup):
    response = create(client, setup, body={**WINDOW, "rule_type": "magic"})
    assert response.status_code == 422


# --- Magyarázat: időablakos és elmaradt adat riasztás ---------------------------------


def test_window_alert_triggers_resolve_with_violations(client, db, setup):
    create(client, setup)
    now = datetime.now(UTC)
    for days, sys in ((3, 146), (1, 144), (0, 152)):
        record_bp(db, setup["patient"], sys, 85, at=now - timedelta(days=days, minutes=5))
    [alert] = client.get(
        f"/api/patients/{setup['pid']}/alerts", headers=auth(setup["doctor"])
    ).json()
    triggers = alert["events"][0]["triggers"]
    assert [t["violations"][0]["value"] for t in triggers] == [146, 144, 152]
    for trigger in triggers:
        assert [(v["component"], v["bound"], v["limit"]) for v in trigger["violations"]] == [
            ("systolic", "max", 140)
        ]

    [row] = client.get("/api/doctor/patients", headers=auth(setup["doctor"])).json()
    reason = row["reasons"][0]
    assert reason["code"] == "open_alert"
    assert reason["trigger"]["violations"][0]["value"] == 152


def test_missing_data_alert_triggers_resolve_as_occurrences(client, db, setup):
    create(client, setup, body=MISSING)
    today = datetime.now(settings.tz).date()
    assign_measurement(
        db,
        patient_id=setup["pid"],
        measurement_type=get_type_by_code(db, "blood_pressure"),
        assigned_by=setup["doctor"].id,
        start_date=today - timedelta(days=6),
        due_time=time(10, 0),
    )
    run_occurrence_check(db)  # a pótlási ablakon túli napok elmulasztva

    [alert] = client.get(
        f"/api/patients/{setup['pid']}/alerts", headers=auth(setup["doctor"])
    ).json()
    triggers = alert["events"][0]["triggers"]
    assert len(triggers) == 2
    for trigger in triggers:
        assert trigger["measurement"] is None
        occurrence = trigger["occurrence"]
        assert occurrence["status"] == "missed"
        assert (occurrence["target_kind"], occurrence["code"]) == (
            "measurement",
            "blood_pressure",
        )
        assert occurrence["name"]
    due = [t["occurrence"]["due_at"] for t in triggers]
    assert due == sorted(due)

    [row] = client.get("/api/doctor/patients", headers=auth(setup["doctor"])).json()
    assert row["status"] == "attention"
    codes = [r["code"] for r in row["reasons"]]
    assert codes == ["open_alert", "missed_occurrence", "no_data_yet"]
    # Az „Ok" oszlop adata: a riasztásnál a legutóbbi elmulasztott alkalom, az
    # Adathiány okánál az előírás legutóbbi lezárt (elmulasztott) alkalma.
    alert_reason, missed_reason, _ = row["reasons"]
    assert alert_reason["trigger"]["occurrence"]["id"] == triggers[-1]["occurrence"]["id"]
    assert missed_reason["trigger"]["occurrence"]["id"] == triggers[-1]["occurrence"]["id"]
    assert missed_reason["alert_id"] is None


def test_missed_questionnaire_occurrence_is_the_no_data_reason(client, db, setup):
    # Elmaradt adat szabály nélkül nincs riasztás, de az elmulasztott heti
    # kérdőív-alkalom Adathiány, az okánál a kérdőív nevével és határidejével.
    template = db.scalar(
        select(QuestionnaireTemplate).where(QuestionnaireTemplate.code == WELLBEING_CODE)
    )
    assign_questionnaire(
        db,
        patient_id=setup["pid"],
        template=template,
        assigned_by=setup["doctor"].id,
        start_date=datetime.now(settings.tz).date() - timedelta(days=8),
        frequency=Frequency.WEEKLY,
        due_time=time(20, 0),
    )
    run_occurrence_check(db)
    [row] = client.get("/api/doctor/patients", headers=auth(setup["doctor"])).json()
    assert row["status"] == "no_data"
    missed = row["reasons"][0]
    assert missed["code"] == "missed_occurrence"
    occurrence = missed["trigger"]["occurrence"]
    assert (occurrence["target_kind"], occurrence["code"], occurrence["name"]) == (
        "questionnaire",
        WELLBEING_CODE,
        WELLBEING_NAME,
    )
    assert occurrence["due_at"] == missed["at"]
