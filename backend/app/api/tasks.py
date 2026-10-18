import uuid

from fastapi import APIRouter

from app.api.deps import CurrentUser, ensure_patient_access
from app.core.db import DbSession
from app.schemas.tasks import TaskOut, task_out
from app.services.tasks import patient_tasks

router = APIRouter(tags=["tasks"])

FORBIDDEN = {403: {"description": "A felhasználó nem érheti el a beteg adatait"}}


@router.get("/patients/{patient_id}/tasks", responses=FORBIDDEN)
def tasks(patient_id: uuid.UUID, db: DbSession, user: CurrentUser) -> list[TaskOut]:
    """A beteg teendői az érvényes előírásai szerint (F6): mi esedékes, mi kész, mi
    maradt el, és meddig pótolható. A beteg a sajátjait, az orvos a hozzá rendelt
    betegéit látja; az admin nem."""
    ensure_patient_access(db, user, patient_id)
    return [task_out(t) for t in patient_tasks(db, patient_id)]
