"""Riasztások lekérdezése és magyarázata (F10, F17).

A magyarázatot nem tároljuk szövegként: az esemény alkalmazott szabályverziójából
és a kiváltó adatokból (mérések vagy kérdőív-kitöltések) állítjuk elő. Mivel
ezek változatlanok (a verziók immutabilisak, a mérés javításkor új sort kap),
a magyarázat utólag sem változik.
"""

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Alert,
    AlertEvent,
    AlertStatus,
    Measurement,
    RuleType,
    RuleVersion,
    Submission,
)
from app.services.measurements import get_measurements
from app.services.questionnaires import band_for, get_submissions
from app.services.rules import SEVERITY_RANK, ThresholdParams, Violation, threshold_violations


@dataclass
class TriggerExplanation:
    """Egy kiváltó adat: mérésnél a határátlépések, kitöltésnél a pontszám sávja."""

    measurement: Measurement | None = None
    violations: list[Violation] = field(default_factory=list)
    submission: Submission | None = None
    band: str | None = None


@dataclass
class EventExplanation:
    event: AlertEvent
    version: RuleVersion | None
    triggers: list[TriggerExplanation] = field(default_factory=list)


def list_patient_alerts(db: Session, patient_id: uuid.UUID, open_only: bool = True) -> list[Alert]:
    """A beteg riasztásai: elöl a súlyosabb, azon belül a frissebb."""
    query = (
        select(Alert)
        .where(Alert.patient_id == patient_id)
        .options(
            selectinload(Alert.rule_version),
            selectinload(Alert.events),
        )
    )
    if open_only:
        query = query.where(Alert.status != AlertStatus.CLOSED)
    alerts = list(db.scalars(query))
    alerts.sort(key=lambda a: (SEVERITY_RANK[a.severity], a.created_at), reverse=True)
    return alerts


def explain_event(db: Session, event: AlertEvent) -> EventExplanation:
    """Melyik verzió, mely adatok alapján: mérésnél melyik határt lépte át,
    kitöltésnél melyik kiértékelési sávba esett a pontszám."""
    version = db.get(RuleVersion, event.rule_version_id) if event.rule_version_id else None
    explanation = EventExplanation(event=event, version=version)
    ids = [uuid.UUID(i) for i in event.trigger_data_ids or []]
    if version is not None and version.rule_type is RuleType.QUESTIONNAIRE:
        for submission in get_submissions(db, ids):
            band = band_for(submission.version, submission.total_score)
            explanation.triggers.append(TriggerExplanation(submission=submission, band=band))
        return explanation
    for measurement in get_measurements(db, ids):
        violations: list[Violation] = []
        if version is not None and version.rule_type is RuleType.THRESHOLD:
            params = ThresholdParams.model_validate(version.params)
            violations = threshold_violations(params, measurement)
        explanation.triggers.append(TriggerExplanation(measurement, violations))
    return explanation


def explain_alert(db: Session, alert: Alert) -> list[EventExplanation]:
    return [explain_event(db, event) for event in alert.events]


def latest_trigger(db: Session, alert: Alert) -> TriggerExplanation | None:
    """A legutóbbi kiváltó adat a magyarázatával (a beteglista „Ok" oszlopához)."""
    for event in reversed(alert.events):
        if event.trigger_data_ids:
            triggers = explain_event(db, event).triggers
            if triggers:
                return triggers[-1]
    return None
