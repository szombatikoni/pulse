"""Kérdőívek: verziók, pontozás, kirendelés és kitöltés (F6, F13, F14).

Pontozás (07_mukodesi_szabalyok.md, 4. rész): egységes szabály, több pont =
rosszabb állapot. Skálás kérdésnél a jobb vég mindig 0 pont:
- ha a kisebb érték a jobb: pont = válasz − skála minimuma;
- ha a nagyobb érték a jobb: pont = skála maximuma − válasz.
A kész válasz → pont tábla a verzióban tárolódik; kitöltéskor a pont onnan
olvasódik ki.
"""

import uuid
from datetime import UTC, date, datetime, time
from typing import Any

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models import (
    Alert,
    Answer,
    Assignment,
    AssignmentTarget,
    Frequency,
    GoodEnd,
    Question,
    QuestionnaireTemplate,
    QuestionnaireVersion,
    QuestionType,
    Submission,
)


class OptionSpec(BaseModel):
    value: str = Field(min_length=1, max_length=50)
    label: str = Field(min_length=1, max_length=200)
    score: int = Field(ge=0)


class QuestionSpec(BaseModel):
    question_type: QuestionType
    text: str = Field(min_length=1)
    scale_min: int | None = None
    scale_max: int | None = None
    good_end: GoodEnd | None = None
    # Skálánál a két vég felirata (pl. „nagyon rosszul", „nagyon jól").
    min_label: str | None = None
    max_label: str | None = None
    options: list[OptionSpec] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_type_fields(self) -> "QuestionSpec":
        if self.question_type is QuestionType.SCALE:
            if self.scale_min is None or self.scale_max is None or self.good_end is None:
                raise ValueError("skálánál kötelező a skála két vége és a jobb vég")
            if self.scale_min >= self.scale_max:
                raise ValueError("a skála minimuma kisebb a maximumánál")
        elif len(self.options) < 2:
            raise ValueError("választós kérdésnél legalább két válaszlehetőség kell")
        values = [o.value for o in self.options]
        if len(values) != len(set(values)):
            raise ValueError("a válaszlehetőségek értéke egyedi")
        return self


class BandSpec(BaseModel):
    band: str = Field(min_length=1, max_length=30)
    min: int = Field(ge=0)
    max: int = Field(ge=0)


class VersionSpec(BaseModel):
    questions: list[QuestionSpec] = Field(min_length=1)
    scoring_thresholds: list[BandSpec] = Field(min_length=1)

    @model_validator(mode="after")
    def bands_cover_all_scores(self) -> "VersionSpec":
        """A sávok hézag és átfedés nélkül fedik le a 0 … max. pontszám tartományt,
        így minden kitöltés pontosan egy sávba esik."""
        bands = sorted(self.scoring_thresholds, key=lambda b: b.min)
        expected = 0
        for band in bands:
            if band.min != expected or band.max < band.min:
                raise ValueError("a sávok 0-tól folytonosan, átfedés nélkül követik egymást")
            expected = band.max + 1
        top = sum(
            _max_score(_options_for(q), q.question_type is QuestionType.MULTI)
            for q in self.questions
        )
        if expected - 1 != top:
            raise ValueError(f"a sávoknak a legnagyobb elérhető pontszámig ({top}) kell tartaniuk")
        return self


def scale_options(spec: QuestionSpec) -> list[dict[str, Any]]:
    """A skála válasz → pont táblája a jobb vég szerint (a jobb vég 0 pont)."""
    assert spec.scale_min is not None and spec.scale_max is not None
    options = []
    for value in range(spec.scale_min, spec.scale_max + 1):
        if spec.good_end is GoodEnd.MIN:
            score = value - spec.scale_min
        else:
            score = spec.scale_max - value
        label = str(value)
        if value == spec.scale_min and spec.min_label:
            label = f"{value} – {spec.min_label}"
        if value == spec.scale_max and spec.max_label:
            label = f"{value} – {spec.max_label}"
        options.append({"value": str(value), "label": label, "score": score})
    return options


def _options_for(spec: QuestionSpec) -> list[dict[str, Any]]:
    if spec.question_type is QuestionType.SCALE:
        return scale_options(spec)
    return [o.model_dump() for o in spec.options]


def _max_score(options: list[dict[str, Any]], multi: bool = False) -> int:
    scores = [o["score"] for o in options]
    return sum(scores) if multi else max(scores)


def question_max_score(question: Question) -> int:
    return _max_score(question.options_scores, question.question_type is QuestionType.MULTI)


def create_template(
    db: Session, *, code: str, name: str, created_by: uuid.UUID, spec: VersionSpec
) -> QuestionnaireTemplate:
    template = QuestionnaireTemplate(code=code, name=name, created_by=created_by)
    db.add(template)
    db.flush()
    add_version(db, template, spec)
    return template


def add_version(
    db: Session, template: QuestionnaireTemplate, spec: VersionSpec
) -> QuestionnaireVersion:
    """Sablonmódosítás = új verzió (F13); a régi változatlan marad."""
    last = current_version(db, template.id, required=False)
    version = QuestionnaireVersion(
        template_id=template.id,
        version_no=(last.version_no if last else 0) + 1,
        scoring_thresholds=[b.model_dump() for b in spec.scoring_thresholds],
        questions=[
            Question(
                order_no=order_no,
                question_type=q.question_type,
                text=q.text,
                scale_min=q.scale_min,
                scale_max=q.scale_max,
                good_end=q.good_end,
                options_scores=_options_for(q),
            )
            for order_no, q in enumerate(spec.questions, start=1)
        ],
    )
    db.add(version)
    db.flush()
    return version


def current_version(
    db: Session, template_id: uuid.UUID, required: bool = True
) -> QuestionnaireVersion | None:
    query = (
        select(QuestionnaireVersion)
        .where(QuestionnaireVersion.template_id == template_id)
        .options(selectinload(QuestionnaireVersion.questions))
        .order_by(QuestionnaireVersion.version_no.desc())
        .limit(1)
    )
    version = db.scalar(query)
    if required and version is None:
        raise LookupError(f"A kérdőívnek nincs verziója: {template_id}")
    return version


def band_for(version: QuestionnaireVersion, total: int) -> str:
    for band in version.scoring_thresholds:
        if band["min"] <= total <= band["max"]:
            return band["band"]
    raise ValueError(f"A pontszám ({total}) egyik sávba sem esik")


def assign_questionnaire(
    db: Session,
    *,
    patient_id: uuid.UUID,
    template: QuestionnaireTemplate,
    assigned_by: uuid.UUID,
    start_date: date,
    frequency: Frequency = Frequency.WEEKLY,
    due_time: time = time(20, 0),
) -> Assignment:
    """Kérdőív kirendelése a betegnek (F14). Az alkalmak az M3-ban jönnek."""
    assignment = Assignment(
        patient_id=patient_id,
        assigned_by=assigned_by,
        target_kind=AssignmentTarget.QUESTIONNAIRE,
        questionnaire_template_id=template.id,
        frequency=frequency,
        due_time=due_time,
        start_date=start_date,
    )
    db.add(assignment)
    db.flush()
    return assignment


def assigned_templates(
    db: Session, patient_id: uuid.UUID, today: date | None = None
) -> list[QuestionnaireTemplate]:
    """A betegnek éppen kirendelt, aktív kérdőívek. A „ma" a rendszer
    időzónája szerinti nap."""
    today = today or datetime.now(settings.tz).date()
    query = (
        select(QuestionnaireTemplate)
        .join(Assignment, Assignment.questionnaire_template_id == QuestionnaireTemplate.id)
        .where(
            Assignment.patient_id == patient_id,
            Assignment.revoked_at.is_(None),
            Assignment.start_date <= today,
            or_(Assignment.end_date.is_(None), Assignment.end_date >= today),
            QuestionnaireTemplate.is_active.is_(True),
        )
        .distinct()
        .order_by(QuestionnaireTemplate.name)
    )
    return list(db.scalars(query))


class SubmissionError(ValueError):
    """Érvénytelen kitöltés; a `code` alapján a felület a saját nyelvén írja ki."""

    def __init__(self, code: str, question_id: str | None = None) -> None:
        super().__init__(code if question_id is None else f"{code}: {question_id}")
        self.code = code
        self.question_id = question_id


def _score_answer(question: Question, value: Any) -> int:
    scores = {o["value"]: o["score"] for o in question.options_scores}
    qid = str(question.id)
    if question.question_type is QuestionType.MULTI:
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise SubmissionError("invalid_answer", qid)
        if len(set(value)) != len(value) or any(v not in scores for v in value):
            raise SubmissionError("invalid_answer", qid)
        return sum(scores[v] for v in value)
    # Skálánál a választ szövegként is, számként is elfogadjuk ("4" vagy 4).
    if isinstance(value, bool) or not isinstance(value, str | int):
        raise SubmissionError("invalid_answer", qid)
    if str(value) not in scores:
        raise SubmissionError("invalid_answer", qid)
    return scores[str(value)]


def submit_questionnaire(
    db: Session,
    *,
    patient_id: uuid.UUID,
    template_code: str,
    answers: dict[str, Any],
    now: datetime | None = None,
) -> tuple[Submission, list[Alert]]:
    """Kitöltés ellenőrzése, pontozása és mentése, majd kiértékelés a beteg
    szabályaival (egy tranzakcióban; a commitot a hívó végzi)."""
    from app.services.rules import evaluate_submission  # körkörös import elkerülése

    now = now or datetime.now(UTC)
    local_today = now.astimezone(settings.tz).date()
    templates = {t.code: t for t in assigned_templates(db, patient_id, local_today)}
    template = templates.get(template_code)
    if template is None:
        raise SubmissionError("not_assigned")
    version = current_version(db, template.id)

    by_id = {str(q.id): q for q in version.questions}
    for qid in answers:
        if qid not in by_id:
            raise SubmissionError("unknown_question", qid)
    scored: list[Answer] = []
    for qid, question in by_id.items():
        if qid not in answers:
            raise SubmissionError("missing_answer", qid)
        value = answers[qid]
        if question.question_type is QuestionType.SCALE:
            value = str(value) if isinstance(value, int) and not isinstance(value, bool) else value
        scored.append(Answer(question=question, value=value, score=_score_answer(question, value)))

    submission = Submission(
        patient_id=patient_id,
        version=version,
        total_score=sum(a.score for a in scored),
        submitted_at=now,
        answers=scored,
    )
    db.add(submission)
    db.flush()
    return submission, evaluate_submission(db, submission, now=now)


def list_submissions(db: Session, patient_id: uuid.UUID, limit: int = 50) -> list[Submission]:
    query = (
        select(Submission)
        .where(Submission.patient_id == patient_id)
        .options(
            selectinload(Submission.version).selectinload(QuestionnaireVersion.template),
            selectinload(Submission.answers).selectinload(Answer.question),
        )
        .order_by(Submission.submitted_at.desc(), Submission.id)
        .limit(limit)
    )
    return list(db.scalars(query))


def get_submissions(db: Session, ids: list[uuid.UUID]) -> list[Submission]:
    query = (
        select(Submission)
        .where(Submission.id.in_(ids))
        .options(
            selectinload(Submission.version).selectinload(QuestionnaireVersion.template),
            selectinload(Submission.answers).selectinload(Answer.question),
        )
        .order_by(Submission.submitted_at)
    )
    return list(db.scalars(query))
