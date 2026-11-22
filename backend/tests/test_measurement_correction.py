"""Mérésjavítás újrakiértékeléssel (M3, A7; 07_mukodesi_szabalyok.md 3. rész;
a hallgató döntései D1–D6, mind az (a) változat).

A javítás új mérés-sor corrected_from-mal; az eredeti megmarad. A felülírt
mérés a közös not_superseded() feltétellel kimarad a kiértékelésből, a
státuszból és a FHIR-kiadásból; az érintett riasztás „kiváltó adat javítva"
eseményt kap, nyitottnál needs_review jelöléssel, automatikus lezárás nélkül."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.security import create_access_token
from app.models import (
    AlertEvent,
    AlertEventType,
    AlertStatus,
    AssignmentOccurrence,
    Measurement,
    RuleType,
    Severity,
)
from app.services.alerts import close_alert, explain_event, latest_trigger
from app.services.fhir import patient_bundle
from app.services.measurements import (
    MeasurementError,
    correct_measurement,
    get_type_by_code,
    list_measurements,
)
from app.services.rules import WindowParams, add_rule_version, create_rule, window_violations
from app.services.status import PatientStatus, compute_status, last_data_at
from app.services.tasks import assign_measurement
from tests.factories import (
    assign,
    make_admin,
    make_doctor,
    make_patient,
    make_threshold_rule,
    record_bp,
)


def local(y, m, d, hh=8, mm=0):
    """Időpont a rendszer időzónájában (Europe/Budapest)."""
    return datetime(y, m, d, hh, mm, tzinfo=settings.tz)


SINCE = local(2026, 8, 1, 0)


@pytest.fixture
def doctor(db):
    return make_doctor(db, name="Dr. Szabó")


@pytest.fixture
def patient(db, measurement_types, doctor):
    patient = make_patient(db)
    assign(db, doctor, patient, valid_from=SINCE)
    return patient


def window_params(limit=140, count=3, days=7):
    return {
        "measurement_type": "blood_pressure",
        "limits": {"systolic": {"max": limit}},
        "count": count,
        "window_days": days,
    }


def window_rule(db, patient, doctor, limit=140, severity=Severity.MODERATE):
    return create_rule(
        db,
        patient_id=patient.patient_profile.id,
        created_by=doctor.id,
        rule_type=RuleType.WINDOW,
        params=window_params(limit),
        severity=severity,
    )


def correct(db, patient, measurement, systolic, diastolic, now):
    return correct_measurement(
        db,
        patient_id=patient.patient_profile.id,
        measurement_id=measurement.id,
        values={"systolic": systolic, "diastolic": diastolic},
        actor_id=patient.id,
        now=now,
    )


def events(db, alert):
    query = select(AlertEvent).where(AlertEvent.alert_id == alert.id)
    return list(db.scalars(query.order_by(AlertEvent.created_at, AlertEvent.id)))


def types(db, alert):
    return [e.event_type for e in events(db, alert)]


def ids(*measurements):
    return [str(m.id) for m in measurements]


# --- A 07-es dokumentum dátumozott példája (3. rész) -------------------------------------


def test_dated_example_of_section_3(db, patient, doctor):
    """Szept. 16.: harmadik 140 feletti mérés → riasztás (v2); 19.: szigorítás v3
    (> 135, súlyos) → szabály módosult; 20.: m4 = 138/88 → ismételt aktiválódás,
    közepes → súlyos; 21.: m3 javítása (151 → 131) → kiváltó adat javítva, a
    feltétel már nem teljesül, needs_review, nincs automatikus lezárás; az orvos
    lezárja → a beteg Kezelve.

    Az m1 (szept. 12.) az m4 7 napos ablakán (szept. 13–20.) kívül esik, ezért az
    m4 kiváltói m2, m3, m4 (mint a dokumentumban)."""
    # A v1 csak azért kell, hogy a riasztást a dokumentum szerint a v2 nyissa.
    rule = window_rule(db, patient, doctor, limit=150)
    v2 = add_rule_version(
        db,
        rule,
        created_by=doctor.id,
        rule_type=RuleType.WINDOW,
        params=window_params(140),
        severity=Severity.MODERATE,
    )
    m1, _ = record_bp(db, patient, 145, 88, local(2026, 9, 12))
    m2, _ = record_bp(db, patient, 148, 92, local(2026, 9, 14))
    m3, [alert] = record_bp(db, patient, 151, 90, local(2026, 9, 16))
    created = events(db, alert)[0]
    assert created.event_type is AlertEventType.CREATED
    assert created.rule_version_id == v2.id
    assert created.trigger_data_ids == ids(m1, m2, m3)
    assert alert.severity is Severity.MODERATE

    v3 = add_rule_version(
        db,
        rule,
        created_by=doctor.id,
        rule_type=RuleType.WINDOW,
        params=window_params(135),
        severity=Severity.SEVERE,
        now=local(2026, 9, 19),
    )
    m4, [same] = record_bp(db, patient, 138, 88, local(2026, 9, 20))
    assert same.id == alert.id
    assert alert.severity is Severity.SEVERE
    retriggered = events(db, alert)[-1]
    assert retriggered.event_type is AlertEventType.RE_TRIGGERED
    assert retriggered.rule_version_id == v3.id
    assert retriggered.trigger_data_ids == ids(m2, m3, m4)

    m3_fixed, evaluated = correct(db, patient, m3, 131, 82, local(2026, 9, 21))
    assert evaluated == []  # a 131 a v3 szerint sem határsértő
    assert m3_fixed.corrected_from == m3.id
    assert m3_fixed.measured_at == m3.measured_at  # D1: a mérés ideje marad
    assert db.get(Measurement, m3.id) is not None  # az eredeti megmarad
    assert types(db, alert) == [
        AlertEventType.CREATED,
        AlertEventType.RULE_CHANGED,
        AlertEventType.RE_TRIGGERED,
        AlertEventType.TRIGGER_CORRECTED,
    ]
    fixed = events(db, alert)[-1]
    assert fixed.trigger_data_ids == ids(m3, m3_fixed)
    assert fixed.rule_version_id == v3.id
    assert fixed.condition_met is False  # m2, m3′, m4: 2 sértő < 3
    assert fixed.actor_id == patient.id
    # Nincs automatikus lezárás; a jelölés nem állapot.
    assert alert.needs_review is True
    assert alert.status is AlertStatus.NEW
    assert alert.severity is Severity.SEVERE
    # A régi események továbbra is az eredetire hivatkoznak, a magyarázat sem változik.
    assert str(m3.id) in created.trigger_data_ids
    explained = explain_event(db, fixed)
    assert [t.measurement.id for t in explained.triggers] == [m3.id, m3_fixed.id]
    # A legutóbbi kiváltó adat (beteglista „Ok") a kiértékelésből jön, nem a javításból.
    assert latest_trigger(db, alert).measurement.id == m4.id
    status = compute_status(db, patient.patient_profile.id, local(2026, 9, 21, 9))
    assert status.status is PatientStatus.SEVERE

    close_alert(db, alert, doctor, "A beteg javította a mérést.", now=local(2026, 9, 21, 10))
    status = compute_status(db, patient.patient_profile.id, local(2026, 9, 21, 11))
    assert status.status is PatientStatus.HANDLED
    assert [r.code for r in status.reasons] == ["closed_awaiting_data"]


# --- A felülírt mérés kizárása ------------------------------------------------------------


def test_window_evaluation_skips_the_superseded_measurement(db, patient, doctor):
    window_rule(db, patient, doctor)
    m1, _ = record_bp(db, patient, 150, 85, local(2026, 9, 1))
    m2, _ = record_bp(db, patient, 152, 85, local(2026, 9, 2))
    m2_fixed, _ = correct(db, patient, m2, 125, 80, local(2026, 9, 3))
    # A harmadik sértő mérés nem nyit riasztást: a felülírt m2 nem számít.
    m3, alerts = record_bp(db, patient, 155, 85, local(2026, 9, 3, 9))
    assert alerts == []
    params = WindowParams.model_validate(window_params())
    assert [m.id for m in window_violations(db, params, m3)] == [m1.id, m3.id]


def test_freshness_counts_only_the_end_of_the_chain(db, patient):
    """A javítás a mérési időt megtartja (D1), ezért a hatás csak közvetlenül
    beszúrt sorral mutatható meg: a közös feltétel a frissességben is él."""
    early, _ = record_bp(db, patient, 120, 80, local(2026, 9, 1))
    late, _ = record_bp(db, patient, 121, 80, local(2026, 9, 5))
    assert last_data_at(db, patient.patient_profile.id) == local(2026, 9, 5)
    db.add(
        Measurement(
            patient_id=late.patient_id,
            type_id=late.type_id,
            measured_at=local(2026, 9, 2),
            recorded_at=local(2026, 9, 6),
            corrected_from=late.id,
        )
    )
    db.flush()
    assert last_data_at(db, patient.patient_profile.id) == local(2026, 9, 2)
    assert early.corrected_from is None


def test_handled_confirmation_ignores_the_superseded_value(db, patient, doctor):
    """Kezelve: a lezárás utáni rendben lévő mérés megerősít; ha a beteg ezt
    határsértőre javítja (de riasztás nem nyílik), a megerősítés elvész."""
    window_rule(db, patient, doctor)
    for day in (1, 2):
        record_bp(db, patient, 150, 85, local(2026, 9, day))
    _, [alert] = record_bp(db, patient, 150, 85, local(2026, 9, 3))
    close_alert(db, alert, doctor, "Egyeztetve.", now=local(2026, 9, 3, 10))
    pid = patient.patient_profile.id

    ok, _ = record_bp(db, patient, 120, 80, local(2026, 9, 12))
    assert compute_status(db, pid, local(2026, 9, 12, 9)).status is PatientStatus.OK

    _, evaluated = correct(db, patient, ok, 150, 85, local(2026, 9, 13))
    assert evaluated == []  # egyetlen sértő mérés az ablakban: nincs riasztás
    assert compute_status(db, pid, local(2026, 9, 13, 9)).status is PatientStatus.HANDLED


def test_fhir_bundle_leaves_out_the_superseded_original(db, patient):
    original, _ = record_bp(db, patient, 148, 92, local(2026, 9, 1))
    other, _ = record_bp(db, patient, 120, 80, local(2026, 9, 2))
    fixed, _ = correct(db, patient, original, 131, 82, local(2026, 9, 3))
    bundle = patient_bundle(db, patient.patient_profile.id, now=local(2026, 9, 3, 9))
    observations = [
        e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == "Observation"
    ]
    assert [o["id"] for o in observations] == [str(fixed.id), str(other.id)]
    assert all(o["status"] == "final" for o in observations)
    values = [c["valueQuantity"]["value"] for c in observations[0]["component"]]
    assert values == [131, 82]


def test_history_keeps_the_original_marked(db, patient):
    original, _ = record_bp(db, patient, 148, 92, local(2026, 9, 1))
    fixed, _ = correct(db, patient, original, 131, 82, local(2026, 9, 3))
    listed = list_measurements(db, patient.patient_profile.id)
    # Azonos mérési idő: a későbbi rögzítés (a javítás) áll elöl.
    assert [m.id for m in listed] == [fixed.id, original.id]
    assert listed[1].correction.id == fixed.id
    assert listed[0].correction is None


# --- Lánc (D2) ------------------------------------------------------------------------


def test_chain_only_the_end_can_be_corrected_and_only_it_counts(db, patient, doctor):
    window_rule(db, patient, doctor)
    m1, _ = record_bp(db, patient, 150, 85, local(2026, 9, 1))
    m2, _ = record_bp(db, patient, 150, 85, local(2026, 9, 2))
    m3, [alert] = record_bp(db, patient, 151, 90, local(2026, 9, 3))

    m3b, _ = correct(db, patient, m3, 131, 82, local(2026, 9, 4))
    with pytest.raises(MeasurementError) as excinfo:
        correct(db, patient, m3, 133, 82, local(2026, 9, 4, 9))
    assert excinfo.value.code == "already_corrected"

    m3c, evaluated = correct(db, patient, m3b, 149, 88, local(2026, 9, 5))
    assert m3c.corrected_from == m3b.id
    with pytest.raises(MeasurementError) as excinfo:
        correct(db, patient, m3b, 133, 82, local(2026, 9, 5, 9))
    assert excinfo.value.code == "already_corrected"

    # Az m3′ javítása ugyanahhoz a riasztáshoz kapcsolódik (az előző javítás-esemény
    # kiváltója az m3′), és az m3″ újra határsértő: a feltétel ismét teljesül, és
    # ismételt aktiválódás is jön (m1, m2, m3″).
    assert [a.id for a in evaluated] == [alert.id]
    corrected = [e for e in events(db, alert) if e.event_type is AlertEventType.TRIGGER_CORRECTED]
    assert [e.trigger_data_ids for e in corrected] == [ids(m3, m3b), ids(m3b, m3c)]
    assert [e.condition_met for e in corrected] == [False, True]
    assert events(db, alert)[-1].event_type is AlertEventType.RE_TRIGGERED
    assert events(db, alert)[-1].trigger_data_ids == ids(m1, m2, m3c)

    params = WindowParams.model_validate(window_params())
    assert [m.id for m in window_violations(db, params, m3c)] == [m1.id, m2.id, m3c.id]


# --- A javított érték kiértékelése ----------------------------------------------------------


def test_violating_correction_opens_an_alert(db, patient, doctor):
    make_threshold_rule(db, patient, doctor)
    ok, alerts = record_bp(db, patient, 128, 82, local(2026, 9, 1))
    assert alerts == []
    fixed, [alert] = correct(db, patient, ok, 158, 96, local(2026, 9, 2))
    assert [e.event_type for e in events(db, alert)] == [AlertEventType.CREATED]
    assert events(db, alert)[0].trigger_data_ids == ids(fixed)
    assert alert.needs_review is False


def test_violating_correction_of_a_trigger_retriggers(db, patient, doctor):
    make_threshold_rule(db, patient, doctor)
    original, [alert] = record_bp(db, patient, 158, 96, local(2026, 9, 1))
    fixed, evaluated = correct(db, patient, original, 152, 94, local(2026, 9, 2))
    assert [a.id for a in evaluated] == [alert.id]
    # Előbb a javítás, utána az újrakiértékelés (egyértelmű sorrend).
    assert types(db, alert) == [
        AlertEventType.CREATED,
        AlertEventType.TRIGGER_CORRECTED,
        AlertEventType.RE_TRIGGERED,
    ]
    assert events(db, alert)[1].condition_met is True
    assert events(db, alert)[2].trigger_data_ids == ids(fixed)
    assert alert.needs_review is True
    assert alert.status is AlertStatus.NEW


def test_correcting_a_non_trigger_adds_no_alert_event(db, patient, doctor):
    make_threshold_rule(db, patient, doctor)
    _, [alert] = record_bp(db, patient, 158, 96, local(2026, 9, 1))
    ok, _ = record_bp(db, patient, 128, 82, local(2026, 9, 2))
    before = types(db, alert)
    _, evaluated = correct(db, patient, ok, 126, 80, local(2026, 9, 3))
    assert evaluated == []
    assert types(db, alert) == before
    assert alert.needs_review is False


def test_correcting_a_closed_alerts_trigger_keeps_it_closed(db, patient, doctor):
    """D4: a lezárt riasztás története teljes (az esemény bekerül), de
    needs_review nem áll be, és az állapot lezárt marad."""
    make_threshold_rule(db, patient, doctor)
    original, [alert] = record_bp(db, patient, 158, 96, local(2026, 9, 1))
    close_alert(db, alert, doctor, "Egyeztetve.", now=local(2026, 9, 1, 10))
    _, evaluated = correct(db, patient, original, 130, 82, local(2026, 9, 2))
    assert evaluated == []
    assert types(db, alert)[-1] is AlertEventType.TRIGGER_CORRECTED
    assert events(db, alert)[-1].condition_met is False
    assert alert.status is AlertStatus.CLOSED
    assert alert.needs_review is False


def test_correction_does_not_fulfil_an_occurrence_again(db, patient, doctor):
    """A javítás alkalmat nem teljesít újra: az eredeti teljesítése áll."""
    assign_measurement(
        db,
        patient_id=patient.patient_profile.id,
        measurement_type=get_type_by_code(db, "blood_pressure"),
        assigned_by=doctor.id,
        start_date=local(2026, 9, 1).date(),
    )
    original, _ = record_bp(db, patient, 128, 82, local(2026, 9, 1))
    occurrences = list(db.scalars(select(AssignmentOccurrence)))
    assert [o.measurement_id for o in occurrences] == [original.id]
    correct(db, patient, original, 126, 80, local(2026, 9, 4))
    occurrences = list(db.scalars(select(AssignmentOccurrence)))
    assert [o.measurement_id for o in occurrences] == [original.id]


def test_values_are_checked_like_recording(db, patient):
    original, _ = record_bp(db, patient, 128, 82, local(2026, 9, 1))
    for values, code in (
        ({"systolic": 400, "diastolic": 80}, "out_of_range"),
        ({"systolic": 120}, "missing_value"),
        ({"systolic": 120, "diastolic": 80, "pulse": 70}, "unknown_component"),
    ):
        with pytest.raises(MeasurementError) as excinfo:
            correct_measurement(
                db,
                patient_id=patient.patient_profile.id,
                measurement_id=original.id,
                values=values,
                now=local(2026, 9, 2),
            )
        assert excinfo.value.code == code
    assert original.correction is None


def test_unknown_or_foreign_measurement_is_not_found(db, patient):
    other = make_patient(db, email="masik@test.example", name="Másik Beteg")
    foreign, _ = record_bp(db, other, 128, 82, local(2026, 9, 1))
    with pytest.raises(MeasurementError) as excinfo:
        correct(db, patient, foreign, 120, 80, local(2026, 9, 2))
    assert excinfo.value.code == "not_found"


# --- Végpont és jogosultság ---------------------------------------------------------------


def auth(user):
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def url(patient, measurement):
    return f"/api/patients/{patient.patient_profile.id}/measurements/{measurement.id}/correction"


BODY = {"values": {"systolic": 131, "diastolic": 82}}


def recent(db, patient, systolic=148, diastolic=92, days_ago=5):
    """Mérés néhány napja (a javításnak nincs időkorlátja, D3)."""
    at = datetime.now(settings.tz) - timedelta(days=days_ago)
    measurement, _ = record_bp(db, patient, systolic, diastolic, at)
    return measurement


def test_patient_corrects_own_measurement(client, db, patient, doctor):
    make_threshold_rule(db, patient, doctor)
    original = recent(db, patient)
    response = client.post(url(patient, original), json=BODY, headers=auth(patient))
    assert response.status_code == 201
    body = response.json()
    assert body["corrected_from"] == str(original.id)
    assert body["corrected_by"] is None
    assert [v["value"] for v in body["values"]] == [131, 82]

    listed = client.get(
        f"/api/patients/{patient.patient_profile.id}/measurements", headers=auth(patient)
    ).json()
    assert [(m["id"], m["corrected_by"]) for m in listed] == [
        (body["id"], None),
        (str(original.id), body["id"]),
    ]

    # Az orvos a riasztáson látja a jelölést és a javítás-eseményt.
    alerts = client.get(
        f"/api/patients/{patient.patient_profile.id}/alerts", headers=auth(doctor)
    ).json()
    [alert] = alerts
    assert alert["needs_review"] is True
    event = alert["events"][-1]
    assert event["event_type"] == "trigger_corrected"
    assert event["condition_met"] is False
    assert event["actor"]["name"] == "Teszt Beteg"
    assert [t["measurement"]["id"] for t in event["triggers"]] == [str(original.id), body["id"]]
    assert event["triggers"][0]["measurement"]["corrected_by"] == body["id"]

    again = client.post(url(patient, original), json=BODY, headers=auth(patient))
    assert again.status_code == 409
    assert again.json()["detail"]["code"] == "already_corrected"


def test_invalid_correction_is_422(client, db, patient):
    original = recent(db, patient)
    bad = {"values": {"systolic": 400, "diastolic": 82}}
    response = client.post(url(patient, original), json=bad, headers=auth(patient))
    assert response.status_code == 422
    assert response.json()["detail"] == {"code": "out_of_range", "component": "systolic"}
    assert (
        client.post(url(patient, original), json={"values": {}}, headers=auth(patient)).status_code
        == 422
    )


def test_only_the_patient_may_correct(client, db, patient, doctor):
    original = recent(db, patient)
    admin = make_admin(db)
    for user in (doctor, admin):
        response = client.post(url(patient, original), json=BODY, headers=auth(user))
        assert response.status_code == 403
    assert original.correction is None


def test_foreign_patient_gets_403(client, db, patient):
    foreign = make_patient(db, email="idegen@test.example", name="Idegen Beteg")
    original = recent(db, patient)
    # Idegen beteg útvonalán a másik mérése.
    response = client.post(url(patient, original), json=BODY, headers=auth(foreign))
    assert response.status_code == 403
    # A saját útvonalán a másik beteg mérése: ugyanúgy 403, mint a nem létező.
    own_path = f"/api/patients/{foreign.patient_profile.id}/measurements/{original.id}/correction"
    assert client.post(own_path, json=BODY, headers=auth(foreign)).status_code == 403
    missing = f"/api/patients/{patient.patient_profile.id}/measurements/{foreign.id}/correction"
    assert client.post(missing, json=BODY, headers=auth(patient)).status_code == 403
