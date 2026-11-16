"""A NICE-kiértékelés végpontja (M3, K2): siker egyezéssel, szándékos eltérés,
a szolgáltatás kiesése (503, cql_unavailable) és a jogosultság (D8a: csak a
hozzárendelt orvos), az 503 okának naplózása, és hogy a HTTP-hívás alatt
nincs nyitott tranzakció. A CQL-szolgáltatást hamis kliens helyettesíti, az óra
rögzített (NOW), így a tesztek éjfél körül is ugyanazt az ablakot látják."""

import logging
import uuid
from datetime import UTC, datetime, time, timedelta

import pytest

from app.api.nice import get_clock, get_cql_evaluate
from app.core.config import settings
from app.core.security import create_access_token
from app.main import app
from app.models import Alert
from app.services.cql_client import CqlServiceError
from app.services.nice import NiceParams, own_result, series_period
from tests.factories import assign, make_admin, make_doctor, make_patient, record_bp
from tests.test_nice import NOW, EchoCql, cql_json


def auth(user):
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def url(patient) -> str:
    return f"/api/patients/{patient.patient_profile.id}/nice-evaluation"


@pytest.fixture(autouse=True)
def fixed_clock():
    """A végpont órája a rögzített NOW (2026. nov. 15. 12:00, Budapest)."""
    app.dependency_overrides[get_clock] = lambda: lambda: NOW
    yield
    app.dependency_overrides.pop(get_clock, None)


@pytest.fixture
def setup(db, measurement_types):
    doctor = make_doctor(db)
    patient = make_patient(db)
    link = assign(db, doctor, patient)
    # Négy nap az elmúlt (lezárt) hétből: az első kiesik, három marad.
    today = NOW.astimezone(settings.tz).date()
    for days_ago in (4, 3, 2, 1):
        noon = datetime.combine(today - timedelta(days=days_ago), time(12), settings.tz)
        record_bp(db, patient, 150, 95, noon)
    return {
        "doctor": doctor,
        "patient": patient,
        "link": link,
        "other_doctor": make_doctor(db, email="masik@test.example", name="Dr. Másik"),
        "admin": make_admin(db),
    }


@pytest.fixture
def cql(db, setup):
    """A hamis szolgáltatás a saját számítás eredményével (egyezés)."""
    profile = setup["patient"].patient_profile
    expected = own_result(db, profile, series_period(NOW), NiceParams())
    fake = EchoCql(cql_json(expected))
    app.dependency_overrides[get_cql_evaluate] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_cql_evaluate, None)


def test_doctor_gets_both_results_and_a_match(client, setup, cql):
    response = client.post(url(setup["patient"]), headers=auth(setup["doctor"]))
    assert response.status_code == 200
    body = response.json()
    assert body["matches"] is True and body["mismatched_fields"] == []
    assert body["patient_id"] == str(setup["patient"].patient_profile.id)
    assert body["cql"] == body["own"]
    own = body["own"]
    assert (own["mean_systolic"], own["mean_diastolic"]) == (150, 95)
    assert (own["included_day_count"], own["enough_data"], own["target_met"]) == (3, True, False)
    assert len(own["excluded_reading_ids"]) == 1 and len(own["included_reading_ids"]) == 3
    assert own["excluded_first_day"] is not None
    assert (own["target_systolic"], own["target_diastolic"]) == (135, 85)
    # Az időszak és a paraméterek a válaszban; a library és az engine továbbadva.
    assert body["period"]["start_closed"] is True and body["period"]["end_closed"] is False
    start = datetime.fromisoformat(body["period"]["start"])
    assert start.time() == time(0) and start.utcoffset() is not None
    assert body["period"]["start"] == "2026-11-08T00:00:00+01:00"
    assert body["period"]["end"] == "2026-11-15T00:00:00+01:00"
    assert body["evaluation_time"] == "2026-11-15T12:00:00+01:00"
    assert body["parameters"]["Min Included Days"] == 3
    assert body["parameters"]["Series Period"] == cql.payloads[0]["parameters"]["Series Period"]
    assert body["library"]["id"] == "PulseHbpmAverage"
    assert body["engine"]["cql-execution"] == "3.3.2"
    assert body["duration_ms"] == 12.5


def test_deliberate_difference_is_reported(client, setup, cql):
    cql.result = {**cql.result, "meanDiastolic": 94.0, "targetMet": True}
    body = client.post(url(setup["patient"]), headers=auth(setup["doctor"])).json()
    assert body["matches"] is False
    assert body["mismatched_fields"] == ["mean_diastolic", "target_met"]
    assert body["cql"]["mean_diastolic"] == 94 and body["own"]["mean_diastolic"] == 95


@pytest.mark.parametrize("reason", ["timeout", "unreachable", "http_500", "invalid_response"])
def test_service_failure_is_503_cql_unavailable(client, db, setup, reason):
    def failing(payload):
        raise CqlServiceError(reason)

    app.dependency_overrides[get_cql_evaluate] = lambda: failing
    try:
        response = client.post(url(setup["patient"]), headers=auth(setup["doctor"]))
    finally:
        app.dependency_overrides.pop(get_cql_evaluate, None)
    assert response.status_code == 503
    assert response.json()["detail"] == {"code": "cql_unavailable"}


def test_failure_reason_is_logged_without_patient_data(client, setup, caplog, monkeypatch):
    """Az 503 oka (reason) a naplóba kerül, de a beteg azonosítója, neve és a
    mérési értékek nem."""
    # A tesztek elején futó migráció (alembic/env.py, fileConfig) a már létező
    # naplózókat letiltja; élesben a migráció külön folyamat, ott ez nem érinti.
    monkeypatch.setattr(logging.getLogger("pulse.nice"), "disabled", False)

    def failing(payload):
        raise CqlServiceError("http_413", "payload_too_large")

    app.dependency_overrides[get_cql_evaluate] = lambda: failing
    try:
        with caplog.at_level(logging.WARNING, logger="pulse.nice"):
            response = client.post(url(setup["patient"]), headers=auth(setup["doctor"]))
    finally:
        app.dependency_overrides.pop(get_cql_evaluate, None)
    assert response.status_code == 503
    [record] = [r for r in caplog.records if r.name == "pulse.nice"]
    assert record.levelno == logging.WARNING
    text = record.getMessage()
    assert "http_413" in text
    profile = setup["patient"].patient_profile
    for secret in (str(profile.id), profile.name, "150", "95"):
        assert secret not in text


def test_no_open_transaction_during_the_service_call(client, db, setup, cql):
    """Az adatok beolvasása után a tranzakció lezárul, a lassú HTTP-hívás alatt
    nem tart nyitva adatbázis-kapcsolatot."""
    seen = []

    def checking(payload):
        seen.append(db.in_transaction())
        return cql(payload)

    app.dependency_overrides[get_cql_evaluate] = lambda: checking
    response = client.post(url(setup["patient"]), headers=auth(setup["doctor"]))
    assert response.status_code == 200 and response.json()["matches"] is True
    assert seen == [False]


def test_unparsable_service_answer_is_503(client, setup, cql):
    cql.result = {"meanSystolic": 150}
    response = client.post(url(setup["patient"]), headers=auth(setup["doctor"]))
    assert response.status_code == 503
    assert response.json()["detail"] == {"code": "cql_unavailable"}


def test_evaluation_opens_no_alert(client, db, setup, cql):
    before = db.query(Alert).count()
    assert client.post(url(setup["patient"]), headers=auth(setup["doctor"])).status_code == 200
    assert db.query(Alert).count() == before


@pytest.mark.parametrize("who", ["patient", "admin", "other_doctor"])
def test_only_the_assigned_doctor(client, setup, cql, who):
    response = client.post(url(setup["patient"]), headers=auth(setup[who]))
    assert response.status_code == 403
    assert cql.payloads == []  # a szolgáltatás meg sem hívódott


def test_ended_assignment_is_403(client, db, setup, cql):
    setup["link"].valid_to = datetime.now(UTC)
    db.flush()
    assert client.post(url(setup["patient"]), headers=auth(setup["doctor"])).status_code == 403


def test_unknown_patient_is_403(client, setup, cql):
    response = client.post(
        f"/api/patients/{uuid.uuid4()}/nice-evaluation", headers=auth(setup["doctor"])
    )
    assert response.status_code == 403


def test_requires_login(client, setup, cql):
    assert client.post(url(setup["patient"])).status_code == 401


def test_default_dependency_is_the_real_client():
    from app.services import cql_client

    assert get_cql_evaluate() is cql_client.evaluate


def test_default_clock_is_the_current_utc_time():
    now = get_clock()()
    assert now.tzinfo is UTC and abs(now - datetime.now(UTC)) < timedelta(seconds=5)
