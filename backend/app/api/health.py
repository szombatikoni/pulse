from fastapi import APIRouter
from sqlalchemy import text

from app.core.db import DbSession

router = APIRouter(tags=["health"])


@router.get("/health")
def health(db: DbSession) -> dict[str, str]:
    """Állapot-ellenőrzés: az API fut, és eléri az adatbázist."""
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "ok"}
