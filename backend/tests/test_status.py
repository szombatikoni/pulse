"""Beteg-státusz és az orvos priorizált listája (F9)."""

from datetime import UTC, date, datetime, time, timedelta

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models import AlertStatus, AssignmentOccurrence, Frequency, OccurrenceStatus, Severity
from app.services.alerts import close_alert
from app.services.measurements import get_type_by_code, record_measurement
from app.services.occurrences import run_occurrence_check
from app.services.plans import revoke
from app.services.status import PatientStatus, compute_status, doctor_patient_list
from app.services.tasks import TaskState, assign_measurement, patient_tasks
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


def occurrences_of(db, plan):
    return list(
        db.scalars(
            select(AssignmentOccurrence).where(AssignmentOccurrence.assignment_id == plan.id)
        )
    )


def test_missed_latest_occurrence_gives_no_data_even_with_fresh_data(db, doctor, patient):
    # Heti vérnyomás-előírás okt. 1-jétől: az első hét (okt. 1–7.) határideje
    # okt. 7. 10:00, NOW-kor (okt. 12. 10:00) már elmulasztott (okt. 10. 0:00
    # óta); a második hét határideje (okt. 14.) még nem járt le, így a
    # legutóbbi lejárt alkalom az elmulasztott. A tegnapi pulzusmérés a 7 napos
    # szabály szerint friss volna, de nem az előírt méréstípus. (K4, 2026-11-16
    # előtt napi előírással futott; napi előírásnál a legutóbbi lejárt alkalom
    # azóta mindig a tegnapi, még pótolható alkalom, lásd a lenti teszteket.)
    bp_plan(db, patient, doctor, start=date(2026, 10, 1), frequency=Frequency.WEEKLY)
    at = NOW - timedelta(days=1)
    record_measurement(
        db,
        patient_id=patient.patient_profile.id,
        type_code="heart_rate",
        values={"value": 72},
        measured_at=at,
        now=at,
    )
    check(db)
    result = status_of(db, patient)
    assert result.status is PatientStatus.NO_DATA
    [reason] = result.reasons
    assert reason.code == "missed_occurrence"
    assert reason.at == local(2026, 10, 7, 10, 0)
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
    # Okt. 10. 9:00-kor nézzük, az okt. 10-i határidő előtt: a legutóbbi lejárt
    # alkalom a késve teljesített okt. 9-i. (K4, 2026-11-16 előtt NOW-kor, okt.
    # 12-én nézett; azóta ott a pótolatlan okt. 10–11-i alkalmak Adathiányt adnak.)
    now = local(2026, 10, 10, 9, 0)
    check(db, now)
    result = status_of(db, patient, now)
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
    # A lekérdezés semmit nem ír: alkalmat nem nyit és nem zár (a zárás a
    # háttérfolyamaté). A lejárt határidőt viszont sor nélkül is látja (review
    # K2, 2026-11-16): az okt. 9–11-i alkalom nincs megnyitva, a státusz mégis
    # Adathiány, az ok alkalom nélkül (a legutóbbi lejárt határidő, okt. 11.).
    # Előtte itt Rendben volt: a garancia a hívási sorrendre (előbb a
    # teendőlista) volt bízva.
    plan = bp_plan(db, patient, doctor, start=date(2026, 10, 8))
    record_bp(db, patient, 125, 80, at=local(2026, 10, 8, 7, 30))
    rows = len(occurrences_of(db, plan))
    result = status_of(db, patient)
    assert result.status is PatientStatus.NO_DATA
    [reason] = result.reasons
    assert (reason.code, reason.at, reason.occurrence) == (
        "missed_occurrence",
        local(2026, 10, 11, 10, 0),
        None,
    )
    assert len(occurrences_of(db, plan)) == rows  # a status_of nem nyitott alkalmat
    assert check(db).missed > 0  # és nem is zárta le őket


# --- Adathiány a határidő után (K4, a hallgató döntése, 2026-11-16) ---------------------
# A dolgozat 7. fejezete szerint a határidő lejárta után a státusz azonnal
# Adathiány; az alkalom a pótlási idő végéig esedékes (DUE) marad, pótolható, és
# csak utána lesz elmulasztott (MISSED). A heti előírás okt. 6-tól (hétfő): az
# első hét határideje okt. 12. 10:00, az időszak vége okt. 13. 0:00, a pótlási
# idő vége okt. 15. 0:00; a következő határidő okt. 19., így a vizsgált
# napokon csak ez az egy alkalom számít.

DEADLINE = local(2026, 10, 12, 10, 0)
SECOND = timedelta(seconds=1)


@pytest.fixture
def weekly_plan(db, doctor, patient):
    plan = bp_plan(db, patient, doctor, start=date(2026, 10, 6), frequency=Frequency.WEEKLY)
    # Friss adat, de nem az előírt méréstípusból (nem teljesít alkalmat): a 7
    # napos szabály szerint a beteg a határidő előtt Rendben.
    at = local(2026, 10, 11, 8, 0)
    record_measurement(
        db,
        patient_id=patient.patient_profile.id,
        type_code="heart_rate",
        values={"value": 72},
        measured_at=at,
        now=at,
    )
    check(db, local(2026, 10, 12, 0, 30))  # a háttérfolyamat megnyitja az alkalmat
    return plan


def the_occurrence(db, plan):
    return db.scalar(
        select(AssignmentOccurrence).where(AssignmentOccurrence.assignment_id == plan.id)
    )


def test_no_data_starts_right_after_the_deadline(db, patient, weekly_plan):
    at_deadline = status_of(db, patient, DEADLINE)
    assert (at_deadline.status, [r.code for r in at_deadline.reasons]) == (
        PatientStatus.OK,
        ["fresh_data"],
    )
    after = status_of(db, patient, DEADLINE + SECOND)
    assert after.status is PatientStatus.NO_DATA
    [reason] = after.reasons
    assert (reason.code, reason.at) == ("missed_occurrence", DEADLINE)
    # Az alkalom nem zárult le: esedékes, pótolható.
    assert reason.occurrence.status is OccurrenceStatus.DUE
    # A beteg teendőlistája ugyanazt a határt használja (késésben), és nem változott.
    pid = patient.patient_profile.id
    assert patient_tasks(db, pid, DEADLINE)[0].state is TaskState.DUE
    assert patient_tasks(db, pid, DEADLINE + SECOND)[0].state is TaskState.LATE


def test_late_fulfilment_restores_the_status(db, patient, weekly_plan):
    assert status_of(db, patient, DEADLINE + SECOND).status is PatientStatus.NO_DATA
    record_measurement(
        db,
        patient_id=patient.patient_profile.id,
        type_code="blood_pressure",
        values={"systolic": 126, "diastolic": 81},
        measured_at=local(2026, 10, 12, 9, 30),
        now=local(2026, 10, 12, 18, 0),  # a határidő után rögzítve: késve teljesít
    )
    assert the_occurrence(db, weekly_plan).status is OccurrenceStatus.FULFILLED_LATE
    result = status_of(db, patient, local(2026, 10, 12, 18, 1))
    assert (result.status, [r.code for r in result.reasons]) == (PatientStatus.OK, ["fresh_data"])


def test_after_the_catch_up_window_missed_and_stays_no_data(db, patient, weekly_plan):
    before = status_of(db, patient, local(2026, 10, 14, 23, 59))
    assert before.status is PatientStatus.NO_DATA
    assert before.reasons[0].occurrence.status is OccurrenceStatus.DUE
    assert check(db, local(2026, 10, 15, 0, 0)).missed == 1
    after = status_of(db, patient, local(2026, 10, 15, 0, 1))
    assert after.status is PatientStatus.NO_DATA
    [reason] = after.reasons
    assert (reason.code, reason.at) == ("missed_occurrence", DEADLINE)
    assert reason.occurrence.status is OccurrenceStatus.MISSED


def test_open_alert_keeps_priority_over_the_lapsed_occurrence(db, doctor, patient, weekly_plan):
    make_threshold_rule(db, patient, doctor, severity=Severity.MODERATE)
    # Az előírás kezdete előtt (okt. 5.) mért magas érték: riaszt, de alkalmat
    # nem teljesít. (A következő hét időszakába eső mérés teljesítené az új
    # alkalmat, és az, mint legutóbbi lezárt alkalom, megszüntetné az okt. 12-i
    # okát; ez a korábbi szabály, nem változott.)
    record_bp(db, patient, 150, 95, at=local(2026, 10, 5, 8, 0))
    result = status_of(db, patient, DEADLINE + SECOND)
    assert result.status is PatientStatus.ATTENTION
    assert [r.code for r in result.reasons] == ["open_alert", "missed_occurrence"]

    make_threshold_rule(
        db, patient, doctor, limits={"systolic": {"max": 180}}, severity=Severity.SEVERE
    )
    record_bp(db, patient, 190, 100, at=local(2026, 10, 5, 8, 30))
    result = status_of(db, patient, DEADLINE + SECOND)
    assert result.status is PatientStatus.SEVERE
    assert [r.status for r in result.reasons] == [
        PatientStatus.SEVERE,
        PatientStatus.ATTENTION,
        PatientStatus.NO_DATA,
    ]


def test_handled_turns_into_no_data_at_the_deadline(db, doctor, patient, weekly_plan):
    make_threshold_rule(db, patient, doctor, severity=Severity.MODERATE)
    # Az előírás kezdete előtti mérés (okt. 5.): riaszt, de alkalmat nem teljesít.
    _, [alert] = record_bp(db, patient, 150, 95, at=local(2026, 10, 5, 8, 0))
    close_alert(db, alert, doctor, "Telefonon egyeztettem.", now=local(2026, 10, 12, 9, 0))
    handled = status_of(db, patient, DEADLINE)
    assert (handled.status, [r.code for r in handled.reasons]) == (
        PatientStatus.HANDLED,
        ["closed_awaiting_data"],
    )
    after = status_of(db, patient, DEADLINE + SECOND)
    assert after.status is PatientStatus.NO_DATA
    assert [r.code for r in after.reasons] == ["missed_occurrence", "closed_awaiting_data"]


def test_revoked_plan_gives_no_no_data_after_its_deadline(db, patient, weekly_plan):
    revoke(db, weekly_plan, now=local(2026, 10, 12, 9, 0))
    result = status_of(db, patient, DEADLINE + SECOND)
    assert (result.status, [r.code for r in result.reasons]) == (PatientStatus.OK, ["fresh_data"])


def test_ended_plan_gives_no_no_data_after_its_last_deadline(db, patient, weekly_plan):
    # Az előírás okt. 12-én véget ér: az utolsó alkalom határideje után, de még
    # aznap Adathiány; másnap a lejárt előírás már nem számít (mint eddig is).
    weekly_plan.end_date = date(2026, 10, 12)
    db.flush()
    assert status_of(db, patient, DEADLINE + SECOND).status is PatientStatus.NO_DATA
    result = status_of(db, patient, local(2026, 10, 13, 9, 0))
    assert (result.status, [r.code for r in result.reasons]) == (PatientStatus.OK, ["fresh_data"])


def test_not_yet_started_plan_gives_no_no_data(db, doctor, patient):
    # Holnap kezdődő előírás: ma nincs lejárt határideje, a 7 napos szabály dönt.
    record_bp(db, patient, 125, 80, at=local(2026, 10, 12, 7, 0))
    bp_plan(db, patient, doctor, start=date(2026, 10, 13))
    result = status_of(db, patient, local(2026, 10, 12, 23, 0))
    assert (result.status, [r.code for r in result.reasons]) == (PatientStatus.OK, ["fresh_data"])


def test_current_period_fulfilled_before_its_deadline_supersedes_the_lapse(db, doctor, patient):
    # A korábbi szabály, változatlanul: a legutóbbi lezárt alkalom a teljesített
    # aktuális is, a határideje előtt. Az okt. 11-i alkalom elmaradt (pótolható),
    # de okt. 12. 7:30-kor a mai mérés megjött: Rendben, nem Adathiány.
    bp_plan(db, patient, doctor, start=date(2026, 10, 11))
    check(db, local(2026, 10, 12, 0, 30))
    assert status_of(db, patient, local(2026, 10, 12, 7, 0)).status is PatientStatus.NO_DATA
    record_bp(db, patient, 125, 80, at=local(2026, 10, 12, 7, 30))
    result = status_of(db, patient, local(2026, 10, 12, 7, 31))
    assert (result.status, [r.code for r in result.reasons]) == (PatientStatus.OK, ["fresh_data"])


# --- Az átnézés hiányzó esetei (review, 2026-11-16) -------------------------------------


def heart_rate(db, patient, at):
    """Friss adat, de nem az előírt méréstípusból: alkalmat nem teljesít."""
    record_measurement(
        db,
        patient_id=patient.patient_profile.id,
        type_code="heart_rate",
        values={"value": 72},
        measured_at=at,
        now=at,
    )


def wellbeing_plan(db, doctor, patient, start):
    from app.services.questionnaires import assign_questionnaire, create_template
    from seed.questionnaires import WELLBEING_CODE, WELLBEING_NAME, WELLBEING_V1

    template = create_template(
        db, code=WELLBEING_CODE, name=WELLBEING_NAME, created_by=doctor.id, spec=WELLBEING_V1
    )
    plan = assign_questionnaire(
        db,
        patient_id=patient.patient_profile.id,
        template=template,
        assigned_by=doctor.id,
        start_date=start,
        frequency=Frequency.WEEKLY,
        due_time=time(20, 0),
    )
    return template, plan


def submit_wellbeing(db, patient, template, now):
    from app.services.questionnaires import current_version, submit_questionnaire
    from seed.questionnaires import WELLBEING_CODE

    q1, q2, q3 = current_version(db, template.id).questions
    submit_questionnaire(
        db,
        patient_id=patient.patient_profile.id,
        template_code=WELLBEING_CODE,
        answers={str(q1.id): 5, str(q2.id): 1, str(q3.id): "never"},
        now=now,
    )


def test_questionnaire_between_its_deadline_and_the_period_end(db, doctor, patient):
    # Heti Közérzet okt. 6-tól, határidő 20:00: az első hét határideje okt. 12.
    # 20:00, az időszak vége okt. 13. 0:00 (kérdőívnél nincs pótlási ablak). A
    # határidő és az időszak vége között a státusz Adathiány, az alkalom még
    # esedékes; az ekkor beküldött kitöltés késve teljesít, és a státusz Rendben.
    template, plan = wellbeing_plan(db, doctor, patient, date(2026, 10, 6))
    heart_rate(db, patient, local(2026, 10, 12, 8, 0))
    check(db, local(2026, 10, 12, 12, 0))
    deadline = local(2026, 10, 12, 20, 0)
    assert status_of(db, patient, deadline).status is PatientStatus.OK
    result = status_of(db, patient, deadline + SECOND)
    assert result.status is PatientStatus.NO_DATA
    [reason] = result.reasons
    assert (reason.code, reason.at, reason.occurrence.status) == (
        "missed_occurrence",
        deadline,
        OccurrenceStatus.DUE,
    )
    submit_wellbeing(db, patient, template, local(2026, 10, 12, 21, 0))
    [occurrence] = occurrences_of(db, plan)
    assert occurrence.status is OccurrenceStatus.FULFILLED_LATE
    result = status_of(db, patient, local(2026, 10, 12, 21, 1))
    assert (result.status, [r.code for r in result.reasons]) == (PatientStatus.OK, ["fresh_data"])


def test_questionnaire_not_submitted_is_missed_at_the_period_end(db, doctor, patient):
    _, plan = wellbeing_plan(db, doctor, patient, date(2026, 10, 6))
    heart_rate(db, patient, local(2026, 10, 12, 8, 0))
    check(db, local(2026, 10, 12, 12, 0))
    assert check(db, local(2026, 10, 12, 23, 59)).missed == 0
    assert check(db, local(2026, 10, 13, 0, 0)).missed == 1
    result = status_of(db, patient, local(2026, 10, 13, 0, 1))
    assert result.status is PatientStatus.NO_DATA
    assert result.reasons[0].occurrence.status is OccurrenceStatus.MISSED


def test_one_fulfilled_and_one_lapsed_plan_gives_one_reason(db, doctor, patient):
    # Két előírás okt. 11-től: a vérnyomás napi (10:00), a testsúly napi 9:00-s
    # határidővel. Okt. 12. 10:01-kor a vérnyomás mai alkalma teljesült, a
    # testsúlyé lejárt: Adathiány, egyetlen elmulasztott okkal, a testsúlyéval.
    bp = bp_plan(db, patient, doctor, start=date(2026, 10, 11))
    weight = assign_measurement(
        db,
        patient_id=patient.patient_profile.id,
        measurement_type=get_type_by_code(db, "body_weight"),
        assigned_by=doctor.id,
        start_date=date(2026, 10, 11),
        due_time=time(9, 0),
    )
    for day in (11, 12):
        record_bp(db, patient, 125, 80, at=local(2026, 10, day, 7, 30))
    record_measurement(
        db,
        patient_id=patient.patient_profile.id,
        type_code="body_weight",
        values={"value": 80},
        measured_at=local(2026, 10, 11, 8, 0),
        now=local(2026, 10, 11, 8, 0),
    )
    now = local(2026, 10, 12, 10, 1)
    result = status_of(db, patient, now)
    assert result.status is PatientStatus.NO_DATA
    [reason] = result.reasons
    assert reason.code == "missed_occurrence"
    assert reason.at == local(2026, 10, 12, 9, 0)
    # Sor nélkül is (a testsúly mai alkalmát senki nem nyitotta meg) ugyanez.
    assert reason.occurrence is None
    check(db, now)
    [reason] = status_of(db, patient, now).reasons
    assert reason.occurrence.assignment_id == weight.id
    assert occurrences_of(db, bp)[-1].status is OccurrenceStatus.FULFILLED


def test_deadline_on_the_dst_change_night(db, doctor, patient):
    # 2026. okt. 25., óraátállítás (3:00 nyári → 2:00 téli): a 2:30-as határidő
    # a kétszer előforduló 2:30 közül az első (nyári idő, UTC 0:30). A teendő
    # és a státusz ugyanabban a pillanatban vált, sorral és sor nélkül is.
    plan = assign_measurement(
        db,
        patient_id=patient.patient_profile.id,
        measurement_type=get_type_by_code(db, "blood_pressure"),
        assigned_by=doctor.id,
        start_date=date(2026, 10, 25),
        due_time=time(2, 30),
    )
    heart_rate(db, patient, datetime(2026, 10, 24, 20, 0, tzinfo=UTC))
    deadline = datetime(2026, 10, 25, 0, 30, tzinfo=UTC)
    # (Zónák közti == a kétértelmű időpontnál mindig hamis, PEP 495: UTC-ben vetjük össze.)
    assert datetime(2026, 10, 25, 2, 30, tzinfo=settings.tz).astimezone(UTC) == deadline
    pid = patient.patient_profile.id
    # Sor nélkül (a státusz az időszakból számol).
    assert status_of(db, patient, deadline).status is PatientStatus.OK
    assert status_of(db, patient, deadline + SECOND).status is PatientStatus.NO_DATA
    assert occurrences_of(db, plan) == []
    # A teendőlista megnyitja a sort; utána ugyanígy.
    assert patient_tasks(db, pid, deadline)[0].state is TaskState.DUE
    assert patient_tasks(db, pid, deadline + SECOND)[0].state is TaskState.LATE
    assert status_of(db, patient, deadline).status is PatientStatus.OK
    after = status_of(db, patient, deadline + SECOND)
    assert after.status is PatientStatus.NO_DATA
    assert after.reasons[0].occurrence.due_at == deadline
    # A téli idő szerinti második 2:30 (UTC 1:30) már egy órával a határidő után van.
    assert status_of(db, patient, datetime(2026, 10, 25, 1, 30, tzinfo=UTC)).status is (
        PatientStatus.NO_DATA
    )
