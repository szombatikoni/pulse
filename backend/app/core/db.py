"""Adatbázis-kapcsolat és kérésenkénti session (szinkron SQLAlchemy 2)."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI-függőség: minden kérés saját sessiont kap, a végén lezárjuk."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Végpontokban: `def vegpont(db: DbSession)` — a session a get_db-ből jön.
DbSession = Annotated[Session, Depends(get_db)]
