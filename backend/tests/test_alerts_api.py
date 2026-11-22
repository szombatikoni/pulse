"""A riasztás-életút végpontjai (M3, A6): megtekintés, felelőshöz rendelés,
lezárás, a Riasztások oldal listája, a jogosultság, a Kezelve ok a beteglistán
és a betegoldali visszajelzés."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.core.security import create_access_token
from app.models import AlertEvent, Notification, Severity
from tests.factories import (
    assign,
    make_admin,
    make_doctor,
    make_patient,
    make_threshold_rule,
    record_bp,
)


def auth(user):
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


@pytest.fixture
def setup(db, measurement_types):
    """Orvos két saját betegével (mindkettőnek nyitott riasztása van), egy
    kolléga ugyanahhoz az első beteghez, egy idegen orvos, egy idegen beteg
    (saját riasztással) és egy admin."""
    since = datetime.now(UTC) - timedelta(days=30)
    doctor = make_doctor(db, name="Dr. Szabó")
    colleague = make_doctor(db, email="kollega@test.example", name="Dr. Kolléga")
    other_doctor = make_doctor(db, email="masik@test.example", name="Dr. Másik")
    patient = make_patient(db, name="Első Beteg")
    second = make_patient(db, email="masodik@test.example", name="Második Beteg")
    foreign = make_patient(db, email="idegen@test.example", name="Idegen Beteg")
    assign(db, doctor, patient, valid_from=since)
    assign(db, colleague, patient, valid_from=since)
    assign(db, doctor, second, valid_from=since)
    assign(db, other_doctor, foreign, valid_from=since)
    now = datetime.now(UTC)
    make_threshold_rule(db, patient, doctor)
    make_threshold_rule(db, second, doctor, severity=Severity.SEVERE)
    make_threshold_rule(db, foreign, other_doctor)
    _, [alert] = record_bp(db, patient, 150, 95, at=now - timedelta(hours=3))
    _, [severe] = record_bp(db, second, 160, 95, at=now - timedelta(hours=2))
    _, [foreign_alert] = record_bp(db, foreign, 150, 95, at=now - timedelta(hours=1))
    return {
        "doctor": doctor,
        "colleague": colleague,
        "other_doctor": other_doctor,
        "patient": patient,
        "second": second,
        "foreign": foreign,
        "admin": make_admin(db),
        "alert": alert,
        "severe": severe,
        "foreign_alert": foreign_alert,
    }


def post(client, setup, action, user="doctor", alert="alert", json=None):
    alert_id = setup[alert].id
    return client.post(f"/api/alerts/{alert_id}/{action}", json=json, headers=auth(setup[user]))


def event_count(db):
    return db.scalar(select(func.count()).select_from(AlertEvent))


CLOSE = {"reason": "Telefonon egyeztettem, gyógyszer módosítva."}


# --- Állapotgép ------------------------------------------------------------------------


def test_seen_is_idempotent(client, db, setup):
    first = post(client, setup, "seen")
    assert first.status_code == 200
    body = first.json()
    assert body["status"] == "seen"
    seen = body["events"][-1]
    assert (seen["event_type"], seen["actor"]["name"]) == ("seen", "Dr. Szabó")
    count = event_count(db)
    again = post(client, setup, "seen")
    assert (again.status_code, again.json()["status"]) == (200, "seen")
    assert event_count(db) == count  # nem írt újabb eseményt


def test_assign_defaults_to_self_and_allows_reassignment(client, db, setup):
    response = post(client, setup, "assign")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "assigned"  # a megtekintés kihagyható
    assert body["assigned_to"] == {"id": str(setup["doctor"].id), "name": "Dr. Szabó"}

    response = post(client, setup, "assign", json={"doctor_id": str(setup["colleague"].id)})
    body = response.json()
    assert body["assigned_to"]["name"] == "Dr. Kolléga"
    assigned = [e for e in body["events"] if e["event_type"] == "assigned"]
    assert [e["actor"]["name"] for e in assigned] == ["Dr. Szabó", "Dr. Szabó"]


def test_assign_events_keep_the_earlier_assignees(client, db, setup):
    """Újra-hozzárendelés után az események őrzik a korábbi felelősöket (az
    esemény assignee mezője), az aktuális felelős az assigned_to."""
    post(client, setup, "assign")
    post(client, setup, "assign", json={"doctor_id": str(setup["colleague"].id)})
    body = post(client, setup, "assign", user="colleague").json()
    assigned = [e for e in body["events"] if e["event_type"] == "assigned"]
    assert [e["assignee"]["name"] for e in assigned] == ["Dr. Szabó", "Dr. Kolléga", "Dr. Kolléga"]
    assert [e["actor"]["name"] for e in assigned] == ["Dr. Szabó", "Dr. Szabó", "Dr. Kolléga"]
    assert assigned[0]["assignee"]["id"] == str(setup["doctor"].id)
    assert body["assigned_to"]["name"] == "Dr. Kolléga"
    # A többi eseménynek nincs felelőse; a beteg riasztáslistája is kiadja.
    assert body["events"][0]["assignee"] is None
    pid = setup["patient"].patient_profile.id
    [alert] = client.get(f"/api/patients/{pid}/alerts", headers=auth(setup["doctor"])).json()
    assert [e["assignee"]["name"] for e in alert["events"] if e["assignee"]] == [
        "Dr. Szabó",
        "Dr. Kolléga",
        "Dr. Kolléga",
    ]


@pytest.mark.parametrize("who", ["other_doctor", "patient", "admin", "unknown"])
def test_assign_only_to_a_currently_assigned_doctor(client, db, setup, who):
    doctor_id = uuid.uuid4() if who == "unknown" else setup[who].id
    count = event_count(db)
    response = post(client, setup, "assign", json={"doctor_id": str(doctor_id)})
    assert response.status_code == 422
    assert response.json()["detail"] == {"code": "doctor_not_assigned"}
    assert event_count(db) == count


def test_assign_to_a_deactivated_but_assigned_doctor_is_422(client, db, setup):
    """A letiltott (is_active=False) orvos nem lehet felelős, akkor sem, ha az
    összerendelése a beteggel még érvényes."""
    setup["colleague"].is_active = False
    db.flush()
    count = event_count(db)
    response = post(client, setup, "assign", json={"doctor_id": str(setup["colleague"].id)})
    assert response.status_code == 422
    assert response.json()["detail"] == {"code": "doctor_not_assigned"}
    assert event_count(db) == count


def test_close_with_too_long_message_is_422(client, db, setup):
    """Érvényes indoklás mellett a betegüzenet felső határa is él (500 karakter)."""
    count = event_count(db)
    response = post(client, setup, "close", json={**CLOSE, "message": "x" * 501})
    assert response.status_code == 422
    assert event_count(db) == count
    assert db.scalar(select(func.count()).select_from(Notification)) == 0
    # A határon (500 karakter) még elfogadja.
    response = post(client, setup, "close", json={**CLOSE, "message": "x" * 500})
    assert response.status_code == 200


def test_close_requires_a_reason(client, db, setup):
    for body in ({}, {"reason": ""}, {"reason": "   "}, {"reason": "x" * 501}):
        assert post(client, setup, "close", json=body).status_code == 422
    assert post(client, setup, "close").status_code == 422  # törzs nélkül
    assert db.scalar(select(func.count()).select_from(Notification)) == 0


def test_close_from_new_with_reason(client, db, setup):
    response = post(client, setup, "close", json=CLOSE)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "closed"
    closed = body["events"][-1]
    assert closed["event_type"] == "closed"
    assert closed["reason"] == CLOSE["reason"]
    assert closed["actor"]["name"] == "Dr. Szabó"
    assert db.scalar(select(func.count()).select_from(Notification)) == 0  # üzenet nélkül


@pytest.mark.parametrize("action", ["seen", "assign", "close"])
def test_every_change_after_closing_is_409(client, db, setup, action):
    post(client, setup, "close", json=CLOSE)
    count = event_count(db)
    response = post(client, setup, action, json=CLOSE if action == "close" else None)
    assert response.status_code == 409
    assert response.json()["detail"] == {"code": "already_closed"}
    assert event_count(db) == count


def test_closed_alert_shows_reason_in_the_patient_alert_list(client, setup):
    post(client, setup, "close", json=CLOSE)
    pid = setup["patient"].patient_profile.id
    url = f"/api/patients/{pid}/alerts?include_closed=true"
    [alert] = client.get(url, headers=auth(setup["doctor"])).json()
    assert alert["events"][-1]["reason"] == CLOSE["reason"]


# --- Jogosultság -----------------------------------------------------------------------


@pytest.mark.parametrize("user", ["other_doctor", "patient", "admin"])
@pytest.mark.parametrize("action", ["seen", "assign", "close"])
def test_others_cannot_change_the_alert(client, db, setup, user, action):
    count = event_count(db)
    response = post(client, setup, action, user=user, json=CLOSE if action == "close" else None)
    assert response.status_code == 403
    assert event_count(db) == count


@pytest.mark.parametrize("action", ["seen", "assign", "close"])
def test_unknown_alert_gives_403_not_404(client, setup, action):
    response = client.post(
        f"/api/alerts/{uuid.uuid4()}/{action}",
        json=CLOSE if action == "close" else None,
        headers=auth(setup["doctor"]),
    )
    assert response.status_code == 403


def test_ended_assignment_closes_access_immediately(client, db, setup):
    from app.models import DoctorPatient

    link = db.scalar(
        select(DoctorPatient).where(
            DoctorPatient.doctor_id == setup["doctor"].doctor_profile.id,
            DoctorPatient.patient_id == setup["patient"].patient_profile.id,
        )
    )
    link.valid_to = datetime.now(UTC)
    db.flush()
    assert post(client, setup, "seen").status_code == 403
    ids = [a["id"] for a in client.get("/api/alerts", headers=auth(setup["doctor"])).json()]
    assert str(setup["alert"].id) not in ids
    # A kolléga hozzárendelése él: ő eléri.
    assert post(client, setup, "seen", user="colleague").status_code == 200


# --- A felelős-választó: a beteg orvosai -----------------------------------------------


def test_patient_doctors_lists_the_currently_assigned_doctors(client, setup):
    pid = setup["patient"].patient_profile.id
    response = client.get(f"/api/patients/{pid}/doctors", headers=auth(setup["doctor"]))
    assert response.status_code == 200
    assert response.json() == [
        {"id": str(setup["colleague"].id), "name": "Dr. Kolléga"},
        {"id": str(setup["doctor"].id), "name": "Dr. Szabó"},
    ]


def test_patient_doctors_follows_the_assignment_immediately(client, db, setup):
    from app.models import DoctorPatient

    pid = setup["patient"].patient_profile.id
    link = db.scalar(
        select(DoctorPatient).where(
            DoctorPatient.doctor_id == setup["colleague"].doctor_profile.id,
            DoctorPatient.patient_id == pid,
        )
    )
    link.valid_to = datetime.now(UTC)
    db.flush()
    response = client.get(f"/api/patients/{pid}/doctors", headers=auth(setup["doctor"]))
    assert [d["name"] for d in response.json()] == ["Dr. Szabó"]
    # Az összerendelés létrejötte azonnal megjelenik (és a választhatóság is).
    assign(db, setup["other_doctor"], setup["patient"])
    response = client.get(f"/api/patients/{pid}/doctors", headers=auth(setup["doctor"]))
    assert [d["name"] for d in response.json()] == ["Dr. Másik", "Dr. Szabó"]


@pytest.mark.parametrize("user", ["other_doctor", "patient", "admin"])
def test_patient_doctors_only_for_the_assigned_doctor(client, setup, user):
    pid = setup["patient"].patient_profile.id
    response = client.get(f"/api/patients/{pid}/doctors", headers=auth(setup[user]))
    assert response.status_code == 403
    unknown = client.get(f"/api/patients/{uuid.uuid4()}/doctors", headers=auth(setup["doctor"]))
    assert unknown.status_code == 403


@pytest.mark.parametrize("user", ["patient", "admin"])
def test_alert_list_is_for_doctors_only(client, setup, user):
    assert client.get("/api/alerts", headers=auth(setup[user])).status_code == 403


# --- Riasztások oldal ------------------------------------------------------------------


def test_alert_list_has_only_own_patients_open_alerts_sorted(client, setup):
    response = client.get("/api/alerts", headers=auth(setup["doctor"]))
    assert response.status_code == 200
    rows = response.json()
    # Elöl a súlyos (Második Beteg), az idegen beteg riasztása nincs benne.
    assert [(r["patient"]["name"], r["severity"]) for r in rows] == [
        ("Második Beteg", "severe"),
        ("Első Beteg", "moderate"),
    ]
    row = rows[1]
    assert row["patient"]["id"] == str(setup["patient"].patient_profile.id)
    assert row["status"] == "new"
    assert row["assigned_to"] is None
    # A kártyacímhez: szabályverzió és a legutóbbi kiváltó adat a határsértéssel.
    assert row["rule_version"]["rule_type"] == "threshold"
    assert row["rule_version"]["params"]["measurement_type"] == "blood_pressure"
    assert [v["bound"] for v in row["trigger"]["violations"]] == ["max", "max"]
    assert row["trigger"]["measurement"]["values"]

    other = client.get("/api/alerts", headers=auth(setup["other_doctor"])).json()
    assert [r["patient"]["name"] for r in other] == ["Idegen Beteg"]


def test_alert_list_filters_by_status_and_drops_closed(client, setup):
    post(client, setup, "assign")
    post(client, setup, "close", alert="severe", json=CLOSE)

    def names(query=""):
        rows = client.get(f"/api/alerts{query}", headers=auth(setup["doctor"])).json()
        return [(r["patient"]["name"], r["status"]) for r in rows]

    assert names() == [("Első Beteg", "assigned")]
    assert names("?status=assigned") == [("Első Beteg", "assigned")]
    assert names("?status=new") == []
    assert names("?status=seen") == []
    response = client.get("/api/alerts?status=closed", headers=auth(setup["doctor"]))
    assert response.status_code == 422
    [row] = client.get("/api/alerts", headers=auth(setup["doctor"])).json()
    assert row["assigned_to"]["name"] == "Dr. Szabó"


# --- Kezelve a beteglistán és az adatlap fejlécén --------------------------------------


def test_closed_alert_gives_handled_with_the_closing_doctor(client, setup):
    post(client, setup, "close", json=CLOSE)
    rows = client.get("/api/doctor/patients", headers=auth(setup["doctor"])).json()
    row = next(r for r in rows if r["name"] == "Első Beteg")
    assert row["status"] == "handled"
    [reason] = row["reasons"]
    assert reason["code"] == "closed_awaiting_data"
    assert reason["alert_id"] == str(setup["alert"].id)
    assert reason["actor"]["name"] == "Dr. Szabó"
    assert reason["trigger"]["violations"]  # mit zárt le az orvos

    pid = setup["patient"].patient_profile.id
    detail = client.get(f"/api/patients/{pid}", headers=auth(setup["doctor"])).json()
    assert detail["status"] == "handled"
    assert detail["reasons"][0]["actor"]["name"] == "Dr. Szabó"


def test_confirming_measurement_after_closing_gives_ok(client, db, setup):
    post(client, setup, "close", json=CLOSE)
    record_bp(db, setup["patient"], 125, 80, at=datetime.now(UTC))
    pid = setup["patient"].patient_profile.id
    detail = client.get(f"/api/patients/{pid}", headers=auth(setup["doctor"])).json()
    assert detail["status"] == "ok"
    assert [r["code"] for r in detail["reasons"]] == ["fresh_data"]


# --- Betegoldali visszajelzés ----------------------------------------------------------


def notices(client, setup, user="patient", patient="patient"):
    pid = setup[patient].patient_profile.id
    return client.get(f"/api/patients/{pid}/plan-notices", headers=auth(setup[user]))


def test_feedback_message_reaches_only_its_patient(client, db, setup):
    message = "Kérem, a jövő héten mérjen naponta kétszer."
    post(client, setup, "close", json={**CLOSE, "message": f"  {message}  "})
    [notification] = db.scalars(select(Notification)).all()
    assert notification.text == message

    response = notices(client, setup)
    assert response.status_code == 200
    [notice] = response.json()
    assert notice["kind"] == "alert_feedback"
    assert notice["text"] == message
    assert notice["doctor_name"] == "Dr. Szabó"
    assert notice["alert_id"] == str(setup["alert"].id)
    assert (notice["rule_type"], notice["target_code"]) == ("threshold", "blood_pressure")
    assert notice["changed_at"]

    # A hozzárendelt orvos is látja (mint a teendőket); a másik beteg nem kapja meg.
    assert len(notices(client, setup, user="doctor").json()) == 1
    assert notices(client, setup, user="second", patient="second").json() == []
    # Idegen beteg és idegen orvos nem kérheti le.
    assert notices(client, setup, user="foreign").status_code == 403
    assert notices(client, setup, user="other_doctor").status_code == 403


def test_blank_message_creates_no_notification(client, db, setup):
    post(client, setup, "close", json={**CLOSE, "message": "   "})
    assert db.scalar(select(func.count()).select_from(Notification)) == 0
    assert notices(client, setup).json() == []


def test_feedback_older_than_7_days_is_not_listed(client, db, setup):
    post(client, setup, "close", json={**CLOSE, "message": "Régi üzenet."})
    notification = db.scalars(select(Notification)).one()
    notification.created_at = datetime.now(UTC) - timedelta(days=8)
    db.flush()
    assert notices(client, setup).json() == []
