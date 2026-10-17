import uuid

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DoctorUser, PatientUser, ensure_patient_access
from app.core.db import DbSession
from app.models import QuestionnaireVersion, Submission
from app.schemas.questionnaires import (
    QuestionnaireOut,
    SubmissionCreate,
    SubmissionOut,
    SubmissionReceipt,
    questionnaire_out,
    submission_out,
)
from app.services.questionnaires import (
    SubmissionError,
    assigned_templates,
    current_version,
    list_submissions,
    submit_questionnaire,
)

router = APIRouter(tags=["questionnaires"])

FORBIDDEN = {403: {"description": "A felhasználó nem érheti el a beteg adatait"}}


@router.get("/patients/{patient_id}/questionnaires", responses=FORBIDDEN)
def patient_questionnaires(
    patient_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> list[QuestionnaireOut]:
    """A betegnek kirendelt kérdőívek az aktuális verziójukkal (F6). A beteg a
    sajátjait, az orvos a hozzá rendelt betegéit látja."""
    ensure_patient_access(db, user, patient_id)
    result = []
    for template in assigned_templates(db, patient_id):
        version = current_version(db, template.id)
        last = db.scalar(
            select(func.max(Submission.submitted_at))
            .join(QuestionnaireVersion)
            .where(
                Submission.patient_id == patient_id,
                QuestionnaireVersion.template_id == template.id,
            )
        )
        result.append(questionnaire_out(template, version, last))
    return result


@router.get("/patients/{patient_id}/submissions", responses=FORBIDDEN)
def patient_submissions(
    patient_id: uuid.UUID,
    db: DbSession,
    user: DoctorUser,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[SubmissionOut]:
    """A beteg kitöltései pontszámmal és sávval, a legújabb elöl. Csak az orvos
    látja (a kiértékelés neki szól)."""
    ensure_patient_access(db, user, patient_id)
    return [submission_out(s) for s in list_submissions(db, patient_id, limit)]


@router.post(
    "/patients/{patient_id}/submissions",
    status_code=status.HTTP_201_CREATED,
    responses={
        403: {"description": "Csak a beteg tölthet ki, és csak a saját nevében"},
        422: {"description": "Érvénytelen kitöltés (a detail.code adja meg az okát)"},
    },
)
def create_submission(
    patient_id: uuid.UUID, body: SubmissionCreate, db: DbSession, user: PatientUser
) -> SubmissionReceipt:
    """Kérdőív kitöltése (F6). A pontozás a kitöltött verzió tárolt táblája
    szerint történik, és egy tranzakcióban lefut a kiértékelés (F19)."""
    ensure_patient_access(db, user, patient_id)
    try:
        submission, _alerts = submit_questionnaire(
            db,
            patient_id=patient_id,
            template_code=body.questionnaire_code,
            answers=body.answers,
        )
    except SubmissionError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": error.code, "question_id": error.question_id},
        ) from error
    db.commit()
    return SubmissionReceipt(
        id=submission.id,
        questionnaire_code=body.questionnaire_code,
        submitted_at=submission.submitted_at,
    )
