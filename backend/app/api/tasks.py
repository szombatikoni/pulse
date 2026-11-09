import uuid

from fastapi import APIRouter

from app.api.deps import CurrentUser, ensure_patient_access
from app.core.db import DbSession
from app.schemas.plans import NoticeOut, alert_feedback_out, plan_notice_out
from app.schemas.tasks import TaskOut, task_out
from app.services.notifications import recent_alert_feedback
from app.services.plans import plan_notices
from app.services.tasks import patient_tasks

router = APIRouter(tags=["tasks"])

FORBIDDEN = {403: {"description": "A felhasználó nem érheti el a beteg adatait"}}


@router.get("/patients/{patient_id}/tasks", responses=FORBIDDEN)
def tasks(patient_id: uuid.UUID, db: DbSession, user: CurrentUser) -> list[TaskOut]:
    """A beteg teendői az érvényes előírásai szerint (F6): mi esedékes, mi kész, mi
    maradt el, és meddig pótolható. A beteg a sajátjait, az orvos a hozzá rendelt
    betegéit látja; az admin nem. A tárolt alkalmakból dolgozik, a hiányzót
    megnyitja (ezért véglegesít)."""
    ensure_patient_access(db, user, patient_id)
    result = [task_out(t) for t in patient_tasks(db, patient_id)]
    db.commit()
    return result


@router.get("/patients/{patient_id}/plan-notices", responses=FORBIDDEN)
def notices(patient_id: uuid.UUID, db: DbSession, user: CurrentUser) -> list[NoticeOut]:
    """A beteg jelzései a teendők fölé, az utóbbi 7 napból, a legújabb elöl: az
    előírások visszavonásai és módosításai az orvos indoklásával (kind:
    revoked / modified; a hallgató döntése, 2026-11-01), és az orvos
    visszajelzései a riasztások lezárásakor (kind: alert_feedback; M3, A6).
    Ugyanaz a hozzáférés, mint a teendőknél: a beteg csak a sajátját látja."""
    ensure_patient_access(db, user, patient_id)
    result: list[NoticeOut] = [plan_notice_out(n) for n in plan_notices(db, patient_id)]
    result += [alert_feedback_out(f) for f in recent_alert_feedback(db, patient_id)]
    result.sort(key=lambda n: n.changed_at, reverse=True)
    return result
