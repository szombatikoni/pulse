"""Követési terv, M3 A3: az új előírás aktuális alkalmát a már meglévő adat
teljesíti; indoklás a visszavonásnál és a módosításnál; a beteg jelzése a
közelmúltbeli visszavonásról és módosításról (a hallgató döntései, 2026-11-01)."""

from datetime import UTC, date, datetime, time, timedelta

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.security import create_access_token
from app.models import AssignmentOccurrence, AssignmentTarget, Frequency, OccurrenceStatus
from app.models.questionnaire import REVOKE_NOTE_MAX
from app.services import plans
from app.services.measurements import get_type_by_code, record_measurement
from app.services.occurrences import fill_version, run_occurrence_check
from app.services.plans import NOTICE_DAYS, PlanParams, plan_notices
from app.services.questionnaires import assign_questionnaire, create_template, submit_questionnaire
from app.services.status import PatientStatus, compute_status
from app.services.tasks import TaskState, assign_measurement, patient_tasks
from seed.questionnaires import WELLBEING_CODE, WELLBEING_NAME, WELLBEING_V1
from tests.factories import assign, make_admin, make_doctor, make_patient


def local(y, m, d, hh=0, mm=0):
    """Időpont a rendszer időzónájában (Europe/Budapest)."""
    return datetime(y, m, d, hh, mm, tzinfo=settings.tz)


def auth(user):
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


@pytest.fixture
def setup(db, measurement_types):
    doctor = make_doctor(db)
    patient = make_patient(db)
    other_doctor = make_doctor(db, email="masik@test.example", name="Dr. Másik")
    foreign = make_patient(db, email="idegen@test.example", name="Idegen Beteg")
    assign(db, doctor, patient, valid_from=datetime.now(UTC) - timedelta(days=30))
    assign(db, other_doctor, foreign, valid_from=datetime.now(UTC) - timedelta(days=30))
    template = create_template(
        db, code=WELLBEING_CODE, name=WELLBEING_NAME, created_by=doctor.id, spec=WELLBEING_V1
    )
    return {
        "doctor": doctor,
        "patient": patient,
        "other_doctor": other_doctor,
        "foreign": foreign,
        "admin": make_admin(db),
        "template": template,
        "pid": patient.patient_profile.id,
    }


def daily(due=time(10, 0), frequency=Frequency.DAILY, start=None):
    return PlanParams(frequency, None, due, None, start, None)


def create(db, setup, now, params=None, kind=AssignmentTarget.MEASUREMENT, code="blood_pressure"):
    return plans.create(
        db,
        patient_id=setup["pid"],
        assigned_by=setup["doctor"].id,
        kind=kind,
        code=code,
        params=params or daily(),
        now=now,
    )


def record(db, setup, measured_at, now=None, patient="patient"):
    measurement, _ = record_measurement(
        db,
        patient_id=setup[patient].patient_profile.id,
        type_code="blood_pressure",
        values={"systolic": 128, "diastolic": 82},
        measured_at=measured_at,
        now=now or measured_at,
    )
    return measurement


def occurrences_of(db, assignment):
    return list(
        db.scalars(
            select(AssignmentOccurrence)
            .where(AssignmentOccurrence.assignment_id == assignment.id)
            .order_by(AssignmentOccurrence.due_at)
        )
    )


# --- (b) Az időszakban már meglévő adat teljesíti az új előírás alkalmát -------


def test_todays_earlier_measurement_fulfils_a_new_plan(db, setup):
    """A beteg reggel mért, az orvos délben írja elő: nincs hamis „esedékes".
    (A határidő 13:00: a 10:00-s már lejárt volna, és az előírás holnap
    kezdődne, lásd test_plan_created_after_todays_deadline_starts_tomorrow.)"""
    measurement = record(db, setup, local(2026, 10, 17, 7, 30))
    now = local(2026, 10, 17, 12, 0)
    assignment = create(db, setup, now, params=daily(due=time(13, 0)))

    [occurrence] = occurrences_of(db, assignment)
    assert occurrence.status is OccurrenceStatus.FULFILLED  # rögzítés 7:30 < határidő 10:00
    assert occurrence.measurement_id == measurement.id
    assert occurrence.fulfilled_at == local(2026, 10, 17, 7, 30)

    [task] = patient_tasks(db, setup["pid"], now=now)
    assert task.state is TaskState.DONE
    assert task.done_at == local(2026, 10, 17, 7, 30)
    assert not task.previous_missed


def test_existing_measurement_after_the_due_time_fulfils_late(db, setup):
    # Új előírásnál ez már nem állhat elő: a határidő utáni létrehozásnál az első
    # alkalom a következő időszakban van (review K1, 2026-11-16). A módosításnál
    # az új előírás ma indul, így ott a késve teljesítés megmarad.
    old = assign_measurement(
        db,
        patient_id=setup["pid"],
        measurement_type=get_type_by_code(db, "blood_pressure"),
        assigned_by=setup["doctor"].id,
        start_date=date(2026, 10, 10),
    )
    record(db, setup, local(2026, 10, 17, 11, 0))
    new = plans.replace(
        db, old, assigned_by=setup["doctor"].id, params=daily(), now=local(2026, 10, 17, 12, 0)
    )
    [occurrence] = occurrences_of(db, new)
    assert occurrence.status is OccurrenceStatus.FULFILLED_LATE


def test_the_first_recorded_measurement_counts(db, setup):
    first = record(db, setup, local(2026, 10, 17, 9, 0))
    record(db, setup, local(2026, 10, 17, 8, 0), now=local(2026, 10, 17, 11, 0))  # később rögzítve
    assignment = create(db, setup, local(2026, 10, 17, 12, 0), params=daily(due=time(13, 0)))
    [occurrence] = occurrences_of(db, assignment)
    assert occurrence.measurement_id == first.id
    assert occurrence.status is OccurrenceStatus.FULFILLED


def test_measurement_outside_the_current_period_does_not_count(db, setup):
    # Tegnap 23:50 (helyi idő): az előző napé, az új előírás mai időszakába nem tartozik.
    record(db, setup, local(2026, 10, 16, 23, 50))
    now = local(2026, 10, 17, 8, 0)
    assignment = create(db, setup, now)
    [occurrence] = occurrences_of(db, assignment)
    assert occurrence.status is OccurrenceStatus.DUE
    [task] = patient_tasks(db, setup["pid"], now=now)
    assert task.state is TaskState.DUE
    assert not task.previous_missed  # ma kezdődött: nincs előző időszaka


def test_plan_starting_later_opens_no_occurrence(db, setup):
    record(db, setup, local(2026, 10, 17, 7, 30))
    params = daily(start=date(2026, 10, 20))
    assignment = create(db, setup, local(2026, 10, 17, 12, 0), params=params)
    assert occurrences_of(db, assignment) == []


def test_replace_fulfils_the_new_plan_from_todays_measurement(db, setup):
    old = assign_measurement(
        db,
        patient_id=setup["pid"],
        measurement_type=get_type_by_code(db, "blood_pressure"),
        assigned_by=setup["doctor"].id,
        start_date=date(2026, 10, 10),
    )
    measurement = record(db, setup, local(2026, 10, 17, 7, 30))
    now = local(2026, 10, 17, 12, 0)
    new = plans.replace(
        db, old, assigned_by=setup["doctor"].id, params=daily(frequency=Frequency.WEEKLY), now=now
    )
    # A régi mai alkalma (teljesített) megmarad, az új is teljesül ugyanazzal a méréssel.
    assert occurrences_of(db, old)[-1].status is OccurrenceStatus.FULFILLED
    [occurrence] = occurrences_of(db, new)
    assert occurrence.status is OccurrenceStatus.FULFILLED
    assert occurrence.measurement_id == measurement.id
    [task] = patient_tasks(db, setup["pid"], now=now)
    assert (task.assignment.id, task.state) == (new.id, TaskState.DONE)


def test_replace_of_a_questionnaire_keeps_the_submissions_reference(db, setup):
    old = assign_questionnaire(
        db,
        patient_id=setup["pid"],
        template=setup["template"],
        assigned_by=setup["doctor"].id,
        start_date=date(2026, 10, 10),
        frequency=Frequency.DAILY,
    )
    questions = fill_version(db, setup["pid"], setup["template"].id, date(2026, 10, 17)).questions
    submission, _ = submit_questionnaire(
        db,
        patient_id=setup["pid"],
        template_code=WELLBEING_CODE,
        answers={str(q.id): q.options_scores[0]["value"] for q in questions},
        now=local(2026, 10, 17, 9, 0),
    )
    old_occurrence = submission.occurrence_id
    now = local(2026, 10, 17, 12, 0)
    new = plans.replace(
        db,
        old,
        assigned_by=setup["doctor"].id,
        params=daily(due=time(20, 0), frequency=Frequency.WEEKLY),
        now=now,
    )
    [occurrence] = occurrences_of(db, new)
    assert occurrence.status is OccurrenceStatus.FULFILLED
    assert occurrence.fulfilled_at == local(2026, 10, 17, 9, 0)
    # A kitöltés hivatkozása a régi előírás (megmaradó) alkalmán marad: az a története.
    assert submission.occurrence_id == old_occurrence
    [task] = patient_tasks(db, setup["pid"], now=now)
    assert task.state is TaskState.DONE


# --- Első alkalom a következő időszakban (review K1, b megoldás, 2026-11-16) ---------


def heart_rate(db, setup, at):
    """Friss adat, de nem az előírt méréstípusból."""
    record_measurement(
        db,
        patient_id=setup["pid"],
        type_code="heart_rate",
        values={"value": 72},
        measured_at=at,
        now=at,
    )


@pytest.mark.parametrize(
    "params",
    [daily(), PlanParams(Frequency.EVERY_N_DAYS, 1, time(10, 0), None, None, None)],
    ids=["daily", "every_1_day"],
)
def test_plan_created_after_todays_deadline_starts_tomorrow(db, setup, params):
    """Okt. 17. 14:00-kor napi, 10:00-s határidejű előírás: a mai alkalom
    határideje már lejárt, ezért az előírás holnap kezdődik. Ma nincs alkalom,
    teendő és Adathiány; a háttérfolyamat 48 óra múlva sem zár hamis
    elmulasztást (és így elmaradt adat riasztás sem lehet belőle)."""
    heart_rate(db, setup, local(2026, 10, 17, 8, 0))
    record(db, setup, local(2026, 10, 17, 7, 30))  # a mai reggeli mérés sem számít
    now = local(2026, 10, 17, 14, 0)
    assignment = create(db, setup, now, params=params)
    assert assignment.start_date == date(2026, 10, 18)
    assert occurrences_of(db, assignment) == []
    assert patient_tasks(db, setup["pid"], now=now) == []
    assert run_occurrence_check(db, now).opened == 0
    assert compute_status(db, setup["pid"], now).status is PatientStatus.OK
    assert compute_status(db, setup["pid"], now + timedelta(hours=1)).status is PatientStatus.OK

    # Másnap az első alkalom esedékes, a beteg időben mér.
    tomorrow = local(2026, 10, 18, 8, 0)
    [task] = patient_tasks(db, setup["pid"], now=tomorrow)
    assert (task.due_at, task.state, task.previous_missed) == (
        local(2026, 10, 18, 10, 0),
        TaskState.DUE,
        False,
    )
    record(db, setup, local(2026, 10, 18, 9, 0))
    record(db, setup, local(2026, 10, 19, 9, 0))
    # A régi szabállyal a mai alkalom okt. 20. 0:00-kor (az időszak vége + 48
    # óra) elmulasztott lett volna; most nincs mit elmulasztani.
    check = run_occurrence_check(db, local(2026, 10, 20, 0, 1))
    assert check.missed == 0
    assert [o.status for o in occurrences_of(db, assignment)] == [
        OccurrenceStatus.FULFILLED,
        OccurrenceStatus.FULFILLED,
        OccurrenceStatus.DUE,
    ]


def test_plan_created_before_todays_deadline_starts_today(db, setup):
    now = local(2026, 10, 17, 9, 59)
    assignment = create(db, setup, now)
    assert assignment.start_date == date(2026, 10, 17)
    [occurrence] = occurrences_of(db, assignment)
    assert (occurrence.due_at, occurrence.status) == (
        local(2026, 10, 17, 10, 0),
        OccurrenceStatus.DUE,
    )
    [task] = patient_tasks(db, setup["pid"], now=now)
    assert task.state is TaskState.DUE


def test_plan_created_exactly_at_the_deadline_starts_today(db, setup):
    # A határ ugyanaz, mint a státusznál: a határidő pillanatában még nem lejárt.
    assignment = create(db, setup, local(2026, 10, 17, 10, 0))
    assert assignment.start_date == date(2026, 10, 17)


@pytest.mark.parametrize("hour", [9, 14])
def test_weekly_plan_mid_week_starts_today_either_way(db, setup, hour):
    """A heti előírás időszakai a kezdettől számítanak (nem naptári hetek): a
    szombaton (okt. 17.) felírt heti előírás első határideje okt. 23. 10:00,
    így a mai 10:00 előtt és után felírva is ma kezdődik."""
    now = local(2026, 10, 17, hour, 0)
    assignment = create(db, setup, now, params=daily(frequency=Frequency.WEEKLY))
    assert assignment.start_date == date(2026, 10, 17)
    [occurrence] = occurrences_of(db, assignment)
    assert occurrence.due_at == local(2026, 10, 23, 10, 0)
    [task] = patient_tasks(db, setup["pid"], now=now)
    assert task.state is TaskState.DUE


def test_plan_with_a_later_start_is_not_shifted(db, setup):
    params = daily(start=date(2026, 10, 20))
    assignment = create(db, setup, local(2026, 10, 17, 14, 0), params=params)
    assert assignment.start_date == date(2026, 10, 20)


def test_one_day_plan_after_its_deadline_keeps_its_start(db, setup):
    """Nyitott kérdés (a hallgató dönt): a ma véget érő napi előírásnak a
    határidő után nincs következő időszaka. A kezdet marad (a régi viselkedés),
    így a mai, már lejárt alkalom azonnal Adathiányt ad."""
    heart_rate(db, setup, local(2026, 10, 17, 8, 0))
    now = local(2026, 10, 17, 14, 0)
    params = PlanParams(Frequency.DAILY, None, time(10, 0), None, None, date(2026, 10, 17))
    assignment = create(db, setup, now, params=params)
    assert assignment.start_date == date(2026, 10, 17)
    assert compute_status(db, setup["pid"], now).status is PatientStatus.NO_DATA


def test_overlap_is_checked_with_the_shifted_start(db, setup):
    """A ma véget érő előírás mellé a határidő után felírt új (holnaptól
    kezdődő) előírás már nem fedi át (a tárolt kezdettel ellenőrzünk)."""
    first = create(
        db,
        setup,
        local(2026, 10, 15, 8, 0),
        params=PlanParams(Frequency.DAILY, None, time(10, 0), None, None, date(2026, 10, 17)),
    )
    second = create(db, setup, local(2026, 10, 17, 14, 0))
    assert (first.end_date, second.start_date) == (date(2026, 10, 17), date(2026, 10, 18))


def test_replace_after_the_deadline_still_starts_today(db, setup):
    """A módosításnál a szabály nem él (nyitott kérdés): az új ma indul, hogy a
    lánc (régi lezárása = új kezdete) megmaradjon; a régi mai, lejárt
    kötelezettsége így az újon folytatódik (Adathiány)."""
    old = assign_measurement(
        db,
        patient_id=setup["pid"],
        measurement_type=get_type_by_code(db, "blood_pressure"),
        assigned_by=setup["doctor"].id,
        start_date=date(2026, 10, 10),
    )
    heart_rate(db, setup, local(2026, 10, 17, 8, 0))
    now = local(2026, 10, 17, 14, 0)
    new = plans.replace(db, old, assigned_by=setup["doctor"].id, params=daily(), now=now)
    assert new.start_date == date(2026, 10, 17)
    [entry] = [e for e in plans.list_plan(db, setup["pid"], now) if e.assignment.id == old.id]
    assert entry.replaced_by == new.id
    assert compute_status(db, setup["pid"], now).status is PatientStatus.NO_DATA


def test_doctor_plan_after_todays_measurement_is_done_for_the_patient(client, db, setup):
    """Végponton át: a beteg most mért, az orvos most írja elő."""
    record(db, setup, datetime.now(UTC) - timedelta(seconds=1))
    response = client.post(
        f"/api/patients/{setup['pid']}/assignments",
        json={
            "kind": "measurement",
            "code": "blood_pressure",
            # Heti: az első határidő hat nap múlva van, így a futás napszakától
            # függetlenül ma indul (napi előírás 23:59 után holnap indulna, K1).
            "frequency": "weekly",
            "due_time": "23:59",
        },
        headers=auth(setup["doctor"]),
    )
    assert response.status_code == 201
    [task] = client.get(
        f"/api/patients/{setup['pid']}/tasks", headers=auth(setup["patient"])
    ).json()
    assert task["state"] == "done"


# --- (c) Indoklás a visszavonásnál és a módosításnál ----------------------------


def plan_url(setup, suffix=""):
    return f"/api/patients/{setup['pid']}/assignments{suffix}"


def new_plan(client, setup, **overrides):
    payload = {
        "kind": "measurement",
        "code": "blood_pressure",
        "frequency": "daily",
        "due_time": "10:00",
    }
    payload.update(overrides)
    response = client.post(plan_url(setup), json=payload, headers=auth(setup["doctor"]))
    assert response.status_code == 201
    return response.json()


def test_revoke_with_a_note(client, db, setup):
    created = new_plan(client, setup)
    response = client.post(
        plan_url(setup, f"/{created['id']}/revoke"),
        json={"note": "  A vérnyomása rendeződött.  "},
        headers=auth(setup["doctor"]),
    )
    assert response.status_code == 200
    assert response.json()["revoke_note"] == "A vérnyomása rendeződött."
    listed = client.get(plan_url(setup), headers=auth(setup["doctor"])).json()
    assert listed[0]["revoke_note"] == "A vérnyomása rendeződött."


@pytest.mark.parametrize("payload", [None, {}, {"note": None}, {"note": "   "}])
def test_revoke_without_a_note(client, db, setup, payload):
    created = new_plan(client, setup)
    response = client.post(
        plan_url(setup, f"/{created['id']}/revoke"), json=payload, headers=auth(setup["doctor"])
    )
    assert response.status_code == 200
    assert response.json()["status"] == "revoked"
    assert response.json()["revoke_note"] is None


@pytest.mark.parametrize("action", ["revoke", "replace"])
def test_too_long_note_is_rejected_and_nothing_changes(client, db, setup, action):
    # Heti: napszaktól függetlenül ma indul, tehát érvényes (a napi 10:00 után
    # holnap indulna, review K1).
    created = new_plan(client, setup, frequency="weekly")
    payload = {"note": "x" * (REVOKE_NOTE_MAX + 1)}
    if action == "replace":
        payload |= {"frequency": "weekly", "due_time": "10:00"}
    response = client.post(
        plan_url(setup, f"/{created['id']}/{action}"), json=payload, headers=auth(setup["doctor"])
    )
    assert response.status_code == 422
    [entry] = client.get(plan_url(setup), headers=auth(setup["doctor"])).json()
    assert entry["status"] == "active"


def test_replace_note_belongs_to_the_closed_plan(client, db, setup):
    created = new_plan(client, setup)
    response = client.post(
        plan_url(setup, f"/{created['id']}/replace"),
        json={"frequency": "weekly", "due_time": "10:00", "note": "Elég hetente."},
        headers=auth(setup["doctor"]),
    )
    assert response.status_code == 201
    assert response.json()["revoke_note"] is None
    listed = {a["id"]: a for a in client.get(plan_url(setup), headers=auth(setup["doctor"])).json()}
    assert listed[created["id"]]["revoke_note"] == "Elég hetente."
    assert listed[created["id"]]["replaced_by"] == response.json()["id"]


# --- (d) A beteg jelzése a közelmúltbeli változásokról ------------------------


def notices_url(setup, patient="patient"):
    return f"/api/patients/{setup[patient].patient_profile.id}/plan-notices"


def test_patient_sees_a_revocation_with_the_note(client, db, setup):
    created = new_plan(client, setup)
    client.post(
        plan_url(setup, f"/{created['id']}/revoke"),
        json={"note": "Már nem szükséges."},
        headers=auth(setup["doctor"]),
    )
    [notice] = client.get(notices_url(setup), headers=auth(setup["patient"])).json()
    assert notice["kind"] == "revoked"
    assert notice["code"] == "blood_pressure"
    assert notice["target_kind"] == "measurement"
    assert notice["frequency"] == "daily"
    assert notice["note"] == "Már nem szükséges."
    assert notice["new_frequency"] is None


def test_patient_sees_a_modification_with_the_new_frequency(client, db, setup):
    created = new_plan(client, setup)
    client.post(
        plan_url(setup, f"/{created['id']}/replace"),
        json={"frequency": "weekly", "due_time": "20:00", "note": "Elég hetente."},
        headers=auth(setup["doctor"]),
    )
    [notice] = client.get(notices_url(setup), headers=auth(setup["patient"])).json()
    assert notice["kind"] == "modified"
    assert notice["frequency"] == "daily"
    assert (notice["new_frequency"], notice["new_due_time"]) == ("weekly", "20:00:00")
    assert notice["note"] == "Elég hetente."


def test_patient_sees_the_modification_of_an_upcoming_plan_with_its_start(client, db, setup):
    """A még el nem kezdett előírás helyére az új a régi kezdetén lép (review
    K3): a beteg „módosult" jelzést kap (nem „visszavonta"), az új kezdetével
    (a felület ebből írja: „…-tól hetente"); az indoklás a régi előírásé."""
    start = datetime.now(settings.tz).date() + timedelta(days=5)
    created = new_plan(client, setup, start_date=start.isoformat())
    client.post(
        plan_url(setup, f"/{created['id']}/replace"),
        json={"frequency": "weekly", "due_time": "20:00", "note": "Elég hetente."},
        headers=auth(setup["doctor"]),
    )
    [notice] = client.get(notices_url(setup), headers=auth(setup["patient"])).json()
    assert notice["kind"] == "modified"
    assert notice["frequency"] == "daily"
    assert (notice["new_frequency"], notice["new_start_date"]) == ("weekly", start.isoformat())
    assert notice["note"] == "Elég hetente."
    # A módosítás ideje (nem az új kezdete) adja a jelzés idejét.
    changed = datetime.fromisoformat(notice["changed_at"])
    assert abs(changed - datetime.now(UTC)) < timedelta(minutes=1)


def test_a_plan_continuing_after_its_own_end_date_gives_no_notice(db, setup):
    """Ha az orvos eleve véggel írt elő, és utána kezdődik egy új, az nem
    módosítás a beteg felé (a régi nincs visszavonva): jelzés nem jár érte."""
    now = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)
    create(
        db, setup, now, PlanParams(Frequency.DAILY, None, time(10), None, None, date(2026, 11, 2))
    )
    create(db, setup, now, daily(frequency=Frequency.WEEKLY, start=date(2026, 11, 3)))
    assert plan_notices(db, setup["pid"], now) == []


def test_a_chain_of_changes_is_one_notice_with_the_final_state(client, db, setup):
    headers = auth(setup["doctor"])
    first = new_plan(client, setup)
    second = client.post(
        plan_url(setup, f"/{first['id']}/replace"),
        json={"frequency": "weekly", "due_time": "10:00", "note": "első"},
        headers=headers,
    ).json()
    third = client.post(
        plan_url(setup, f"/{second['id']}/replace"),
        json={
            "frequency": "every_n_days",
            "interval_days": 3,
            "due_time": "10:00",
            "note": "második",
        },
        headers=headers,
    ).json()
    [notice] = client.get(notices_url(setup), headers=auth(setup["patient"])).json()
    assert notice["kind"] == "modified"
    assert (notice["new_frequency"], notice["new_interval_days"]) == ("every_n_days", 3)
    assert notice["note"] == "második"
    assert notice["frequency"] == "daily"  # amiről indult

    # A lánc végét visszavonva egyetlen „visszavonta" jelzés marad, a saját indoklásával.
    client.post(plan_url(setup, f"/{third['id']}/revoke"), json={"note": "vége"}, headers=headers)
    [notice] = client.get(notices_url(setup), headers=auth(setup["patient"])).json()
    assert (notice["kind"], notice["note"]) == ("revoked", "vége")


def test_notice_window_edges(db, setup):
    now = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)
    inside = assign_measurement(
        db,
        patient_id=setup["pid"],
        measurement_type=get_type_by_code(db, "blood_pressure"),
        assigned_by=setup["doctor"].id,
        start_date=date(2026, 10, 1),
    )
    outside = assign_measurement(
        db,
        patient_id=setup["pid"],
        measurement_type=get_type_by_code(db, "heart_rate"),
        assigned_by=setup["doctor"].id,
        start_date=date(2026, 10, 1),
    )
    inside.revoked_at = now - timedelta(days=NOTICE_DAYS)  # pontosan a határon: még látszik
    outside.revoked_at = now - timedelta(days=NOTICE_DAYS, seconds=1)
    db.flush()
    assert [n.entry.code for n in plan_notices(db, setup["pid"], now)] == ["blood_pressure"]


def test_an_unchanged_plan_gives_no_notice(client, db, setup):
    new_plan(client, setup)
    assert client.get(notices_url(setup), headers=auth(setup["patient"])).json() == []


def test_notices_access(client, db, setup):
    created = new_plan(client, setup)
    client.post(plan_url(setup, f"/{created['id']}/revoke"), headers=auth(setup["doctor"]))
    for user in (setup["patient"], setup["doctor"]):
        response = client.get(notices_url(setup), headers=auth(user))
        assert response.status_code == 200
        assert len(response.json()) == 1
    for role in ("foreign", "other_doctor", "admin"):
        assert client.get(notices_url(setup), headers=auth(setup[role])).status_code == 403
    assert client.get(notices_url(setup)).status_code == 401
    # A másik beteg a saját (üres) listáját látja, a mi betegünk jelzését nem.
    foreign = client.get(notices_url(setup, "foreign"), headers=auth(setup["foreign"]))
    assert foreign.status_code == 200
    assert foreign.json() == []
