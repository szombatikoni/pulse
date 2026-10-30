from fastapi import APIRouter

from app.api.deps import AdminUser
from app.core.db import DbSession
from app.schemas.occurrences import OccurrenceCheckOut
from app.services.occurrences import run_occurrence_check

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post(
    "/occurrence-check",
    responses={403: {"description": "Csak az admin indíthatja"}},
)
def occurrence_check(db: DbSession, _user: AdminUser) -> OccurrenceCheckOut:
    """„Ellenőrzés most": a háttérfolyamat egy futása azonnal (alkalom-nyitás és
    az elmulasztottak lezárása). A demóban így nem kell a következő óránkénti
    futásra várni; ismételt hívás nem okoz változást (idempotens)."""
    result = run_occurrence_check(db)
    db.commit()
    return OccurrenceCheckOut(opened=result.opened, missed=result.missed)
