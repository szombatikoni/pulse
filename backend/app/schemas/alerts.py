"""A riasztás-életút végpontjainak sémái (M3, A6)."""

import uuid
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from app.models.notification import NOTIFICATION_TEXT_MAX
from app.schemas.patients import AlertOut, TriggerOut

# Az indoklás és a betegüzenet legfeljebb ennyi karakter (a betegüzenet a
# Notification.text oszlopba kerül).
REASON_MAX = NOTIFICATION_TEXT_MAX

Reason = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=REASON_MAX)
]
Message = Annotated[str, StringConstraints(strip_whitespace=True, max_length=NOTIFICATION_TEXT_MAX)]


class AlertAssign(BaseModel):
    doctor_id: uuid.UUID | None = Field(
        default=None,
        description="A felelős orvos FELHASZNÁLÓ-azonosítója (users.id, mint a /auth/me id-je); "
        "csak a beteghez éppen hozzárendelt orvos lehet. Üresen: a kérő orvos maga.",
    )


class AlertClose(BaseModel):
    reason: Reason = Field(
        description="Kötelező indoklás (1–500 karakter); az eseménytörténetbe kerül.",
        examples=["Telefonon egyeztettem, gyógyszer módosítva."],
    )
    message: Message | None = Field(
        default=None,
        description="Nem kötelező visszajelzés a betegnek (legfeljebb 500 karakter); a beteg a "
        "jelzései közt látja. Üres szöveg = nincs üzenet.",
        examples=["Kérem, a jövő héten mérjen naponta kétszer."],
    )


class PatientRefOut(BaseModel):
    id: uuid.UUID
    name: str


class AlertListItemOut(AlertOut):
    """Egy nyitott riasztás a Riasztások oldalhoz: a beteg-adatlapi kártya
    adatai (a cím a szabályverzióból és a legutóbbi kiváltó adatból írható
    ki, mint ott), kiegészítve a beteggel és a legutóbbi kiváltó adattal."""

    patient: PatientRefOut
    trigger: TriggerOut | None
