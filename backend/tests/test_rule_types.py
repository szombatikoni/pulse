"""Az M3 szabálytípusai (F11; M3 A4): időablakos ismétlődés, romló kérdőív-trend,
elmaradt adatküldés, valamint a „szabály módosult" esemény és a típuszár
(07_mukodesi_szabalyok.md, 1–3. rész)."""

from datetime import UTC, date, datetime, time, timedelta

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models import (
    AlertEvent,
    AlertEventType,
    AlertStatus,
    AssignmentOccurrence,
    Frequency,
    OccurrenceStatus,
    RuleType,
    Severity,
)
from app.services.measurements import get_type_by_code, record_measurement
from app.services.occurrences import run_occurrence_check
from app.services.plans import revoke
from app.services.questionnaires import (
    add_version,
    assign_questionnaire,
    create_template,
    current_version,
    submit_questionnaire,
)
from app.services.rules import add_rule_version, create_rule, open_alert
from app.services.tasks import assign_measurement
from seed.questionnaires import WELLBEING_CODE, WELLBEING_NAME, WELLBEING_V1
from tests.factories import make_doctor, make_patient, make_threshold_rule, record_bp

NOW = datetime(2026, 10, 12, 8, 0, tzinfo=UTC)


def local(y, m, d, hh=0, mm=0):
    """Időpont a rendszer időzónájában (Europe/Budapest)."""
    return datetime(y, m, d, hh, mm, tzinfo=settings.tz)


@pytest.fixture
def doctor(db):
    return make_doctor(db)


@pytest.fixture
def patient(db, measurement_types):
    return make_patient(db)


@pytest.fixture
def template(db, doctor):
    return create_template(
        db, code=WELLBEING_CODE, name=WELLBEING_NAME, created_by=doctor.id, spec=WELLBEING_V1
    )


def events(db, alert):
    query = select(AlertEvent).where(AlertEvent.alert_id == alert.id)
    return list(db.scalars(query.order_by(AlertEvent.created_at)))


def rule(db, patient, doctor, rule_type, params, severity=Severity.MODERATE):
    return create_rule(
        db,
        patient_id=patient.patient_profile.id,
        created_by=doctor.id,
        rule_type=rule_type,
        params=params,
        severity=severity,
    )


# --- Időablakos ismétlődés -------------------------------------------------------------


def window_rule(db, patient, doctor, count=3, window_days=7):
    """≥count szisztolés érték 140 felett window_days napon belül (07, 3. rész)."""
    return rule(
        db,
        patient,
        doctor,
        RuleType.WINDOW,
        {
            "measurement_type": "blood_pressure",
            "limits": {"systolic": {"max": 140}},
            "count": count,
            "window_days": window_days,
        },
    )


def test_window_fires_at_exactly_count_violations(db, doctor, patient):
    window_rule(db, patient, doctor)
    m1, none1 = record_bp(db, patient, 146, 85, at=NOW)
    m2, none2 = record_bp(db, patient, 150, 85, at=NOW + timedelta(days=2))
    assert none1 == none2 == []  # count − 1 sértés: még nincs riasztás
    m3, [alert] = record_bp(db, patient, 148, 85, at=NOW + timedelta(days=4))
    assert alert.trigger_data_ids == [str(m1.id), str(m2.id), str(m3.id)]
    [created] = events(db, alert)
    assert created.event_type is AlertEventType.CREATED


def test_window_edge_is_inclusive(db, doctor, patient):
    # Az ablak [új mérés − 7 nap, új mérés]: a pontosan 7 nappal korábbi mérés
    # még beleszámít.
    window_rule(db, patient, doctor)
    first, _ = record_bp(db, patient, 146, 85, at=NOW)
    record_bp(db, patient, 150, 85, at=NOW + timedelta(days=3))
    last, [alert] = record_bp(db, patient, 148, 85, at=NOW + timedelta(days=7))
    assert alert.trigger_data_ids[0] == str(first.id)
    assert alert.trigger_data_ids[-1] == str(last.id)


def test_window_just_past_the_edge_does_not_count(db, doctor, patient):
    window_rule(db, patient, doctor)
    record_bp(db, patient, 146, 85, at=NOW)
    record_bp(db, patient, 150, 85, at=NOW + timedelta(days=3))
    _, touched = record_bp(db, patient, 148, 85, at=NOW + timedelta(days=7, seconds=1))
    assert touched == []


def test_window_triggers_are_all_violations_in_the_window(db, doctor, patient):
    window_rule(db, patient, doctor)
    m1, _ = record_bp(db, patient, 146, 85, at=NOW)
    record_bp(db, patient, 128, 82, at=NOW + timedelta(days=1))  # rendben: nem kiváltó
    m3, _ = record_bp(db, patient, 150, 85, at=NOW + timedelta(days=2))
    m4, [alert] = record_bp(db, patient, 148, 85, at=NOW + timedelta(days=3))
    assert alert.trigger_data_ids == [str(m1.id), str(m3.id), str(m4.id)]

    # Nyitott riasztás mellett az újabb teljesülés ismételt aktiválódás, és a
    # kiváltó az ablak összes sértő mérése (nem csak az utolsó count darab).
    m5, [same] = record_bp(db, patient, 152, 85, at=NOW + timedelta(days=4))
    assert same.id == alert.id
    created, re_triggered = events(db, alert)
    assert re_triggered.event_type is AlertEventType.RE_TRIGGERED
    assert re_triggered.trigger_data_ids == [str(m.id) for m in (m1, m3, m4, m5)]
    assert alert.trigger_data_ids == [str(m1.id), str(m3.id), str(m4.id)]  # a nyitáskori marad


def test_normal_measurement_does_not_reopen_from_old_window_values(db, doctor, patient):
    # 07, 1. rész: lezárás után a rendben lévő mérés nem nyit új riasztást, bár
    # az ablakban még három magas érték van; az újabb magas érték viszont igen.
    window_rule(db, patient, doctor)
    for day in range(3):
        _, touched = record_bp(db, patient, 146, 85, at=NOW + timedelta(days=day))
    [alert] = touched
    alert.status = AlertStatus.CLOSED
    db.flush()
    assert record_bp(db, patient, 128, 82, at=NOW + timedelta(days=3))[1] == []
    _, [new_alert] = record_bp(db, patient, 146, 92, at=NOW + timedelta(days=4))
    assert new_alert.id != alert.id


def test_window_counts_only_the_rule_measurement_type(db, doctor, patient):
    window_rule(db, patient, doctor, count=2)
    record_bp(db, patient, 146, 85, at=NOW)
    record_measurement(
        db,
        patient_id=patient.patient_profile.id,
        type_code="heart_rate",
        values={"value": 150},
        measured_at=NOW + timedelta(hours=1),
        now=NOW + timedelta(hours=1),
    )
    assert len(record_bp(db, patient, 146, 85, at=NOW + timedelta(days=1))[1]) == 1


# --- Romló kérdőív-trend ---------------------------------------------------------------


@pytest.fixture
def wellbeing_patient(db, doctor, template, measurement_types):
    patient = make_patient(db, email="trend@test.example")
    assign_questionnaire(
        db,
        patient_id=patient.patient_profile.id,
        template=template,
        assigned_by=doctor.id,
        start_date=NOW.date() - timedelta(days=7),
    )
    return patient


def submit_score(db, patient, template, score, week):
    """Kitöltés a megadott összpontszámmal (0–4: csak az alvás kérdés romlik),
    a `week`-edik heti időszakban, hogy minden kitöltés külön alkalomra essen."""
    q1, q2, q3 = current_version(db, template.id).questions
    return submit_questionnaire(
        db,
        patient_id=patient.patient_profile.id,
        template_code=WELLBEING_CODE,
        answers={str(q1.id): 5 - score, str(q2.id): 1, str(q3.id): "never"},
        now=NOW + timedelta(days=7 * week),
    )


def trend_rule(db, patient, doctor, count=3):
    return rule(
        db,
        patient,
        doctor,
        RuleType.QUESTIONNAIRE,
        {"questionnaire": WELLBEING_CODE, "trend_count": count},
    )


def test_strictly_increasing_scores_raise_trend_alert(db, doctor, wellbeing_patient, template):
    trend_rule(db, wellbeing_patient, doctor)
    s1, none1 = submit_score(db, wellbeing_patient, template, 0, 0)
    s2, none2 = submit_score(db, wellbeing_patient, template, 1, 1)
    assert none1 == none2 == []  # kevesebb, mint K kitöltés
    s3, [alert] = submit_score(db, wellbeing_patient, template, 3, 2)
    assert s3.total_score == 3
    assert alert.trigger_data_ids == [str(s1.id), str(s2.id), str(s3.id)]


def test_equal_scores_break_the_trend(db, doctor, wellbeing_patient, template):
    trend_rule(db, wellbeing_patient, doctor)
    submit_score(db, wellbeing_patient, template, 0, 0)
    submit_score(db, wellbeing_patient, template, 2, 1)
    assert submit_score(db, wellbeing_patient, template, 2, 2)[1] == []


def test_trend_restarts_after_version_change(db, doctor, wellbeing_patient, template):
    trend_rule(db, wellbeing_patient, doctor)
    submit_score(db, wellbeing_patient, template, 0, 0)
    submit_score(db, wellbeing_patient, template, 1, 1)
    add_version(db, template, WELLBEING_V1)  # v2; a következő alkalom már ezt rögzíti
    s3, touched = submit_score(db, wellbeing_patient, template, 2, 2)
    assert s3.version.version_no == 2
    assert touched == []  # a K-n belül verzióváltás: nincs trend
    s4, touched = submit_score(db, wellbeing_patient, template, 3, 3)
    assert touched == []  # még benne van egy v1-es kitöltés
    s5, [alert] = submit_score(db, wellbeing_patient, template, 4, 4)
    assert alert.trigger_data_ids == [str(s3.id), str(s4.id), str(s5.id)]


def test_trend_rule_ignores_bands(db, doctor, wellbeing_patient, template):
    # Egy szabály = egy feltétel: a trendszabály a kritikus sávra sem riaszt.
    trend_rule(db, wellbeing_patient, doctor)
    q1, q2, q3 = current_version(db, template.id).questions
    _, touched = submit_questionnaire(
        db,
        patient_id=wellbeing_patient.patient_profile.id,
        template_code=WELLBEING_CODE,
        answers={str(q1.id): 1, str(q2.id): 5, str(q3.id): "daily"},  # 13 pont
        now=NOW,
    )
    assert touched == []


# --- Elmaradt adatküldés ---------------------------------------------------------------


def daily_bp_plan(db, patient, doctor, start=date(2026, 10, 1)):
    """Napi vérnyomás-előírás 10:00-s határidővel; a mérés alkalma az időszak
    vége + 48 óra után elmulasztott."""
    return assign_measurement(
        db,
        patient_id=patient.patient_profile.id,
        measurement_type=get_type_by_code(db, "blood_pressure"),
        assigned_by=doctor.id,
        start_date=start,
        due_time=time(10, 0),
    )


def weekly_questionnaire(db, patient, doctor, template, start=date(2026, 10, 6)):
    """Kedden kezdődő heti kérdőív: keddtől hétfőig, határidő hétfő 20:00; az
    alkalom az időszak vége (kedd 0:00) után azonnal elmulasztott."""
    return assign_questionnaire(
        db,
        patient_id=patient.patient_profile.id,
        template=template,
        assigned_by=doctor.id,
        start_date=start,
        frequency=Frequency.WEEKLY,
        due_time=time(20, 0),
    )


def missing_rule(db, patient, doctor, consecutive=2, **target):
    return rule(
        db,
        patient,
        doctor,
        RuleType.MISSING_DATA,
        {**target, "consecutive_missed": consecutive},
    )


def occurrences_of(db, assignment):
    return list(
        db.scalars(
            select(AssignmentOccurrence)
            .where(AssignmentOccurrence.assignment_id == assignment.id)
            .order_by(AssignmentOccurrence.due_at)
        )
    )


def test_missed_measurements_raise_alert_at_the_nth(db, doctor, patient):
    plan = daily_bp_plan(db, patient, doctor)
    rule_ = missing_rule(db, patient, doctor, measurement_type="blood_pressure")
    pid = patient.patient_profile.id

    assert run_occurrence_check(db, local(2026, 10, 4, 0, 0)).missed == 1  # okt. 1.
    assert open_alert(db, pid, rule_.id) is None  # N − 1 elmulasztás: nincs riasztás

    assert run_occurrence_check(db, local(2026, 10, 5, 0, 0)).missed == 1  # okt. 2.
    alert = open_alert(db, pid, rule_.id)
    assert alert is not None
    first, second = occurrences_of(db, plan)[:2]
    assert alert.trigger_data_ids == [str(first.id), str(second.id)]
    assert alert.created_at == local(2026, 10, 5, 0, 0)


def test_repeated_check_does_not_duplicate(db, doctor, patient):
    daily_bp_plan(db, patient, doctor)
    rule_ = missing_rule(db, patient, doctor, measurement_type="blood_pressure")
    run_occurrence_check(db, local(2026, 10, 5, 0, 0))  # okt. 1. és 2. elmulasztva
    alert = open_alert(db, patient.patient_profile.id, rule_.id)
    assert [e.event_type for e in events(db, alert)] == [AlertEventType.CREATED]

    run_occurrence_check(db, local(2026, 10, 5, 0, 10))  # nem zár le semmit
    assert len(events(db, alert)) == 1

    # Újabb elmulasztás nyitott riasztás mellett: ismételt aktiválódás, nem új riasztás.
    run_occurrence_check(db, local(2026, 10, 6, 0, 0))
    assert [e.event_type for e in events(db, alert)] == [
        AlertEventType.CREATED,
        AlertEventType.RE_TRIGGERED,
    ]


def test_late_fulfilment_breaks_the_streak(db, doctor, patient, template):
    plan = weekly_questionnaire(db, patient, doctor, template)
    rule_ = missing_rule(db, patient, doctor, questionnaire=WELLBEING_CODE)
    pid = patient.patient_profile.id

    run_occurrence_check(db, local(2026, 10, 13, 0, 0))  # 1. hét elmulasztva
    # 2. hét: hétfő 20:00 után, de még az időszakban kitöltve → késve teljesítve.
    q1, q2, q3 = current_version(db, template.id).questions
    submit_questionnaire(
        db,
        patient_id=pid,
        template_code=WELLBEING_CODE,
        answers={str(q1.id): 5, str(q2.id): 1, str(q3.id): "never"},
        now=local(2026, 10, 19, 21, 0),
    )
    run_occurrence_check(db, local(2026, 10, 20, 0, 0))
    run_occurrence_check(db, local(2026, 10, 27, 0, 0))  # 3. hét elmulasztva
    statuses = [o.status for o in occurrences_of(db, plan)[:3]]
    assert statuses == [
        OccurrenceStatus.MISSED,
        OccurrenceStatus.FULFILLED_LATE,
        OccurrenceStatus.MISSED,
    ]
    assert open_alert(db, pid, rule_.id) is None

    run_occurrence_check(db, local(2026, 11, 3, 0, 0))  # 4. hét: újra kettő egymás után
    alert = open_alert(db, pid, rule_.id)
    third, fourth = occurrences_of(db, plan)[2:4]
    assert alert.trigger_data_ids == [str(third.id), str(fourth.id)]


def test_missed_other_target_does_not_touch_the_rule(db, doctor, patient, template):
    weekly_questionnaire(db, patient, doctor, template)
    missing_rule(db, patient, doctor, consecutive=1, measurement_type="blood_pressure")
    run_occurrence_check(db, local(2026, 10, 20, 0, 0))  # két kérdőív-alkalom elmulasztva
    assert db.scalars(select(AlertEvent)).all() == []


def test_streak_spans_a_replaced_assignment(db, doctor, patient):
    # Csak a célpont számít: a módosított (lecserélt) előírás alkalmai is a
    # sorozat részei.
    old = daily_bp_plan(db, patient, doctor)
    rule_ = missing_rule(db, patient, doctor, measurement_type="blood_pressure")
    run_occurrence_check(db, local(2026, 10, 4, 0, 0))  # okt. 1. elmulasztva
    # Okt. 4-én a régi lezárul (esedékes alkalmai törlődnek), az új aznap indul.
    revoke(db, old, now=local(2026, 10, 4, 0, 5))
    new = daily_bp_plan(db, patient, doctor, start=date(2026, 10, 4))
    run_occurrence_check(db, local(2026, 10, 6, 0, 0))
    assert open_alert(db, patient.patient_profile.id, rule_.id) is None
    run_occurrence_check(db, local(2026, 10, 7, 0, 0))  # okt. 4. (az új előírásé)
    alert = open_alert(db, patient.patient_profile.id, rule_.id)
    assert alert.trigger_data_ids == [
        str(occurrences_of(db, old)[0].id),
        str(occurrences_of(db, new)[0].id),
    ]


# --- „Szabály módosult" esemény --------------------------------------------------------

BP_135 = {"measurement_type": "blood_pressure", "limits": {"systolic": {"max": 135}}}


def test_rule_change_without_open_alert_adds_no_event(db, doctor, patient):
    rule_ = make_threshold_rule(db, patient, doctor)
    add_rule_version(
        db,
        rule_,
        created_by=doctor.id,
        rule_type=RuleType.THRESHOLD,
        params=BP_135,
        severity=Severity.MODERATE,
    )
    assert db.scalars(select(AlertEvent)).all() == []


def test_rule_change_with_closed_alert_adds_no_event(db, doctor, patient):
    rule_ = make_threshold_rule(db, patient, doctor)
    _, [alert] = record_bp(db, patient, 150, 95, at=NOW)
    alert.status = AlertStatus.CLOSED
    db.flush()
    add_rule_version(
        db,
        rule_,
        created_by=doctor.id,
        rule_type=RuleType.THRESHOLD,
        params=BP_135,
        severity=Severity.MODERATE,
    )
    assert len(events(db, alert)) == 1


def test_rule_change_is_recorded_on_the_open_alert(db, doctor, patient):
    rule_ = make_threshold_rule(db, patient, doctor, severity=Severity.MODERATE)
    measurement, [alert] = record_bp(db, patient, 150, 95, at=NOW)
    opened_version = alert.rule_version_id
    v2 = add_rule_version(
        db,
        rule_,
        created_by=doctor.id,
        rule_type=RuleType.THRESHOLD,
        params=BP_135,
        severity=Severity.SEVERE,
        now=NOW + timedelta(hours=1),
    )
    created, changed = events(db, alert)
    assert changed.event_type is AlertEventType.RULE_CHANGED
    assert changed.actor_id == doctor.id
    assert changed.rule_version_id == v2.id
    assert changed.trigger_data_ids is None
    assert changed.created_at == NOW + timedelta(hours=1)
    # A riasztás jelentése nem változik: a megnyitáskori verzió, súlyosság, kiváltó.
    assert alert.rule_version_id == opened_version
    assert alert.severity is Severity.MODERATE
    assert alert.trigger_data_ids == [str(measurement.id)]
    assert alert.status is AlertStatus.NEW


# --- Paraméter-ellenőrzés és típuszár --------------------------------------------------


@pytest.mark.parametrize(
    "params",
    [
        {"questionnaire": WELLBEING_CODE, "bands": ["warning"], "trend_count": 3},
        {"questionnaire": WELLBEING_CODE},
        {"questionnaire": WELLBEING_CODE, "trend_count": 1},
    ],
)
def test_questionnaire_rule_needs_exactly_one_condition(db, doctor, patient, template, params):
    with pytest.raises(ValueError):
        rule(db, patient, doctor, RuleType.QUESTIONNAIRE, params)


def test_trend_rule_checks_the_questionnaire(db, doctor, patient):
    with pytest.raises(ValueError, match="Ismeretlen kérdőív"):
        rule(db, patient, doctor, RuleType.QUESTIONNAIRE, {"questionnaire": "x", "trend_count": 3})


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ({"measurement_type": "blood_presure", "consecutive_missed": 2}, "Ismeretlen méréstípus"),
        ({"questionnaire": "nincs-ilyen", "consecutive_missed": 2}, "Ismeretlen kérdőív"),
        (
            {"measurement_type": "blood_pressure", "questionnaire": "x", "consecutive_missed": 2},
            "pontosan egy",
        ),
        ({"consecutive_missed": 2}, "pontosan egy"),
        ({"measurement_type": "blood_pressure", "consecutive_missed": 0}, "consecutive_missed"),
    ],
)
def test_invalid_missing_data_params_are_rejected(db, doctor, patient, params, message):
    with pytest.raises(ValueError, match=message):
        rule(db, patient, doctor, RuleType.MISSING_DATA, params)


@pytest.mark.parametrize(
    "change",
    [
        {"count": 1},
        {"window_days": 0},
        {"limits": {}},
    ],
)
def test_invalid_window_params_are_rejected(db, doctor, patient, change):
    params = {
        "measurement_type": "blood_pressure",
        "limits": {"systolic": {"max": 140}},
        "count": 3,
        "window_days": 7,
        **change,
    }
    with pytest.raises(ValueError):
        rule(db, patient, doctor, RuleType.WINDOW, params)


def test_rule_type_cannot_change_between_versions(db, doctor, patient):
    rule_ = make_threshold_rule(db, patient, doctor)
    with pytest.raises(ValueError, match="típusa nem módosítható"):
        add_rule_version(
            db,
            rule_,
            created_by=doctor.id,
            rule_type=RuleType.WINDOW,
            params={**BP_135, "count": 3, "window_days": 7},
            severity=Severity.MODERATE,
        )
