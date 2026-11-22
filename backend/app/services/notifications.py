"""A betegnek szóló értesítések lekérdezése (M3, A6).

Az értesítés most egy típusú: az orvos visszajelzése a riasztás lezárásakor
(a létrehozása: alerts.close_alert). A beteg a teendői közt látja, az
előírás-jelzésekkel (plans.plan_notices) azonos, NOTICE_DAYS napos ablakban.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Alert,
    MeasurementType,
    Notification,
    NotificationType,
    QuestionnaireTemplate,
    RuleType,
    User,
)
from app.services.plans import NOTICE_DAYS


@dataclass
class AlertFeedback:
    """Egy visszajelzés a kártyához: a szöveg, ki írta, mikor, és melyik
    riasztásról (a szabály típusa és célpontja, pl. vérnyomás vagy egy kérdőív)."""

    notification: Notification
    doctor_name: str
    rule_type: RuleType
    target_code: str
    target_name: str


def _target(db: Session, params: dict) -> tuple[str, str]:
    """A szabály célpontjának kódja és neve: méréstípus vagy kérdőív."""
    code = params.get("questionnaire")
    if code is not None:
        template = db.scalar(
            select(QuestionnaireTemplate).where(QuestionnaireTemplate.code == code)
        )
        return code, template.name if template else code
    code = params.get("measurement_type", "")
    mtype = db.scalar(select(MeasurementType).where(MeasurementType.code == code))
    return code, mtype.name if mtype else code


def recent_alert_feedback(
    db: Session, patient_id: uuid.UUID, now: datetime | None = None
) -> list[AlertFeedback]:
    """A beteg utóbbi NOTICE_DAYS napban kapott visszajelzései, a legújabb elöl."""
    now = now or datetime.now(UTC)
    since = now - timedelta(days=NOTICE_DAYS)
    notifications = db.scalars(
        select(Notification)
        .where(
            Notification.patient_id == patient_id,
            Notification.type == NotificationType.ALERT_FEEDBACK,
            Notification.created_at >= since,
            Notification.created_at <= now,
        )
        .order_by(Notification.created_at.desc(), Notification.id)
    ).all()
    if not notifications:
        return []
    authors = {
        u.id: u
        for u in db.scalars(
            select(User)
            .where(User.id.in_({n.created_by for n in notifications}))
            .options(selectinload(User.doctor_profile))
        )
    }
    alerts = {
        a.id: a
        for a in db.scalars(
            select(Alert)
            .where(Alert.id.in_({n.alert_id for n in notifications if n.alert_id}))
            .options(selectinload(Alert.rule_version))
        )
    }
    result = []
    for n in notifications:
        author = authors[n.created_by]
        alert = alerts[n.alert_id] if n.alert_id else None
        assert alert is not None  # visszajelzés mindig riasztáshoz tartozik
        code, name = _target(db, alert.rule_version.params)
        result.append(
            AlertFeedback(
                notification=n,
                doctor_name=author.doctor_profile.name if author.doctor_profile else author.email,
                rule_type=alert.rule_version.rule_type,
                target_code=code,
                target_name=name,
            )
        )
    return result
