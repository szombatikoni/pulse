import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models import QuestionnaireTemplate, QuestionnaireVersion, QuestionType, Submission
from app.services.questionnaires import band_for, question_max_score


class OptionOut(BaseModel):
    value: str
    label: str


class QuestionOut(BaseModel):
    id: uuid.UUID
    order_no: int
    question_type: QuestionType
    text: str
    # A pontokat a beteg nem látja, csak a válaszlehetőségeket.
    options: list[OptionOut]


class QuestionnaireOut(BaseModel):
    """Egy kirendelt kérdőív az aktuális verziójával (ezt tölti ki a beteg)."""

    code: str
    name: str
    version_no: int
    questions: list[QuestionOut]
    last_submitted_at: datetime | None


class SubmissionCreate(BaseModel):
    questionnaire_code: str = Field(max_length=50, examples=["wellbeing"])
    # Kérdésazonosító → válasz (skálánál és egyválasztósnál egy érték,
    # többválasztósnál lista).
    answers: dict[str, Any] = Field(min_length=1, max_length=100)


class SubmissionReceipt(BaseModel):
    """A betegnek visszaadott nyugta: a kitöltés beérkezett. A pontszám és a
    kiértékelési sáv az orvosnak szól, a beteg nem kapja meg."""

    id: uuid.UUID
    questionnaire_code: str
    submitted_at: datetime


class AnswerOut(BaseModel):
    question_id: uuid.UUID
    order_no: int
    text: str
    value: Any
    label: str
    score: int


class SubmissionOut(BaseModel):
    id: uuid.UUID
    questionnaire_code: str
    questionnaire_name: str
    version_no: int
    submitted_at: datetime
    total_score: int
    max_score: int
    # A kiértékelési sáv a kitöltött verzió sávjai szerint (pl. "warning").
    band: str
    answers: list[AnswerOut]


def questionnaire_out(
    template: QuestionnaireTemplate,
    version: QuestionnaireVersion,
    last_submitted_at: datetime | None,
) -> QuestionnaireOut:
    return QuestionnaireOut(
        code=template.code,
        name=template.name,
        version_no=version.version_no,
        last_submitted_at=last_submitted_at,
        questions=[
            QuestionOut(
                id=q.id,
                order_no=q.order_no,
                question_type=q.question_type,
                text=q.text,
                options=[OptionOut(value=o["value"], label=o["label"]) for o in q.options_scores],
            )
            for q in version.questions
        ],
    )


def _label(options: list[dict[str, Any]], value: Any) -> str:
    labels = {o["value"]: o["label"] for o in options}
    if isinstance(value, list):
        return ", ".join(labels.get(v, v) for v in value)
    return labels.get(str(value), str(value))


def submission_out(submission: Submission) -> SubmissionOut:
    version = submission.version
    answers = sorted(submission.answers, key=lambda a: a.question.order_no)
    return SubmissionOut(
        id=submission.id,
        questionnaire_code=version.template.code,
        questionnaire_name=version.template.name,
        version_no=version.version_no,
        submitted_at=submission.submitted_at,
        total_score=submission.total_score,
        max_score=sum(question_max_score(q) for q in version.questions),
        band=band_for(version, submission.total_score),
        answers=[
            AnswerOut(
                question_id=a.question_id,
                order_no=a.question.order_no,
                text=a.question.text,
                value=a.value,
                label=_label(a.question.options_scores, a.value),
                score=a.score,
            )
            for a in answers
        ],
    )
