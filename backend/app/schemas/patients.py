import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models import (
    Alert,
    AlertEventType,
    AlertStatus,
    AssignmentTarget,
    OccurrenceStatus,
    PatientProfile,
    RuleType,
    RuleVersion,
    Severity,
)
from app.schemas.measurements import MeasurementOut, measurement_out
from app.schemas.questionnaires import SubmissionOut, submission_out
from app.schemas.tasks import TaskOut
from app.services.alerts import EventExplanation, OccurrenceTrigger, TriggerExplanation
from app.services.status import PatientStatus, PatientStatusResult


class ViolationOut(BaseModel):
    component: str
    value: float
    bound: str
    limit: float


class OccurrenceTriggerOut(BaseModel):
    """Egy alkalom (elmaradt adatnál a kiváltó, Adathiánynál az ok): mit
    kellett volna rögzíteni és mikorra."""

    id: uuid.UUID
    due_at: datetime
    status: OccurrenceStatus
    target_kind: AssignmentTarget
    code: str
    name: str


class TriggerOut(BaseModel):
    """Egy kiváltó adat: mérésnél melyik értéke lépte át a határt, kérdőív-
    kitöltésnél a pontszám és a kiértékelési sáv, elmaradt adatnál az
    elmulasztott alkalom."""

    measurement: MeasurementOut | None = None
    violations: list[ViolationOut] = []
    submission: SubmissionOut | None = None
    band: str | None = None
    occurrence: OccurrenceTriggerOut | None = None


class RuleVersionOut(BaseModel):
    rule_id: uuid.UUID
    version_no: int
    rule_type: RuleType
    severity: Severity
    params: dict[str, Any]


class UserRefOut(BaseModel):
    """Egy felhasználó röviden (orvosnál a profil szerinti név)."""

    id: uuid.UUID
    name: str


class AlertEventOut(BaseModel):
    event_type: AlertEventType
    created_at: datetime
    rule_version: RuleVersionOut | None
    triggers: list[TriggerOut]
    # Ki váltotta ki; üres = a rendszer (pl. kiértékelés).
    actor: UserRefOut | None = None
    # Lezárásnál az orvos indoklása.
    reason: str | None = None
    # Felelőshöz rendelésnél: kihez rendelték (a korábbi felelősök is látszanak).
    assignee: UserRefOut | None = None


class AlertOut(BaseModel):
    id: uuid.UUID
    status: AlertStatus
    severity: Severity
    created_at: datetime
    needs_review: bool
    # A riasztást megnyitó szabályverzió; a további eseményeké az events-ben.
    rule_version: RuleVersionOut
    events: list[AlertEventOut]
    # Az aktuális felelős orvos; üres = még nincs felelős.
    assigned_to: UserRefOut | None = None


class StatusReasonOut(BaseModel):
    status: PatientStatus
    code: str = Field(
        description="open_alert | missed_occurrence | no_data_yet | stale_data "
        "| closed_awaiting_data | fresh_data"
    )
    at: datetime | None
    alert_id: uuid.UUID | None
    severity: Severity | None
    trigger: TriggerOut | None
    # Kezelve oknál (closed_awaiting_data) a lezáró orvos; az at a lezárás ideje.
    actor: UserRefOut | None = None


class PatientSummaryOut(BaseModel):
    id: uuid.UUID
    name: str
    birth_date: date
    status: PatientStatus
    # Az összes fennálló ok, a státusz szerinti sorrendben; az első a státuszé.
    reasons: list[StatusReasonOut]
    # A legutóbbi adat (mérés vagy kitöltés) ideje.
    last_data_at: datetime | None
    # A beteg teendői az előírásai szerint (mi kész, mi esedékes, mi maradt el):
    # az orvos ebből látja, követi-e a beteg a tervet.
    tasks: list[TaskOut] = []


def rule_version_out(version: RuleVersion) -> RuleVersionOut:
    return RuleVersionOut(
        rule_id=version.rule_id,
        version_no=version.version_no,
        rule_type=version.rule_type,
        severity=version.severity,
        params=version.params,
    )


def occurrence_trigger_out(trigger: OccurrenceTrigger) -> OccurrenceTriggerOut:
    return OccurrenceTriggerOut(
        id=trigger.occurrence.id,
        due_at=trigger.occurrence.due_at,
        status=trigger.occurrence.status,
        target_kind=trigger.target_kind,
        code=trigger.code,
        name=trigger.name,
    )


def trigger_out(trigger: TriggerExplanation) -> TriggerOut:
    return TriggerOut(
        measurement=measurement_out(trigger.measurement) if trigger.measurement else None,
        violations=[
            ViolationOut(component=v.component, value=v.value, bound=v.bound, limit=v.limit)
            for v in trigger.violations
        ],
        submission=submission_out(trigger.submission) if trigger.submission else None,
        band=trigger.band,
        occurrence=occurrence_trigger_out(trigger.occurrence) if trigger.occurrence else None,
    )


def user_ref(user_id: uuid.UUID | None, names: dict[uuid.UUID, str]) -> UserRefOut | None:
    """A names a felhasználók neve azonosító szerint (services/alerts.user_names)."""
    if user_id is None:
        return None
    return UserRefOut(id=user_id, name=names.get(user_id, ""))


def alert_out(
    alert: Alert, events: list[EventExplanation], names: dict[uuid.UUID, str] | None = None
) -> AlertOut:
    names = names or {}
    return AlertOut(
        id=alert.id,
        status=alert.status,
        severity=alert.severity,
        created_at=alert.created_at,
        needs_review=alert.needs_review,
        rule_version=rule_version_out(alert.rule_version),
        events=[
            AlertEventOut(
                event_type=e.event.event_type,
                created_at=e.event.created_at,
                rule_version=rule_version_out(e.version) if e.version else None,
                triggers=[trigger_out(t) for t in e.triggers],
                actor=user_ref(e.event.actor_id, names),
                reason=e.event.reason,
                assignee=user_ref(e.event.assignee_id, names),
            )
            for e in events
        ],
        assigned_to=user_ref(alert.assigned_to, names),
    )


def patient_summary_out(
    patient: PatientProfile,
    result: PatientStatusResult,
    triggers: dict[uuid.UUID, TriggerExplanation | None],
    names: dict[uuid.UUID, str] | None = None,
) -> PatientSummaryOut:
    """A triggers a riasztás okainál a riasztás azonosítója, az elmulasztott
    alkalom okainál az alkalom azonosítója szerint adja az „Ok" oszlop adatát.
    A names a Kezelve okok lezáró orvosainak neve."""
    names = names or {}
    reasons = []
    for reason in result.reasons:
        key = reason.alert.id if reason.alert else reason.occurrence_id
        trigger = triggers.get(key) if key else None
        reasons.append(
            StatusReasonOut(
                status=reason.status,
                code=reason.code,
                at=reason.at,
                alert_id=reason.alert.id if reason.alert else None,
                severity=reason.alert.severity if reason.alert else None,
                trigger=trigger_out(trigger) if trigger else None,
                actor=user_ref(reason.actor_id, names),
            )
        )
    return PatientSummaryOut(
        id=patient.id,
        name=patient.name,
        birth_date=patient.birth_date,
        status=result.status,
        reasons=reasons,
        last_data_at=result.last_data_at,
    )
