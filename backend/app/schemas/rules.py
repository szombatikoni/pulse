import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models import RuleType, Severity, User
from app.services.rules import RuleEntry

# A paraméterek szerkezete típusonként más (services/rules.py: ThresholdParams,
# WindowParams, QuestionnaireParams, MissingDataParams); a szolgáltatás
# ellenőrzi, hiba esetén 422 jön a detail.code-dal.
Params = Field(
    description="A szabálytípus paraméterei (lásd services/rules.py).",
    examples=[
        {
            "measurement_type": "blood_pressure",
            "limits": {"systolic": {"max": 140}, "diastolic": {"max": 90}},
            "count": 3,
            "window_days": 7,
        }
    ],
)


class RuleCreate(BaseModel):
    """Új szabály az első verziójával."""

    rule_type: RuleType
    params: dict[str, Any] = Params
    severity: Severity


class RuleVersionCreate(BaseModel):
    """Módosítás = új verzió. A típus a szabályé, nem váltható: ha a kliens
    megadja, egyeznie kell (különben 422, rule_type_locked)."""

    rule_type: RuleType | None = None
    params: dict[str, Any] = Params
    severity: Severity


class RuleVersionDetailOut(BaseModel):
    id: uuid.UUID
    version_no: int
    rule_type: RuleType
    severity: Severity
    params: dict[str, Any]
    # Mióta érvényes (a verzió létrejötte) és ki hozta létre.
    created_at: datetime
    created_by: str = Field(description="A verziót létrehozó orvos neve.")


class RuleOut(BaseModel):
    id: uuid.UUID
    rule_type: RuleType
    is_active: bool
    created_at: datetime
    # Az aktuális (legutóbbi) verzió; a versions utolsó eleme.
    current: RuleVersionDetailOut
    # Az összes verzió verziószám szerint növekvő sorrendben.
    versions: list[RuleVersionDetailOut]
    # A szabály nyitott (nem lezárt) riasztásainak száma.
    open_alerts: int


def _author(users: dict[uuid.UUID, User], user_id: uuid.UUID) -> str:
    user = users[user_id]
    return user.doctor_profile.name if user.doctor_profile else user.email


def rule_out(entry: RuleEntry, users: dict[uuid.UUID, User]) -> RuleOut:
    """A users a verziók létrehozói azonosító szerint (a hívó tölti be)."""
    versions = [
        RuleVersionDetailOut(
            id=v.id,
            version_no=v.version_no,
            rule_type=v.rule_type,
            severity=v.severity,
            params=v.params,
            created_at=v.created_at,
            created_by=_author(users, v.created_by),
        )
        for v in entry.versions
    ]
    return RuleOut(
        id=entry.rule.id,
        rule_type=entry.current.rule_type,
        is_active=entry.rule.is_active,
        created_at=entry.rule.created_at,
        current=versions[-1],
        versions=versions,
        open_alerts=entry.open_alerts,
    )
