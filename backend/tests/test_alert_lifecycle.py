"""A riasztás-életút szolgáltatása és a Kezelve státusz (M3, A6;
07_mukodesi_szabalyok.md, 1. rész; a hallgató döntései D4a + D5)."""

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models import (
    AlertEvent,
    AlertEventType,
    AlertStatus,
    AssignmentOccurrence,
    Notification,
    OccurrenceStatus,
    RuleType,
    Severity,
)
from app.services.alerts import AlertError, assign_alert, close_alert, mark_seen
from app.services.measurements import get_type_by_code, record_measurement
from app.services.notifications import recent_alert_feedback
from app.services.occurrences import run_occurrence_check
from app.services.questionnaires import (
    assign_questionnaire,
    create_template,
    current_version,
    submit_questionnaire,
)
from app.services.rules import add_rule_version, create_rule, open_alert
from app.services.status import PatientStatus, compute_status
from app.services.tasks import assign_measurement
from seed.questionnaires import WELLBEING_CODE, WELLBEING_NAME, WELLBEING_V1
from tests.factories import assign, make_doctor, make_patient, make_threshold_rule, record_bp


def local(y, m, d, hh=0, mm=0):
    """Időpont a rendszer időzónájában (Europe/Budapest)."""
    return datetime(y, m, d, hh, mm, tzinfo=settings.tz)


SINCE = local(2026, 8, 1)


@pytest.fixture
def doctor(db):
    return make_doctor(db, name="Dr. Szabó")


@pytest.fixture
def patient(db, measurement_types, doctor):
    patient = make_patient(db)
    assign(db, doctor, patient, valid_from=SINCE)
    return patient


def rule(db, patient, doctor, rule_type, params, severity=Severity.MODERATE):
    return create_rule(
        db,
        patient_id=patient.patient_profile.id,
        created_by=doctor.id,
        rule_type=rule_type,
        params=params,
        severity=severity,
    )


def events(db, alert):
    query = select(AlertEvent).where(AlertEvent.alert_id == alert.id)
    return list(db.scalars(query.order_by(AlertEvent.created_at, AlertEvent.id)))


def status_of(db, patient, now):
    return compute_status(db, patient.patient_profile.id, now)


def codes(result):
    return [r.code for r in result.reasons]


# --- Állapotgép ------------------------------------------------------------------------


@pytest.fixture
def alert(db, doctor, patient):
    make_threshold_rule(db, patient, doctor)
    _, [alert] = record_bp(db, patient, 150, 95, at=local(2026, 9, 1, 8))
    return alert


def test_seen_is_idempotent_and_records_the_actor(db, doctor, alert):
    t = local(2026, 9, 1, 9)
    assert mark_seen(db, alert, doctor, now=t) is True
    assert mark_seen(db, alert, doctor, now=t + timedelta(hours=1)) is False
    assert alert.status is AlertStatus.SEEN
    seen = [e for e in events(db, alert) if e.event_type is AlertEventType.SEEN]
    assert [(e.actor_id, e.created_at) for e in seen] == [(doctor.id, t)]


def test_seen_after_assign_does_not_step_back(db, doctor, alert):
    assign_alert(db, alert, doctor, doctor, now=local(2026, 9, 1, 9))
    assert mark_seen(db, alert, doctor) is False
    assert alert.status is AlertStatus.ASSIGNED


def test_steps_can_be_skipped_and_every_change_is_an_event(db, doctor, patient, alert):
    colleague = make_doctor(db, email="kollega@test.example", name="Dr. Kolléga")
    assign(db, colleague, patient, valid_from=SINCE)
    assign_alert(db, alert, doctor, colleague, now=local(2026, 9, 1, 9))  # new → assigned
    assert (alert.status, alert.assigned_to) == (AlertStatus.ASSIGNED, colleague.id)
    assign_alert(db, alert, colleague, colleague, now=local(2026, 9, 1, 10))  # újra
    close_alert(db, alert, colleague, "Egyeztetve.", now=local(2026, 9, 1, 11))
    assert alert.status is AlertStatus.CLOSED
    assert [(e.event_type, e.actor_id, e.reason) for e in events(db, alert)] == [
        (AlertEventType.CREATED, None, None),
        (AlertEventType.ASSIGNED, doctor.id, None),
        (AlertEventType.ASSIGNED, colleague.id, None),
        (AlertEventType.CLOSED, colleague.id, "Egyeztetve."),
    ]


def test_only_a_currently_assigned_doctor_can_be_responsible(db, doctor, patient, alert):
    stranger = make_doctor(db, email="idegen@test.example", name="Dr. Idegen")
    with pytest.raises(AlertError) as error:
        assign_alert(db, alert, doctor, stranger)
    assert (error.value.code, error.value.conflict) == ("doctor_not_assigned", False)
    # Lejárt összerendelés sem elég.
    former = make_doctor(db, email="volt@test.example", name="Dr. Volt")
    assign(db, former, patient, valid_from=SINCE, valid_to=local(2026, 8, 15))
    with pytest.raises(AlertError):
        assign_alert(db, alert, doctor, former)
    with pytest.raises(AlertError):
        assign_alert(db, alert, doctor, patient)  # beteg nem lehet felelős
    with pytest.raises(AlertError):
        assign_alert(db, alert, doctor, None)  # nem létező felhasználó
    assert alert.status is AlertStatus.NEW and alert.assigned_to is None


def test_closed_alert_rejects_every_further_change(db, doctor, alert):
    close_alert(db, alert, doctor, "Rendben.", now=local(2026, 9, 1, 9))
    for action in (
        lambda: mark_seen(db, alert, doctor),
        lambda: assign_alert(db, alert, doctor, doctor),
        lambda: close_alert(db, alert, doctor, "Még egyszer."),
    ):
        with pytest.raises(AlertError) as error:
            action()
        assert (error.value.code, error.value.conflict) == ("already_closed", True)
    assert len(events(db, alert)) == 2  # created + closed


def test_blank_reason_is_rejected(db, doctor, alert):
    with pytest.raises(AlertError) as error:
        close_alert(db, alert, doctor, "   ")
    assert error.value.code == "reason_required"
    assert alert.status is AlertStatus.NEW


def test_message_creates_a_notification_without_message_none(db, doctor, patient):
    make_threshold_rule(db, patient, doctor)
    _, [first] = record_bp(db, patient, 150, 95, at=local(2026, 9, 1, 8))
    assert close_alert(db, first, doctor, "Rendben.", message="  ") is None
    _, [second] = record_bp(db, patient, 152, 95, at=local(2026, 9, 2, 8))
    t = local(2026, 9, 2, 9)
    notification = close_alert(
        db, second, doctor, "Gyógyszer módosítva.", message="Mérjen naponta kétszer.", now=t
    )
    assert notification is not None
    assert (notification.patient_id, notification.alert_id, notification.created_by) == (
        patient.patient_profile.id,
        second.id,
        doctor.id,
    )
    assert (notification.text, notification.created_at) == ("Mérjen naponta kétszer.", t)
    assert len(db.scalars(select(Notification)).all()) == 1


def test_feedback_is_shown_for_7_days_and_only_to_its_patient(db, doctor, patient, alert):
    other = make_patient(db, email="masik@test.example", name="Másik Beteg")
    t = local(2026, 9, 1, 9)
    close_alert(db, alert, doctor, "Rendben.", message="Minden rendben.", now=t)
    pid = patient.patient_profile.id
    [feedback] = recent_alert_feedback(db, pid, now=t + timedelta(days=7))
    assert (feedback.notification.text, feedback.doctor_name) == ("Minden rendben.", "Dr. Szabó")
    assert (feedback.rule_type, feedback.target_code) == (RuleType.THRESHOLD, "blood_pressure")
    assert recent_alert_feedback(db, pid, now=t + timedelta(days=8)) == []
    assert recent_alert_feedback(db, other.patient_profile.id, now=t + timedelta(hours=1)) == []


# --- Kezelve: a 07/1. példa mindhárom kimenete ----------------------------------------


@pytest.fixture
def closed_window_alert(db, doctor, patient):
    """07/1.: ≥3 szisztolés 140 felett 7 napon belül (közepes). Szept. 12., 14.,
    16. (riasztás) és 18. (ismételt aktiválódás); az orvos szept. 21. 10:02-kor
    lezárja."""
    rule(
        db,
        patient,
        doctor,
        RuleType.WINDOW,
        {
            "measurement_type": "blood_pressure",
            "limits": {"systolic": {"max": 140}, "diastolic": {"max": 90}},
            "count": 3,
            "window_days": 7,
        },
    )
    for day in (12, 14):
        assert record_bp(db, patient, 146, 88, at=local(2026, 9, day, 7, 40))[1] == []
    _, [alert] = record_bp(db, patient, 148, 92, at=local(2026, 9, 16, 7, 40))
    assert record_bp(db, patient, 144, 90, at=local(2026, 9, 18, 7, 40))[1] == [alert]
    assert status_of(db, patient, local(2026, 9, 20)).status is PatientStatus.ATTENTION
    close_alert(
        db,
        alert,
        doctor,
        "Telefonon egyeztettem, gyógyszer módosítva.",
        now=local(2026, 9, 21, 10, 2),
    )
    return alert


def test_closed_without_confirming_data_is_handled(db, doctor, patient, closed_window_alert):
    result = status_of(db, patient, local(2026, 9, 21, 11))
    assert result.status is PatientStatus.HANDLED
    [reason] = result.reasons
    assert reason.code == "closed_awaiting_data"
    assert reason.alert.id == closed_window_alert.id
    assert (reason.at, reason.actor_id) == (local(2026, 9, 21, 10, 2), doctor.id)


def test_outcome_1_confirming_measurement_gives_ok(db, patient, closed_window_alert):
    assert record_bp(db, patient, 128, 82, at=local(2026, 9, 22, 7, 40))[1] == []
    result = status_of(db, patient, local(2026, 9, 22, 8))
    assert result.status is PatientStatus.OK
    assert codes(result) == ["fresh_data"]


def test_outcome_2_missed_measurement_gives_no_data(db, doctor, patient, closed_window_alert):
    assign_measurement(
        db,
        patient_id=patient.patient_profile.id,
        measurement_type=get_type_by_code(db, "blood_pressure"),
        assigned_by=doctor.id,
        start_date=date(2026, 9, 22),
    )
    # A szept. 22-i alkalom a pótlási idő (időszak vége + 48 óra) után elmulasztott.
    now = local(2026, 9, 25, 0, 30)
    run_occurrence_check(db, now)
    result = status_of(db, patient, now)
    assert result.status is PatientStatus.NO_DATA
    assert codes(result) == ["missed_occurrence", "closed_awaiting_data"]


def test_outcome_3_high_again_opens_a_new_alert(db, patient, closed_window_alert):
    # A 7 napos ablakban a szept. 16-i és 18-i érték is benne van → azonnal új riasztás.
    _, [new] = record_bp(db, patient, 146, 92, at=local(2026, 9, 22, 7, 40))
    assert new.id != closed_window_alert.id
    assert new.status is AlertStatus.NEW
    result = status_of(db, patient, local(2026, 9, 22, 8))
    assert result.status is PatientStatus.ATTENTION
    # Ugyanarra a szabályra a nyitott riasztás mellett nincs „megerősítő adatra vár".
    assert codes(result) == ["open_alert"]


def test_measurement_before_the_closure_does_not_confirm(db, patient, closed_window_alert):
    # A lezárás UTÁN rögzített, de a lezárás ELŐTTI mérési idejű (visszadátumozott)
    # normál érték nem megerősítés: a mérés ideje dönt, nem a rögzítésé.
    record_measurement(
        db,
        patient_id=patient.patient_profile.id,
        type_code="blood_pressure",
        values={"systolic": 120, "diastolic": 80},
        measured_at=local(2026, 9, 21, 9),
        now=local(2026, 9, 21, 12),
    )
    assert status_of(db, patient, local(2026, 9, 21, 13)).status is PatientStatus.HANDLED


def test_other_measurement_type_does_not_confirm(db, patient, doctor):
    make_threshold_rule(db, patient, doctor)
    _, [alert] = record_bp(db, patient, 150, 95, at=local(2026, 9, 1, 8))
    close_alert(db, alert, doctor, "Rendben.", now=local(2026, 9, 1, 9))
    # A pulzus nem a vérnyomás-szabály célpontja.
    at = local(2026, 9, 1, 10)
    record_measurement(
        db,
        patient_id=patient.patient_profile.id,
        type_code="heart_rate",
        values={"value": 72},
        measured_at=at,
        now=at,
    )
    assert status_of(db, patient, local(2026, 9, 1, 11)).status is PatientStatus.HANDLED


def test_two_rules_each_need_their_own_confirmation(db, doctor, patient):
    make_threshold_rule(db, patient, doctor, limits={"systolic": {"max": 140}})
    make_threshold_rule(
        db, patient, doctor, limits={"systolic": {"max": 180}}, severity=Severity.SEVERE
    )
    _, alerts = record_bp(db, patient, 190, 95, at=local(2026, 9, 1, 8))
    for i, a in enumerate(alerts):
        close_alert(db, a, doctor, "Rendben.", now=local(2026, 9, 1, 9 + i))
    result = status_of(db, patient, local(2026, 9, 1, 12))
    assert codes(result) == ["closed_awaiting_data", "closed_awaiting_data"]
    # 150: a 180-as szabály szerint rendben, a 140-es szerint új riasztás.
    _, [new] = record_bp(db, patient, 150, 85, at=local(2026, 9, 2, 8))
    result = status_of(db, patient, local(2026, 9, 2, 9))
    assert result.status is PatientStatus.ATTENTION
    assert codes(result) == ["open_alert"]
    assert result.reasons[0].alert.id == new.id


def test_current_rule_version_decides_what_is_ok(db, doctor, patient):
    rule_ = make_threshold_rule(db, patient, doctor, limits={"systolic": {"max": 140}})
    _, [alert] = record_bp(db, patient, 150, 85, at=local(2026, 9, 1, 8))
    close_alert(db, alert, doctor, "Rendben.", now=local(2026, 9, 1, 9))
    add_rule_version(
        db,
        rule_,
        created_by=doctor.id,
        rule_type=RuleType.THRESHOLD,
        params={"measurement_type": "blood_pressure", "limits": {"systolic": {"max": 150}}},
        severity=Severity.MODERATE,
    )
    # 145: a lezárt riasztás verziója (v1, >140) szerint határsértő volna, az
    # aktuális (v2, >150) szerint rendben: ez dönt.
    assert record_bp(db, patient, 145, 85, at=local(2026, 9, 2, 8))[1] == []
    assert status_of(db, patient, local(2026, 9, 2, 9)).status is PatientStatus.OK


# --- Kezelve: elmaradt adat és kérdőív -------------------------------------------------


def test_missing_data_rule_is_confirmed_by_a_fulfilled_occurrence(db, doctor, patient):
    assign_measurement(
        db,
        patient_id=patient.patient_profile.id,
        measurement_type=get_type_by_code(db, "blood_pressure"),
        assigned_by=doctor.id,
        start_date=date(2026, 10, 1),
    )
    rule_ = rule(
        db,
        patient,
        doctor,
        RuleType.MISSING_DATA,
        {"measurement_type": "blood_pressure", "consecutive_missed": 2},
    )
    run_occurrence_check(db, local(2026, 10, 5, 0, 0))  # okt. 1. és 2. elmulasztva
    alert = open_alert(db, patient.patient_profile.id, rule_.id)
    close_alert(db, alert, doctor, "Felhívtam, újra mér.", now=local(2026, 10, 5, 0, 30))
    result = status_of(db, patient, local(2026, 10, 5, 1))
    assert codes(result) == ["missed_occurrence", "no_data_yet", "closed_awaiting_data"]

    record_bp(db, patient, 125, 80, at=local(2026, 10, 5, 7, 30))  # az okt. 5-i alkalom
    result = status_of(db, patient, local(2026, 10, 5, 8))
    assert result.status is PatientStatus.OK
    assert codes(result) == ["fresh_data"]


@pytest.fixture
def closed_missing_alert(db, doctor, patient):
    """Napi vérnyomás okt. 1-jétől; 2 egymást követő elmulasztás riaszt. Okt. 5.
    0:00-kor az okt. 1-i és 2-i alkalom elmulasztott (riasztás), az orvos 0:30-kor
    lezárja. Az okt. 3-i és 4-i alkalom ekkor még esedékes (pótlási időben)."""
    assign_measurement(
        db,
        patient_id=patient.patient_profile.id,
        measurement_type=get_type_by_code(db, "blood_pressure"),
        assigned_by=doctor.id,
        start_date=date(2026, 10, 1),
    )
    rule_ = rule(
        db,
        patient,
        doctor,
        RuleType.MISSING_DATA,
        {"measurement_type": "blood_pressure", "consecutive_missed": 2},
    )
    run_occurrence_check(db, local(2026, 10, 5, 0, 0))
    alert = open_alert(db, patient.patient_profile.id, rule_.id)
    close_alert(db, alert, doctor, "Felhívtam, pótolja.", now=local(2026, 10, 5, 0, 30))
    return alert


def test_missing_data_late_fulfilment_after_closing_gives_ok(db, patient, closed_missing_alert):
    """Kezelve → Rendben: a lezárás után KÉSVE teljesített alkalom (a határidő
    utáni, de a pótlási időn belüli visszadátumozott mérés) is megerősítés, mert a
    státusz a teljesített és a késve teljesített alkalmat egyaránt elfogadja."""
    # Előtte: az okt. 2-i mulasztás (Adathiány) és a Kezelve ok is él.
    before = status_of(db, patient, local(2026, 10, 5, 0, 45))
    assert "closed_awaiting_data" in codes(before)
    _, touched = record_measurement(
        db,
        patient_id=patient.patient_profile.id,
        type_code="blood_pressure",
        values={"systolic": 125, "diastolic": 80},
        measured_at=local(2026, 10, 3, 8),  # az okt. 3-i időszakba esik
        now=local(2026, 10, 5, 1),  # a határidő után rögzítve
    )
    assert touched == []
    occurrence = db.scalar(
        select(AssignmentOccurrence).where(AssignmentOccurrence.fulfilled_at.is_not(None))
    )
    assert occurrence.status is OccurrenceStatus.FULFILLED_LATE
    result = status_of(db, patient, local(2026, 10, 5, 2))
    assert result.status is PatientStatus.OK
    assert codes(result) == ["fresh_data"]


def test_missing_data_new_miss_after_closing_opens_a_new_alert(db, patient, closed_missing_alert):
    """A lezárás után egy újabb elmulasztás (okt. 3.) új, különálló riasztást
    nyit; a lezárt riasztás története változatlan (nem kap ismételt aktiválódást)."""
    before = [e.event_type for e in events(db, closed_missing_alert)]
    assert before == [AlertEventType.CREATED, AlertEventType.CLOSED]
    run_occurrence_check(db, local(2026, 10, 6, 0, 0))  # az okt. 3-i alkalom elmulasztva
    new = open_alert(db, patient.patient_profile.id, closed_missing_alert.rule_id)
    assert new is not None and new.id != closed_missing_alert.id
    assert new.status is AlertStatus.NEW
    assert [e.event_type for e in events(db, new)] == [AlertEventType.CREATED]
    assert [e.event_type for e in events(db, closed_missing_alert)] == before
    assert status_of(db, patient, local(2026, 10, 6, 1)).status is PatientStatus.ATTENTION


@pytest.fixture
def template(db, doctor):
    return create_template(
        db, code=WELLBEING_CODE, name=WELLBEING_NAME, created_by=doctor.id, spec=WELLBEING_V1
    )


QNOW = local(2026, 10, 6, 9)


def submit(db, patient, template, sleep, tired, week):
    """Kitöltés a `week`-edik heti időszakban; a pont: (5 − alvás) + (fáradtság − 1)."""
    q1, q2, q3 = current_version(db, template.id).questions
    return submit_questionnaire(
        db,
        patient_id=patient.patient_profile.id,
        template_code=WELLBEING_CODE,
        answers={str(q1.id): sleep, str(q2.id): tired, str(q3.id): "never"},
        now=QNOW + timedelta(days=7 * week),
    )


@pytest.fixture
def q_patient(db, doctor, patient, template):
    assign_questionnaire(
        db,
        patient_id=patient.patient_profile.id,
        template=template,
        assigned_by=doctor.id,
        start_date=QNOW.date() - timedelta(days=1),
    )
    return patient


def test_band_rule_is_confirmed_by_a_submission_outside_the_bands(db, doctor, q_patient, template):
    rule(
        db,
        q_patient,
        doctor,
        RuleType.QUESTIONNAIRE,
        {"questionnaire": WELLBEING_CODE, "bands": ["warning", "critical"]},
    )
    submission, [alert] = submit(db, q_patient, template, 1, 3, 0)  # 4 + 2 = 6: figyelmeztető
    assert submission.total_score == 6
    close_alert(db, alert, doctor, "Egyeztetve.", now=QNOW + timedelta(hours=1))
    assert status_of(db, q_patient, QNOW + timedelta(hours=2)).status is PatientStatus.HANDLED

    good, touched = submit(db, q_patient, template, 5, 1, 1)  # 0 pont: rendben sáv
    assert (good.total_score, touched) == (0, [])
    result = status_of(db, q_patient, QNOW + timedelta(days=7, hours=1))
    assert result.status is PatientStatus.OK


def test_trend_rule_is_confirmed_by_a_submission_without_trend(db, doctor, q_patient, template):
    rule(
        db,
        q_patient,
        doctor,
        RuleType.QUESTIONNAIRE,
        {"questionnaire": WELLBEING_CODE, "trend_count": 3},
    )
    submit(db, q_patient, template, 5, 1, 0)  # 0
    submit(db, q_patient, template, 4, 1, 1)  # 1
    _, [alert] = submit(db, q_patient, template, 3, 1, 2)  # 2: szigorúan nő → trend
    close_alert(db, alert, doctor, "Egyeztetve.", now=QNOW + timedelta(days=14, hours=1))
    later = QNOW + timedelta(days=14, hours=2)
    assert status_of(db, q_patient, later).status is PatientStatus.HANDLED

    _, touched = submit(db, q_patient, template, 4, 1, 3)  # 1: a trend megszakad
    assert touched == []
    assert status_of(db, q_patient, QNOW + timedelta(days=21, hours=1)).status is (PatientStatus.OK)
