"""Orvosi megjegyzés a beteghez (M3, A8; F16, 03_adatmodell.md „Note").

A megjegyzés az orvosok belső feljegyzése: a beteg nem látja, a beteghez éppen
hozzárendelt minden orvos igen, a szerző nevével (a hallgató döntése, A8 D2).
Csak hozzáírható: nem szerkeszthető és nem törölhető, a tévedést új megjegyzés
javítja (mint az AlertEvent). Az M1-es `doctor_id` helyett `author_id` (a
users táblára, mint a Notification.created_by).
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# A megjegyzés szövege legfeljebb ennyi karakter.
NOTE_TEXT_MAX = 1000


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # A beteg, akiről szól; a lekérés erre szűr.
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patient_profiles.id"), index=True)
    # Ki írta (az orvos felhasználója).
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    text: Mapped[str] = mapped_column(String(NOTE_TEXT_MAX))
    # A létrehozás idejét a szolgáltatás adja: a now() a tranzakció kezdete, így
    # egy tranzakción belül két megjegyzés sorrendje nem dőlne el.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        # Üres (csak szóközből, tabulátorból, sortörésből álló) megjegyzés az
        # adatbázisban sem lehet: legalább egy nem üreshely-karakter kell.
        CheckConstraint("text ~ '[^[:space:]]'", name="text_not_blank"),
    )
