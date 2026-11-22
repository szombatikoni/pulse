import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DoctorUser, PatientUser, ensure_patient_access
from app.core.config import settings
from app.core.db import DbSession
from app.models import QuestionnaireTemplate, QuestionnaireVersion, Submission
from app.schemas.questionnaires import (
    QuestionnaireCreate,
    QuestionnaireDetailOut,
    QuestionnaireOut,
    QuestionnaireTemplateOut,
    QuestionnaireVersionCreate,
    SubmissionCreate,
    SubmissionOut,
    SubmissionReceipt,
    questionnaire_detail_out,
    questionnaire_out,
    submission_out,
    template_out,
)
from app.services.occurrences import fill_version
from app.services.questionnaires import (
    QuestionnaireError,
    SubmissionError,
    add_version,
    assigned_templates,
    code_from_name,
    create_template,
    current_version,
    list_submissions,
    submit_questionnaire,
)

router = APIRouter(tags=["questionnaires"])

FORBIDDEN = {403: {"description": "A felhasználó nem érheti el a beteg adatait"}}


DOCTOR_ONLY = {403: {"description": "Csak orvos"}}
EDITOR_ERRORS = {
    **DOCTOR_ONLY,
    422: {"description": "Érvénytelen kérdőív (korlátok, sávok); névnél detail.code: invalid_name"},
}


@router.get("/questionnaires", responses=DOCTOR_ONLY)
def questionnaire_templates(db: DbSession, _user: DoctorUser) -> list[QuestionnaireTemplateOut]:
    """A kirendelhető (aktív) kérdőívek, név szerint: a követési terv űrlapjához és
    a kérdőívlistához, az aktuális verzió számával, kérdésszámával és legnagyobb
    pontszámával."""
    templates = db.scalars(
        select(QuestionnaireTemplate)
        .where(QuestionnaireTemplate.is_active.is_(True))
        .order_by(QuestionnaireTemplate.name)
    )
    return [template_out(t, current_version(db, t.id)) for t in templates]


def _versions(db: DbSession, template: QuestionnaireTemplate) -> list[QuestionnaireVersion]:
    return list(
        db.scalars(
            select(QuestionnaireVersion)
            .where(QuestionnaireVersion.template_id == template.id)
            .options(selectinload(QuestionnaireVersion.questions))
            .order_by(QuestionnaireVersion.version_no)
        )
    )


def _detail(db: DbSession, template: QuestionnaireTemplate) -> QuestionnaireDetailOut:
    return questionnaire_detail_out(template, _versions(db, template))


def _error(error: QuestionnaireError) -> HTTPException:
    code = status.HTTP_409_CONFLICT if error.conflict else status.HTTP_422_UNPROCESSABLE_CONTENT
    return HTTPException(status_code=code, detail={"code": error.code, **error.extra})


@router.get(
    "/questionnaires/{code}",
    responses={**DOCTOR_ONLY, 404: {"description": "Nincs ilyen kérdőív"}},
)
def questionnaire_detail(code: str, db: DbSession, _user: DoctorUser) -> QuestionnaireDetailOut:
    """A kérdőív a szerkesztőhöz (M3, A5): az aktuális verzió teljes leírása
    (kérdések, pontok, sávhatárok, skála-végfeliratok) és a verziólista. A
    sablonok közösek, bármely orvos szerkesztheti őket (a hallgató döntése, D1);
    betegadatot a válasz nem tartalmaz."""
    template = db.scalar(select(QuestionnaireTemplate).where(QuestionnaireTemplate.code == code))
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return _detail(db, template)


@router.post(
    "/questionnaires",
    status_code=status.HTTP_201_CREATED,
    responses={**EDITOR_ERRORS, 409: {"description": "A névből képzett kód foglalt (code_taken)"}},
)
def create_questionnaire(
    body: QuestionnaireCreate, db: DbSession, user: DoctorUser
) -> QuestionnaireDetailOut:
    """Új kérdőív az első verziójával. A kód a névből képződik (ékezet nélkül,
    kisbetű, szám, aláhúzás); ha ilyen kód már van, 409 code_taken."""
    code = code_from_name(body.name)
    if not code:
        raise _error(QuestionnaireError("invalid_name"))
    exists = db.scalar(select(QuestionnaireTemplate.id).where(QuestionnaireTemplate.code == code))
    if exists is not None:
        raise _error(QuestionnaireError("code_taken", conflict=True))
    try:
        with db.begin_nested():
            template = create_template(db, code=code, name=body.name, created_by=user.id, spec=body)
    except IntegrityError as error:
        # Egyidejű létrehozás ugyanazzal a kóddal: az egyediségi megkötés fogja meg.
        raise _error(QuestionnaireError("code_taken", conflict=True)) from error
    db.commit()
    return _detail(db, template)


@router.post(
    "/questionnaires/{code}/versions",
    status_code=status.HTTP_201_CREATED,
    responses={
        **EDITOR_ERRORS,
        404: {"description": "Nincs ilyen kérdőív"},
        409: {"description": "Közben újabb verzió született (stale_version)"},
    },
)
def add_questionnaire_version(
    code: str, body: QuestionnaireVersionCreate, db: DbSession, _user: DoctorUser
) -> QuestionnaireDetailOut:
    """Módosítás = új, immutabilis verzió (F13). A régi verziók, a rájuk
    hivatkozó kitöltések és a már megnyílt alkalmak nem változnak: a beteg az új
    verziót a következő időszaktól kapja. A sablon a mentés idejére zárolva van;
    ha a base_version_no már nem a legutolsó, 409 stale_version (a válaszban a
    current_version_no)."""
    template = db.scalar(select(QuestionnaireTemplate).where(QuestionnaireTemplate.code == code))
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    try:
        with db.begin_nested():
            add_version(db, template, body, base_version_no=body.base_version_no)
    except QuestionnaireError as error:
        raise _error(error) from error
    db.commit()
    return _detail(db, template)


@router.get("/patients/{patient_id}/questionnaires", responses=FORBIDDEN)
def patient_questionnaires(
    patient_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> list[QuestionnaireOut]:
    """A betegnek kirendelt kérdőívek (F6) az aktuális időszak alkalmához
    rögzített verzióval: ezt tölti ki a beteg, és a beküldés is ezzel pontoz.
    A beteg a sajátjait, az orvos a hozzá rendelt betegéit látja."""
    ensure_patient_access(db, user, patient_id)
    today = datetime.now(settings.tz).date()
    result = []
    for template in assigned_templates(db, patient_id, today):
        # Ha az alkalom még nincs meg, itt jön létre (ugyanaz, amit a háttérfolyamat
        # is megnyitna), így a kitöltés közbeni sablonmódosítás nem cseréli ki a kérdéseket.
        version = fill_version(db, patient_id, template.id, today)
        last = db.scalar(
            select(func.max(Submission.submitted_at))
            .join(QuestionnaireVersion)
            .where(
                Submission.patient_id == patient_id,
                QuestionnaireVersion.template_id == template.id,
            )
        )
        result.append(questionnaire_out(template, version, last))
    db.commit()
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
