"""A beteg teendői (F6, F14): időszak, határidő, kész / esedékes / lejárt, az előző
időszak elmaradása és pótolhatósága (docs/M1/03_adatmodell.md, „Előírás és alkalom")."""

from datetime import UTC, date, datetime, time, timedelta

import pytest

from app.core.config import settings
from app.core.security import create_access_token
from app.models import Frequency
from app.services.measurements import get_type_by_code, record_measurement
from app.services.questionnaires import assign_questionnaire, create_template, submit_questionnaire
from app.services.tasks import TaskState, assign_measurement, patient_tasks
from seed.questionnaires import WELLBEING_CODE, WELLBEING_NAME, WELLBEING_V1
from tests.factories import assign, make_admin, make_doctor, make_measurement_types, make_patient


def local(y, m, d, hh=0, mm=0):
    """Időpont a rendszer időzónájában (Europe/Budapest; október 17-én UTC+2)."""
    return datetime(y, m, d, hh, mm, tzinfo=settings.tz)


@pytest.fixture
def setup(db):
    make_measurement_types(db)
    doctor = make_doctor(db)
    patient = make_patient(db)
    assign(db, doctor, patient)
    return {"doctor": doctor, "patient": patient, "pid": patient.patient_profile.id}


def bp_daily(db, setup, start=date(2026, 10, 1), due=time(10, 0)):
    return assign_measurement(
        db,
        patient_id=setup["pid"],
        measurement_type=get_type_by_code(db, "blood_pressure"),
        assigned_by=setup["doctor"].id,
        start_date=start,
        frequency=Frequency.DAILY,
        due_time=due,
    )


def record(db, setup, measured_at, now=None):
    return record_measurement(
        db,
        patient_id=setup["pid"],
        type_code="blood_pressure",
        values={"systolic": 128, "diastolic": 82},
        measured_at=measured_at,
        now=now or measured_at,
    )


def the_task(db, setup, now):
    [task] = patient_tasks(db, setup["pid"], now=now)
    return task


def test_daily_task_is_due_then_late_then_done(db, setup):
    bp_daily(db, setup)
    record(db, setup, local(2026, 10, 16, 7, 30))  # tegnap megvolt

    due = the_task(db, setup, local(2026, 10, 17, 8, 0))
    assert due.state is TaskState.DUE
    assert due.period_start == local(2026, 10, 17)
    assert due.period_end == local(2026, 10, 18)
    assert due.due_at == local(2026, 10, 17, 10, 0)

    assert the_task(db, setup, local(2026, 10, 17, 11, 0)).state is TaskState.LATE

    record(db, setup, local(2026, 10, 17, 11, 5))
    done = the_task(db, setup, local(2026, 10, 17, 11, 10))
    assert done.state is TaskState.DONE
    assert done.done_at == local(2026, 10, 17, 11, 5)
    assert not done.previous_missed


def test_weekly_period_counts_from_the_start_date(db, setup):
    template = create_template(
        db,
        code=WELLBEING_CODE,
        name=WELLBEING_NAME,
        created_by=setup["doctor"].id,
        spec=WELLBEING_V1,
    )
    # Kedden kezdődött: az időszakok keddtől hétfőig tartanak, a határidő hétfő 20:00.
    assign_questionnaire(
        db,
        patient_id=setup["pid"],
        template=template,
        assigned_by=setup["doctor"].id,
        start_date=date(2026, 10, 6),
        frequency=Frequency.WEEKLY,
        due_time=time(20, 0),
    )
    task = the_task(db, setup, local(2026, 10, 17, 9, 0))
    assert task.period_start == local(2026, 10, 13)
    assert task.period_end == local(2026, 10, 20)
    assert task.due_at == local(2026, 10, 19, 20, 0)
    assert task.state is TaskState.DUE
    # Az előző hét (okt. 6–12.) kitöltés nélkül maradt, de kérdőívnél nincs pótlás.
    assert task.previous_missed
    assert task.catch_up_until is None

    questions = template.versions[0].questions
    answers = {str(q.id): q.options_scores[0]["value"] for q in questions}
    submit_questionnaire(
        db,
        patient_id=setup["pid"],
        template_code=WELLBEING_CODE,
        answers=answers,
        now=local(2026, 10, 17, 9, 30),
    )
    assert the_task(db, setup, local(2026, 10, 17, 9, 31)).state is TaskState.DONE


def test_missed_measurement_can_be_caught_up_within_two_days(db, setup):
    bp_daily(db, setup)
    record(db, setup, local(2026, 10, 15, 7, 30))  # okt. 16-án nem mért
    now = local(2026, 10, 17, 8, 0)

    task = the_task(db, setup, now)
    assert task.previous_missed
    # Az okt. 16-i időszak éjfélkor ért véget; a mérés ideje két napig visszadátumozható.
    assert task.catch_up_until == local(2026, 10, 19)
    assert task.catch_up_suggested_at == local(2026, 10, 16, 10, 0)

    # A javasolt időponttal a rögzítés tényleg elfogadott, és az elmaradás megszűnik.
    record(db, setup, task.catch_up_suggested_at, now=now)
    assert not the_task(db, setup, now).previous_missed


def test_first_period_has_no_previous_one(db, setup):
    bp_daily(db, setup, start=date(2026, 10, 17))
    task = the_task(db, setup, local(2026, 10, 17, 8, 0))
    assert not task.previous_missed
    assert task.catch_up_until is None


def test_the_local_day_decides_the_period(db, setup):
    bp_daily(db, setup)
    record(db, setup, local(2026, 10, 16, 7, 0))
    # Helyi idő szerint 23:10-kor mért (UTC-ben még ugyanaz a nap, 21:10).
    record(db, setup, local(2026, 10, 17, 23, 10))
    assert the_task(db, setup, local(2026, 10, 17, 23, 30)).state is TaskState.DONE

    # Helyi éjfél után új nap: 00:10 helyi = 22:10 UTC előző nap, mégis új időszak.
    after_midnight = local(2026, 10, 18, 0, 10)
    assert after_midnight.astimezone(UTC).date() == date(2026, 10, 17)
    task = the_task(db, setup, after_midnight)
    assert task.state is TaskState.DUE
    assert not task.previous_missed


def test_revoked_ended_and_future_assignments_are_not_listed(db, setup):
    revoked = bp_daily(db, setup)
    revoked.revoked_at = local(2026, 10, 10)
    ended = bp_daily(db, setup)
    ended.end_date = date(2026, 10, 16)
    bp_daily(db, setup, start=date(2026, 10, 20))
    db.flush()
    assert patient_tasks(db, setup["pid"], now=local(2026, 10, 17, 8, 0)) == []


def test_missing_tasks_come_first(db, setup):
    bp_daily(db, setup, due=time(10, 0))
    assign_measurement(
        db,
        patient_id=setup["pid"],
        measurement_type=get_type_by_code(db, "heart_rate"),
        assigned_by=setup["doctor"].id,
        start_date=date(2026, 10, 1),
        due_time=time(21, 0),
    )
    record(db, setup, local(2026, 10, 17, 7, 30))
    tasks = patient_tasks(db, setup["pid"], now=local(2026, 10, 17, 12, 0))
    assert [(t.code, t.state) for t in tasks] == [
        ("heart_rate", TaskState.DUE),
        ("blood_pressure", TaskState.DONE),
    ]


# --- A végpont: ki látja a beteg teendőit (F2) ---------------------------------------


def auth(user):
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def test_tasks_endpoint_for_patient_and_assigned_doctor_only(client, db, setup):
    bp_daily(db, setup, start=(datetime.now(settings.tz) - timedelta(days=3)).date())
    other_doctor = make_doctor(db, email="masik.orvos@test.example")
    other_patient = make_patient(db, email="masik.beteg@test.example")
    admin = make_admin(db)
    url = f"/api/patients/{setup['pid']}/tasks"

    for user in (setup["patient"], setup["doctor"]):
        response = client.get(url, headers=auth(user))
        assert response.status_code == 200
        [task] = response.json()
        assert task["kind"] == "measurement"
        assert task["code"] == "blood_pressure"
        assert task["state"] in {"due", "late"}
        assert task["previous_missed"] is True
        assert task["catch_up_suggested_at"] is not None

    for user in (other_doctor, other_patient, admin):
        assert client.get(url, headers=auth(user)).status_code == 403
    assert client.get(url).status_code == 401


def test_doctor_list_and_detail_include_the_tasks(client, db, setup):
    """Az orvos a beteglistán és az adatlapon is látja, követi-e a beteg a tervet."""
    bp_daily(db, setup, start=(datetime.now(settings.tz) - timedelta(days=3)).date())
    [row] = client.get("/api/doctor/patients", headers=auth(setup["doctor"])).json()
    assert [t["code"] for t in row["tasks"]] == ["blood_pressure"]
    detail = client.get(f"/api/patients/{setup['pid']}", headers=auth(setup["doctor"])).json()
    assert detail["tasks"] == row["tasks"]
