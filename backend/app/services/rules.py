"""Szabályok és kiértékelés (F11, F12, F17, F18).

Az M2-ben két szabálytípus működik:
- egyszeri küszöbátlépés: ha egy mérés valamelyik értéke a szabályverzióban
  megadott határon kívül esik, riasztás keletkezik. A határ maga még rendben
  van (szigorú összehasonlítás: a „140 feletti" szisztolés a 141-től kezdődik);
- kérdőív-pontszám: ha a kitöltés összpontszáma a megadott kiértékelési
  sávok egyikébe esik (pl. figyelmeztető sáv), riasztás keletkezik.
"""

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Alert,
    AlertEvent,
    AlertEventType,
    AlertStatus,
    Measurement,
    QuestionnaireTemplate,
    Rule,
    RuleType,
    RuleVersion,
    Severity,
    Submission,
)
from app.services.questionnaires import band_for
from app.services.questionnaires import current_version as questionnaire_version

SEVERITY_RANK = {Severity.MODERATE: 1, Severity.SEVERE: 2}


class Limit(BaseModel):
    min: float | None = None
    max: float | None = None

    @model_validator(mode="after")
    def at_least_one_bound(self) -> "Limit":
        if self.min is None and self.max is None:
            raise ValueError("min vagy max megadása kötelező")
        if self.min is not None and self.max is not None and self.min >= self.max:
            raise ValueError("min < max kell")
        return self


class ThresholdParams(BaseModel):
    """Az egyszeri küszöbátlépés paraméterei: méréstípus és komponensenkénti
    határok. Pl. vérnyomás: {"systolic": {"max": 140}, "diastolic": {"max": 90}}
    — bármelyik érték határon kívül esése riasztást vált ki."""

    measurement_type: str
    limits: dict[str, Limit] = Field(min_length=1)


class QuestionnaireParams(BaseModel):
    """A kérdőívszabály paraméterei: melyik kérdőív, és mely kiértékelési
    sávok váltanak ki riasztást (pl. ["warning", "critical"]). A sávok határai
    a kérdőívverzióban vannak, így az új verzió a saját határait hozza."""

    questionnaire: str
    bands: list[str] = Field(min_length=1)


PARAMS_BY_TYPE: dict[RuleType, type[BaseModel]] = {
    RuleType.THRESHOLD: ThresholdParams,
    RuleType.QUESTIONNAIRE: QuestionnaireParams,
}


@dataclass(frozen=True)
class Violation:
    """Egy érték határon kívül: melyik komponens, mennyi, melyik határ."""

    component: str
    value: float
    bound: str  # "max" vagy "min"
    limit: float


def _validated_params(db: Session, rule_type: RuleType, params: dict[str, Any]) -> dict[str, Any]:
    model = PARAMS_BY_TYPE.get(rule_type)
    if model is None:
        raise ValueError(f"A(z) {rule_type} szabálytípus még nincs megvalósítva")
    validated = model.model_validate(params)
    if isinstance(validated, QuestionnaireParams):
        _check_questionnaire_params(db, validated)
    return validated.model_dump(exclude_none=True)


def _check_questionnaire_params(db: Session, params: QuestionnaireParams) -> None:
    """A kérdőív létezik, és a megadott sávok az aktuális verziójában vannak —
    különben egy elgépelt sávnév miatt a szabály csendben soha nem riasztana
    (Fable-átnézés, 2026-10-12)."""
    template = db.scalar(
        select(QuestionnaireTemplate).where(QuestionnaireTemplate.code == params.questionnaire)
    )
    if template is None:
        raise ValueError(f"Ismeretlen kérdőív: {params.questionnaire}")
    version = questionnaire_version(db, template.id)
    known = {band["band"] for band in version.scoring_thresholds}
    unknown = [band for band in params.bands if band not in known]
    if unknown:
        raise ValueError(f"A kérdőívben nincs ilyen sáv: {', '.join(unknown)}")


def create_rule(
    db: Session,
    *,
    patient_id: uuid.UUID,
    created_by: uuid.UUID,
    rule_type: RuleType,
    params: dict[str, Any],
    severity: Severity,
) -> Rule:
    """Új szabály az első verziójával."""
    rule = Rule(patient_id=patient_id, created_by=created_by)
    db.add(rule)
    db.flush()
    add_rule_version(
        db, rule, created_by=created_by, rule_type=rule_type, params=params, severity=severity
    )
    return rule


def add_rule_version(
    db: Session,
    rule: Rule,
    *,
    created_by: uuid.UUID,
    rule_type: RuleType,
    params: dict[str, Any],
    severity: Severity,
) -> RuleVersion:
    """Szabálymódosítás = új verzió (F12); a korábbiak változatlanok maradnak.

    TODO M3: a nyitott riasztás(ok) történetébe „szabály módosult" esemény is
    kell (07_mukodesi_szabalyok.md 3. rész; Fable-átnézés F2, 2026-10-12)."""
    last = db.scalar(select(func.max(RuleVersion.version_no)).where(RuleVersion.rule_id == rule.id))
    version = RuleVersion(
        rule_id=rule.id,
        version_no=(last or 0) + 1,
        rule_type=rule_type,
        params=_validated_params(db, rule_type, params),
        severity=severity,
        created_by=created_by,
    )
    db.add(version)
    db.flush()
    return version


def current_version(db: Session, rule_id: uuid.UUID) -> RuleVersion:
    return db.scalars(
        select(RuleVersion)
        .where(RuleVersion.rule_id == rule_id)
        .order_by(RuleVersion.version_no.desc())
        .limit(1)
    ).one()


def threshold_violations(params: ThresholdParams, measurement: Measurement) -> list[Violation]:
    """A mérés határon kívüli értékei a megadott paraméterek szerint."""
    if measurement.type.code != params.measurement_type:
        return []
    violations: list[Violation] = []
    for value in sorted(measurement.values, key=lambda v: v.component.order_no):
        limit = params.limits.get(value.component.code)
        if limit is None:
            continue
        if limit.max is not None and value.value > limit.max:
            violations.append(Violation(value.component.code, value.value, "max", limit.max))
        elif limit.min is not None and value.value < limit.min:
            violations.append(Violation(value.component.code, value.value, "min", limit.min))
    return violations


def open_alert(db: Session, patient_id: uuid.UUID, rule_id: uuid.UUID) -> Alert | None:
    return db.scalar(
        select(Alert).where(
            Alert.patient_id == patient_id,
            Alert.rule_id == rule_id,
            Alert.status != AlertStatus.CLOSED,
        )
    )


def _active_rules(
    db: Session, patient_id: uuid.UUID, rule_type: RuleType
) -> Iterator[tuple[Rule, RuleVersion]]:
    """A beteg aktív szabályai az aktuális verziójukkal, egy szabálytípusból."""
    rules = db.scalars(
        select(Rule).where(Rule.patient_id == patient_id, Rule.is_active.is_(True))
    ).all()
    for rule in rules:
        version = current_version(db, rule.id)
        if version.rule_type is rule_type:
            yield rule, version


def _raise_alert(
    db: Session,
    rule: Rule,
    version: RuleVersion,
    patient_id: uuid.UUID,
    trigger_ids: list[str],
    now: datetime,
) -> Alert:
    """Riasztás nyitása, vagy ha a beteg + szabály párosra már van nyitott,
    „ismételt aktiválódás" esemény hozzá (F18; a súlyosság emelkedhet). Minden
    esemény tárolja az alkalmazott szabályverziót és a kiváltó adatot (F17).

    TODO M3: két egyidejű kérés ugyanarra a beteg + szabály párosra mindkettőben
    „nincs nyitott riasztást" láthat; a második ekkor az uq_alerts_open_per_rule
    indexbe ütközik, és a mérése is visszagördül. Megoldás: a beteg szabályainak
    zárolása (SELECT … FOR UPDATE) a kiértékelés elején (Fable-átnézés F4)."""
    alert = open_alert(db, patient_id, rule.id)
    if alert is None:
        alert = Alert(
            patient_id=patient_id,
            rule_id=rule.id,
            rule_version_id=version.id,
            severity=version.severity,
            trigger_data_ids=trigger_ids,
            created_at=now,
        )
        db.add(alert)
        db.flush()
        event_type = AlertEventType.CREATED
    else:
        if SEVERITY_RANK[version.severity] > SEVERITY_RANK[alert.severity]:
            alert.severity = version.severity
        event_type = AlertEventType.RE_TRIGGERED
    db.add(
        AlertEvent(
            alert_id=alert.id,
            event_type=event_type,
            rule_version_id=version.id,
            trigger_data_ids=trigger_ids,
            created_at=now,
        )
    )
    return alert


def evaluate_measurement(
    db: Session, measurement: Measurement, now: datetime | None = None
) -> list[Alert]:
    """Az új mérés kiértékelése a beteg aktív küszöbszabályainak aktuális verziójával."""
    now = now or datetime.now(UTC)
    touched: list[Alert] = []
    for rule, version in _active_rules(db, measurement.patient_id, RuleType.THRESHOLD):
        if threshold_violations(ThresholdParams.model_validate(version.params), measurement):
            touched.append(
                _raise_alert(db, rule, version, measurement.patient_id, [str(measurement.id)], now)
            )
    db.flush()
    return touched


def evaluate_submission(
    db: Session, submission: Submission, now: datetime | None = None
) -> list[Alert]:
    """Az új kérdőív-kitöltés kiértékelése a beteg aktív kérdőívszabályaival:
    riasztás, ha az összpontszám a szabályban megadott sávok egyikébe esik.
    A sávhatárok a kitöltött kérdőívverzió részei (F13). A romló trend az M3-ban jön."""
    now = now or datetime.now(UTC)
    touched: list[Alert] = []
    for rule, version in _active_rules(db, submission.patient_id, RuleType.QUESTIONNAIRE):
        params = QuestionnaireParams.model_validate(version.params)
        if submission.version.template.code != params.questionnaire:
            continue
        if band_for(submission.version, submission.total_score) in params.bands:
            touched.append(
                _raise_alert(db, rule, version, submission.patient_id, [str(submission.id)], now)
            )
    db.flush()
    return touched
