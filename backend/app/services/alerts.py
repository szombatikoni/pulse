"""Riasztások lekérdezése, magyarázata és életútja (F10, F17, F18).

Az életút (M3, A6; a hallgató döntései, 2026-11-09): keletkezett (new) →
megtekintett (seen) → felelőshöz rendelt (assigned) → lezárt (closed). Lépés
előre kihagyható (pl. lezárás közvetlenül new-ból), visszaút és újranyitás
nincs: lezárás után az új kiváltó adat ÚJ riasztást nyit (07/1. példa).
Minden váltás AlertEvent a szereplővel. A lezárt riasztáson minden további
váltás hiba (409, already_closed), a megtekintés is: a lezárás a végállapot.

A magyarázatot nem tároljuk szövegként: az esemény alkalmazott szabályverziójából
és a kiváltó adatokból állítjuk elő. A kiváltó adat a szabálytípustól függ:
küszöb- és időablakos szabálynál mérés (a határátlépéseivel), kérdőívszabálynál
kitöltés (a sávjával), elmaradt adatnál az elmulasztott alkalom (határidővel és
célponttal). Mivel ezek változatlanok (a verziók immutabilisak, a mérés
javításkor új sort kap, a lezárt alkalom határideje és célpontja nem változik),
a magyarázat utólag sem változik.

A „kiváltó adat javítva" esemény (A7) kiváltó adata [eredeti, javított] mérés,
és tárolja, hogy a feltétel a javítás után még teljesül-e. Ez nem kiértékelés:
a riasztás „legutóbbi kiváltó adata" (beteglista, Riasztások oldal) ezért nem
ebből, hanem a legutóbbi keletkezés vagy ismételt aktiválódás eseményből jön.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models import (
    Alert,
    AlertEvent,
    AlertEventType,
    AlertStatus,
    Assignment,
    AssignmentOccurrence,
    AssignmentTarget,
    Measurement,
    MeasurementType,
    Notification,
    NotificationType,
    QuestionnaireTemplate,
    RuleType,
    RuleVersion,
    Submission,
    User,
)
from app.services.access import active_assignment_exists, assigned_patients_query
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
    # A tárolt sorrendben (javításnál [eredeti, javított], amelyek mérési ideje azonos).
    by_id = {m.id: m for m in get_measurements(db, ids)}
    for measurement in (by_id[i] for i in ids if i in by_id):
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
    """A legutóbbi kiváltó adat a magyarázatával (a beteglista „Ok" oszlopához).
    A „kiváltó adat javítva" esemény nem kiértékelés, ezért kimarad (A7)."""
    for event in reversed(alert.events):
        if event.trigger_data_ids and event.event_type is not AlertEventType.TRIGGER_CORRECTED:
            triggers = explain_event(db, event).triggers
            if triggers:
                return triggers[-1]
    return None


def user_names(db: Session, ids: set[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    """A felhasználók megjelenítendő neve (orvosnál és betegnél a profil szerinti
    név, adminnál az e-mail-cím) egy lekérdezéssel."""
    ids = {i for i in ids if i is not None}
    if not ids:
        return {}
    users = db.scalars(
        select(User)
        .where(User.id.in_(ids))
        .options(selectinload(User.doctor_profile), selectinload(User.patient_profile))
    )
    names = {}
    for user in users:
        profile = user.doctor_profile or user.patient_profile
        names[user.id] = profile.name if profile else user.email
    return names


def alert_user_ids(alerts: list[Alert]) -> set[uuid.UUID | None]:
    """A riasztások eseményeinek szereplői és felelősei, valamint az aktuális
    felelősök (a névfeloldáshoz)."""
    ids: set[uuid.UUID | None] = {a.assigned_to for a in alerts}
    ids.update(e.actor_id for a in alerts for e in a.events)
    ids.update(e.assignee_id for a in alerts for e in a.events)
    return ids


# --- Életút (M3, A6) -------------------------------------------------------------------


class AlertError(ValueError):
    """Érvénytelen életút-művelet; a `code` alapján a felület a saját nyelvén
    írja ki (mint a PlanError). A `conflict` a riasztás állapotával ütköző
    műveletet jelzi (HTTP 409), a többi érvénytelen adat (HTTP 422)."""

    def __init__(self, code: str, conflict: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.conflict = conflict


def lock_alert(db: Session, alert_id: uuid.UUID) -> Alert | None:
    """A riasztás sorzárral (SELECT … FOR UPDATE): két egyidejű váltás (pl. két
    orvos egyszerre zár le) egymás után fut, a második már a lezártat látja."""
    return db.scalar(
        select(Alert)
        .where(Alert.id == alert_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def _event(
    db: Session,
    alert: Alert,
    event_type: AlertEventType,
    actor: User,
    now: datetime,
    reason: str | None = None,
    assignee_id: uuid.UUID | None = None,
) -> AlertEvent:
    event = AlertEvent(
        alert_id=alert.id,
        actor_id=actor.id,
        event_type=event_type,
        reason=reason,
        assignee_id=assignee_id,
        created_at=now,
    )
    db.add(event)
    db.flush()
    return event


def _ensure_open(alert: Alert) -> None:
    if alert.status is AlertStatus.CLOSED:
        raise AlertError("already_closed", conflict=True)


def mark_seen(db: Session, alert: Alert, actor: User, now: datetime | None = None) -> bool:
    """Megtekintett: csak a keletkezett (new) riasztás vált, és csak egyszer;
    a már megtekintett vagy felelőshöz rendelt riasztásnál nem ír semmit
    (idempotens). Lezárt riasztásnál hiba. Visszaadja, történt-e váltás."""
    _ensure_open(alert)
    if alert.status is not AlertStatus.NEW:
        return False
    alert.status = AlertStatus.SEEN
    _event(db, alert, AlertEventType.SEEN, actor, now or datetime.now(UTC))
    return True


def assign_alert(
    db: Session, alert: Alert, actor: User, doctor: User | None, now: datetime | None = None
) -> None:
    """Felelőshöz rendelés: a felelős csak a beteghez ÉPPEN hozzárendelt orvos
    lehet, önmaga is (A6 D2). Újra-hozzárendelés megengedett, új eseménnyel.
    Az esemény szereplője a hozzárendelő orvos, a felelőse (assignee_id) akihez
    rendelte; az aktuális felelős az Alert.assigned_to mezőbe is bekerül."""
    _ensure_open(alert)
    now = now or datetime.now(UTC)
    if (
        doctor is None
        or not doctor.is_active
        or doctor.doctor_profile is None
        or not active_assignment_exists(db, doctor.doctor_profile.id, alert.patient_id, now)
    ):
        raise AlertError("doctor_not_assigned")
    alert.status = AlertStatus.ASSIGNED
    alert.assigned_to = doctor.id
    _event(db, alert, AlertEventType.ASSIGNED, actor, now, assignee_id=doctor.id)


def close_alert(
    db: Session,
    alert: Alert,
    actor: User,
    reason: str,
    message: str | None = None,
    now: datetime | None = None,
) -> Notification | None:
    """Lezárás bármely nyitott állapotból, kötelező indoklással (az esemény
    reason mezőjébe). Ha az orvos a betegnek is üzen, az értesítés ugyanebben a
    tranzakcióban jön létre (alert_feedback, a lezáró orvossal); ezt adja
    vissza. Az indoklás és az üzenet szóközök nélkül; üres indoklás hiba."""
    _ensure_open(alert)
    reason = reason.strip()
    if not reason:
        raise AlertError("reason_required")
    message = (message or "").strip() or None
    now = now or datetime.now(UTC)
    alert.status = AlertStatus.CLOSED
    _event(db, alert, AlertEventType.CLOSED, actor, now, reason=reason)
    if message is None:
        return None
    notification = Notification(
        patient_id=alert.patient_id,
        type=NotificationType.ALERT_FEEDBACK,
        text=message,
        alert_id=alert.id,
        created_by=actor.id,
        created_at=now,
    )
    db.add(notification)
    db.flush()
    return notification


def list_doctor_alerts(
    db: Session,
    doctor_profile_id: uuid.UUID,
    status: AlertStatus | None = None,
    now: datetime | None = None,
) -> list[Alert]:
    """Az orvos ÉPPEN hozzárendelt betegeinek nyitott riasztásai (a Riasztások
    oldalhoz), opcionálisan egy állapotra szűrve. Sorrend, mint a beteg
    riasztásainál: elöl a súlyosabb, azon belül a frissebb."""
    now = now or datetime.now(UTC)
    patients = assigned_patients_query(doctor_profile_id, now).subquery()
    query = (
        select(Alert)
        .where(Alert.patient_id.in_(select(patients.c.id)), Alert.status != AlertStatus.CLOSED)
        .options(selectinload(Alert.rule_version), selectinload(Alert.events))
    )
    if status is not None:
        query = query.where(Alert.status == status)
    alerts = list(db.scalars(query))
    alerts.sort(key=lambda a: (SEVERITY_RANK[a.severity], a.created_at), reverse=True)
    return alerts
