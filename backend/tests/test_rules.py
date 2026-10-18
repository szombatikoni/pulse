"""Szabálykiértékelés (F11, F12, F17, F18): küszöbhatárok, deduplikáció,
verziók és az immutabilitás."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.models import AlertEvent, AlertEventType, AlertStatus, RuleType, Severity
from app.services.measurements import record_measurement
from app.services.rules import add_rule_version, current_version, open_alert
from tests.factories import make_doctor, make_patient, make_threshold_rule, record_bp

NOW = datetime(2026, 10, 12, 8, 0, tzinfo=UTC)


@pytest.fixture
def doctor(db):
    return make_doctor(db)


@pytest.fixture
def patient(db, measurement_types):
    return make_patient(db)


def events(db, alert):
    query = select(AlertEvent).where(AlertEvent.alert_id == alert.id)
    return list(db.scalars(query.order_by(AlertEvent.created_at)))


# --- Küszöbhatárok -----------------------------------------------------------


@pytest.mark.parametrize(
    ("systolic", "diastolic", "alerts"),
    [
        (140, 90, 0),  # pont a határon: még rendben (a „140 feletti" a 141-től)
        (141, 80, 1),  # csak a szisztolés lépi át
        (120, 91, 1),  # csak a diasztolés lépi át
        (150, 95, 1),  # mindkettő: akkor is egy riasztás
        (139.9, 89.9, 0),
    ],
)
def test_threshold_boundaries(db, doctor, patient, systolic, diastolic, alerts):
    make_threshold_rule(db, patient, doctor)
    _, touched = record_bp(db, patient, systolic, diastolic, at=NOW)
    assert len(touched) == alerts


def test_lower_bound(db, doctor, patient):
    make_threshold_rule(db, patient, doctor, limits={"systolic": {"min": 90}})
    assert record_bp(db, patient, 90, 60, at=NOW)[1] == []
    assert len(record_bp(db, patient, 89, 60, at=NOW + timedelta(minutes=1))[1]) == 1


def test_rule_for_other_measurement_type_does_not_fire(db, doctor, patient):
    make_threshold_rule(
        db, patient, doctor, limits={"value": {"max": 100}}, measurement_type="heart_rate"
    )
    assert record_bp(db, patient, 200, 120, at=NOW)[1] == []


def test_inactive_rule_does_not_fire(db, doctor, patient):
    rule = make_threshold_rule(db, patient, doctor)
    rule.is_active = False
    db.flush()
    assert record_bp(db, patient, 160, 100, at=NOW)[1] == []


def test_other_patients_rule_does_not_fire(db, doctor, patient):
    other = make_patient(db, email="masik@test.example")
    make_threshold_rule(db, other, doctor)
    assert record_bp(db, patient, 160, 100, at=NOW)[1] == []


# --- A riasztás tartalma és magyarázhatósága (F17) ---------------------------


def test_alert_stores_version_and_trigger_data(db, doctor, patient):
    rule = make_threshold_rule(db, patient, doctor, severity=Severity.MODERATE)
    measurement, [alert] = record_bp(db, patient, 152, 95, at=NOW)
    version = current_version(db, rule.id)
    assert alert.status is AlertStatus.NEW
    assert alert.severity is Severity.MODERATE
    assert alert.rule_version_id == version.id
    assert alert.trigger_data_ids == [str(measurement.id)]
    assert alert.created_at == NOW
    [created] = events(db, alert)
    assert created.event_type is AlertEventType.CREATED
    assert created.rule_version_id == version.id
    assert created.trigger_data_ids == [str(measurement.id)]
    assert created.actor_id is None  # a rendszer hozta létre


# --- Deduplikáció (F18) ------------------------------------------------------


def test_second_violation_re_triggers_the_open_alert(db, doctor, patient):
    make_threshold_rule(db, patient, doctor)
    first, [alert] = record_bp(db, patient, 146, 92, at=NOW)
    second, [same] = record_bp(db, patient, 152, 95, at=NOW + timedelta(days=1))
    assert same.id == alert.id
    assert alert.trigger_data_ids == [str(first.id)]  # a megnyitáskori adat marad
    created, re_triggered = events(db, alert)
    assert re_triggered.event_type is AlertEventType.RE_TRIGGERED
    assert re_triggered.trigger_data_ids == [str(second.id)]


def test_normal_measurement_does_not_touch_open_alert(db, doctor, patient):
    make_threshold_rule(db, patient, doctor)
    _, [alert] = record_bp(db, patient, 150, 95, at=NOW)
    assert record_bp(db, patient, 120, 80, at=NOW + timedelta(hours=1))[1] == []
    assert len(events(db, alert)) == 1
    assert alert.status is AlertStatus.NEW  # a jó érték nem zárja le (csak az orvos zárhat)


def test_closed_alert_does_not_absorb_new_violation(db, doctor, patient):
    make_threshold_rule(db, patient, doctor)
    _, [alert] = record_bp(db, patient, 150, 95, at=NOW)
    alert.status = AlertStatus.CLOSED  # a lezárás folyamata az M3-ban jön
    db.flush()
    _, [new_alert] = record_bp(db, patient, 150, 95, at=NOW + timedelta(days=1))
    assert new_alert.id != alert.id


def test_two_rules_give_two_alerts(db, doctor, patient):
    make_threshold_rule(db, patient, doctor, severity=Severity.MODERATE)
    make_threshold_rule(
        db, patient, doctor, limits={"systolic": {"max": 180}}, severity=Severity.SEVERE
    )
    _, touched = record_bp(db, patient, 186, 104, at=NOW)
    assert sorted(a.severity for a in touched) == [Severity.MODERATE, Severity.SEVERE]


def test_database_allows_only_one_open_alert_per_rule(db, doctor, patient):
    # Védelem mélységben: ha egy kódút megkerülné a deduplikációt, a részleges
    # egyedi index akkor is elutasítja a második nyitott riasztást.
    make_threshold_rule(db, patient, doctor)
    _, [alert] = record_bp(db, patient, 150, 95, at=NOW)
    with pytest.raises(DBAPIError, match="uq_alerts_open_per_rule"), db.begin_nested():
        db.execute(
            text(
                "INSERT INTO alerts (id, patient_id, rule_id, rule_version_id, status, severity,"
                " trigger_data_ids, needs_review) SELECT gen_random_uuid(), patient_id, rule_id,"
                " rule_version_id, 'new', severity, '[]', false FROM alerts WHERE id = :id"
            ),
            {"id": alert.id},
        )


# --- Verziók (F12) -----------------------------------------------------------


def test_new_version_evaluates_new_data_and_old_alert_keeps_its_version(db, doctor, patient):
    rule = make_threshold_rule(db, patient, doctor, limits={"systolic": {"max": 140}})
    v1 = current_version(db, rule.id)
    _, [alert] = record_bp(db, patient, 145, 85, at=NOW)

    v2 = add_rule_version(
        db,
        rule,
        created_by=doctor.id,
        rule_type=RuleType.THRESHOLD,
        params={"measurement_type": "blood_pressure", "limits": {"systolic": {"max": 135}}},
        severity=Severity.SEVERE,
    )
    assert (v1.version_no, v2.version_no) == (1, 2)

    # 138: az 1. verzió szerint rendben lenne, a 2. szerint nem.
    _, [same] = record_bp(db, patient, 138, 85, at=NOW + timedelta(days=1))
    assert same.id == alert.id
    assert alert.rule_version_id == v1.id  # a megnyitáskori verzió nem változik
    assert alert.severity is Severity.SEVERE  # a súlyosság emelkedhet (F18)
    # TODO M3: itt egy „szabály módosult" esemény is lesz (Fable-átnézés F2).
    created, re_triggered = events(db, alert)
    assert (created.rule_version_id, re_triggered.rule_version_id) == (v1.id, v2.id)


def test_severity_does_not_decrease_on_re_trigger(db, doctor, patient):
    rule = make_threshold_rule(db, patient, doctor, severity=Severity.SEVERE)
    _, [alert] = record_bp(db, patient, 150, 95, at=NOW)
    add_rule_version(
        db,
        rule,
        created_by=doctor.id,
        rule_type=RuleType.THRESHOLD,
        params={"measurement_type": "blood_pressure", "limits": {"systolic": {"max": 140}}},
        severity=Severity.MODERATE,
    )
    record_bp(db, patient, 150, 95, at=NOW + timedelta(days=1))
    assert alert.severity is Severity.SEVERE


def test_rule_version_cannot_be_modified_or_deleted(db, doctor, patient):
    rule = make_threshold_rule(db, patient, doctor)
    version = current_version(db, rule.id)
    with pytest.raises(DBAPIError, match="append-only"), db.begin_nested():
        db.execute(
            text("UPDATE rule_versions SET severity = 'severe' WHERE id = :id"), {"id": version.id}
        )
    with pytest.raises(DBAPIError, match="append-only"), db.begin_nested():
        db.execute(text("DELETE FROM rule_versions WHERE id = :id"), {"id": version.id})


def test_alert_events_cannot_be_modified_or_deleted(db, doctor, patient):
    make_threshold_rule(db, patient, doctor)
    _, [alert] = record_bp(db, patient, 150, 95, at=NOW)
    with pytest.raises(DBAPIError, match="append-only"), db.begin_nested():
        db.execute(
            text("UPDATE alert_events SET reason = 'x' WHERE alert_id = :id"), {"id": alert.id}
        )
    with pytest.raises(DBAPIError, match="append-only"), db.begin_nested():
        db.execute(text("DELETE FROM alert_events WHERE alert_id = :id"), {"id": alert.id})


# --- Paraméter-ellenőrzés ----------------------------------------------------


@pytest.mark.parametrize(
    "limits",
    [
        {},  # legalább egy komponens kell
        {"systolic": {}},  # min vagy max kell
        {"systolic": {"min": 150, "max": 140}},  # min < max
    ],
)
def test_invalid_threshold_params_are_rejected(db, doctor, patient, limits):
    with pytest.raises(ValidationError):
        make_threshold_rule(db, patient, doctor, limits=limits)


def test_open_alert_lookup_ignores_closed(db, doctor, patient):
    rule = make_threshold_rule(db, patient, doctor)
    _, [alert] = record_bp(db, patient, 150, 95, at=NOW)
    assert open_alert(db, patient.patient_profile.id, rule.id) is alert
    alert.status = AlertStatus.CLOSED
    db.flush()
    assert open_alert(db, patient.patient_profile.id, rule.id) is None


def test_backdated_measurement_alert_carries_recording_time(db, doctor, patient):
    # A mérés tegnapi, de ma rögzítik: a riasztás a rögzítés (a kiértékelés)
    # idejét kapja, a kiváltó mérés a saját mérési idejét őrzi.
    make_threshold_rule(db, patient, doctor)
    measured_at = NOW - timedelta(days=1)
    measurement, [alert] = record_measurement(
        db,
        patient_id=patient.patient_profile.id,
        type_code="blood_pressure",
        values={"systolic": 150, "diastolic": 95},
        measured_at=measured_at,
        now=NOW,
    )
    assert alert.created_at == NOW
    assert measurement.measured_at == measured_at
