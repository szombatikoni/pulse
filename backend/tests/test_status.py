"""Beteg-státusz és az orvos priorizált listája (F9)."""

from datetime import UTC, date, datetime, timedelta

import pytest

from app.core.config import settings
from app.models import AlertStatus, Frequency, OccurrenceStatus, Severity
from app.services.measurements import get_type_by_code, record_measurement
from app.services.occurrences import run_occurrence_check
from app.services.plans import revoke
from app.services.status import PatientStatus, compute_status, doctor_patient_list
from app.services.tasks import assign_measurement
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


# --- Adathiány és frissesség az alkalmakból (M3, A4 2. lépés) ---------------------------


def local(y, m, d, hh=0, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=settings.tz)


def bp_plan(db, patient, doctor, start, frequency=None, interval_days=None):
    """Vérnyomás-előírás 10:00-s határidővel (alapból naponta). A mérés alkalma
    az időszak vége + 48 óra után elmulasztott."""
    return assign_measurement(
        db,
        patient_id=patient.patient_profile.id,
        measurement_type=get_type_by_code(db, "blood_pressure"),
        assigned_by=doctor.id,
        start_date=start,
        frequency=frequency or Frequency.DAILY,
        interval_days=interval_days,
    )


def check(db, now=NOW):
    return run_occurrence_check(db, now)


def test_missed_latest_occurrence_gives_no_data_even_with_fresh_data(db, doctor, patient):
    # NOW = okt. 12. 10:00 (helyi): az okt. 9-i alkalom okt. 12. 0:00-kor zárult.
    # Az okt. 8-i mérés 4 napos, a 7 napos szabály szerint friss lenne.
    bp_plan(db, patient, doctor, start=date(2026, 10, 8))
    record_bp(db, patient, 125, 80, at=local(2026, 10, 8, 7, 30))
    check(db)
    result = status_of(db, patient)
    assert result.status is PatientStatus.NO_DATA
    [reason] = result.reasons
    assert reason.code == "missed_occurrence"
    assert reason.at == local(2026, 10, 9, 10, 0)
    assert reason.occurrence.status is OccurrenceStatus.MISSED


def test_later_fulfilled_occurrence_supersedes_an_earlier_miss(db, doctor, patient):
    # A „legutóbbi lezárt alkalom" a nem esedékesek közül a legkésőbbi
    # határidejű (mint az elmaradt adat szabálynál): az okt. 11-i teljesítés
    # után az okt. 9-i elmulasztás már nem az utolsó.
    bp_plan(db, patient, doctor, start=date(2026, 10, 8))
    record_bp(db, patient, 125, 80, at=local(2026, 10, 8, 7, 30))
    record_bp(db, patient, 124, 79, at=local(2026, 10, 11, 7, 30))
    check(db)
    assert [r.code for r in status_of(db, patient).reasons] == ["fresh_data"]


def test_late_fulfilment_is_not_missed(db, doctor, patient):
    bp_plan(db, patient, doctor, start=date(2026, 10, 8))
    record_bp(db, patient, 125, 80, at=local(2026, 10, 8, 7, 30))
    # Pótlás: az okt. 9-i mérést másnap rögzíti (a határidő után, a pótlási ablakban).
    record_measurement(
        db,
        patient_id=patient.patient_profile.id,
        type_code="blood_pressure",
        values={"systolic": 126, "diastolic": 81},
        measured_at=local(2026, 10, 9, 19, 0),
        now=local(2026, 10, 10, 8, 0),
    )
    check(db)
    result = status_of(db, patient)
    assert result.status is PatientStatus.OK
    assert [r.code for r in result.reasons] == ["fresh_data"]


def test_fulfilled_monthly_plan_keeps_20_day_old_data_fresh(db, doctor, patient):
    # 30 napos előírás szept. 2-től: az első időszak (szept. 2. – okt. 1.) a
    # szept. 22-i méréssel teljesítve, a második még esedékes. A 7 napos szabály
    # nem él, mert van lezárt alkalom: a frissességet az alkalmak adják.
    bp_plan(
        db,
        patient,
        doctor,
        start=date(2026, 9, 2),
        frequency=Frequency.EVERY_N_DAYS,
        interval_days=30,
    )
    record_bp(db, patient, 125, 80, at=NOW - timedelta(days=20))
    check(db)
    result = status_of(db, patient)
    assert result.status is PatientStatus.OK
    assert [r.code for r in result.reasons] == ["fresh_data"]
    assert result.last_data_at == NOW - timedelta(days=20)


def test_revoked_plan_misses_do_not_stick(db, doctor, patient):
    plan = bp_plan(db, patient, doctor, start=date(2026, 10, 1))
    check(db)  # okt. 1–9. elmulasztva
    # Friss adat, de nem az előírt méréstípusból (nem teljesít alkalmat).
    at = NOW - timedelta(days=1)
    record_measurement(
        db,
        patient_id=patient.patient_profile.id,
        type_code="heart_rate",
        values={"value": 72},
        measured_at=at,
        now=at,
    )
    assert [r.code for r in status_of(db, patient).reasons] == ["missed_occurrence"]

    revoke(db, plan, now=NOW)
    result = status_of(db, patient)
    # Nincs lezárt alkalom érvényes előíráson: a 7 napos szabály él, az adat friss.
    assert result.status is PatientStatus.OK
    assert [r.code for r in result.reasons] == ["fresh_data"]


def test_before_the_first_deadline_the_7_day_rule_applies(db, doctor, patient):
    # Módosítás = visszavonás + új előírás mától: a régi elmulasztása nem
    # számít, az új első határideje még nem járt le, így a 7 napos szabály dönt.
    old = bp_plan(db, patient, doctor, start=date(2026, 10, 1))
    record_bp(db, patient, 125, 80, at=NOW - timedelta(days=10))
    check(db)
    revoke(db, old, now=NOW)
    bp_plan(db, patient, doctor, start=date(2026, 10, 12))
    result = status_of(db, patient)
    assert result.status is PatientStatus.NO_DATA
    assert [r.code for r in result.reasons] == ["stale_data"]


def test_without_plan_the_7_day_rule_applies(db, patient):
    record_bp(db, patient, 125, 80, at=NOW - timedelta(days=8))
    assert [r.code for r in status_of(db, patient).reasons] == ["stale_data"]


def test_no_data_yet_with_missed_occurrence_lists_both(db, doctor, patient):
    bp_plan(db, patient, doctor, start=date(2026, 10, 8))
    check(db)
    result = status_of(db, patient)
    assert result.status is PatientStatus.NO_DATA
    assert [r.code for r in result.reasons] == [
        "missed_occurrence",
        "no_data_yet",
    ]


def test_status_does_not_close_occurrences(db, doctor, patient):
    # A lekérdezés csak a tárolt állapotot olvassa: a zárás a háttérfolyamaté.
    bp_plan(db, patient, doctor, start=date(2026, 10, 8))
    record_bp(db, patient, 125, 80, at=local(2026, 10, 8, 7, 30))
    result = status_of(db, patient)
    assert result.status is PatientStatus.OK
    assert check(db).missed > 0  # a status_of nem zárta le őket
