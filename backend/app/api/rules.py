"""Szabályok az orvosi felülethez (F11, F12; M3, A4 2. lépés): a beteg
szabályai a verziólistával, új szabály, és a módosítás mint új verzió.

Csak a beteg hozzárendelt orvosa éri el (a beteg és az admin nem: a szabályok
betegadatok). A szolgáltatás hibái 422-vel, a detail.code-ban kóddal jönnek, a
felület a saját nyelvén írja ki (mint a követési tervnél)."""

import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import DoctorUser, ensure_patient_access
from app.core.db import DbSession
from app.models import Rule, User
from app.schemas.rules import RuleCreate, RuleOut, RuleVersionCreate, rule_out
from app.services import rules
from app.services.rules import RuleError

router = APIRouter(tags=["rules"])

FORBIDDEN = {403: {"description": "Csak a beteg hozzárendelt orvosa"}}
ERRORS = {
    **FORBIDDEN,
    422: {
        "description": "Érvénytelen szabály (a detail.code adja meg az okát: invalid_params, "
        "unknown_measurement_type, unknown_component, unknown_questionnaire, unknown_band, "
        "rule_type_locked)"
    },
}


def _error(error: RuleError | ValidationError) -> HTTPException:
    """A szolgáltatás hívása mentési pontban (begin_nested) fut: új szabálynál
    a szabály sora a verzió ellenőrzése előtt íródik ki, hibánál ez is
    visszagördül, és a kérés sessionje commit nélkül zárul.

    A paraméterek szerkezeti hibájánál (pydantic) a fields a hibás mezők útja
    (pl. "limits.systolic", "count"); a modell-szintű feltételnél (pl. pontosan
    egy célpont) üres útvonal helyett a "params" szerepel."""
    if isinstance(error, RuleError):
        detail: dict = {"code": error.code}
    else:
        fields = [".".join(str(part) for part in e["loc"]) or "params" for e in error.errors()]
        detail = {"code": "invalid_params", "fields": fields}
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail)


def _rules_out(db: DbSession, patient_id: uuid.UUID) -> list[RuleOut]:
    entries = rules.list_rules(db, patient_id)
    author_ids = {v.created_by for entry in entries for v in entry.versions}
    users = {
        u.id: u
        for u in db.scalars(
            select(User).where(User.id.in_(author_ids)).options(selectinload(User.doctor_profile))
        )
    }
    return [rule_out(entry, users) for entry in entries]


def _rule_out(db: DbSession, rule: Rule) -> RuleOut:
    return next(r for r in _rules_out(db, rule.patient_id) if r.id == rule.id)


@router.get("/patients/{patient_id}/rules", responses=FORBIDDEN)
def patient_rules(patient_id: uuid.UUID, db: DbSession, user: DoctorUser) -> list[RuleOut]:
    """A beteg szabályai: szabályonként az aktuális verzió (típus, paraméterek,
    súlyosság, verziószám, mióta), a teljes verziólista és a nyitott
    riasztások száma."""
    ensure_patient_access(db, user, patient_id)
    return _rules_out(db, patient_id)


@router.post("/patients/{patient_id}/rules", status_code=status.HTTP_201_CREATED, responses=ERRORS)
def create_rule(
    patient_id: uuid.UUID, body: RuleCreate, db: DbSession, user: DoctorUser
) -> RuleOut:
    """Új szabály az első verziójával. A meglévő adatokra nem értékel
    visszamenőleg: a következő mérés, kitöltés, illetve alkalom-zárás számít."""
    ensure_patient_access(db, user, patient_id)
    try:
        with db.begin_nested():
            rule = rules.create_rule(
                db,
                patient_id=patient_id,
                created_by=user.id,
                rule_type=body.rule_type,
                params=body.params,
                severity=body.severity,
            )
    except (RuleError, ValidationError) as error:
        raise _error(error) from error
    db.commit()
    return _rule_out(db, rule)


@router.post("/rules/{rule_id}/versions", status_code=status.HTTP_201_CREATED, responses=ERRORS)
def add_rule_version(
    rule_id: uuid.UUID, body: RuleVersionCreate, db: DbSession, user: DoctorUser
) -> RuleOut:
    """Módosítás = új, immutabilis verzió (F12); a régiek és a rájuk hivatkozó
    riasztások jelentése nem változik. A típus nem váltható (rule_type_locked).
    Ha a szabálynak nyitott riasztása van, abba „szabály módosult" esemény kerül.

    A jogosultság a szabály betegén át dől el; nem létező szabályra is 403 jön,
    így a válaszból nem derül ki, létezik-e az azonosító (mint a betegnél)."""
    rule = db.get(Rule, rule_id)
    if rule is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    ensure_patient_access(db, user, rule.patient_id)
    current = rules.current_version(db, rule.id)
    if body.rule_type is not None and body.rule_type is not current.rule_type:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "rule_type_locked"},
        )
    try:
        with db.begin_nested():
            rules.add_rule_version(
                db,
                rule,
                created_by=user.id,
                rule_type=current.rule_type,
                params=body.params,
                severity=body.severity,
            )
    except (RuleError, ValidationError) as error:
        raise _error(error) from error
    db.commit()
    return _rule_out(db, rule)
