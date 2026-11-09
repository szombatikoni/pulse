"""Riasztások lekérdezése és magyarázata (F10, F17).

A magyarázatot nem tároljuk szövegként: az esemény alkalmazott szabályverziójából
és a kiváltó adatokból állítjuk elő. A kiváltó adat a szabálytípustól függ:
küszöb- és időablakos szabálynál mérés (a határátlépéseivel), kérdőívszabálynál
kitöltés (a sávjával), elmaradt adatnál az elmulasztott alkalom (határidővel és
célponttal). Mivel ezek változatlanok (a verziók immutabilisak, a mérés
javításkor új sort kap, a lezárt alkalom határideje és célpontja nem változik),
a magyarázat utólag sem változik.
"""

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models import (
    Alert,
    AlertEvent,
    AlertStatus,
    Assignment,
    AssignmentOccurrence,
    AssignmentTarget,
    Measurement,
    MeasurementType,
    QuestionnaireTemplate,
    RuleType,
    RuleVersion,
    Submission,
)
from app.services.measurements import get_measurements
from app.services.questionnaires import band_for, get_submissions
from app.services.rules import SEVERITY_RANK, ThresholdParams, Violation, threshold_violations


@dataclass(frozen=True)
class OccurrenceTrigger:
    """Egy elmulasztott (vagy más módon lezárt) alkalom a célpontjával: mit
    kellett volna rögzíteni (méréstípus vagy kérdőív) és mikorra."""

    occurrence: AssignmentOccurrence
    target_kind: AssignmentTarget
    code: str
    name: str


@dataclass
class TriggerExplanation:
    """Egy kiváltó adat: mérésnél a határátlépések, kitöltésnél a pontszám
    sávja, elmaradt adatnál az alkalom a célpontjával."""

    measurement: Measurement | None = None
    violations: list[Violation] = field(default_factory=list)
    submission: Submission | None = None
    band: str | None = None
    occurrence: OccurrenceTrigger | None = None


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


def occurrence_triggers(db: Session, ids: list[uuid.UUID]) -> list[OccurrenceTrigger]:
    """Az alkalmak a célpontjukkal, a megadott azonosítók sorrendjében (a
    kiváltók határidő szerint rendezve tárolódnak); a nem létezőket kihagyja."""
    if not ids:
        return []
    occurrences = {
        o.id: o
        for o in db.scalars(
            select(AssignmentOccurrence)
            .where(AssignmentOccurrence.id.in_(ids))
            .options(joinedload(AssignmentOccurrence.assignment).joinedload(Assignment.template))
        )
    }
    type_ids = {o.assignment.measurement_type_id for o in occurrences.values()} - {None}
    types = {
        t.id: t for t in db.scalars(select(MeasurementType).where(MeasurementType.id.in_(type_ids)))
    }
    result = []
    for occurrence_id in ids:
        occurrence = occurrences.get(occurrence_id)
        if occurrence is None:
            continue
        assignment = occurrence.assignment
        if assignment.target_kind is AssignmentTarget.MEASUREMENT:
            target: MeasurementType | QuestionnaireTemplate = types[assignment.measurement_type_id]
        else:
            assert assignment.template is not None
            target = assignment.template
        result.append(
            OccurrenceTrigger(occurrence, assignment.target_kind, target.code, target.name)
        )
    return result


def explain_event(db: Session, event: AlertEvent) -> EventExplanation:
    """Melyik verzió, mely adatok alapján: mérésnél melyik határt lépte át
    (küszöb- és időablakos szabálynál), kitöltésnél melyik kiértékelési sávba
    esett a pontszám, elmaradt adatnál melyik alkalom maradt el."""
    version = db.get(RuleVersion, event.rule_version_id) if event.rule_version_id else None
    explanation = EventExplanation(event=event, version=version)
    ids = [uuid.UUID(i) for i in event.trigger_data_ids or []]
    rule_type = version.rule_type if version is not None else None
    if rule_type is RuleType.QUESTIONNAIRE:
        for submission in get_submissions(db, ids):
            band = band_for(submission.version, submission.total_score)
            explanation.triggers.append(TriggerExplanation(submission=submission, band=band))
        return explanation
    if rule_type is RuleType.MISSING_DATA:
        for occurrence in occurrence_triggers(db, ids):
            explanation.triggers.append(TriggerExplanation(occurrence=occurrence))
        return explanation
    for measurement in get_measurements(db, ids):
        violations: list[Violation] = []
        if version is not None and rule_type in (RuleType.THRESHOLD, RuleType.WINDOW):
            # A WindowParams a ThresholdParams leszármazottja: a határok ugyanott
            # vannak, a többletkulcsokat (count, window_days) a modell elhagyja.
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
