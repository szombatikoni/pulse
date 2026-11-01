"""Követési terv (M3, A2 3. lépés): az orvosi végpontok jogosultsága, az új
előírás ellenőrzései, a módosítás (lezárás + új előírás) atomisága és a
visszavonás alkalom-kezelése (javasolt döntés, 2026-10-30)."""

import uuid
from datetime import UTC, date, datetime, time, timedelta

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.core.security import create_access_token
from app.models import Assignment, AssignmentOccurrence, Frequency, OccurrenceStatus
from app.services import plans
from app.services.measurements import get_type_by_code, record_measurement
from app.services.occurrences import run_occurrence_check
from app.services.plans import PlanError, PlanParams
from app.services.questionnaires import assign_questionnaire, create_template
from app.services.tasks import assign_measurement, patient_tasks
from seed.questionnaires import WELLBEING_CODE, WELLBEING_NAME, WELLBEING_V1
from tests.factories import assign, make_admin, make_doctor, make_patient


def auth(user):
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def today() -> date:
    return datetime.now(settings.tz).date()


def at(day: date, hh: int, mm: int = 0) -> datetime:
    return datetime.combine(day, time(hh, mm), tzinfo=settings.tz)


@pytest.fixture
def setup(db, measurement_types):
    """Orvos a saját betegével; egy idegen orvos (a beteg nincs hozzá rendelve),
    egy idegen beteg a saját orvosával, egy admin, és a „Közérzet" kérdőív."""
    doctor = make_doctor(db)
    patient = make_patient(db)
    other_doctor = make_doctor(db, email="masik@test.example", name="Dr. Másik")
    foreign = make_patient(db, email="idegen@test.example", name="Idegen Beteg")
    link = assign(db, doctor, patient, valid_from=datetime.now(UTC) - timedelta(days=30))
    assign(db, other_doctor, foreign)
    template = create_template(
        db, code=WELLBEING_CODE, name=WELLBEING_NAME, created_by=doctor.id, spec=WELLBEING_V1
    )
    return {
        "doctor": doctor,
        "patient": patient,
        "other_doctor": other_doctor,
        "foreign": foreign,
        "admin": make_admin(db),
        "link": link,
        "template": template,
        "pid": patient.patient_profile.id,
    }


def url(setup, suffix="", patient="patient"):
    return f"/api/patients/{setup[patient].patient_profile.id}/assignments{suffix}"


def body(**overrides):
    data = {
        "kind": "measurement",
        "code": "blood_pressure",
        "frequency": "daily",
        "due_time": "10:00",
        "suggested_time": "07:30",
    }
    data.update(overrides)
    return data


def measurement_plan(db, setup, start, code="blood_pressure", patient="patient", end_date=None):
    """Előírás közvetlenül (múltbeli kezdettel is, amit a végpont nem enged)."""
    assignment = assign_measurement(
        db,
        patient_id=setup[patient].patient_profile.id,
        measurement_type=get_type_by_code(db, code),
        assigned_by=setup["doctor"].id,
        start_date=start,
    )
    assignment.end_date = end_date
    db.flush()
    return assignment


def occurrences(db, assignment):
    return {
        o.due_at.astimezone(settings.tz).date(): o.status
        for o in db.scalars(
            select(AssignmentOccurrence).where(AssignmentOccurrence.assignment_id == assignment.id)
        )
    }


def history_plan(db, setup):
    """Öt napja kezdődött napi vérnyomás-előírás vegyes alkalmakkal: az első
    három elmulasztva, tegnapelőtt késve, tegnap időben teljesítve, ma esedékes."""
    d = today()
    old = measurement_plan(db, setup, d - timedelta(days=5))
    for day, hh in ((d - timedelta(days=2), 12), (d - timedelta(days=1), 8)):
        record_measurement(
            db,
            patient_id=setup["pid"],
            type_code="blood_pressure",
            values={"systolic": 128, "diastolic": 82},
            measured_at=at(day, hh),
            now=at(day, hh),
        )
    run_occurrence_check(db)
    assert occurrences(db, old) == {
        d - timedelta(days=5): OccurrenceStatus.MISSED,
        d - timedelta(days=4): OccurrenceStatus.MISSED,
        d - timedelta(days=3): OccurrenceStatus.MISSED,
        d - timedelta(days=2): OccurrenceStatus.FULFILLED_LATE,
        d - timedelta(days=1): OccurrenceStatus.FULFILLED,
        d: OccurrenceStatus.DUE,
    }
    return old


# --- Jogosultság ---------------------------------------------------------------


def _calls(setup, assignment_id):
    return [
        ("get", url(setup), None),
        ("post", url(setup), body()),
        ("post", url(setup, f"/{assignment_id}/replace"), body(frequency="weekly")),
        ("post", url(setup, f"/{assignment_id}/revoke"), None),
    ]


@pytest.mark.parametrize("call", range(4))
@pytest.mark.parametrize("role", ["other_doctor", "patient", "admin"])
def test_only_the_assigned_doctor_may_use_the_plan(client, db, setup, role, call):
    assignment = measurement_plan(db, setup, today(), code="heart_rate")
    method, path, payload = _calls(setup, assignment.id)[call]
    response = client.request(method, path, json=payload, headers=auth(setup[role]))
    assert response.status_code == 403
    db.refresh(assignment)
    assert assignment.revoked_at is None


@pytest.mark.parametrize("call", range(4))
def test_the_plan_requires_login(client, db, setup, call):
    assignment = measurement_plan(db, setup, today(), code="heart_rate")
    method, path, payload = _calls(setup, assignment.id)[call]
    assert client.request(method, path, json=payload).status_code == 401


@pytest.mark.parametrize("action", ["replace", "revoke"])
def test_another_patients_assignment_is_not_reachable_through_own_patient(
    client, db, setup, action
):
    """A saját beteg útvonalán sem érhető el egy idegen beteg előírása (404)."""
    foreign_plan = measurement_plan(db, setup, today(), patient="foreign")
    response = client.post(
        url(setup, f"/{foreign_plan.id}/{action}"),
        json=body(frequency="weekly") if action == "replace" else None,
        headers=auth(setup["doctor"]),
    )
    assert response.status_code == 404
    db.refresh(foreign_plan)
    assert foreign_plan.revoked_at is None


def test_unknown_assignment_is_404(client, setup):
    response = client.post(url(setup, f"/{uuid.uuid4()}/revoke"), headers=auth(setup["doctor"]))
    assert response.status_code == 404


def test_access_ends_with_the_doctor_patient_link(client, db, setup):
    setup["link"].valid_to = datetime.now(UTC) - timedelta(seconds=1)
    db.flush()
    assert client.get(url(setup), headers=auth(setup["doctor"])).status_code == 403
    assert client.post(url(setup), json=body(), headers=auth(setup["doctor"])).status_code == 403


def test_questionnaire_catalog_is_for_doctors(client, db, setup):
    inactive = create_template(
        db, code="old", name="Régi", created_by=setup["doctor"].id, spec=WELLBEING_V1
    )
    inactive.is_active = False
    db.flush()
    response = client.get("/api/questionnaires", headers=auth(setup["doctor"]))
    assert response.status_code == 200
    assert response.json() == [{"code": WELLBEING_CODE, "name": WELLBEING_NAME}]
    for role in ("patient", "admin"):
        assert client.get("/api/questionnaires", headers=auth(setup[role])).status_code == 403


# --- Lista és új előírás -------------------------------------------------------


def test_doctor_creates_and_lists_a_measurement_plan(client, db, setup):
    response = client.post(url(setup), json=body(), headers=auth(setup["doctor"]))
    assert response.status_code == 201
    created = response.json()
    assert created["kind"] == "measurement"
    assert created["code"] == "blood_pressure"
    assert created["start_date"] == today().isoformat()  # alapból ma
    assert created["due_time"] == "10:00:00"
    assert created["suggested_time"] == "07:30:00"
    assert created["assigned_by"] == "Dr. Teszt"
    assert created["status"] == "active"
    assert created["revoked_at"] is None and created["replaced_by"] is None

    listed = client.get(url(setup), headers=auth(setup["doctor"])).json()
    assert [a["id"] for a in listed] == [created["id"]]
    # A beteg teendői között azonnal megjelenik.
    assert [t.code for t in patient_tasks(db, setup["pid"])] == ["blood_pressure"]


def test_doctor_assigns_a_questionnaire_every_n_days_with_an_end(client, setup):
    start = today() + timedelta(days=3)
    response = client.post(
        url(setup),
        json=body(
            kind="questionnaire",
            code=WELLBEING_CODE,
            frequency="every_n_days",
            interval_days=3,
            due_time="20:00",
            suggested_time=None,
            start_date=start.isoformat(),
            end_date=(start + timedelta(days=30)).isoformat(),
        ),
        headers=auth(setup["doctor"]),
    )
    assert response.status_code == 201
    created = response.json()
    assert created["name"] == WELLBEING_NAME
    assert created["interval_days"] == 3
    assert created["status"] == "upcoming"


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"start_date": (date.today() - timedelta(days=3)).isoformat()}, "start_in_past"),
        (
            {
                "start_date": (date.today() + timedelta(days=5)).isoformat(),
                "end_date": (date.today() + timedelta(days=4)).isoformat(),
            },
            "end_before_start",
        ),
        ({"code": "cholesterol"}, "unknown_target"),
        ({"kind": "questionnaire", "code": "blood_pressure"}, "unknown_target"),
    ],
)
def test_invalid_plan_is_rejected_with_a_code(client, db, setup, overrides, code):
    response = client.post(url(setup), json=body(**overrides), headers=auth(setup["doctor"]))
    assert response.status_code == 422
    assert response.json()["detail"] == {"code": code}
    assert db.scalar(select(func.count()).select_from(Assignment)) == 0


@pytest.mark.parametrize(
    "overrides",
    [
        {"frequency": "every_n_days"},  # időköz nélkül
        {"frequency": "every_n_days", "interval_days": 0},
        {"frequency": "daily", "interval_days": 2},  # időköz napi előírásnál
        {"frequency": "monthly"},
        {"due_time": "25:00"},
        {"kind": "medication"},
    ],
)
def test_malformed_plan_is_rejected(client, db, setup, overrides):
    response = client.post(url(setup), json=body(**overrides), headers=auth(setup["doctor"]))
    assert response.status_code == 422
    assert db.scalar(select(func.count()).select_from(Assignment)) == 0


def test_inactive_questionnaire_cannot_be_assigned(client, db, setup):
    setup["template"].is_active = False
    db.flush()
    response = client.post(
        url(setup),
        json=body(kind="questionnaire", code=WELLBEING_CODE, frequency="weekly"),
        headers=auth(setup["doctor"]),
    )
    assert response.status_code == 422
    assert response.json()["detail"] == {"code": "unknown_target"}


def test_second_valid_plan_for_the_same_target_is_a_conflict(client, db, setup):
    """Ugyanarra a célra egyszerre egy érvényes előírás: a változtatás útja a
    módosítás. Más cél, vagy a meglévő vége utáni kezdet viszont rendben van."""
    measurement_plan(db, setup, today(), end_date=today() + timedelta(days=9))
    response = client.post(
        url(setup),
        json=body(start_date=(today() + timedelta(days=9)).isoformat()),
        headers=auth(setup["doctor"]),
    )
    assert response.status_code == 409
    assert response.json()["detail"] == {"code": "overlap"}

    after_end = body(start_date=(today() + timedelta(days=10)).isoformat())
    assert client.post(url(setup), json=after_end, headers=auth(setup["doctor"])).status_code == 201
    other_target = body(code="heart_rate")
    assert (
        client.post(url(setup), json=other_target, headers=auth(setup["doctor"])).status_code == 201
    )


# --- Módosítás -----------------------------------------------------------------


def test_replace_closes_the_old_and_creates_the_new_in_one_step(client, db, setup):
    old = history_plan(db, setup)
    response = client.post(
        url(setup, f"/{old.id}/replace"),
        json={"frequency": "weekly", "due_time": "20:00"},
        headers=auth(setup["doctor"]),
    )
    assert response.status_code == 201
    new = response.json()
    assert new["code"] == "blood_pressure"  # ugyanaz a cél
    assert new["frequency"] == "weekly"
    assert new["start_date"] == today().isoformat()  # alapból ma
    assert new["suggested_time"] is None
    assert new["status"] == "active"

    db.refresh(old)
    assert old.revoked_at is not None
    # A régi nyitott alkalma törlődött, a történet megmaradt.
    d = today()
    assert occurrences(db, old) == {
        d - timedelta(days=5): OccurrenceStatus.MISSED,
        d - timedelta(days=4): OccurrenceStatus.MISSED,
        d - timedelta(days=3): OccurrenceStatus.MISSED,
        d - timedelta(days=2): OccurrenceStatus.FULFILLED_LATE,
        d - timedelta(days=1): OccurrenceStatus.FULFILLED,
    }

    # A listában a váltás az adatból látszik: a régi helyébe az új lépett.
    listed = {a["id"]: a for a in client.get(url(setup), headers=auth(setup["doctor"])).json()}
    assert listed[str(old.id)]["status"] == "revoked"
    assert listed[str(old.id)]["replaced_by"] == new["id"]
    assert listed[new["id"]]["replaced_by"] is None
    # A beteg teendője már az új (heti) előírás szerint számolódik.
    tasks = patient_tasks(db, setup["pid"])
    assert [(t.code, t.assignment.frequency) for t in tasks] == [
        ("blood_pressure", Frequency.WEEKLY)
    ]


def test_replace_of_an_upcoming_plan_keeps_its_start(client, db, setup):
    start = today() + timedelta(days=4)
    old = measurement_plan(db, setup, start)
    response = client.post(
        url(setup, f"/{old.id}/replace"),
        json={"frequency": "every_n_days", "interval_days": 2, "due_time": "09:00"},
        headers=auth(setup["doctor"]),
    )
    assert response.status_code == 201
    new = response.json()
    assert new["start_date"] == start.isoformat()
    listed = {a["id"]: a for a in client.get(url(setup), headers=auth(setup["doctor"])).json()}
    assert listed[str(old.id)]["replaced_by"] == new["id"]


def test_replacing_twice_on_the_same_day_chains_the_versions(client, db, setup):
    first = measurement_plan(db, setup, today() - timedelta(days=3))
    headers = auth(setup["doctor"])
    second = client.post(
        url(setup, f"/{first.id}/replace"),
        json={"frequency": "weekly", "due_time": "10:00"},
        headers=headers,
    ).json()
    third = client.post(
        url(setup, f"/{second['id']}/replace"),
        json={"frequency": "daily", "due_time": "12:00"},
        headers=headers,
    ).json()
    listed = {a["id"]: a for a in client.get(url(setup), headers=headers).json()}
    assert listed[str(first.id)]["replaced_by"] == second["id"]
    assert listed[second["id"]]["replaced_by"] == third["id"]
    assert listed[third["id"]]["replaced_by"] is None
    assert [a["status"] for a in listed.values()] == ["revoked", "revoked", "active"]


@pytest.mark.parametrize(
    ("payload", "status_code"),
    [
        ({"frequency": "every_n_days", "due_time": "10:00"}, 422),  # időköz nélkül
        (
            {
                "frequency": "weekly",
                "due_time": "10:00",
                "start_date": (date.today() - timedelta(days=1)).isoformat(),
            },
            422,
        ),
    ],
)
def test_failed_replace_leaves_the_old_plan_untouched(client, db, setup, payload, status_code):
    old = history_plan(db, setup)
    response = client.post(
        url(setup, f"/{old.id}/replace"), json=payload, headers=auth(setup["doctor"])
    )
    assert response.status_code == status_code
    db.refresh(old)
    assert old.revoked_at is None
    assert occurrences(db, old)[today()] is OccurrenceStatus.DUE
    assert db.scalar(select(func.count()).select_from(Assignment)) == 1


def test_replace_conflicting_with_another_plan_leaves_the_old_untouched(client, db, setup):
    """Az új előírás ütközne egy már rögzített, később kezdődővel: 409, és a
    régi sem záródik le."""
    old = measurement_plan(db, setup, today(), end_date=today() + timedelta(days=6))
    measurement_plan(db, setup, today() + timedelta(days=7))
    response = client.post(
        url(setup, f"/{old.id}/replace"),
        json={"frequency": "weekly", "due_time": "10:00"},  # vég nélkül: átér a későbbire
        headers=auth(setup["doctor"]),
    )
    assert response.status_code == 409
    assert response.json()["detail"] == {"code": "overlap"}
    db.refresh(old)
    assert old.revoked_at is None


def test_replace_is_atomic_when_closing_the_old_fails(db, setup, monkeypatch):
    """Ha a lezárás (az új beszúrása UTÁN) hibára fut, a tranzakció egészében
    visszagörgetődik: nincs új előírás, és a régi sem záródik le."""
    old = history_plan(db, setup)
    real_close = plans._close

    def failing_close(db_, assignment, now):
        real_close(db_, assignment, now)
        raise RuntimeError("szimulált hiba a lezárás után")

    monkeypatch.setattr(plans, "_close", failing_close)
    params = PlanParams(Frequency.WEEKLY, None, time(20, 0), None, None, None)
    with pytest.raises(RuntimeError), db.begin_nested():
        plans.replace(db, old, assigned_by=setup["doctor"].id, params=params)

    db.refresh(old)
    assert old.revoked_at is None
    assert occurrences(db, old)[today()] is OccurrenceStatus.DUE
    assert db.scalar(select(func.count()).select_from(Assignment)) == 1


def test_replace_fails_before_touching_the_old_if_the_new_is_invalid(db, setup):
    """Az ellenőrzés az első módosítás előtt fut: a hibás új előírás a régit
    a tranzakción belül sem érinti."""
    old = history_plan(db, setup)
    params = PlanParams(Frequency.WEEKLY, None, time(20, 0), None, today(), today() - timedelta(1))
    with pytest.raises(PlanError, match="end_before_start"):
        plans.replace(db, old, assigned_by=setup["doctor"].id, params=params)
    assert old.revoked_at is None
    assert occurrences(db, old)[today()] is OccurrenceStatus.DUE


# --- Visszavonás ---------------------------------------------------------------


def test_revoke_deletes_open_occurrences_and_keeps_history(client, db, setup):
    old = history_plan(db, setup)
    response = client.post(url(setup, f"/{old.id}/revoke"), headers=auth(setup["doctor"]))
    assert response.status_code == 200
    assert response.json()["status"] == "revoked"
    assert response.json()["revoked_at"] is not None

    d = today()
    assert occurrences(db, old) == {
        d - timedelta(days=5): OccurrenceStatus.MISSED,
        d - timedelta(days=4): OccurrenceStatus.MISSED,
        d - timedelta(days=3): OccurrenceStatus.MISSED,
        d - timedelta(days=2): OccurrenceStatus.FULFILLED_LATE,
        d - timedelta(days=1): OccurrenceStatus.FULFILLED,
    }
    # A háttérfolyamat nem nyit neki újat, és a beteg teendői közül is kikerül.
    assert run_occurrence_check(db).opened == 0
    assert today() not in occurrences(db, old)
    assert patient_tasks(db, setup["pid"]) == []


def test_revoke_keeps_a_submission_fulfilled_occurrence(client, db, setup):
    """Kérdőívnél a kitöltés az alkalmára hivatkozik: a teljesített alkalom a
    visszavonás után is megmarad, a hivatkozás nem szakad meg."""
    from app.services.occurrences import fill_version
    from app.services.questionnaires import submit_questionnaire

    assignment = assign_questionnaire(
        db,
        patient_id=setup["pid"],
        template=setup["template"],
        assigned_by=setup["doctor"].id,
        start_date=today(),
        frequency=Frequency.DAILY,
    )
    questions = fill_version(db, setup["pid"], setup["template"].id, today()).questions
    submission, _ = submit_questionnaire(
        db,
        patient_id=setup["pid"],
        template_code=WELLBEING_CODE,
        answers={str(q.id): q.options_scores[0]["value"] for q in questions},
    )
    response = client.post(url(setup, f"/{assignment.id}/revoke"), headers=auth(setup["doctor"]))
    assert response.status_code == 200
    occurrence = db.get(AssignmentOccurrence, submission.occurrence_id)
    assert occurrence is not None
    assert occurrence.status in (OccurrenceStatus.FULFILLED, OccurrenceStatus.FULFILLED_LATE)


@pytest.mark.parametrize("action", ["replace", "revoke"])
def test_revoked_or_ended_plan_cannot_be_changed(client, db, setup, action):
    revoked = measurement_plan(db, setup, today() - timedelta(days=9))
    revoked.revoked_at = datetime.now(UTC) - timedelta(days=1)
    ended = measurement_plan(
        db, setup, today() - timedelta(days=9), code="heart_rate", end_date=today() - timedelta(1)
    )
    db.flush()
    payload = {"frequency": "weekly", "due_time": "10:00"} if action == "replace" else None
    for assignment, code in ((revoked, "already_revoked"), (ended, "already_ended")):
        response = client.post(
            url(setup, f"/{assignment.id}/{action}"), json=payload, headers=auth(setup["doctor"])
        )
        assert response.status_code == 409
        assert response.json()["detail"] == {"code": code}
    assert db.scalar(select(func.count()).select_from(Assignment)) == 2


# --- A váltás kiolvasása az adatból ---------------------------------------------


def test_plain_revoke_and_a_later_new_plan_is_not_a_modification(client, db, setup):
    """Ha a visszavonás és az új kezdete nem ér össze, az nem módosítás."""
    old = measurement_plan(db, setup, today() - timedelta(days=9))
    old.revoked_at = datetime.now(UTC) - timedelta(days=3)
    db.flush()
    created = client.post(url(setup), json=body(), headers=auth(setup["doctor"])).json()
    listed = {a["id"]: a for a in client.get(url(setup), headers=auth(setup["doctor"])).json()}
    assert listed[str(old.id)]["replaced_by"] is None
    assert listed[created["id"]]["replaced_by"] is None


def test_plan_continuing_right_after_an_end_date_counts_as_a_change(client, db, setup):
    old = measurement_plan(
        db, setup, today() - timedelta(days=9), end_date=today() + timedelta(days=2)
    )
    created = client.post(
        url(setup),
        json=body(frequency="weekly", start_date=(today() + timedelta(days=3)).isoformat()),
        headers=auth(setup["doctor"]),
    ).json()
    listed = {a["id"]: a for a in client.get(url(setup), headers=auth(setup["doctor"])).json()}
    assert listed[str(old.id)]["replaced_by"] == created["id"]
    assert listed[str(old.id)]["status"] == "active"


def test_replace_of_an_inactive_questionnaire_is_rejected(client, db, setup):
    """Inaktív kérdőívre módosítással sem adható új előírás; a régi marad."""
    old = assign_questionnaire(
        db,
        patient_id=setup["pid"],
        template=setup["template"],
        assigned_by=setup["doctor"].id,
        start_date=today(),
    )
    setup["template"].is_active = False
    db.flush()
    response = client.post(
        url(setup, f"/{old.id}/replace"),
        json={"frequency": "daily", "due_time": "20:00"},
        headers=auth(setup["doctor"]),
    )
    assert response.status_code == 422
    assert response.json()["detail"] == {"code": "unknown_target"}
    db.refresh(old)
    assert old.revoked_at is None
