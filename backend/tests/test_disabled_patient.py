"""A letiltott beteg (M3, A1; a hallgató döntése, 2026-11-16, A változat):

- az orvos listáján marad „Letiltva" jelöléssel, a korábbi adatai látszanak;
- az az alkalma, amelynek határideje a letiltott időszakba esik, nem számít
  elmulasztottnak, utólag sem; minden más (a letiltás előtti és utáni alkalmak,
  előírások, szabályok, mérések, riasztások) változatlan (services/disabled.py).

Szimulált idővel: napi vérnyomás-előírás okt. 1-jétől, 10:00-s határidővel; a
mérés alkalma az időszak vége + 48 óra után elmulasztott (occurrences.py)."""

import uuid
from datetime import date, datetime, time, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select, text

from app.core.config import settings
from app.core.db import engine
from app.core.security import create_access_token
from app.models import (
    Alert,
    AlertStatus,
    AssignmentOccurrence,
    AssignmentTarget,
    Frequency,
    NotificationDelivery,
    OccurrenceStatus,
    RuleType,
    Severity,
)
from app.models.user import UserDisabledPeriod
from app.services import admin, plans
from app.services.disabled import (
    DisabledPeriod,
    disabled_periods,
    excused_deadline,
    inactive_patients,
    is_excused,
    overlaps,
)
from app.services.measurements import get_type_by_code, record_measurement
from app.services.occurrences import (
    OccurrenceCheck,
    fill_version,
    occurrence_for,
    period_containing,
    run_occurrence_check,
)
from app.services.questionnaires import (
    assign_questionnaire,
    create_template,
    submit_questionnaire,
)
from app.services.rules import MissingDataParams, create_rule, missed_streak
from app.services.status import PatientStatus, compute_status, data_age
from app.services.tasks import TaskState, assign_measurement, patient_tasks
from seed.questionnaires import WELLBEING_CODE, WELLBEING_NAME, WELLBEING_V1
from tests.factories import (
    assign,
    make_admin,
    make_doctor,
    make_measurement_types,
    make_patient,
    make_threshold_rule,
    record_bp,
)


def local(y, m, d, hh=0, mm=0):
    """Időpont a rendszer időzónájában (Europe/Budapest)."""
    return datetime(y, m, d, hh, mm, tzinfo=settings.tz)


@pytest.fixture
def s(db):
    make_measurement_types(db)
    doctor = make_doctor(db)
    patient = make_patient(db)
    # Az összerendelés a szimulált idők előtt kezdődik, így az orvos a riasztás
    # pillanatában is hozzá van rendelve (az e-mail címzettje, A9).
    assign(db, doctor, patient, valid_from=local(2026, 1, 1))
    return {
        "doctor": doctor,
        "patient": patient,
        "pid": patient.patient_profile.id,
        "admin": make_admin(db),
    }


def daily_plan(db, s, start=date(2026, 10, 1), frequency=Frequency.DAILY):
    return assign_measurement(
        db,
        patient_id=s["pid"],
        measurement_type=get_type_by_code(db, "blood_pressure"),
        assigned_by=s["doctor"].id,
        start_date=start,
        due_time=time(10, 0),
        frequency=frequency,
    )


MISSING = {"measurement_type": "blood_pressure", "consecutive_missed": 2}


def missing_rule(db, s):
    return create_rule(
        db,
        patient_id=s["pid"],
        created_by=s["doctor"].id,
        rule_type=RuleType.MISSING_DATA,
        params=MISSING,
        severity=Severity.MODERATE,
    )


def rows(db, plan):
    return list(
        db.scalars(
            select(AssignmentOccurrence)
            .where(AssignmentOccurrence.assignment_id == plan.id)
            .order_by(AssignmentOccurrence.due_at)
        )
    )


def days(items, status=None):
    return [
        o.due_at.astimezone(settings.tz).day for o in items if status is None or o.status is status
    ]


def alerts(db, s):
    return list(db.scalars(select(Alert).where(Alert.patient_id == s["pid"])))


def codes(result):
    return [r.code for r in result.reasons]


def disable(db, s, at):
    admin.disable_user(db, s["admin"], s["patient"], now=at)


def enable(db, s, at):
    admin.enable_user(db, s["patient"], now=at)


def streak_days(db, s):
    target = get_type_by_code(db, "blood_pressure").id
    return days(missed_streak(db, s["pid"], MissingDataParams.model_validate(MISSING), target))


# --- A szabály és a tárolás --------------------------------------------------------


def test_interval_boundaries_python_and_sql_agree(db, s):
    """[disabled_at, enabled_at): a letiltás pillanatára eső határidő kimentett,
    a visszaengedélyezés pillanatára eső már számít. Az SQL-feltétel ugyanígy dönt."""
    start, end = local(2026, 10, 5, 10), local(2026, 10, 8, 10)
    disable(db, s, start)
    enable(db, s, end)
    assert disabled_periods(db, s["pid"]) == [DisabledPeriod(start, end)]
    cases = {
        start - timedelta(microseconds=1): False,
        start: True,
        end - timedelta(microseconds=1): True,
        end: False,
    }
    for at, expected in cases.items():
        assert is_excused(disabled_periods(db, s["pid"]), at) is expected
        assert db.scalar(select(excused_deadline(s["pid"], at))) is expected, at


def test_open_interval_lasts_until_reenable(db, s):
    disable(db, s, local(2026, 10, 5, 10))
    periods = disabled_periods(db, s["pid"])
    assert periods == [DisabledPeriod(local(2026, 10, 5, 10), None)]
    assert is_excused(periods, local(2030, 1, 1))


def test_cycles_are_stored_and_consistent_with_is_active(db, s):
    disable(db, s, local(2026, 10, 1, 8))
    disable(db, s, local(2026, 10, 1, 9))  # már letiltva: nem ír semmit
    assert s["patient"].is_active is False
    enable(db, s, local(2026, 10, 2, 8))
    enable(db, s, local(2026, 10, 3, 8))  # már aktív: nem ír semmit
    assert s["patient"].is_active is True
    disable(db, s, local(2026, 10, 4, 8))
    assert disabled_periods(db, s["pid"]) == [
        DisabledPeriod(local(2026, 10, 1, 8), local(2026, 10, 2, 8)),
        DisabledPeriod(local(2026, 10, 4, 8), None),
    ]
    open_rows = db.scalars(
        select(UserDisabledPeriod).where(UserDisabledPeriod.enabled_at.is_(None))
    ).all()
    assert [r.user_id for r in open_rows] == [s["patient"].id]


def test_enable_never_closes_before_the_start(db, s):
    """Ha a kapott idő nem későbbi a letiltásnál, a vég a kezdet utáni pillanat."""
    disable(db, s, local(2026, 10, 5, 10))
    enable(db, s, local(2026, 10, 5, 10))
    (period,) = disabled_periods(db, s["pid"])
    assert period.end == local(2026, 10, 5, 10) + timedelta(microseconds=1)


def test_never_disabled_patient_queries_are_unchanged(db, s):
    """Sosem letiltott betegnél nincs időszak: semmi nem kimentett, a háttér-
    folyamat, a státusz és a teendőlista pontosan úgy dolgozik, mint eddig."""
    plan = daily_plan(db, s)
    assert disabled_periods(db, s["pid"]) == []
    check = run_occurrence_check(db, local(2026, 10, 5, 12))
    assert check == OccurrenceCheck(opened=5, missed=2)
    assert days(rows(db, plan), OccurrenceStatus.MISSED) == [1, 2]
    assert not db.scalar(select(excused_deadline(s["pid"], local(2026, 10, 3, 10))))
    result = compute_status(db, s["pid"], local(2026, 10, 5, 12))
    assert result.status is PatientStatus.NO_DATA
    assert codes(result) == ["missed_occurrence", "no_data_yet"]
    (task,) = patient_tasks(db, s["pid"], local(2026, 10, 5, 12))
    assert task.state is TaskState.LATE and task.previous_missed


# --- Letiltva ----------------------------------------------------------------------


def test_disabled_patient_gets_no_missed_occurrence_or_alert(db, s):
    plan = daily_plan(db, s)
    missing_rule(db, s)
    disable(db, s, local(2026, 10, 1, 0))  # az első határidő előtt

    check = run_occurrence_check(db, local(2026, 10, 10, 12))
    assert check == OccurrenceCheck(opened=0, missed=0)
    assert rows(db, plan) == []
    assert alerts(db, s) == []
    # (a) változat: a státusz ugyanúgy számol, mint bárki másnál, a letiltott
    # időszak határidői nélkül. Adat sosem jött, ezért „még nem érkezett adat".
    result = compute_status(db, s["pid"], local(2026, 10, 10, 12))
    assert result.status is PatientStatus.NO_DATA
    assert codes(result) == ["no_data_yet"]


def deliveries(db):
    return db.scalars(select(NotificationDelivery)).all()


def test_pre_disable_miss_closed_on_time_without_alert(db, s):
    """P2: a letiltás előtt lejárt határidő a szokásos időben, letiltva is
    elmulasztottra zárul (a státuszban és a későbbi sorozatban számít), de sem
    letiltva, sem a visszaengedélyezéskor nem lesz belőle riasztás és e-mail. Az
    első visszaengedélyezés utáni elmulasztás a sorozatot rendesen értékeli, és a
    régi elmulasztást is a kiváltók közt sorolja."""
    plan = daily_plan(db, s)
    missing_rule(db, s)  # 2 egymást követő elmulasztás
    run_occurrence_check(db, local(2026, 10, 2, 12))  # okt. 1–2. megnyitva
    disable(db, s, local(2026, 10, 2, 13))
    assert run_occurrence_check(db, local(2026, 10, 9, 12)).missed == 2
    assert days(rows(db, plan), OccurrenceStatus.MISSED) == [1, 2]
    assert alerts(db, s) == [] and deliveries(db) == []
    assert "missed_occurrence" in codes(compute_status(db, s["pid"], local(2026, 10, 9, 12)))

    enable(db, s, local(2026, 10, 9, 13))
    run_occurrence_check(db, local(2026, 10, 9, 14))
    assert alerts(db, s) == [] and deliveries(db) == []  # utólag sem

    run_occurrence_check(db, local(2026, 10, 13, 0))  # okt. 10. az első új elmulasztás
    (alert,) = alerts(db, s)
    by_id = {str(o.id): o for o in rows(db, plan)}
    assert [by_id[i].due_at.day for i in alert.trigger_data_ids] == [2, 10]
    assert len(deliveries(db)) == 1  # az orvosnak egy levél (A9)


def test_single_miss_rule_ignores_old_miss_and_fires_on_new_one(db, s):
    """P2, consecutive_missed = 1: a letiltás előtti elmulasztás magában nem riaszt
    a visszaengedélyezés után sem; az első új elmulasztás igen."""
    plan = daily_plan(db, s)
    create_rule(
        db,
        patient_id=s["pid"],
        created_by=s["doctor"].id,
        rule_type=RuleType.MISSING_DATA,
        params={"measurement_type": "blood_pressure", "consecutive_missed": 1},
        severity=Severity.MODERATE,
    )
    record_bp(db, s["patient"], 120, 80, at=local(2026, 10, 1, 9))
    run_occurrence_check(db, local(2026, 10, 3, 8))  # okt. 2. lejárt, pótolható
    disable(db, s, local(2026, 10, 3, 9))
    run_occurrence_check(db, local(2026, 10, 6, 8))
    assert days(rows(db, plan), OccurrenceStatus.MISSED) == [2]
    enable(db, s, local(2026, 10, 6, 12))  # okt. 6. 10:00 kimentett
    run_occurrence_check(db, local(2026, 10, 6, 13))
    assert alerts(db, s) == [] and deliveries(db) == []
    run_occurrence_check(db, local(2026, 10, 10, 0))  # okt. 7. elmulasztva
    (alert,) = alerts(db, s)
    by_id = {str(o.id): o for o in rows(db, plan)}
    assert [by_id[i].due_at.day for i in alert.trigger_data_ids] == [7]


@pytest.mark.parametrize("worker_while_disabled", [True, False])
def test_no_alert_regardless_of_worker_timing(db, s, worker_while_disabled):
    """P2 determinisztikusan: akár futott a háttérfolyamat a letiltás alatt, akár
    csak a visszaengedélyezés után, a letiltás alatt lejárt pótlási idejű
    elmulasztásból nincs riasztás (a felülvizsgálat N3/N3b esete)."""
    plan = daily_plan(db, s)
    create_rule(
        db,
        patient_id=s["pid"],
        created_by=s["doctor"].id,
        rule_type=RuleType.MISSING_DATA,
        params={"measurement_type": "blood_pressure", "consecutive_missed": 1},
        severity=Severity.MODERATE,
    )
    record_bp(db, s["patient"], 120, 80, at=local(2026, 10, 1, 9))
    run_occurrence_check(db, local(2026, 10, 3, 8))
    disable(db, s, local(2026, 10, 3, 9))
    if worker_while_disabled:
        run_occurrence_check(db, local(2026, 10, 20, 12))
    enable(db, s, local(2026, 10, 30, 9))
    run_occurrence_check(db, local(2026, 10, 30, 9, 10))
    record_bp(db, s["patient"], 120, 80, at=local(2026, 10, 30, 9, 30))
    run_occurrence_check(db, local(2026, 10, 30, 9, 40))
    assert alerts(db, s) == [] and deliveries(db) == []
    assert days(rows(db, plan), OccurrenceStatus.MISSED) == [2]


def test_grace_ending_after_reenable_alerts_normally(db, s):
    """Ha a letiltás előtti alkalom pótlási ideje a visszaengedélyezés után jár le,
    a lezárás a szokásos módon riaszt (akkor a beteg már aktív)."""
    plan = daily_plan(db, s)
    create_rule(
        db,
        patient_id=s["pid"],
        created_by=s["doctor"].id,
        rule_type=RuleType.MISSING_DATA,
        params={"measurement_type": "blood_pressure", "consecutive_missed": 1},
        severity=Severity.MODERATE,
    )
    record_bp(db, s["patient"], 120, 80, at=local(2026, 10, 1, 9))
    run_occurrence_check(db, local(2026, 10, 3, 8))  # okt. 2. pótlási ideje okt. 5. 0:00
    disable(db, s, local(2026, 10, 3, 9))
    enable(db, s, local(2026, 10, 4, 8))
    run_occurrence_check(db, local(2026, 10, 5, 0, 5))
    (alert,) = alerts(db, s)
    by_id = {str(o.id): o for o in rows(db, plan)}
    assert [by_id[i].due_at.day for i in alert.trigger_data_ids] == [2]


def test_disabled_patient_never_gets_a_delivery(db, s):
    """I3: letiltott betegnél a háttérfolyamat semmilyen úton nem hoz létre
    riasztást, így kézbesítési sort sem (rögzíteni letiltva nem lehet)."""
    daily_plan(db, s)
    missing_rule(db, s)
    make_threshold_rule(db, s["patient"], s["doctor"])
    record_bp(db, s["patient"], 120, 80, at=local(2026, 10, 1, 9))
    run_occurrence_check(db, local(2026, 10, 2, 12))
    disable(db, s, local(2026, 10, 2, 13))
    for day in range(3, 31):
        run_occurrence_check(db, local(2026, 10, day, 12))
    assert alerts(db, s) == [] and deliveries(db) == []


# --- P1: a frissességi szabály a letiltott időt nem számolja ------------------------


def test_stale_rule_skips_disabled_time_without_plan(db, s):
    """N6: előírás nélkül, utolsó adat okt. 1. 9:00, letiltva okt. 2. 9:00-tól
    okt. 20. 13:00-ig. Letiltva nem lesz Adathiány; utána a 7 nap onnan folytatódik,
    ahol megállt (1 nap már eltelt, még 6 kell). Okt. 25-én véget ér a nyári
    időszámítás (az a nap 25 órás), ezért a 6 nap abszolút időben okt. 26. 12:00."""
    record_bp(db, s["patient"], 120, 80, at=local(2026, 10, 1, 9))
    disable(db, s, local(2026, 10, 2, 9))
    assert compute_status(db, s["pid"], local(2026, 10, 20, 12)).status is PatientStatus.OK
    enable(db, s, local(2026, 10, 20, 13))
    assert compute_status(db, s["pid"], local(2026, 10, 20, 13, 1)).status is PatientStatus.OK
    assert compute_status(db, s["pid"], local(2026, 10, 26, 11, 59)).status is PatientStatus.OK
    late = compute_status(db, s["pid"], local(2026, 10, 26, 12, 1))
    assert late.status is PatientStatus.NO_DATA and codes(late) == ["stale_data"]


def test_stale_rule_with_plan_disabled_before_first_deadline(db, s):
    """N17: utolsó adat szept. 30. 9:00, előírás okt. 1-jétől, letiltva okt. 1. 0:00
    (az első határidő előtt), visszaengedélyezve okt. 20. 13:00-kor."""
    record_bp(db, s["patient"], 120, 80, at=local(2026, 9, 30, 9))
    daily_plan(db, s)
    disable(db, s, local(2026, 10, 1, 0))
    for at in (local(2026, 10, 5, 12), local(2026, 10, 9, 12)):
        assert compute_status(db, s["pid"], at).status is PatientStatus.OK
    enable(db, s, local(2026, 10, 20, 13))
    for at in (local(2026, 10, 20, 13, 1), local(2026, 10, 21, 9)):
        assert compute_status(db, s["pid"], at).status is PatientStatus.OK
    # Az első visszaengedélyezés utáni határidő (okt. 21. 10:00) után már az alkalom dönt.
    after = compute_status(db, s["pid"], local(2026, 10, 21, 11))
    assert codes(after) == ["missed_occurrence"]


def test_fresh_data_does_not_age_while_disabled(db, s):
    """N23: friss adat, utána letiltás; 8 nappal később is Rendben."""
    record_bp(db, s["patient"], 120, 80, at=local(2026, 10, 5, 9))
    disable(db, s, local(2026, 10, 5, 10))
    for at in (local(2026, 10, 6, 11), local(2026, 10, 13, 11)):
        assert compute_status(db, s["pid"], at).status is PatientStatus.OK


def test_plan_replaced_while_disabled_does_not_turn_stale(db, s):
    """N8: az előírás letiltva módosul (a régi visszavonva, az új határidői
    kimentettek); a letiltás alatti idő a frissességbe sem számít."""
    plan = daily_plan(db, s)
    record_bp(db, s["patient"], 120, 80, at=local(2026, 10, 1, 9))
    run_occurrence_check(db, local(2026, 10, 3, 11))
    disable(db, s, local(2026, 10, 3, 12))
    plans.replace(
        db,
        plan,
        assigned_by=s["doctor"].id,
        params=plans.PlanParams(Frequency.DAILY, None, time(18, 0), None, None, None),
        now=local(2026, 10, 3, 13),
    )
    assert compute_status(db, s["pid"], local(2026, 10, 10, 12)).status is PatientStatus.OK
    enable(db, s, local(2026, 10, 10, 13))
    assert compute_status(db, s["pid"], local(2026, 10, 10, 13, 6)).status is PatientStatus.OK
    # Az első új határidő (okt. 10. 18:00) után az alkalom dönt.
    later = compute_status(db, s["pid"], local(2026, 10, 10, 19))
    assert codes(later) == ["missed_occurrence"]


def test_data_age_overlap_helper(db, s):
    record_bp(db, s["patient"], 120, 80, at=local(2026, 10, 1, 9))
    disable(db, s, local(2026, 10, 2, 0))
    enable(db, s, local(2026, 10, 3, 0))
    disable(db, s, local(2026, 10, 4, 0))
    # [okt. 1. 9:00, okt. 5. 0:00] = 3 nap 15 óra, ebből letiltva 1 + 1 nap.
    age = data_age(db, s["pid"], local(2026, 10, 1, 9), local(2026, 10, 5, 0))
    assert age == timedelta(days=1, hours=15)


# --- A felülvizsgálat négy hibás esete (regressziós tesztek) -------------------------


def test_disabling_keeps_real_pre_disable_miss(db, s):
    """(a) Adathiányos beteg letiltása nem teszi Rendbenné, és a gyors
    letiltás/visszaengedélyezés sem."""
    daily_plan(db, s)
    record_bp(db, s["patient"], 120, 80, at=local(2026, 10, 1, 9))
    run_occurrence_check(db, local(2026, 10, 5, 12))  # okt. 2. elmulasztva
    now = local(2026, 10, 5, 13)
    before = compute_status(db, s["pid"], now)
    assert before.status is PatientStatus.NO_DATA and "missed_occurrence" in codes(before)

    disable(db, s, now)
    during = compute_status(db, s["pid"], now)
    assert during.status is PatientStatus.NO_DATA and "missed_occurrence" in codes(during)
    enable(db, s, local(2026, 10, 5, 14))
    after = compute_status(db, s["pid"], local(2026, 10, 5, 15))
    assert codes(after) == codes(before)


def test_toggle_keeps_misses_and_the_streak(db, s):
    """(b) Gyors letiltás/visszaengedélyezés: a letiltás előtti elmulasztás
    megmarad, és az elmaradt adat sorozata folytatódik."""
    plan = daily_plan(db, s)
    rule_ = missing_rule(db, s)
    run_occurrence_check(db, local(2026, 10, 4, 0))  # okt. 1. elmulasztva
    disable(db, s, local(2026, 10, 4, 0, 30))
    enable(db, s, local(2026, 10, 4, 0, 40))
    assert days(rows(db, plan), OccurrenceStatus.MISSED) == [1]

    run_occurrence_check(db, local(2026, 10, 5, 0))  # okt. 2. elmulasztva
    (alert,) = alerts(db, s)
    assert alert.rule_id == rule_.id
    by_id = {str(o.id): o for o in rows(db, plan)}
    assert [by_id[i].due_at.day for i in alert.trigger_data_ids] == [1, 2]


def test_compliant_weekly_patient_stays_ok_after_toggle(db, s):
    """(c) A teljesített alkalom a letiltás után is számít: a heti előírását
    teljesítő beteg 8 napos méréssel is Rendben marad."""
    daily_plan(db, s, start=date(2026, 10, 5), frequency=Frequency.WEEKLY)
    record_bp(db, s["patient"], 120, 80, at=local(2026, 10, 5, 9))
    now = local(2026, 10, 13, 12)
    run_occurrence_check(db, now)
    assert compute_status(db, s["pid"], now).status is PatientStatus.OK
    disable(db, s, now)
    assert compute_status(db, s["pid"], now).status is PatientStatus.OK
    enable(db, s, now + timedelta(minutes=1))
    after = compute_status(db, s["pid"], now + timedelta(minutes=2))
    assert after.status is PatientStatus.OK


def test_misses_between_two_cycles_remain(db, s):
    """(d) Két letiltás közti aktív szakasz elmulasztásai megmaradnak."""
    plan = daily_plan(db, s)
    disable(db, s, local(2026, 10, 1, 0))
    enable(db, s, local(2026, 10, 3, 12))  # okt. 1–3. határideje kimentett
    run_occurrence_check(db, local(2026, 10, 10, 12))
    active = compute_status(db, s["pid"], local(2026, 10, 10, 12))
    assert "missed_occurrence" in codes(active)
    assert days(rows(db, plan), OccurrenceStatus.MISSED) == [4, 5, 6, 7]

    disable(db, s, local(2026, 10, 10, 12, 30))
    enable(db, s, local(2026, 10, 10, 13))
    again = compute_status(db, s["pid"], local(2026, 10, 10, 14))
    assert "missed_occurrence" in codes(again)
    assert days(rows(db, plan), OccurrenceStatus.MISSED) == [4, 5, 6, 7]
    assert 1 not in days(rows(db, plan))  # a kimentett időszak sosem nyílt meg


# --- Több ciklus, sorozat, határesetek ----------------------------------------------


def test_streak_continues_across_the_disabled_gap(db, s):
    """A kimentett időszak a sorozatból kimarad, mintha ott sem lenne: a
    letiltás előtti és utáni elmulasztás egymást követő."""
    plan = daily_plan(db, s)
    run_occurrence_check(db, local(2026, 10, 4, 0))  # okt. 1–4. nyitva, okt. 1. elmulasztva
    disable(db, s, local(2026, 10, 4, 1))  # okt. 4., 5., 6. határideje kimentett
    run_occurrence_check(db, local(2026, 10, 5, 12))  # letiltva: nem zár
    enable(db, s, local(2026, 10, 6, 12))

    run_occurrence_check(db, local(2026, 10, 7, 12))
    # okt. 2–3. (a letiltás előtti határidő) most zárul; okt. 4. sora kimentett,
    # lejárt, ezért törlődött; okt. 5–6. nem nyílt meg.
    assert days(rows(db, plan)) == [1, 2, 3, 7]
    assert days(rows(db, plan), OccurrenceStatus.MISSED) == [1, 2, 3]

    run_occurrence_check(db, local(2026, 10, 10, 0))  # okt. 7. elmulasztva
    assert streak_days(db, s) == [3, 7]


def test_multiple_cycles(db, s):
    plan = daily_plan(db, s)
    disable(db, s, local(2026, 10, 2, 0))
    enable(db, s, local(2026, 10, 3, 12))  # okt. 2–3. kimentett
    disable(db, s, local(2026, 10, 6, 0))
    enable(db, s, local(2026, 10, 7, 12))  # okt. 6–7. kimentett
    run_occurrence_check(db, local(2026, 10, 12, 0))
    assert days(rows(db, plan)) == [1, 4, 5, 8, 9, 10, 11, 12]
    assert days(rows(db, plan), OccurrenceStatus.MISSED) == [1, 4, 5, 8, 9]


def test_weekly_period_straddling_reenable_counts(db, s):
    """Heti előírás hétfőtől (okt. 5.), határidő vasárnap (okt. 11.) 10:00.
    Letiltás szerdán, visszaengedélyezés pénteken: a vasárnapi határidő a
    visszaengedélyezés utáni első, ezért számít, és elmulasztható."""
    plan = daily_plan(db, s, start=date(2026, 10, 5), frequency=Frequency.WEEKLY)
    disable(db, s, local(2026, 10, 7, 12))
    assert run_occurrence_check(db, local(2026, 10, 8, 12)).opened == 0
    enable(db, s, local(2026, 10, 9, 12))
    assert run_occurrence_check(db, local(2026, 10, 14, 0)).missed == 1
    row, current = rows(db, plan)
    assert row.due_at == local(2026, 10, 11, 10)
    assert row.status is OccurrenceStatus.MISSED
    assert current.status is OccurrenceStatus.DUE


def test_no_row_stays_due_forever(db, s):
    """A letiltáskor esedékes sor, amelynek határideje a letiltás alatt telik le,
    és a letiltás alatt más úton nyitott sor sem marad örökre esedékes: a pótlási
    ablak végén törlődik, elmulasztott nem lesz, és a státusz sem számolja."""
    plan = daily_plan(db, s, start=date(2026, 10, 5))
    occurrence_for(db, plan, period_containing(plan, date(2026, 10, 5)))  # határidő 10:00
    disable(db, s, local(2026, 10, 5, 9))
    occurrence_for(db, plan, period_containing(plan, date(2026, 10, 6)))  # pl. tervmódosítás
    assert "missed_occurrence" not in codes(compute_status(db, s["pid"], local(2026, 10, 7, 12)))

    run_occurrence_check(db, local(2026, 10, 9, 12))
    assert rows(db, plan) == []
    enable(db, s, local(2026, 10, 9, 13))
    run_occurrence_check(db, local(2026, 10, 20, 12))
    assert days(rows(db, plan), OccurrenceStatus.DUE) == [18, 19, 20]
    assert all(o.due_at > local(2026, 10, 9, 13) for o in rows(db, plan))


def test_task_list_after_reenable(db, s):
    """Visszaengedélyezés napján a letiltás alatt lejárt határidő nem „késésben",
    és pótlást sem ajánl; másnap a következő időszak esedékes, harmadnap az előző
    (már számító) időszak elmaradt."""
    plan = daily_plan(db, s)
    disable(db, s, local(2026, 10, 1, 0))
    enable(db, s, local(2026, 10, 6, 12))
    assert patient_tasks(db, s["pid"], local(2026, 10, 6, 13)) == []
    (task,) = patient_tasks(db, s["pid"], local(2026, 10, 7, 8))
    assert task.state is TaskState.DUE
    assert task.previous_missed is False and task.catch_up_until is None
    (task,) = patient_tasks(db, s["pid"], local(2026, 10, 8, 8))
    assert task.previous_missed is True
    assert days(rows(db, plan)) == [7, 8]


def test_reenable_keeps_plans_rules_measurements_and_open_alerts(db, s):
    plan = daily_plan(db, s, start=date(2026, 11, 1))
    rule_ = make_threshold_rule(db, s["patient"], s["doctor"])
    now = datetime.now(settings.tz)
    measurement, (alert,) = record_bp(db, s["patient"], 165, 95, at=now)
    disable(db, s, now + timedelta(seconds=1))
    assert compute_status(db, s["pid"], now + timedelta(seconds=2)).status is (
        PatientStatus.ATTENTION
    )
    enable(db, s, now + timedelta(seconds=3))
    db.refresh(alert)
    assert alert.status is AlertStatus.NEW
    assert rule_.is_active and plan.revoked_at is None
    assert measurement.values[0].value == 165


# --- Az orvos és a teendő végpontjai -----------------------------------------------


def auth(user):
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def test_doctor_sees_disabled_patient_with_mark_and_no_tasks(client, db, s):
    today = datetime.now(settings.tz).date()
    daily_plan(db, s, start=today - timedelta(days=3))
    record_bp(db, s["patient"], 128, 82)
    admin.disable_user(db, s["admin"], s["patient"])
    rows_before = len(db.scalars(select(AssignmentOccurrence)).all())

    response = client.get("/api/doctor/patients", headers=auth(s["doctor"]))
    assert response.status_code == 200
    (row,) = response.json()
    assert row["id"] == str(s["pid"])
    assert row["is_active"] is False
    assert row["tasks"] == []

    detail = client.get(f"/api/patients/{s['pid']}", headers=auth(s["doctor"]))
    assert detail.json()["is_active"] is False and detail.json()["tasks"] == []
    tasks = client.get(f"/api/patients/{s['pid']}/tasks", headers=auth(s["doctor"]))
    assert tasks.status_code == 200 and tasks.json() == []
    # Egyik lekérés sem nyitott alkalmat a letiltott betegnél.
    assert len(db.scalars(select(AssignmentOccurrence)).all()) == rows_before
    # A korábbi adatai látszanak.
    measurements = client.get(f"/api/patients/{s['pid']}/measurements", headers=auth(s["doctor"]))
    assert measurements.status_code == 200 and len(measurements.json()) == 1


def test_active_patient_summary_is_marked_active(client, db, s):
    (row,) = client.get("/api/doctor/patients", headers=auth(s["doctor"])).json()
    assert row["is_active"] is True


def test_unknown_patient_has_no_disabled_periods(db):
    assert disabled_periods(db, uuid.uuid4()) == []


# --- Második átnézés: teendők a visszaengedélyezés napján --------------------------


def test_reenable_day_keeps_done_task_and_previous_catch_up(db, s):
    """A mai határidő a letiltás alatt telt le, de a mai mérés már megvolt: a kész
    teendő látszik, és az előző (letiltás előtti, számító) időszak pótolható."""
    daily_plan(db, s)
    record_bp(db, s["patient"], 120, 80, at=local(2026, 10, 1, 9))
    record_bp(db, s["patient"], 120, 80, at=local(2026, 10, 3, 8))  # okt. 2. kimaradt
    disable(db, s, local(2026, 10, 3, 9))
    enable(db, s, local(2026, 10, 3, 11))  # a 10:00-s határidő kimentett
    (task,) = patient_tasks(db, s["pid"], local(2026, 10, 3, 11, 30))
    assert task.state is TaskState.DONE
    assert task.due_at == local(2026, 10, 3, 10)
    assert task.previous_missed is True
    assert task.catch_up_until == local(2026, 10, 5, 0)


def test_reenable_day_offers_catch_up_for_pre_disable_period(db, s):
    """A mai (kimentett) alkalom nem teendő, de az előző, letiltás előtti időszak
    pótlása látszik és működik: a pótlás után nem lesz elmulasztott."""
    plan = daily_plan(db, s)
    record_bp(db, s["patient"], 120, 80, at=local(2026, 10, 1, 9))
    disable(db, s, local(2026, 10, 3, 9))
    enable(db, s, local(2026, 10, 3, 11))
    (task,) = patient_tasks(db, s["pid"], local(2026, 10, 3, 11, 30))
    assert task.state is TaskState.LATE
    assert task.due_at == local(2026, 10, 2, 10)  # az előző időszak
    assert task.catch_up_until == local(2026, 10, 5, 0)
    assert task.catch_up_suggested_at == local(2026, 10, 2, 10)
    assert 3 not in days(rows(db, plan))  # a kimentett mai alkalom nem nyílt meg

    late_bp(db, s, task.catch_up_suggested_at, now=local(2026, 10, 3, 11, 40))
    run_occurrence_check(db, local(2026, 10, 5, 0, 5))
    by_day = {o.due_at.astimezone(settings.tz).day: o.status for o in rows(db, plan)}
    assert by_day[2] is OccurrenceStatus.FULFILLED_LATE
    assert 3 not in by_day


def test_reenable_day_without_catch_up_shows_nothing(db, s):
    daily_plan(db, s)
    record_bp(db, s["patient"], 120, 80, at=local(2026, 10, 2, 9))  # az előző kész
    disable(db, s, local(2026, 10, 3, 9))
    enable(db, s, local(2026, 10, 3, 11))
    assert patient_tasks(db, s["pid"], local(2026, 10, 3, 11, 30)) == []


# --- Második átnézés: késői mérés, kérdőív, előírás letiltva ------------------------


def late_bp(db, s, measured_at, now):
    return record_measurement(
        db,
        patient_id=s["pid"],
        type_code="blood_pressure",
        values={"systolic": 120, "diastolic": 80},
        measured_at=measured_at,
        now=now,
    )


def test_late_measurement_into_pre_disable_period(db, s):
    plan = daily_plan(db, s)
    disable(db, s, local(2026, 10, 2, 12))  # okt. 2. 10:00 a letiltás előtt: számít
    enable(db, s, local(2026, 10, 3, 9))
    late_bp(db, s, local(2026, 10, 2, 11), now=local(2026, 10, 3, 9, 30))
    run_occurrence_check(db, local(2026, 10, 6, 0))
    by_day = {o.due_at.astimezone(settings.tz).day: o.status for o in rows(db, plan)}
    assert by_day[2] is OccurrenceStatus.FULFILLED_LATE
    assert by_day[1] is OccurrenceStatus.MISSED


def test_late_measurement_into_excused_period_is_kept(db, s):
    """A kimentett időszakba visszadátumozott mérés teljesíti az alkalmát; a
    teljesített alkalom megmarad és számít (adat, nem hiány)."""
    plan = daily_plan(db, s)
    disable(db, s, local(2026, 10, 3, 8))
    enable(db, s, local(2026, 10, 4, 9))  # okt. 3. 10:00 kimentett
    late_bp(db, s, local(2026, 10, 3, 12), now=local(2026, 10, 4, 9, 30))
    run_occurrence_check(db, local(2026, 10, 7, 0))
    by_day = {o.due_at.astimezone(settings.tz).day: o.status for o in rows(db, plan)}
    assert by_day[3] is OccurrenceStatus.FULFILLED_LATE
    assert by_day[4] is OccurrenceStatus.MISSED  # okt. 4. 10:00 a visszaengedélyezés után


@pytest.fixture
def wellbeing(db, s):
    template = create_template(
        db, code=WELLBEING_CODE, name=WELLBEING_NAME, created_by=s["doctor"].id, spec=WELLBEING_V1
    )
    plan = assign_questionnaire(
        db,
        patient_id=s["pid"],
        template=template,
        assigned_by=s["doctor"].id,
        start_date=date(2026, 10, 6),  # kedd; határidő hétfő 20:00
        frequency=Frequency.WEEKLY,
        due_time=time(20, 0),
    )
    return template, plan


def test_questionnaire_rows_in_excused_period_are_removed(db, s, wellbeing):
    template, plan = wellbeing
    run_occurrence_check(db, local(2026, 10, 7, 12))  # az 1. hét sora (okt. 12. 20:00)
    disable(db, s, local(2026, 10, 10, 12))
    run_occurrence_check(db, local(2026, 10, 13, 0, 5))
    assert rows(db, plan) == []  # kimentett, lejárt: törölve, nem elmulasztott
    enable(db, s, local(2026, 10, 19, 21))  # a 2. hét határideje (20:00) is kimentett
    # A kitöltőoldal megnyitása sort nyit a kimentett időszakra.
    fill_version(db, s["pid"], template.id, date(2026, 10, 19))
    assert days(rows(db, plan)) == [19]
    result = compute_status(db, s["pid"], local(2026, 10, 19, 21, 30))
    assert "missed_occurrence" not in codes(result)
    run_occurrence_check(db, local(2026, 10, 20, 0, 5))
    assert days(rows(db, plan)) == [26]  # a kimentett sor törölve, a következő hét nyitva


def test_questionnaire_submitted_in_excused_period_is_kept(db, s, wellbeing):
    template, plan = wellbeing
    disable(db, s, local(2026, 10, 10, 12))
    enable(db, s, local(2026, 10, 19, 21))
    version = fill_version(db, s["pid"], template.id, date(2026, 10, 19))
    submission, _ = submit_questionnaire(
        db,
        patient_id=s["pid"],
        template_code=WELLBEING_CODE,
        answers={str(q.id): q.options_scores[0]["value"] for q in version.questions},
        now=local(2026, 10, 19, 21, 40),
    )
    assert submission.occurrence_id is not None
    run_occurrence_check(db, local(2026, 10, 20, 0, 5))
    by_day = {o.due_at.astimezone(settings.tz).day: o.status for o in rows(db, plan)}
    assert by_day[19] is OccurrenceStatus.FULFILLED_LATE
    assert 12 not in by_day


def test_plan_created_while_disabled(db, s):
    record_bp(db, s["patient"], 120, 80, at=local(2026, 10, 1, 9))
    disable(db, s, local(2026, 10, 2, 9))
    plan = plans.create(
        db,
        patient_id=s["pid"],
        assigned_by=s["doctor"].id,
        kind=AssignmentTarget.MEASUREMENT,
        code="blood_pressure",
        params=plans.PlanParams(Frequency.DAILY, None, time(10, 0), None, None, None),
        now=local(2026, 10, 10, 8),
    )
    run_occurrence_check(db, local(2026, 10, 15, 12))
    assert rows(db, plan) == []  # a létrehozáskor nyitott, kimentett sor törölve
    assert "missed_occurrence" not in codes(compute_status(db, s["pid"], local(2026, 10, 15, 12)))
    enable(db, s, local(2026, 10, 20, 13))
    run_occurrence_check(db, local(2026, 10, 20, 13, 5))
    assert rows(db, plan) == []  # okt. 10–20. határideje kimentett, nem nyílik meg
    run_occurrence_check(db, local(2026, 10, 24, 0))
    assert days(rows(db, plan), OccurrenceStatus.MISSED) == [21]


def test_plan_replaced_while_disabled(db, s):
    plan = daily_plan(db, s)
    rule_ = create_rule(
        db,
        patient_id=s["pid"],
        created_by=s["doctor"].id,
        rule_type=RuleType.MISSING_DATA,
        params={"measurement_type": "blood_pressure", "consecutive_missed": 1},
        severity=Severity.MODERATE,
    )
    record_bp(db, s["patient"], 120, 80, at=local(2026, 10, 1, 9))
    run_occurrence_check(db, local(2026, 10, 3, 11))
    disable(db, s, local(2026, 10, 3, 12))
    new = plans.replace(
        db,
        plan,
        assigned_by=s["doctor"].id,
        params=plans.PlanParams(Frequency.DAILY, None, time(18, 0), None, None, None),
        now=local(2026, 10, 3, 13),
    )
    run_occurrence_check(db, local(2026, 10, 10, 12))
    assert alerts(db, s) == []
    assert rows(db, new) == []  # az új előírás kimentett sorai törölve
    enable(db, s, local(2026, 10, 10, 13))
    run_occurrence_check(db, local(2026, 10, 10, 13, 5))
    assert alerts(db, s) == []
    assert rule_.is_active
    result = compute_status(db, s["pid"], local(2026, 10, 10, 13, 6))
    assert "missed_occurrence" not in codes(result)


def test_worker_disable_and_enable_exactly_at_deadlines(db, s):
    """Letiltás pontosan okt. 3. 10:00-kor (az a határidő kimentett), visszaengedélyezés
    pontosan okt. 5. 10:00-kor (az a határidő már számít)."""
    plan = daily_plan(db, s)
    disable(db, s, local(2026, 10, 3, 10))
    enable(db, s, local(2026, 10, 5, 10))
    run_occurrence_check(db, local(2026, 10, 9, 0))
    assert days(rows(db, plan)) == [1, 2, 5, 6, 7, 8, 9]
    assert days(rows(db, plan), OccurrenceStatus.MISSED) == [1, 2, 5, 6]


# --- Soha le nem tiltott betegek: az eredmény a régi -------------------------------

# Eset: (előírás kezdete, gyakoriság, mérések ideje, várt státusz, várt okok,
# a teendő állapota, előző elmaradt, elmulasztott napok). A várt értékek kézzel
# számoltak (okt. 5. 12:00-kor), nem a letiltási kódútból.
NEVER_DISABLED = {
    "követő": (
        date(2026, 10, 1),
        Frequency.DAILY,
        [local(2026, 10, d, 9) for d in (1, 2, 3, 4, 5)],
        PatientStatus.OK,
        ["fresh_data"],
        TaskState.DONE,
        False,
        [],
    ),
    "mulasztó": (
        date(2026, 10, 1),
        Frequency.DAILY,
        [local(2026, 10, 1, 9)],
        PatientStatus.NO_DATA,
        ["missed_occurrence"],
        TaskState.LATE,
        True,
        [2],
    ),
    "heti, régi adattal": (
        date(2026, 9, 28),
        Frequency.WEEKLY,
        [local(2026, 9, 28, 9)],
        PatientStatus.OK,
        ["fresh_data"],
        TaskState.DUE,
        False,
        [],
    ),
    "előírás nélkül": (
        None,
        None,
        [local(2026, 9, 20, 9)],
        PatientStatus.NO_DATA,
        ["stale_data"],
        None,
        None,
        [],
    ),
}


@pytest.mark.parametrize("case", NEVER_DISABLED)
def test_never_disabled_patients_match_expectations(db, s, case):
    start, frequency, measured, status, reason_codes, state, previous, missed = NEVER_DISABLED[case]
    plan = daily_plan(db, s, start=start, frequency=frequency) if start else None
    for at in measured:
        late_bp(db, s, at, now=at)
    now = local(2026, 10, 5, 12)
    run_occurrence_check(db, now)
    result = compute_status(db, s["pid"], now)
    assert result.status is status
    assert codes(result) == reason_codes
    tasks = patient_tasks(db, s["pid"], now)
    if plan is None:
        assert tasks == []
    else:
        (task,) = tasks
        assert (task.state, task.previous_missed) == (state, previous)
        assert days(rows(db, plan), OccurrenceStatus.MISSED) == missed


# --- A migráció visszamenőleges kitöltése ------------------------------------------


def test_migration_backfills_open_period_for_already_disabled_users():
    """A migráció előtt letiltott felhasználó a migrációkor nyitott időszakot kap."""
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    user_id = uuid.uuid4()
    command.downgrade(cfg, "e14010eb61d3")
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO users (id, email, password_hash, role, is_active) "
                    "VALUES (:id, 'regi.letiltott@test.example', 'x', 'patient', false)"
                ),
                {"id": user_id},
            )
    finally:
        command.upgrade(cfg, "head")
    try:
        with engine.connect() as conn:
            periods = conn.execute(
                text("SELECT enabled_at FROM user_disabled_periods WHERE user_id = :id"),
                {"id": user_id},
            ).all()
        assert [p.enabled_at for p in periods] == [None]
    finally:
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM user_disabled_periods WHERE user_id = :id"), {"id": user_id}
            )
            conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})


def test_reenable_day_edge_cases_show_no_task(db, s, wellbeing):
    """Visszaengedélyezés napja, kimentett mai határidővel, teljesítés nélkül:
    nincs teendő, ha az első időszakról van szó, ha kérdőívről (ott nincs pótlás),
    vagy ha az előző időszak pótlási ideje már lejárt (heti előírás)."""
    template, questionnaire_plan = wellbeing
    first = daily_plan(db, s, start=date(2026, 10, 19))  # okt. 19. az első nap
    weekly = assign_measurement(
        db,
        patient_id=s["pid"],
        measurement_type=get_type_by_code(db, "body_weight"),
        assigned_by=s["doctor"].id,
        start_date=date(2026, 10, 6),  # kedd; határidő hétfő 10:00
        frequency=Frequency.WEEKLY,
        due_time=time(10, 0),
    )
    # okt. 19. hétfő: a napi 10:00-s, a heti 10:00-s és a kérdőív 20:00-s határideje
    # mind a letiltott időszakba esik.
    disable(db, s, local(2026, 10, 19, 9))
    enable(db, s, local(2026, 10, 19, 21))
    assert patient_tasks(db, s["pid"], local(2026, 10, 19, 21, 30)) == []
    for plan in (first, weekly, questionnaire_plan):
        assert rows(db, plan) == []


def test_inactive_patients_helper(db, s):
    assert inactive_patients(db, []) == set()
    assert inactive_patients(db, [s["pid"]]) == set()
    disable(db, s, local(2026, 10, 1))
    assert inactive_patients(db, [s["pid"], uuid.uuid4()]) == {s["pid"]}


# --- Harmadik átnézés: a riasztás kihagyása egyetlen szabállyal ---------------------


def missing_n(db, s, n):
    return create_rule(
        db,
        patient_id=s["pid"],
        created_by=s["doctor"].id,
        rule_type=RuleType.MISSING_DATA,
        params={"measurement_type": "blood_pressure", "consecutive_missed": n},
        severity=Severity.MODERATE,
    )


@pytest.mark.parametrize("n", [1, 2])
@pytest.mark.parametrize("worker", ["during", "after"])
def test_alert_skip_does_not_depend_on_worker_timing(db, s, n, worker):
    """A felülvizsgálat P2a esete: okt. 1-jétől napi előírás, semmi nem érkezik; az
    okt. 1. pótlási ideje okt. 4. 0:00-kor jár le, a letiltás okt. 4. 0:30-kor jön,
    a visszaengedélyezés okt. 10. 9:00-kor. Akár futott a háttérfolyamat a letiltás
    alatt, akár csak utána, a letiltás alatt (vagy a lejárat és a futás között)
    lezárt elmulasztásból nincs riasztás; az első új elmulasztás (okt. 10.) a régieket
    is a sorozatba veszi."""
    plan = daily_plan(db, s)
    missing_n(db, s, n)
    disable(db, s, local(2026, 10, 4, 0, 30))
    if worker == "during":
        run_occurrence_check(db, local(2026, 10, 4, 0, 59))
        run_occurrence_check(db, local(2026, 10, 8, 12))
    enable(db, s, local(2026, 10, 10, 9))
    run_occurrence_check(db, local(2026, 10, 10, 9, 5))
    assert alerts(db, s) == [] and deliveries(db) == []
    assert days(rows(db, plan), OccurrenceStatus.MISSED) == [1, 2, 3]

    run_occurrence_check(db, local(2026, 10, 13, 0, 5))  # okt. 10. elmulasztva
    (alert,) = alerts(db, s)
    by_id = {str(o.id): o for o in rows(db, plan)}
    assert [by_id[i].due_at.day for i in alert.trigger_data_ids] == [3, 10][-n:]
    assert len(deliveries(db)) == 1


def test_short_toggle_between_grace_end_and_worker_run_skips_alert(db, s):
    """A felülvizsgálat P2j esete, az egységes szabály szerint: ha a pótlási idő
    lejárta (okt. 5. 0:00) és a háttérfolyamat futása (1:00) között a beteg rövid
    ideig le volt tiltva (0:10–0:20), a lezárás nem riaszt, akkor sem, ha a beteg a
    futáskor már aktív. (Sosem letiltott betegnél ugyanez a futás riasztana.) Az
    elmulasztás megmarad, és a következő elmulasztás sorozatában számít."""
    plan = daily_plan(db, s)
    missing_rule(db, s)  # 2 egymást követő
    run_occurrence_check(db, local(2026, 10, 4, 23))  # okt. 1. elmulasztva
    disable(db, s, local(2026, 10, 5, 0, 10))
    enable(db, s, local(2026, 10, 5, 0, 20))
    run_occurrence_check(db, local(2026, 10, 5, 1))  # okt. 2. lezárva, riasztás nélkül
    assert days(rows(db, plan), OccurrenceStatus.MISSED) == [1, 2]
    assert alerts(db, s) == []
    run_occurrence_check(db, local(2026, 10, 6, 1))  # okt. 3. elmulasztva: sorozat
    (alert,) = alerts(db, s)
    by_id = {str(o.id): o for o in rows(db, plan)}
    assert [by_id[i].due_at.day for i in alert.trigger_data_ids] == [2, 3]


def test_overlap_helper_boundaries(db, s):
    disable(db, s, local(2026, 10, 5, 10))
    enable(db, s, local(2026, 10, 6, 10))
    periods = disabled_periods(db, s["pid"])
    assert overlaps(periods, local(2026, 10, 6, 9), local(2026, 10, 7))
    assert not overlaps(periods, local(2026, 10, 6, 10), local(2026, 10, 7))  # a vég nem
    assert overlaps(periods, local(2026, 10, 4), local(2026, 10, 5, 10))  # a kezdet igen
    assert not overlaps(periods, local(2026, 10, 4), local(2026, 10, 5, 9))
