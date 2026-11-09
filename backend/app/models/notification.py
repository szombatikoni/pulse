"""Értesítések a betegnek (M3, A6; 03_adatmodell.md „Notification").

Egy értesítés egy betegnek szóló, egyirányú üzenet (válaszolni nem lehet,
Bilicki jóváhagyása szerint). Most egy típusa van: az orvos visszajelzése a
riasztás lezárásakor. A beteg a teendői közt látja, a többi jelzéssel azonos
7 napos ablakban. Az e-mail-kézbesítés (A9, NotificationDelivery) erre épül
majd; most még nem készül.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, str_enum

# Az értesítés szövege legfeljebb ennyi karakter.
NOTIFICATION_TEXT_MAX = 500


class NotificationType(StrEnum):
    ALERT_FEEDBACK = "alert_feedback"  # az orvos visszajelzése a riasztás lezárásakor


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # A címzett beteg; a betegoldali lekérés erre szűr.
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patient_profiles.id"), index=True)
    type: Mapped[NotificationType] = mapped_column(
        str_enum(NotificationType, "notification_type", length=20)
    )
    text: Mapped[str] = mapped_column(String(NOTIFICATION_TEXT_MAX))
    # Melyik riasztás lezárásához tartozik (visszajelzésnél); más típusnál üres.
    alert_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("alerts.id"))
    # Ki írta (visszajelzésnél a lezáró orvos).
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    # A létrehozás idejét a szolgáltatás adja (a tesztekben szimulált idő).
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
