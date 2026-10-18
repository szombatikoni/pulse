"""Beteg-státusz és az orvos priorizált listája (F9)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import settings
from app.models import AlertStatus, Severity
from app.services.status import PatientStatus, compute_status, doctor_patient_list
from tests.factories import assign, make_doctor, make_patient, make_threshold_rule, record_bp

NOW = datetime(2026, 10, 12, 8, 0, tzinfo=UTC)
# Az összerendelések a szimulált idő előtt kezdődnek (az alapérték a valódi
# „most" lenne, ami a szimulált NOW után is lehet).
SINCE = NOW - timedelta(days=30)


@pytest.fixture
def doctor(db):
    return make_doctor(db)


@pytest.fixture
def patient(db, measurement_types, doctor):
    patient = make_patient(db)
    assign(db, doctor, patient, valid_from=SINCE)
    return patient


def status_of(db, patient, now=NOW):
    return compute_status(db, patient.patient_profile.id, now)


def test_patient_without_data_is_no_data_not_ok(db, patient):
    result = status_of(db, patient)
    assert result.status is PatientStatus.NO_DATA
    assert result.reasons[0].code == "no_data_yet"


def test_fresh_normal_data_is_ok(db, doctor, patient):
    make_threshold_rule(db, patient, doctor)
    record_bp(db, patient, 125, 80, at=NOW - timedelta(hours=2))
    result = status_of(db, patient)
    assert result.status is PatientStatus.OK
    assert result.last_data_at == NOW - timedelta(hours=2)


def test_data_becomes_stale_after_the_freshness_limit(db, patient):
    limit = timedelta(days=settings.data_freshness_days)
    record_bp(db, patient, 125, 80, at=NOW - limit)
    assert status_of(db, patient).status is PatientStatus.OK  # pont a határon még friss
    later = NOW + timedelta(seconds=1)
    result = status_of(db, patient, now=later)
    assert result.status is PatientStatus.NO_DATA
    assert result.reasons[0].code == "stale_data"


def test_open_moderate_alert_gives_attention(db, doctor, patient):
    make_threshold_rule(db, patient, doctor, severity=Severity.MODERATE)
    record_bp(db, patient, 150, 95, at=NOW)
    result = status_of(db, patient)
    assert result.status is PatientStatus.ATTENTION
    assert result.reasons[0].code == "open_alert"


def test_severe_alert_wins_and_other_reasons_are_kept(db, doctor, patient):
    make_threshold_rule(db, patient, doctor, severity=Severity.MODERATE)
    make_threshold_rule(
        db, patient, doctor, limits={"systolic": {"max": 180}}, severity=Severity.SEVERE
    )
    record_bp(db, patient, 186, 104, at=NOW - timedelta(days=10))
    result = status_of(db, patient)
    assert result.status is PatientStatus.SEVERE
    # A felület a többi okot is kiírja: közepes riasztás és régi adat.
    assert [r.status for r in result.reasons] == [
        PatientStatus.SEVERE,
        PatientStatus.ATTENTION,
        PatientStatus.NO_DATA,
    ]


def test_normal_value_after_alert_keeps_attention(db, doctor, patient):
    # A jó érték a riasztást nem zárja le: a státuszt csak az orvos lezárása változtatja.
    make_threshold_rule(db, patient, doctor)
    record_bp(db, patient, 150, 95, at=NOW - timedelta(days=1))
    record_bp(db, patient, 120, 80, at=NOW)
    assert status_of(db, patient).status is PatientStatus.ATTENTION


def test_closed_alert_no_longer_counts(db, doctor, patient):
    make_threshold_rule(db, patient, doctor)
    _, [alert] = record_bp(db, patient, 150, 95, at=NOW)
    alert.status = AlertStatus.CLOSED
    db.flush()
    assert status_of(db, patient).status is PatientStatus.OK


def test_doctor_list_is_prioritised_and_limited_to_assigned_patients(db, doctor, patient):
    severe = make_patient(db, email="sulyos@test.example", name="B Súlyos")
    no_data = make_patient(db, email="adathiany@test.example", name="C Adathiány")
    ok = make_patient(db, email="rendben@test.example", name="A Rendben")
    foreign = make_patient(db, email="idegen@test.example", name="Idegen")
    for p in (severe, no_data, ok):
        assign(db, doctor, p, valid_from=SINCE)
    make_threshold_rule(
        db, severe, doctor, limits={"systolic": {"max": 180}}, severity=Severity.SEVERE
    )
    make_threshold_rule(db, patient, doctor)
    record_bp(db, severe, 190, 100, at=NOW)
    record_bp(db, patient, 150, 95, at=NOW)  # Figyelem
    record_bp(db, ok, 120, 80, at=NOW)
    record_bp(db, foreign, 120, 80, at=NOW)

    rows = doctor_patient_list(db, doctor.doctor_profile.id, NOW)
    assert [(p.name, r.status) for p, r in rows] == [
        ("B Súlyos", PatientStatus.SEVERE),
        ("Teszt Beteg", PatientStatus.ATTENTION),
        ("C Adathiány", PatientStatus.NO_DATA),
        ("A Rendben", PatientStatus.OK),
    ]


def test_ended_assignment_removes_patient_from_list(db, doctor, measurement_types):
    patient = make_patient(db, email="vege@test.example")
    link = assign(db, doctor, patient, valid_from=SINCE)
    assert [p.id for p, _ in doctor_patient_list(db, doctor.doctor_profile.id, NOW)] == [
        patient.patient_profile.id
    ]
    link.valid_to = NOW - timedelta(seconds=1)
    db.flush()
    assert doctor_patient_list(db, doctor.doctor_profile.id, NOW) == []


def test_questionnaire_submission_also_counts_as_fresh_data(db, doctor, patient):
    from app.services.questionnaires import (
        assign_questionnaire,
        create_template,
        current_version,
        submit_questionnaire,
    )
    from seed.questionnaires import WELLBEING_CODE, WELLBEING_NAME, WELLBEING_V1

    template = create_template(
        db, code=WELLBEING_CODE, name=WELLBEING_NAME, created_by=doctor.id, spec=WELLBEING_V1
    )
    assign_questionnaire(
        db,
        patient_id=patient.patient_profile.id,
        template=template,
        assigned_by=doctor.id,
        start_date=SINCE.date(),
    )
    # Régi mérés (Adathiány), de friss kitöltés → van friss adat.
    record_bp(db, patient, 125, 80, at=NOW - timedelta(days=20))
    q1, q2, q3 = current_version(db, template.id).questions
    submit_questionnaire(
        db,
        patient_id=patient.patient_profile.id,
        template_code=WELLBEING_CODE,
        answers={str(q1.id): 5, str(q2.id): 1, str(q3.id): "never"},
        now=NOW - timedelta(hours=1),
    )
    result = status_of(db, patient)
    assert result.status is PatientStatus.OK
    assert result.last_data_at == NOW - timedelta(hours=1)
