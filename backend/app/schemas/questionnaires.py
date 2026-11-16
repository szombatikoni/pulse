import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models import (
    GoodEnd,
    Question,
    QuestionnaireTemplate,
    QuestionnaireVersion,
    QuestionType,
    Submission,
)
from app.services.questionnaires import (
    NAME_MAX,
    EditorVersionSpec,
    band_for,
    question_max_score,
    scale_end_labels,
)


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


class QuestionnaireTemplateOut(BaseModel):
    """Egy kirendelhető kérdőív a követési terv űrlapjához és a kérdőívlistához
    (az aktuális verzió száma, kérdésszáma és legnagyobb pontszáma)."""

    code: str
    name: str
    version_no: int
    question_count: int
    max_score: int


# --- A kérdőívszerkesztő (M3, A5) ----------------------------------------------


class EditorOptionOut(BaseModel):
    value: str
    label: str
    score: int


class EditorQuestionOut(BaseModel):
    """Egy kérdés a szerkesztő alakjában (ugyanaz, amit a mentés vár): skálánál a
    két vég, a jobb vég és a végfeliratok, választósnál a lehetőségek pontokkal."""

    question_type: QuestionType
    text: str
    scale_min: int | None = None
    scale_max: int | None = None
    good_end: GoodEnd | None = None
    min_label: str | None = None
    max_label: str | None = None
    options: list[EditorOptionOut] = []


class BandOut(BaseModel):
    band: str
    min: int
    max: int


class VersionDetailOut(BaseModel):
    version_no: int
    created_at: datetime
    max_score: int
    questions: list[EditorQuestionOut]
    scoring_thresholds: list[BandOut]


class VersionSummaryOut(BaseModel):
    version_no: int
    created_at: datetime
    question_count: int


class QuestionnaireDetailOut(BaseModel):
    """A sablon az aktuális verzió teljes leírásával és a verziólistával
    (a legújabb elöl)."""

    code: str
    name: str
    current: VersionDetailOut
    versions: list[VersionSummaryOut]


# A törzs a szerkesztő verziómodellje (EditorVersionSpec): a korlátok, a sávok
# lefedése és a rögzített sávnevek már a kérés ellenőrzésekor futnak, a hibájuk
# a FastAPI szokásos 422-es válasza. A felület ugyanezt azonnal ellenőrzi, a 422
# csak védőháló.


class QuestionnaireCreate(EditorVersionSpec):
    """Új kérdőív: név és az első verzió. A kód a névből képződik."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=NAME_MAX, examples=["Közérzet"])


class QuestionnaireVersionCreate(EditorVersionSpec):
    """Új verzió. A base_version_no az a verzió, amelyből a szerkesztés indult;
    ha közben újabb született, a mentés 409 (stale_version)."""

    base_version_no: int = Field(ge=1)


class QuestionnaireOut(BaseModel):
    """Egy kirendelt kérdőív a kitöltendő verziójával: az aktuális időszak
    alkalmához rögzített verzióval (ezt tölti ki a beteg)."""

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


def version_max_score(version: QuestionnaireVersion) -> int:
    return sum(question_max_score(q) for q in version.questions)


def template_out(
    template: QuestionnaireTemplate, version: QuestionnaireVersion
) -> QuestionnaireTemplateOut:
    return QuestionnaireTemplateOut(
        code=template.code,
        name=template.name,
        version_no=version.version_no,
        question_count=len(version.questions),
        max_score=version_max_score(version),
    )


def _editor_question(q: Question) -> EditorQuestionOut:
    if q.question_type is QuestionType.SCALE:
        min_label, max_label = scale_end_labels(q)
        return EditorQuestionOut(
            question_type=q.question_type,
            text=q.text,
            scale_min=q.scale_min,
            scale_max=q.scale_max,
            good_end=q.good_end,
            min_label=min_label,
            max_label=max_label,
        )
    return EditorQuestionOut(
        question_type=q.question_type,
        text=q.text,
        options=[EditorOptionOut(**o) for o in q.options_scores],
    )


def questionnaire_detail_out(
    template: QuestionnaireTemplate, versions: list[QuestionnaireVersion]
) -> QuestionnaireDetailOut:
    """versions: a sablon összes verziója, verziószám szerint növekvő sorrendben."""
    current = versions[-1]
    return QuestionnaireDetailOut(
        code=template.code,
        name=template.name,
        current=VersionDetailOut(
            version_no=current.version_no,
            created_at=current.created_at,
            max_score=version_max_score(current),
            questions=[_editor_question(q) for q in current.questions],
            scoring_thresholds=[BandOut(**b) for b in current.scoring_thresholds],
        ),
        versions=[
            VersionSummaryOut(
                version_no=v.version_no, created_at=v.created_at, question_count=len(v.questions)
            )
            for v in reversed(versions)
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
        max_score=version_max_score(version),
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
