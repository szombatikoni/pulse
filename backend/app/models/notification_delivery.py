"""E-mail-kézbesítések (M3, A9; 03_adatmodell.md „NotificationDelivery").

„Kimenő postafiók" minta: a riasztás keletkezésekor ugyanabban a tranzakcióban
címzettenként egy `pending` sor jön létre (services/deliveries.py,
queue_alert_email). Ha a tranzakció visszagördül, sor sincs; ha commitol, a
háttérfolyamat kézbesítő köre biztosan felveszi. A sikertelen e-mail így soha
nem érinti a riasztást. A sor a küldés után is megmarad (kézbesítési napló).

A levél szövege nincs tárolva: a küldéskor a riasztásból áll elő, és nem
tartalmaz betegadatot. A címzett címe is a küldéskor olvasódik a users
táblából.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, SmallInteger, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, str_enum

# A legutóbbi hiba rövid leírása legfeljebb ennyi karakter (betegadat nélkül).
LAST_ERROR_MAX = 300


class DeliveryKind(StrEnum):
    ALERT_CREATED = "alert_created"  # új riasztás a beteghez rendelt orvosnak


class DeliveryStatus(StrEnum):
    PENDING = "pending"  # küldésre vár (az első kísérlet előtt vagy hiba után)
    SENT = "sent"
    FAILED = "failed"  # végleg sikertelen; újraküldés nincs


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    kind: Mapped[DeliveryKind] = mapped_column(str_enum(DeliveryKind, "delivery_kind", length=20))
    # Melyik riasztásról szól; más (későbbi) fajtánál üres lehet.
    alert_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("alerts.id"))
    recipient_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    status: Mapped[DeliveryStatus] = mapped_column(
        str_enum(DeliveryStatus, "delivery_status", length=10), default=DeliveryStatus.PENDING
    )
    attempts: Mapped[int] = mapped_column(SmallInteger, default=0)
    # Mikortól vehető fel a következő kísérletre (sorba állításkor azonnal).
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(LAST_ERROR_MAX))
    # A létrehozás idejét a szolgáltatás adja (a tesztekben szimulált idő).
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        # A kézbesítő kör a lejárt, várakozó sorokat keresi.
        Index("ix_notification_deliveries_status_next_attempt_at", "status", "next_attempt_at"),
        # Az új riasztásról szóló sor mindig riasztáshoz tartozik (a levél abból
        # áll elő); az alert_id csak egy későbbi, más fajtájú sornál lehet üres.
        CheckConstraint(
            "kind <> 'alert_created' OR alert_id IS NOT NULL", name="alert_created_has_alert"
        ),
    )
