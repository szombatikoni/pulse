"""Az előírások tárolt alkalmai (M3, A2): nyitás, lezárás, hozzárendelés a mentéskor
(docs/M1/03_adatmodell.md, „Előírás és alkalom"; tervezet: a2_terv_2026-10-30.md)."""

from datetime import UTC, date, datetime, time, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from app.core.config import settings
from app.models import AssignmentOccurrence, Frequency, OccurrenceStatus
from app.services import occurrences
from app.services.measurements import MeasurementError, get_type_by_code, record_measurement
from app.services.occurrences import (
    OccurrenceCheck,
    close_missed_occurrences,
    fill_version,
    open_due_occurrences,
    period_containing,
    period_end,
    run_occurrence_check,
)
from app.services.questionnaires import (
    SubmissionError,
    VersionSpec,
    add_version,
    assign_questionnaire,
    band_for,
    create_template,
    submit_questionnaire,
)
from app.services.tasks import TaskState, _last_data_at, assign_measurement, patient_tasks
from seed.demo import seed_demo_data
from seed.questionnaires import WELLBEING_CODE, WELLBEING_NAME, WELLBEING_V1
from tests.factories import assign, make_doctor, make_measurement_types, make_patient

VALUES = {
    "blood_pressure": {"systolic": 128, "diastolic": 82},
    "heart_rate": {"value": 72},
    "body_weight": {"value": 80},
    "blood_glucose": {"value": 6.1},
}


def local(y, m, d, hh=0, mm=0):
    """Időpont a rendszer időzónájában (Europe/Budapest)."""
    return datetime(y, m, d, hh, mm, tzinfo=settings.tz)


@pytest.fixture
def setup(db):
    make_measurement_types(db)
    doctor = make_doctor(db)
    patient = make_patient(db)
    assign(db, doctor, patient)
    return {"doctor": doctor, "patient": patient, "pid": patient.patient_profile.id}


def plan(db, setup, code="blood_pressure", start=date(2026, 10, 1), due=time(10, 0), **kwargs):
    return assign_measurement(
        db,
        patient_id=setup["pid"],
        measurement_type=get_type_by_code(db, code),
        assigned_by=setup["doctor"].id,
        start_date=start,
        due_time=due,
        **kwargs,
    )


def record(db, setup, measured_at, now=None, code="blood_pressure"):
    measurement, _ = record_measurement(
        db,
        patient_id=setup["pid"],
        type_code=code,
        values=VALUES[code],
        measured_at=measured_at,
        now=now or measured_at,
    )
    return measurement


@pytest.fixture
def template(db, setup):
    return create_template(
        db,
        code=WELLBEING_CODE,
        name=WELLBEING_NAME,
        created_by=setup["doctor"].id,
        spec=WELLBEING_V1,
    )


def weekly_questionnaire(db, setup, template, start=date(2026, 10, 6)):
    """Kedden (alapból okt. 6.) kezdődő heti kérdőív: keddtől hétfőig, határidő
    hétfő 20:00."""
    return assign_questionnaire(
        db,
        patient_id=setup["pid"],
        template=template,
        assigned_by=setup["doctor"].id,
        start_date=start,
        frequency=Frequency.WEEKLY,
        due_time=time(20, 0),
    )


def fill(db, setup, template, now):
    """Kitöltés azokkal a kérdésekkel, amelyeket a felület is kapna (az aktuális
    időszak alkalmának verziója)."""
    day = now.astimezone(settings.tz).date()
    questions = fill_version(db, setup["pid"], template.id, day).questions
    submission, _ = submit_questionnaire(
        db,
        patient_id=setup["pid"],
        template_code=WELLBEING_CODE,
        answers={str(q.id): q.options_scores[0]["value"] for q in questions},
        now=now,
    )
    return submission


def occurrences_of(db, assignment):
    return list(
        db.scalars(
            select(AssignmentOccurrence)
            .where(AssignmentOccurrence.assignment_id == assignment.id)
            .order_by(AssignmentOccurrence.due_at)
        )
    )


def snapshot(db):
    rows = db.execute(
        select(
            AssignmentOccurrence.assignment_id,
            AssignmentOccurrence.due_at,
            AssignmentOccurrence.status,
        ).order_by(AssignmentOccurrence.assignment_id, AssignmentOccurrence.due_at)
    )
    return [tuple(row) for row in rows]


# --- Nyitás és lezárás: idempotencia -------------------------------------------------


def test_running_the_check_twice_gives_the_same_state(db, setup, template):
    bp = plan(db, setup, start=date(2026, 10, 17))
    wellbeing = weekly_questionnaire(db, setup, template, start=date(2026, 10, 13))

    first = run_occurrence_check(db, local(2026, 10, 17, 8, 0))
    assert (first.opened, first.missed) == (2, 0)
    state = snapshot(db)
    again = run_occurrence_check(db, local(2026, 10, 17, 8, 10))
    assert (again.opened, again.missed) == (0, 0)
    assert snapshot(db) == state

    # Három nappal később: a 18–20-i mérés és az új heti kérdőív alkalma nyílik meg;
    # a 17-i mérés pótlási ideje és az előző heti kérdőív időszaka lejárt.
    later = run_occurrence_check(db, local(2026, 10, 20, 9, 0))
    assert (later.opened, later.missed) == (4, 2)
    state = snapshot(db)
    assert run_occurrence_check(db, local(2026, 10, 20, 9, 10)) == OccurrenceCheck(0, 0)
    assert snapshot(db) == state

    assert [o.status for o in occurrences_of(db, bp)] == [
        OccurrenceStatus.MISSED,
        OccurrenceStatus.DUE,
        OccurrenceStatus.DUE,
        OccurrenceStatus.DUE,
    ]
    assert [o.status for o in occurrences_of(db, wellbeing)] == [
        OccurrenceStatus.MISSED,
        OccurrenceStatus.DUE,
    ]


def test_no_future_occurrences_are_created(db, setup):
    bp = plan(db, setup, start=date(2026, 10, 17))
    open_due_occurrences(db, local(2026, 10, 17, 8, 0))
    [occurrence] = occurrences_of(db, bp)
    assert occurrence.due_at == local(2026, 10, 17, 10, 0)


# --- Visszamenőleges nyitás (a hallgató döntése, 2026-10-30) ------------------------------


def test_missing_past_periods_are_opened_and_closed(db, setup):
    """Ha a háttérfolyamat a kezdet óta nem futott, az első futás minden kimaradt
    időszak alkalmát megnyitja, és a lejártakat a szokott szabállyal zárja."""
    bp = plan(db, setup)  # okt. 1-től naponta, határidő 10:00
    # Egy korábbi mérés már létrehozta és teljesítette a saját alkalmát.
    record(db, setup, local(2026, 10, 5, 9, 0))

    result = run_occurrence_check(db, local(2026, 10, 17, 12, 0))
    stored = occurrences_of(db, bp)
    # 17 időszak (okt. 1–17.), ebből egy már megvolt; a holnapi (jövőbeli) nem nyílik meg.
    assert result.opened == 16
    assert [o.due_at for o in stored] == [local(2026, 10, d, 10, 0) for d in range(1, 18)]
    # Okt. 14-ig a pótlási ablak is lejárt (13 elmulasztott + a teljesített okt. 5.);
    # okt. 15–17. még pótolható, tehát esedékes.
    assert result.missed == 13
    statuses = [o.status for o in stored]
    assert statuses[4] is OccurrenceStatus.FULFILLED
    assert statuses[:4] + statuses[5:14] == [OccurrenceStatus.MISSED] * 13
    assert statuses[14:] == [OccurrenceStatus.DUE] * 3

    assert run_occurrence_check(db, local(2026, 10, 17, 12, 5)) == OccurrenceCheck(0, 0)
    assert len(occurrences_of(db, bp)) == 17


def test_ended_assignment_gets_occurrences_only_until_its_end(db, setup):
    """A lejárt előírás kimaradt időszakai is megnyílnak, de csak a vége
    (end_date) előtt kezdődők; a vége napját tartalmazó időszak még igen."""
    weight = plan(
        db,
        setup,
        code="body_weight",
        start=date(2026, 10, 6),
        due=time(20, 0),
        frequency=Frequency.WEEKLY,
    )
    weight.end_date = date(2026, 10, 15)  # a második hét közepe
    db.flush()

    assert open_due_occurrences(db, local(2026, 10, 30, 8, 0)) == 2
    assert [o.period_start for o in occurrences_of(db, weight)] == [
        local(2026, 10, 6),
        local(2026, 10, 13),
    ]


def test_unique_key_rejects_a_duplicate_occurrence(db, setup):
    bp = plan(db, setup)
    open_due_occurrences(db, local(2026, 10, 17, 8, 0))
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(
            AssignmentOccurrence(
                assignment_id=bp.id,
                period_start=local(2026, 10, 17),
                due_at=local(2026, 10, 17, 10, 0),
            )
        )
        db.flush()


def test_concurrent_creation_is_absorbed_by_the_unique_key(db, setup, monkeypatch):
    """Ha a háttérfolyamat és a mentés egyszerre nyitná ugyanazt az alkalmat, a
    második beszúrás csendben elmarad, és mindkettő ugyanazt a sort kapja."""
    bp = plan(db, setup, start=date(2026, 10, 17))
    open_due_occurrences(db, local(2026, 10, 17, 8, 0))
    [existing] = occurrences_of(db, bp)

    # A másik fél még nem látta a sort: az előzetes keresés üres, a beszúrás ütközik.
    real_find = occurrences._find
    missing_once = [True]

    def find(*args):
        return None if missing_once and missing_once.pop() else real_find(*args)

    monkeypatch.setattr(occurrences, "_find", find)
    measurement = record(db, setup, local(2026, 10, 17, 9, 0))

    assert occurrences_of(db, bp) == [existing]
    assert existing.status is OccurrenceStatus.FULFILLED
    assert existing.measurement_id == measurement.id

    missing_once.append(True)
    occurrence, created = occurrences._ensure(db, bp, period_containing(bp, date(2026, 10, 17)))
    assert (occurrence, created) == (existing, False)


# --- Időszak-szélek ------------------------------------------------------------------


def test_daily_period_follows_the_local_midnight(db, setup):
    bp = plan(db, setup, start=date(2026, 10, 17))
    open_due_occurrences(db, local(2026, 10, 17, 23, 30))
    # 00:10 helyi idő = előző nap 22:10 UTC, mégis új időszak.
    after_midnight = local(2026, 10, 18, 0, 10)
    assert after_midnight.astimezone(UTC).date() == date(2026, 10, 17)
    open_due_occurrences(db, after_midnight)

    first, second = occurrences_of(db, bp)
    assert (first.period_start, first.due_at) == (local(2026, 10, 17), local(2026, 10, 17, 10))
    assert (second.period_start, second.due_at) == (local(2026, 10, 18), local(2026, 10, 18, 10))

    # A 23:50-kor (helyi) mért érték a 17-i alkalmat teljesíti, késve.
    record(db, setup, local(2026, 10, 17, 23, 50))
    assert first.status is OccurrenceStatus.FULFILLED_LATE
    assert second.status is OccurrenceStatus.DUE


def test_period_on_the_daylight_saving_change_day(db, setup):
    """Október 25-én (óraátállítás) a helyi nap 25 órás; az időszak akkor is
    éjféltől éjfélig tart."""
    bp = plan(db, setup, start=date(2026, 10, 25))
    period = period_containing(bp, date(2026, 10, 25))
    assert (period.start, period.end) == (local(2026, 10, 25), local(2026, 10, 26))
    assert period.end.astimezone(UTC) - period.start.astimezone(UTC) == timedelta(hours=25)

    open_due_occurrences(db, local(2026, 10, 25, 8, 0))
    # A pótlási ablak az időszak vége után két nappal zárul (okt. 28. 00:00 helyi).
    assert close_missed_occurrences(db, local(2026, 10, 27, 23, 59)) == 0
    assert close_missed_occurrences(db, local(2026, 10, 28, 0, 0)) == 1


def test_weekly_period_boundary(db, setup):
    weight = plan(
        db,
        setup,
        code="body_weight",
        start=date(2026, 10, 6),
        due=time(20, 0),
        frequency=Frequency.WEEKLY,
    )
    assert open_due_occurrences(db, local(2026, 10, 19, 23, 59)) == 2  # okt. 6. és 13.
    assert open_due_occurrences(db, local(2026, 10, 20, 0, 0)) == 1
    _, first, second = occurrences_of(db, weight)
    # A határidő az időszak utolsó napján (hétfőn) van.
    assert (first.period_start, first.due_at) == (local(2026, 10, 13), local(2026, 10, 19, 20))
    assert (second.period_start, second.due_at) == (local(2026, 10, 20), local(2026, 10, 26, 20))


def test_every_n_days_period_boundary(db, setup):
    pulse = plan(db, setup, code="heart_rate", frequency=Frequency.EVERY_N_DAYS, interval_days=3)
    # Okt. 1-től háromnaponta: … okt. 16–18., okt. 19–21.
    assert open_due_occurrences(db, local(2026, 10, 18, 23, 59)) == 6  # okt. 1., 4., … 16.
    assert open_due_occurrences(db, local(2026, 10, 19, 0, 0)) == 1
    *_, first, second = occurrences_of(db, pulse)
    assert (first.period_start, first.due_at) == (local(2026, 10, 16), local(2026, 10, 18, 10))
    assert (second.period_start, second.due_at) == (local(2026, 10, 19), local(2026, 10, 21, 10))


# --- Lezárás: pótlási ablak mérésnél, azonnali elmulasztás kérdőívnél ---------------------


def test_measurement_caught_up_just_before_the_window_closes_is_late(db, setup):
    bp = plan(db, setup, start=date(2026, 10, 16))
    open_due_occurrences(db, local(2026, 10, 16, 8, 0))
    [occurrence] = occurrences_of(db, bp)

    # Az okt. 16-i időszak éjfélkor véget ért; a pótlás okt. 19. 00:00-ig lehetséges.
    assert close_missed_occurrences(db, local(2026, 10, 18, 23, 58)) == 0
    now = local(2026, 10, 18, 23, 58)
    measurement = record(db, setup, local(2026, 10, 16, 23, 59), now=now)

    assert occurrence.status is OccurrenceStatus.FULFILLED_LATE
    assert occurrence.fulfilled_at == now
    assert occurrence.measurement_id == measurement.id
    assert close_missed_occurrences(db, local(2026, 10, 19, 0, 0)) == 0


def test_measurement_occurrence_is_missed_after_the_window(db, setup):
    bp = plan(db, setup, start=date(2026, 10, 16))
    open_due_occurrences(db, local(2026, 10, 16, 8, 0))
    [occurrence] = occurrences_of(db, bp)

    assert close_missed_occurrences(db, local(2026, 10, 18, 23, 59)) == 0
    assert occurrence.status is OccurrenceStatus.DUE
    assert close_missed_occurrences(db, local(2026, 10, 19, 0, 0)) == 1
    assert occurrence.status is OccurrenceStatus.MISSED

    # Az időszakba eső mérés ekkor már nem rögzíthető (két napnál régebbi).
    with pytest.raises(MeasurementError, match="too_old"):
        record(db, setup, local(2026, 10, 16, 23, 59), now=local(2026, 10, 19, 0, 0))


def test_missed_occurrence_is_not_overwritten_by_a_late_measurement(db, setup):
    """Ha a lezárás és a mentés órája kissé eltér, az elmulasztott alkalom akkor sem
    fordul át csendben teljesítettre."""
    bp = plan(db, setup, start=date(2026, 10, 16))
    open_due_occurrences(db, local(2026, 10, 16, 8, 0))
    close_missed_occurrences(db, local(2026, 10, 19, 0, 0))
    record(db, setup, local(2026, 10, 16, 23, 59), now=local(2026, 10, 18, 23, 0))

    [occurrence] = occurrences_of(db, bp)
    assert occurrence.status is OccurrenceStatus.MISSED
    assert occurrence.measurement_id is None
    assert occurrence.fulfilled_at is None


def test_questionnaire_occurrence_is_missed_right_after_the_period(db, setup, template):
    wellbeing = weekly_questionnaire(db, setup, template, start=date(2026, 10, 13))
    open_due_occurrences(db, local(2026, 10, 13, 9, 0))
    [occurrence] = occurrences_of(db, wellbeing)

    # A határidő (hétfő 20:00) után még az időszakban van: esedékes marad.
    assert close_missed_occurrences(db, local(2026, 10, 19, 23, 59)) == 0
    assert close_missed_occurrences(db, local(2026, 10, 20, 0, 0)) == 1
    assert occurrence.status is OccurrenceStatus.MISSED

    # Nincs pótlás: a kedd hajnali kitöltés már az új időszak alkalmát teljesíti.
    submission = fill(db, setup, template, local(2026, 10, 20, 0, 5))
    old, new = occurrences_of(db, wellbeing)
    assert old.status is OccurrenceStatus.MISSED
    assert new.status is OccurrenceStatus.FULFILLED
    assert submission.occurrence_id == new.id


def test_late_questionnaire_within_the_period_is_fulfilled_late(db, setup, template):
    wellbeing = weekly_questionnaire(db, setup, template)
    now = local(2026, 10, 19, 21, 0)  # hétfő, a 20:00-s határidő után
    submission = fill(db, setup, template, now)
    [occurrence] = occurrences_of(db, wellbeing)
    assert occurrence.status is OccurrenceStatus.FULFILLED_LATE
    assert occurrence.fulfilled_at == now
    assert submission.occurrence_id == occurrence.id


# --- Érvényesség ----------------------------------------------------------------------


def test_revoked_ended_and_future_assignments_get_no_new_occurrence(db, setup):
    revoked = plan(db, setup)
    revoked.revoked_at = local(2026, 10, 10)
    ended = plan(db, setup, code="heart_rate")
    ended.end_date = date(2026, 10, 16)
    plan(db, setup, code="body_weight", start=date(2026, 10, 20))
    db.flush()

    # A visszavont és a jövőbeli előírás egy alkalmat sem kap; a lejárt csak a
    # vége előtti (okt. 1–16.) kimaradt időszakait.
    assert open_due_occurrences(db, local(2026, 10, 17, 8, 0)) == 16
    assert occurrences_of(db, revoked) == []
    assert occurrences_of(db, ended)[-1].due_at == local(2026, 10, 16, 10, 0)
    assert db.scalar(select(func.count()).select_from(AssignmentOccurrence)) == 16

    # A mentés sem nyit alkalmat érvénytelen előírásra.
    record(db, setup, local(2026, 10, 17, 9, 0))
    record(db, setup, local(2026, 10, 17, 9, 0), code="heart_rate")
    assert db.scalar(select(func.count()).select_from(AssignmentOccurrence)) == 16


def test_inactive_questionnaire_gets_no_new_occurrence(db, setup, template):
    weekly_questionnaire(db, setup, template)
    template.is_active = False
    db.flush()
    assert open_due_occurrences(db, local(2026, 10, 17, 8, 0)) == 0


# --- Hozzárendelés mentéskor ------------------------------------------------------------


def test_measurement_saved_before_the_worker_creates_and_fulfils_the_occurrence(db, setup):
    bp = plan(db, setup, start=date(2026, 10, 17))
    pulse = plan(db, setup, code="heart_rate", start=date(2026, 10, 17))

    on_time = record(db, setup, local(2026, 10, 17, 9, 0))
    late = record(db, setup, local(2026, 10, 17, 11, 0), code="heart_rate")

    [bp_occurrence] = occurrences_of(db, bp)
    assert bp_occurrence.status is OccurrenceStatus.FULFILLED
    assert bp_occurrence.measurement_id == on_time.id
    assert bp_occurrence.fulfilled_at == local(2026, 10, 17, 9, 0)
    [pulse_occurrence] = occurrences_of(db, pulse)
    assert pulse_occurrence.status is OccurrenceStatus.FULFILLED_LATE
    assert pulse_occurrence.measurement_id == late.id

    # A háttérfolyamat utána már nem nyit újat, és nem írja át a teljesítést.
    assert run_occurrence_check(db, local(2026, 10, 17, 12, 0)).opened == 0
    assert bp_occurrence.status is OccurrenceStatus.FULFILLED

    # Az időszak második mérése nem cseréli le a teljesítőt.
    record(db, setup, local(2026, 10, 17, 18, 0))
    assert bp_occurrence.measurement_id == on_time.id
    assert len(occurrences_of(db, bp)) == 1


def test_lateness_is_decided_by_the_recording_time(db, setup):
    """A határidő előtt mért, de utána rögzített érték késve teljesít."""
    bp = plan(db, setup)
    record(db, setup, local(2026, 10, 17, 9, 0), now=local(2026, 10, 17, 10, 30))
    [occurrence] = occurrences_of(db, bp)
    assert occurrence.status is OccurrenceStatus.FULFILLED_LATE
    assert occurrence.fulfilled_at == local(2026, 10, 17, 10, 30)


def test_measurements_outside_any_plan_are_not_linked(db, setup):
    plan(db, setup, start=date(2026, 10, 17))
    record(db, setup, local(2026, 10, 16, 9, 0), now=local(2026, 10, 17, 9, 0))  # a kezdet előtt
    record(db, setup, local(2026, 10, 17, 9, 0), code="body_weight")  # nincs előírva
    assert db.scalars(select(AssignmentOccurrence)).all() == []


def test_every_submission_of_the_period_points_to_its_occurrence(db, setup, template):
    wellbeing = weekly_questionnaire(db, setup, template)
    first = fill(db, setup, template, local(2026, 10, 14, 9, 0))
    second = fill(db, setup, template, local(2026, 10, 15, 9, 0))
    [occurrence] = occurrences_of(db, wellbeing)
    assert first.occurrence_id == second.occurrence_id == occurrence.id
    # Az első kitöltés teljesítette; a második nem írja át.
    assert occurrence.fulfilled_at == local(2026, 10, 14, 9, 0)


# --- Kérdőívverzió -----------------------------------------------------------------------


def test_occurrence_keeps_the_version_valid_at_its_creation(db, setup, template):
    wellbeing = weekly_questionnaire(db, setup, template, start=date(2026, 10, 13))
    v1 = template.versions[0]
    open_due_occurrences(db, local(2026, 10, 13, 9, 0))

    v2 = add_version(db, template, WELLBEING_V1)
    db.refresh(template)
    open_due_occurrences(db, local(2026, 10, 14, 9, 0))
    fill(db, setup, template, local(2026, 10, 14, 10, 0))
    [occurrence] = occurrences_of(db, wellbeing)
    assert occurrence.questionnaire_version_id == v1.id
    assert occurrence.status is OccurrenceStatus.FULFILLED

    # A következő időszak alkalma már az új verziót rögzíti.
    open_due_occurrences(db, local(2026, 10, 20, 9, 0))
    old, new = occurrences_of(db, wellbeing)
    assert old.questionnaire_version_id == v1.id
    assert new.questionnaire_version_id == v2.id


def stricter_version(db, template):
    """v2 más pontozással: a szédülés „Ritkán" válasza 4 pontot ér (v1-ben 2),
    és szigorúbbak a sávok (0–3 rendben, 4–10 figyelmeztető)."""
    spec = WELLBEING_V1.model_copy(deep=True)
    spec.questions[2].options[1].score = 4
    spec.scoring_thresholds[0].max = 3
    spec.scoring_thresholds[1].min = 4
    version = add_version(db, template, VersionSpec.model_validate(spec.model_dump()))
    db.refresh(template)
    return version


def answers_for(version, sleep="4", fatigue="4", dizziness="rarely"):
    q1, q2, q3 = version.questions
    return {str(q1.id): sleep, str(q2.id): fatigue, str(q3.id): dizziness}


def submit(db, setup, answers, now):
    submission, _ = submit_questionnaire(
        db, patient_id=setup["pid"], template_code=WELLBEING_CODE, answers=answers, now=now
    )
    return submission


def test_submission_uses_the_version_pinned_to_the_occurrence(db, setup, template):
    """A sablon az időszak közben új verziót kap: a kitöltés az alkalom (régi)
    verziójával és annak pontozásával rögzül (M1: a kitöltés az alkalomhoz
    rögzített verzióra hivatkozik)."""
    wellbeing = weekly_questionnaire(db, setup, template, start=date(2026, 10, 13))
    v1 = template.versions[0]
    open_due_occurrences(db, local(2026, 10, 13, 9, 0))
    v2 = stricter_version(db, template)

    # A felület az alkalom verziójának kérdéseit kapja, nem a legújabbét.
    assert fill_version(db, setup["pid"], template.id, date(2026, 10, 14)) == v1
    submission = submit(db, setup, answers_for(v1), local(2026, 10, 14, 10, 0))
    [occurrence] = occurrences_of(db, wellbeing)
    assert submission.version_id == occurrence.questionnaire_version_id == v1.id
    # v1 szerint 1 + 3 + 2 = 6 pont, figyelmeztető (v2 szerint 8 lenne).
    assert submission.total_score == 6
    assert band_for(submission.version, submission.total_score) == "warning"
    assert {a.question_id for a in submission.answers} == {q.id for q in v1.questions}

    # Az új verzió kérdéseivel ebben az időszakban nem lehet kitölteni.
    with pytest.raises(SubmissionError, match="unknown_question"):
        submit(db, setup, answers_for(v2), local(2026, 10, 15, 10, 0))

    # A következő időszak alkalma már a v2-t rögzíti, és a kitöltés annak pontozását kapja.
    later = submit(db, setup, answers_for(v2), local(2026, 10, 20, 10, 0))
    assert later.version_id == v2.id
    assert later.total_score == 8
    _, new = occurrences_of(db, wellbeing)
    assert later.occurrence_id == new.id
    assert new.questionnaire_version_id == v2.id


def test_occurrence_created_at_fill_time_pins_the_then_current_version(db, setup, template):
    """Ha a háttérfolyamat még nem nyitotta meg az alkalmat, a kitöltés kérése
    hozza létre, az akkor aktuális verzióval; a későbbi módosítás már nem hat rá."""
    wellbeing = weekly_questionnaire(db, setup, template, start=date(2026, 10, 13))
    v1 = template.versions[0]
    assert fill_version(db, setup["pid"], template.id, date(2026, 10, 14)) == v1
    [occurrence] = occurrences_of(db, wellbeing)
    assert occurrence.questionnaire_version_id == v1.id

    stricter_version(db, template)
    assert fill_version(db, setup["pid"], template.id, date(2026, 10, 15)) == v1


def test_fill_version_without_a_valid_assignment_is_the_current_one(db, setup, template):
    v2 = stricter_version(db, template)
    assert fill_version(db, setup["pid"], template.id, date(2026, 10, 14)) == v2
    assert db.scalars(select(AssignmentOccurrence)).all() == []


def test_measurement_occurrence_has_no_questionnaire_version(db, setup):
    bp = plan(db, setup, start=date(2026, 10, 17))
    open_due_occurrences(db, local(2026, 10, 17, 8, 0))
    [occurrence] = occurrences_of(db, bp)
    assert occurrence.questionnaire_version_id is None


# --- Egyezés a számított teendőlistával (az A3-ig védi az átállást) ---------------------------


def test_stored_occurrences_match_the_computed_tasks(db, setup, template):
    plan(db, setup, code="blood_pressure", due=time(10, 0))  # időben mérve
    plan(db, setup, code="blood_glucose", due=time(8, 0))  # késve mérve
    plan(db, setup, code="heart_rate", due=time(10, 0))  # lejárt, nincs adat
    plan(db, setup, code="body_weight", due=time(21, 0))  # még esedékes
    weekly_questionnaire(db, setup, template)  # kitöltve
    record(db, setup, local(2026, 10, 17, 7, 30))
    record(db, setup, local(2026, 10, 17, 9, 0), code="blood_glucose")
    fill(db, setup, template, local(2026, 10, 17, 9, 30))

    now = local(2026, 10, 17, 12, 0)
    run_occurrence_check(db, now)
    # A teendőlista csak az aktuális időszakot mutatja; a visszamenőleg megnyitott
    # korábbi alkalmak ebből az összevetésből kimaradnak.
    stored = {
        (o.assignment_id, o.due_at): o
        for o in db.scalars(select(AssignmentOccurrence))
        if o.period_start <= now < period_end(o)
    }
    tasks = patient_tasks(db, setup["pid"], now=now)
    assert len(tasks) == len(stored) == 5

    expected = {
        TaskState.DONE: {OccurrenceStatus.FULFILLED, OccurrenceStatus.FULFILLED_LATE},
        TaskState.DUE: {OccurrenceStatus.DUE},
        TaskState.LATE: {OccurrenceStatus.DUE},
    }
    for task in tasks:
        occurrence = stored[(task.assignment.id, task.due_at)]
        assert occurrence.period_start == task.period_start
        assert occurrence.status in expected[task.state], task.code
        # A teendőlista „lejárt" állapota a tárolt alkalomnál: esedékes, a határidő után.
        assert (task.state is TaskState.LATE) == (
            occurrence.status is OccurrenceStatus.DUE and now > occurrence.due_at
        )

    by_code = {t.code: stored[(t.assignment.id, t.due_at)].status for t in tasks}
    assert by_code == {
        "blood_pressure": OccurrenceStatus.FULFILLED,
        "blood_glucose": OccurrenceStatus.FULFILLED_LATE,
        "heart_rate": OccurrenceStatus.DUE,
        "body_weight": OccurrenceStatus.DUE,
        WELLBEING_CODE: OccurrenceStatus.FULFILLED,
    }


# --- Demóadat ------------------------------------------------------------------------------


def test_seed_history_gets_consistent_occurrences(db):
    """A demóadat két hetes múltja a seed végi ellenőrzés után: minden elmulasztott
    alkalom időszakában valóban nincs adat, minden teljesítettében van, és a
    háttérfolyamat első futására már nem marad munka."""
    now = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)
    seed_demo_data(db, now=now)
    assert run_occurrence_check(db, now) == OccurrenceCheck(0, 0)

    stored = db.scalars(
        select(AssignmentOccurrence).options(joinedload(AssignmentOccurrence.assignment))
    ).all()
    assert any(o.status is OccurrenceStatus.MISSED for o in stored)
    for occurrence in stored:
        data_at = _last_data_at(
            db, occurrence.assignment, occurrence.period_start, period_end(occurrence)
        )
        if occurrence.status is OccurrenceStatus.MISSED:
            assert data_at is None
        elif occurrence.status is not OccurrenceStatus.DUE:
            assert data_at is not None
