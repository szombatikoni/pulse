import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel

from app.models import (
    Alert,
    AlertEventType,
    AlertStatus,
    PatientProfile,
    RuleType,
    RuleVersion,
    Severity,
)
from app.schemas.measurements import MeasurementOut, measurement_out
from app.schemas.questionnaires import SubmissionOut, submission_out
from app.schemas.tasks import TaskOut
from app.services.alerts import EventExplanation, TriggerExplanation
from app.services.status import PatientStatus, PatientStatusResult


class ViolationOut(BaseModel):
    component: str
    value: float
    bound: str
    limit: float


class TriggerOut(BaseModel):
    """Egy kiváltó adat: mérésnél melyik értéke lépte át a határt, kérdőív-
    kitöltésnél a pontszám és a kiértékelési sáv."""

    measurement: MeasurementOut | None = None
    violations: list[ViolationOut] = []
    submission: SubmissionOut | None = None
    band: str | None = None


class RuleVersionOut(BaseModel):
    rule_id: uuid.UUID
    version_no: int
    rule_type: RuleType
    severity: Severity
    params: dict[str, Any]


class AlertEventOut(BaseModel):
    event_type: AlertEventType
    created_at: datetime
    rule_version: RuleVersionOut | None
    triggers: list[TriggerOut]


class AlertOut(BaseModel):
    id: uuid.UUID
    status: AlertStatus
    severity: Severity
    created_at: datetime
    needs_review: bool
    # A riasztást megnyitó szabályverzió; a további eseményeké az events-ben.
    rule_version: RuleVersionOut
    events: list[AlertEventOut]


class StatusReasonOut(BaseModel):
    status: PatientStatus
    code: str
    at: datetime | None
    alert_id: uuid.UUID | None
    severity: Severity | None
    trigger: TriggerOut | None


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


def trigger_out(trigger: TriggerExplanation) -> TriggerOut:
    return TriggerOut(
        measurement=measurement_out(trigger.measurement) if trigger.measurement else None,
        violations=[
            ViolationOut(component=v.component, value=v.value, bound=v.bound, limit=v.limit)
            for v in trigger.violations
        ],
        submission=submission_out(trigger.submission) if trigger.submission else None,
        band=trigger.band,
    )


def alert_out(alert: Alert, events: list[EventExplanation]) -> AlertOut:
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
            )
            for e in events
        ],
    )


def patient_summary_out(
    patient: PatientProfile,
    result: PatientStatusResult,
    triggers: dict[uuid.UUID, TriggerExplanation | None],
) -> PatientSummaryOut:
    reasons = []
    for reason in result.reasons:
        trigger = triggers.get(reason.alert.id) if reason.alert else None
        reasons.append(
            StatusReasonOut(
                status=reason.status,
                code=reason.code,
                at=reason.at,
                alert_id=reason.alert.id if reason.alert else None,
                severity=reason.alert.severity if reason.alert else None,
                trigger=trigger_out(trigger) if trigger else None,
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
