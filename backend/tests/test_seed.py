"""A seed (mesterséges demóadat, M2-leadandó) gépi ellenőrzése."""

from datetime import UTC, datetime, time, timedelta

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.models import (
    Alert,
    AlertEventType,
    Assignment,
    AssignmentOccurrence,
    DoctorPatient,
    Measurement,
    MeasurementType,
    OccurrenceStatus,
    QuestionnaireTemplate,
    Rule,
    RuleType,
    Severity,
    Submission,
    User,
)
from app.services.access import can_access_patient
from app.services.occurrences import OccurrenceCheck, run_occurrence_check
from app.services.rules import current_version
from app.services.status import PatientStatus, doctor_patient_list
from app.services.users import get_user_by_email
from seed.demo import ASSIGNMENTS, DEMO_PASSWORD, USERS, seed_demo_data


def count(db, model):
    return db.scalar(select(func.count()).select_from(model))


def test_seed_creates_demo_accounts_and_assignments(db):
    users_before, links_before = count(db, User), count(db, DoctorPatient)
    seed_demo_data(db)
    assert count(db, User) == users_before + len(USERS)
    assert count(db, DoctorPatient) == links_before + len(ASSIGNMENTS)


def test_seed_is_idempotent(db):
    seed_demo_data(db)
    models = (
        User,
        DoctorPatient,
        Rule,
        Measurement,
        Alert,
        QuestionnaireTemplate,
        Assignment,
        AssignmentOccurrence,
        Submission,
    )
    before = [count(db, m) for m in models]
    second_run = seed_demo_data(db)
    assert [count(db, m) for m in models] == before
    created = (
        "létrehozva",
        "összerendelve",
        "méréstípus",
        "szabályok",
        "mérések",
        "kérdőív",
        "kirendelés",
        "kitöltések",
    )
    assert not any(line.startswith(created) for line in second_run)


def test_seed_opens_and_closes_occurrences_at_once(db):
    # A seed végén lefut az alkalom-ellenőrzés: a háttérfolyamat első futására
    # nem marad munka. Tóth Mária esti pulzusmérése két hete indult, és még
    # egyszer sem rögzítette: a pótlási ablakon (2 nap) túli 12 nap elmulasztott,
    # a tegnapelőtti, a tegnapi és a mai alkalom még esedékes.
    now = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)
    log = seed_demo_data(db, now=now)
    assert any(line.startswith("alkalom-ellenőrzés") for line in log)
    assert run_occurrence_check(db, now) == OccurrenceCheck(0, 0)

    toth = get_user_by_email(db, "toth.maria@pulse.example").patient_profile
    statuses = db.scalars(
        select(AssignmentOccurrence.status)
        .join(Assignment)
        .join(MeasurementType)
        .where(Assignment.patient_id == toth.id, MeasurementType.code == "heart_rate")
    ).all()
    assert statuses.count(OccurrenceStatus.MISSED) == 12
    assert statuses.count(OccurrenceStatus.DUE) == 3
    assert len(statuses) == 15


@pytest.mark.parametrize("hour", [3, 9, 20])
def test_seeded_doctor_list_shows_every_status(db, hour):
    # A bemutatóhoz: Kovács doktor listáján minden státusz megjelenik (a Kezelve
    # kivételével), a valódi szabálykiértékelés eredményeként, priorizálva, a
    # futtatás napszakától függetlenül (a mérések reggel, a kitöltések este
    # vannak, a pótlási ablak 48 óra). A seed holnapi időpontja azért kell,
    # mert az összerendelés a valódi „most"-tól érvényes.
    now = datetime.combine(
        datetime.now(settings.tz).date() + timedelta(days=1), time(hour), tzinfo=settings.tz
    )
    seed_demo_data(db, now=now)
    kovacs = get_user_by_email(db, "dr.kovacs@pulse.example")
    rows = doctor_patient_list(db, kovacs.doctor_profile.id, now)
    assert [(p.name, r.status, [x.code for x in r.reasons]) for p, r in rows] == [
        # 186 Hgmm (küszöb, súlyos) és tartósan 140/90 felett (időablak); a
        # Közérzetet nem tölti ki.
        ("Varga Béla", PatientStatus.SEVERE, ["open_alert", "open_alert", "missed_occurrence"]),
        # Három 140/90 feletti érték egy héten belül, és figyelmeztető sávú kitöltés.
        ("Szabó János", PatientStatus.ATTENTION, ["open_alert", "open_alert"]),
        # A múlt heti Közérzet-alkalma elmaradt (a vérnyomását méri).
        ("Kiss Ilona", PatientStatus.NO_DATA, ["missed_occurrence"]),
        ("Molnár Katalin", PatientStatus.OK, ["fresh_data"]),
    ]
    varga, szabo, kiss, _ = (r for _, r in rows)
    assert [r.alert.rule_version.rule_type for r in varga.reasons[:2]] == [
        RuleType.THRESHOLD,
        RuleType.WINDOW,
    ]
    assert [r.alert.rule_version.rule_type for r in szabo.reasons] == [
        RuleType.WINDOW,
        RuleType.QUESTIONNAIRE,
    ]
    window_events = [e.event_type for e in szabo.reasons[0].alert.events]
    assert window_events == [AlertEventType.CREATED, AlertEventType.RE_TRIGGERED]
    assert kiss.reasons[0].occurrence.assignment.questionnaire_template_id is not None


def test_seed_rules_follow_the_comparison_setup(db):
    # 07_mukodesi_szabalyok.md, 5. rész: küszöb csak a kritikus határon, időablak,
    # kérdőív sáv és trend, elmaradt adat.
    seed_demo_data(db)
    molnar = get_user_by_email(db, "molnar.katalin@pulse.example").patient_profile
    versions = [
        current_version(db, rule.id)
        for rule in db.scalars(select(Rule).where(Rule.patient_id == molnar.id))
    ]
    by_type = [(v.rule_type, v.severity, v.params) for v in versions]
    assert (
        RuleType.THRESHOLD,
        Severity.SEVERE,
        {"measurement_type": "blood_pressure", "limits": {"systolic": {"max": 180}}},
    ) in by_type
    assert (
        RuleType.MISSING_DATA,
        Severity.MODERATE,
        {"measurement_type": "blood_pressure", "consecutive_missed": 2},
    ) in by_type
    assert sorted(v.rule_type for v in versions) == sorted(
        [
            RuleType.THRESHOLD,
            RuleType.WINDOW,
            RuleType.QUESTIONNAIRE,
            RuleType.QUESTIONNAIRE,
            RuleType.QUESTIONNAIRE,
            RuleType.MISSING_DATA,
        ]
    )
    trend = [v.params for v in versions if v.params.get("trend_count")]
    assert trend == [{"questionnaire": "wellbeing", "trend_count": 3}]


def test_seeded_doctor_sees_only_own_patient(db):
    seed_demo_data(db)
    kovacs = get_user_by_email(db, "dr.kovacs@pulse.example")
    szabo = get_user_by_email(db, "szabo.janos@pulse.example")
    toth = get_user_by_email(db, "toth.maria@pulse.example")
    assert can_access_patient(db, kovacs, szabo.patient_profile.id)
    assert not can_access_patient(db, kovacs, toth.patient_profile.id)


def test_seeded_accounts_can_log_in(client, db):
    seed_demo_data(db)
    for spec in USERS:
        response = client.post(
            "/api/auth/login", json={"email": spec["email"], "password": DEMO_PASSWORD}
        )
        assert response.status_code == 200, spec["email"]
