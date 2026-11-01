import uuid

from fastapi import APIRouter, HTTPException, status

from app.api.deps import DoctorUser, ensure_patient_access
from app.core.db import DbSession
from app.schemas.plans import AssignmentCreate, AssignmentOut, AssignmentReplace, assignment_out
from app.services import plans
from app.services.plans import PlanError

router = APIRouter(tags=["plans"])

FORBIDDEN = {403: {"description": "Csak a beteg hozzárendelt orvosa"}}
ERRORS = {
    **FORBIDDEN,
    404: {"description": "Nincs ilyen előírás ennél a betegnél"},
    409: {"description": "Az előírás már visszavont, lejárt, vagy ütközik egy érvényessel"},
    422: {"description": "Érvénytelen előírás (a detail.code adja meg az okát)"},
}


def _error(error: PlanError) -> HTTPException:
    """Az ellenőrzések minden módosítás előtt futnak, így hibánál nincs mit
    visszavonni; egyéb hibánál a kérés sessionje commit nélkül zárul."""
    code = status.HTTP_409_CONFLICT if error.conflict else status.HTTP_422_UNPROCESSABLE_CONTENT
    return HTTPException(status_code=code, detail={"code": error.code})


def _entry(db: DbSession, patient_id: uuid.UUID, assignment_id: uuid.UUID) -> AssignmentOut:
    entry = next(e for e in plans.list_plan(db, patient_id) if e.assignment.id == assignment_id)
    return assignment_out(entry)


def _load(db: DbSession, patient_id: uuid.UUID, assignment_id: uuid.UUID):
    try:
        return plans.get_for_patient(db, patient_id, assignment_id)
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from error


@router.get("/patients/{patient_id}/assignments", responses=FORBIDDEN)
def patient_plan(patient_id: uuid.UUID, db: DbSession, user: DoctorUser) -> list[AssignmentOut]:
    """A beteg követési terve (F14): az érvényes és a korábbi előírások, ki írta
    elő, mit, milyen gyakran, mettől meddig. Csak a hozzárendelt orvos látja."""
    ensure_patient_access(db, user, patient_id)
    return [assignment_out(e) for e in plans.list_plan(db, patient_id)]


@router.post(
    "/patients/{patient_id}/assignments", status_code=status.HTTP_201_CREATED, responses=ERRORS
)
def create_assignment(
    patient_id: uuid.UUID, body: AssignmentCreate, db: DbSession, user: DoctorUser
) -> AssignmentOut:
    """Új előírás (mérés vagy kérdőív). Az alkalmait a háttérfolyamat, illetve a
    beteg első mentése nyitja meg."""
    ensure_patient_access(db, user, patient_id)
    try:
        assignment = plans.create(
            db,
            patient_id=patient_id,
            assigned_by=user.id,
            kind=body.kind,
            code=body.code,
            params=body.params(),
        )
    except PlanError as error:
        raise _error(error) from error
    db.commit()
    return _entry(db, patient_id, assignment.id)


@router.post(
    "/patients/{patient_id}/assignments/{assignment_id}/replace",
    status_code=status.HTTP_201_CREATED,
    responses=ERRORS,
)
def replace_assignment(
    patient_id: uuid.UUID,
    assignment_id: uuid.UUID,
    body: AssignmentReplace,
    db: DbSession,
    user: DoctorUser,
) -> AssignmentOut:
    """Módosítás (a2_terv 6/1. pont): a régi előírás lezárása és az új
    paraméterekkel új előírás ugyanarra a célra, egy tranzakcióban. Az új
    előírást adja vissza."""
    ensure_patient_access(db, user, patient_id)
    old = _load(db, patient_id, assignment_id)
    try:
        new = plans.replace(db, old, assigned_by=user.id, params=body.params())
    except PlanError as error:
        raise _error(error) from error
    db.commit()
    return _entry(db, patient_id, new.id)


@router.post("/patients/{patient_id}/assignments/{assignment_id}/revoke", responses=ERRORS)
def revoke_assignment(
    patient_id: uuid.UUID, assignment_id: uuid.UUID, db: DbSession, user: DoctorUser
) -> AssignmentOut:
    """Visszavonás: az előírás a mai naptól nem érvényes; a még nyitott alkalma
    törlődik, a teljesített és elmulasztott alkalmak megmaradnak."""
    ensure_patient_access(db, user, patient_id)
    assignment = _load(db, patient_id, assignment_id)
    try:
        plans.revoke(db, assignment)
    except PlanError as error:
        raise _error(error) from error
    db.commit()
    return _entry(db, patient_id, assignment.id)
