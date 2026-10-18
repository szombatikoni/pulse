"""Kérdőív-pontozás, verziók és a kérdőívszabály (F6, F11/3, F13;
07_mukodesi_szabalyok.md, 4. rész)."""

from datetime import UTC, date, datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.models import AlertEventType, QuestionType, RuleType, Severity
from app.services.questionnaires import (
    SubmissionError,
    VersionSpec,
    add_version,
    assign_questionnaire,
    band_for,
    create_template,
    current_version,
    scale_options,
    submit_questionnaire,
)
from app.services.rules import create_rule
from seed.questionnaires import WELLBEING_CODE, WELLBEING_NAME, WELLBEING_V1
from tests.factories import make_doctor, make_patient

NOW = datetime(2026, 10, 12, 18, 0, tzinfo=UTC)


@pytest.fixture
def doctor(db):
    return make_doctor(db)


@pytest.fixture
def template(db, doctor):
    return create_template(
        db, code=WELLBEING_CODE, name=WELLBEING_NAME, created_by=doctor.id, spec=WELLBEING_V1
    )


@pytest.fixture
def patient(db, doctor, template):
    patient = make_patient(db)
    assign_questionnaire(
        db,
        patient_id=patient.patient_profile.id,
        template=template,
        assigned_by=doctor.id,
        start_date=NOW.date() - timedelta(days=7),
    )
    return patient


def answers_for(db, template, sleep, fatigue, dizziness):
    """A három kérdésre adott válasz a kérdések azonosítójával."""
    q1, q2, q3 = current_version(db, template.id).questions
    return {str(q1.id): sleep, str(q2.id): fatigue, str(q3.id): dizziness}


def submit(db, patient, template, sleep, fatigue, dizziness, now=NOW):
    return submit_questionnaire(
        db,
        patient_id=patient.patient_profile.id,
        template_code=WELLBEING_CODE,
        answers=answers_for(db, template, sleep, fatigue, dizziness),
        now=now,
    )


def wellbeing_rule(db, patient, doctor, bands=("warning", "critical"), severity=Severity.MODERATE):
    return create_rule(
        db,
        patient_id=patient.patient_profile.id,
        created_by=doctor.id,
        rule_type=RuleType.QUESTIONNAIRE,
        params={"questionnaire": WELLBEING_CODE, "bands": list(bands)},
        severity=severity,
    )


# --- Pontozás ------------------------------------------------------------------


def test_scale_scoring_good_end_is_always_zero():
    spec = WELLBEING_V1.questions
    sleep = {o["value"]: o["score"] for o in scale_options(spec[0])}  # a nagyobb a jobb
    fatigue = {o["value"]: o["score"] for o in scale_options(spec[1])}  # a kisebb a jobb
    assert sleep == {"1": 4, "2": 3, "3": 2, "4": 1, "5": 0}
    assert fatigue == {"1": 0, "2": 1, "3": 2, "4": 3, "5": 4}


def test_scale_labels_mark_the_ends():
    labels = [o["label"] for o in scale_options(WELLBEING_V1.questions[0])]
    assert labels == ["1 – nagyon rosszul", "2", "3", "4", "5 – nagyon jól"]


def test_worked_example_from_the_m1_document(db, patient, template):
    # 07_mukodesi_szabalyok.md, 4. rész: alvás 4 → 1 pont, fáradtság 4 → 3 pont,
    # szédülés „Ritkán" → 2 pont; összesen 6 → figyelmeztető sáv.
    submission, _ = submit(db, patient, template, 4, 4, "rarely")
    assert [a.score for a in sorted(submission.answers, key=lambda a: a.question.order_no)] == [
        1,
        3,
        2,
    ]
    assert submission.total_score == 6
    assert band_for(submission.version, 6) == "warning"


@pytest.mark.parametrize(
    ("total", "band"),
    [
        (0, "normal"),
        (5, "normal"),
        (6, "warning"),
        (10, "warning"),
        (11, "critical"),
        (13, "critical"),
    ],
)
def test_band_boundaries(db, template, total, band):
    assert band_for(current_version(db, template.id), total) == band


def test_answers_accept_scale_value_as_number_or_text(db, patient, template):
    submission, _ = submit(db, patient, template, "5", 1, "never")
    assert submission.total_score == 0


# --- Érvénytelen kitöltés -----------------------------------------------------------


@pytest.mark.parametrize(
    ("sleep", "dizziness"),
    [(6, "never"), (0, "never"), (3, "sometimes"), (3, ["never"]), (True, "never")],
)
def test_invalid_answers_are_rejected(db, patient, template, sleep, dizziness):
    with pytest.raises(SubmissionError) as excinfo:
        submit(db, patient, template, sleep, 3, dizziness)
    assert excinfo.value.code == "invalid_answer"


def test_missing_answer_is_rejected(db, patient, template):
    answers = answers_for(db, template, 3, 3, "never")
    answers.pop(next(iter(answers)))
    with pytest.raises(SubmissionError) as excinfo:
        submit_questionnaire(
            db,
            patient_id=patient.patient_profile.id,
            template_code=WELLBEING_CODE,
            answers=answers,
            now=NOW,
        )
    assert excinfo.value.code == "missing_answer"


def test_unknown_question_is_rejected(db, patient, template):
    answers = answers_for(db, template, 3, 3, "never") | {"nincs-ilyen": 1}
    with pytest.raises(SubmissionError) as excinfo:
        submit_questionnaire(
            db,
            patient_id=patient.patient_profile.id,
            template_code=WELLBEING_CODE,
            answers=answers,
            now=NOW,
        )
    assert excinfo.value.code == "unknown_question"


def test_only_assigned_questionnaire_can_be_submitted(db, doctor, template):
    stranger = make_patient(db, email="nincs.kirendelve@test.example")
    with pytest.raises(SubmissionError) as excinfo:
        submit(db, stranger, template, 3, 3, "never")
    assert excinfo.value.code == "not_assigned"


def test_revoked_or_future_assignment_does_not_count(db, doctor, template):
    patient = make_patient(db, email="kesobb@test.example")
    assignment = assign_questionnaire(
        db,
        patient_id=patient.patient_profile.id,
        template=template,
        assigned_by=doctor.id,
        start_date=NOW.date() + timedelta(days=1),
    )
    with pytest.raises(SubmissionError):
        submit(db, patient, template, 3, 3, "never")
    assignment.start_date = date(2026, 1, 1)
    assignment.revoked_at = NOW - timedelta(hours=1)
    with pytest.raises(SubmissionError):
        submit(db, patient, template, 3, 3, "never")


# --- Verziók (F13) -------------------------------------------------------------------


def test_new_version_does_not_change_old_submissions(db, patient, template):
    old, _ = submit(db, patient, template, 4, 4, "rarely")  # 6 pont, figyelmeztető
    # v2: a szédülés „Ritkán" válasza már 4 pontot ér, és szigorúbb sávok.
    spec = WELLBEING_V1.model_copy(deep=True)
    spec.questions[2].options[1].score = 4
    spec.scoring_thresholds[0].max = 3
    spec.scoring_thresholds[1].min = 4
    v2 = add_version(db, template, VersionSpec.model_validate(spec.model_dump()))
    assert v2.version_no == 2

    new, _ = submit(db, patient, template, 4, 4, "rarely", now=NOW + timedelta(days=1))
    assert (old.version.version_no, old.total_score) == (1, 6)
    assert (new.version.version_no, new.total_score) == (2, 8)
    assert band_for(old.version, old.total_score) == "warning"  # a régi jelentése marad


def test_questionnaire_version_and_questions_are_immutable(db, template):
    version = current_version(db, template.id)
    for statement in (
        "UPDATE questionnaire_versions SET scoring_thresholds = '[]' WHERE id = :id",
        "DELETE FROM questionnaire_versions WHERE id = :id",
        "UPDATE questions SET text = 'x' WHERE version_id = :id",
        "DELETE FROM questions WHERE version_id = :id",
    ):
        with pytest.raises(DBAPIError, match="append-only"), db.begin_nested():
            db.execute(text(statement), {"id": version.id})


@pytest.mark.parametrize(
    "bands",
    [
        [{"band": "a", "min": 0, "max": 5}],  # nem ér el 13-ig
        [{"band": "a", "min": 1, "max": 13}],  # nem 0-ról indul
        [{"band": "a", "min": 0, "max": 6}, {"band": "b", "min": 6, "max": 13}],  # átfedés
        [{"band": "a", "min": 0, "max": 4}, {"band": "b", "min": 6, "max": 13}],  # hézag
    ],
)
def test_bands_must_cover_all_scores_without_gaps(bands):
    with pytest.raises(ValidationError):
        VersionSpec.model_validate({**WELLBEING_V1.model_dump(), "scoring_thresholds": bands})


def test_scale_question_requires_good_end():
    with pytest.raises(ValidationError):
        VersionSpec.model_validate(
            {
                "questions": [
                    {"question_type": "scale", "text": "?", "scale_min": 1, "scale_max": 5}
                ],
                "scoring_thresholds": [{"band": "a", "min": 0, "max": 4}],
            }
        )


def test_multi_choice_scores_are_summed(db, doctor):
    spec = VersionSpec.model_validate(
        {
            "questions": [
                {
                    "question_type": "multi",
                    "text": "Mely tünetek?",
                    "options": [
                        {"value": "headache", "label": "Fejfájás", "score": 2},
                        {"value": "nausea", "label": "Hányinger", "score": 3},
                    ],
                }
            ],
            "scoring_thresholds": [
                {"band": "normal", "min": 0, "max": 2},
                {"band": "warning", "min": 3, "max": 5},
            ],
        }
    )
    template = create_template(db, code="symptoms", name="Tünetek", created_by=doctor.id, spec=spec)
    assert current_version(db, template.id).questions[0].question_type is QuestionType.MULTI
    patient = make_patient(db, email="tunet@test.example")
    assign_questionnaire(
        db,
        patient_id=patient.patient_profile.id,
        template=template,
        assigned_by=doctor.id,
        start_date=NOW.date(),
    )
    [question] = current_version(db, template.id).questions
    submission, _ = submit_questionnaire(
        db,
        patient_id=patient.patient_profile.id,
        template_code="symptoms",
        answers={str(question.id): ["headache", "nausea"]},
        now=NOW,
    )
    assert submission.total_score == 5


# --- Kérdőívszabály → riasztás ---------------------------------------------------------


def test_warning_band_raises_alert_with_submission_as_trigger(db, doctor, patient, template):
    wellbeing_rule(db, patient, doctor)
    submission, [alert] = submit(db, patient, template, 4, 4, "rarely")  # 6 pont
    assert alert.severity is Severity.MODERATE
    assert alert.trigger_data_ids == [str(submission.id)]


def test_normal_band_raises_no_alert(db, doctor, patient, template):
    wellbeing_rule(db, patient, doctor)
    assert submit(db, patient, template, 5, 1, "rarely")[1] == []  # 2 pont


def test_critical_band_raises_both_rules(db, doctor, patient, template):
    wellbeing_rule(db, patient, doctor)
    wellbeing_rule(db, patient, doctor, bands=("critical",), severity=Severity.SEVERE)
    _, touched = submit(db, patient, template, 1, 5, "daily")  # 13 pont
    assert sorted(a.severity for a in touched) == [Severity.MODERATE, Severity.SEVERE]


def test_repeated_bad_submission_re_triggers(db, doctor, patient, template):
    wellbeing_rule(db, patient, doctor)
    _, [alert] = submit(db, patient, template, 4, 4, "rarely")
    _, [same] = submit(db, patient, template, 3, 4, "rarely", now=NOW + timedelta(days=7))
    assert same.id == alert.id
    assert [e.event_type for e in alert.events] == [
        AlertEventType.CREATED,
        AlertEventType.RE_TRIGGERED,
    ]


def test_rule_for_other_questionnaire_does_not_fire(db, doctor, patient, template):
    other_spec = WELLBEING_V1.model_copy(deep=True)
    create_template(db, code="other", name="Másik", created_by=doctor.id, spec=other_spec)
    create_rule(
        db,
        patient_id=patient.patient_profile.id,
        created_by=doctor.id,
        rule_type=RuleType.QUESTIONNAIRE,
        params={"questionnaire": "other", "bands": ["warning", "critical"]},
        severity=Severity.MODERATE,
    )
    assert submit(db, patient, template, 1, 5, "daily")[1] == []


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ({"questionnaire": "nincs-ilyen", "bands": ["warning"]}, "Ismeretlen kérdőív"),
        ({"questionnaire": WELLBEING_CODE, "bands": ["warnig"]}, "nincs ilyen sáv"),
    ],
)
def test_questionnaire_rule_params_are_checked_against_the_questionnaire(
    db, doctor, patient, template, params, message
):
    # Egy elgépelt sávnév miatt a szabály különben csendben soha nem riasztana.
    with pytest.raises(ValueError, match=message):
        create_rule(
            db,
            patient_id=patient.patient_profile.id,
            created_by=doctor.id,
            rule_type=RuleType.QUESTIONNAIRE,
            params=params,
            severity=Severity.MODERATE,
        )


def test_assignment_start_uses_the_local_day(db, doctor, template):
    # A kirendelés okt. 13-tól érvényes (helyi nap). Budapesten (UTC+2) a
    # 12-i 23:30 még 12-e, a 13-i 00:30 viszont már 13-a — UTC-ben mindkettő 12-e.
    patient = make_patient(db, email="hataron@test.example")
    assign_questionnaire(
        db,
        patient_id=patient.patient_profile.id,
        template=template,
        assigned_by=doctor.id,
        start_date=date(2026, 10, 13),
    )
    with pytest.raises(SubmissionError):
        submit(db, patient, template, 3, 3, "never", now=datetime(2026, 10, 12, 21, 30, tzinfo=UTC))
    submit(db, patient, template, 3, 3, "never", now=datetime(2026, 10, 12, 22, 30, tzinfo=UTC))
