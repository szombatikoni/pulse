"""A riasztás-életút végpontjai (F18; M3, A6): megtekintés, felelőshöz
rendelés, lezárás, és az orvos összes betegének nyitott riasztásai a
Riasztások oldalhoz.

Csak a beteg hozzárendelt orvosa éri el (a beteg és az admin nem); nem létező
riasztásra is 403 jön, így a válaszból nem derül ki, létezik-e az azonosító
(mint a szabályoknál). A szolgáltatás hibái a detail.code-ban kóddal jönnek: a
lezárt riasztáson minden további váltás 409 (already_closed, mint a visszavont
előírásnál), az érvénytelen adat 422 (doctor_not_assigned, reason_required)."""

import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import DoctorUser, ensure_patient_access
from app.core.db import DbSession
from app.models import Alert, AlertStatus, PatientProfile, User
from app.schemas.alerts import AlertAssign, AlertClose, AlertListItemOut, PatientRefOut
from app.schemas.patients import AlertOut, alert_out, trigger_out
from app.services import alerts
from app.services.alerts import AlertError

router = APIRouter(tags=["alerts"])

FORBIDDEN = {403: {"description": "Csak a beteg hozzárendelt orvosa"}}
ERRORS = {
    **FORBIDDEN,
    409: {"description": "A riasztás már lezárt (already_closed)"},
    422: {
        "description": "Érvénytelen adat (a detail.code adja meg az okát: doctor_not_assigned, "
        "reason_required)"
    },
}


def _error(error: AlertError) -> HTTPException:
    """Az ellenőrzések minden módosítás előtt futnak, így hibánál nincs mit
    visszavonni; a kérés sessionje commit nélkül zárul."""
    code = status.HTTP_409_CONFLICT if error.conflict else status.HTTP_422_UNPROCESSABLE_CONTENT
    return HTTPException(status_code=code, detail={"code": error.code})


def _load(db: DbSession, user: User, alert_id: uuid.UUID) -> Alert:
    """A riasztás sorzárral; nem létezőre és idegenre egyaránt 403."""
    alert = alerts.lock_alert(db, alert_id)
    if alert is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    ensure_patient_access(db, user, alert.patient_id)
    return alert


def _alert_out(db: DbSession, alert_id: uuid.UUID) -> AlertOut:
    """A riasztás friss állapota az eseménytörténettel (a véglegesítés után)."""
    alert = db.get(Alert, alert_id, populate_existing=True)
    assert alert is not None
    db.refresh(alert, ["events"])
    names = alerts.user_names(db, alerts.alert_user_ids([alert]))
    return alert_out(alert, alerts.explain_alert(db, alert), names)


@router.post("/alerts/{alert_id}/seen", responses=ERRORS)
def mark_seen(alert_id: uuid.UUID, db: DbSession, user: DoctorUser) -> AlertOut:
    """Megtekintett: a felület az adatlap megnyitásakor küldi (nem a GET
    mellékhatása). Csak a keletkezett (new) riasztás vált; ha már megtekintett
    vagy felelősnél van, nem ír semmit (idempotens, 200)."""
    alert = _load(db, user, alert_id)
    try:
        alerts.mark_seen(db, alert, user)
    except AlertError as error:
        raise _error(error) from error
    db.commit()
    return _alert_out(db, alert_id)


@router.post("/alerts/{alert_id}/assign", responses=ERRORS)
def assign(
    alert_id: uuid.UUID, db: DbSession, user: DoctorUser, body: AlertAssign | None = None
) -> AlertOut:
    """Felelőshöz rendelés (a megtekintés kihagyható). A felelős csak a
    beteghez éppen hozzárendelt orvos lehet, önmaga is (alapértelmezés);
    újra-hozzárendelés megengedett, új eseménnyel."""
    alert = _load(db, user, alert_id)
    doctor_id = body.doctor_id if body and body.doctor_id else user.id
    doctor = db.get(User, doctor_id)
    try:
        alerts.assign_alert(db, alert, user, doctor)
    except AlertError as error:
        raise _error(error) from error
    db.commit()
    return _alert_out(db, alert_id)


@router.post("/alerts/{alert_id}/close", responses=ERRORS)
def close(alert_id: uuid.UUID, body: AlertClose, db: DbSession, user: DoctorUser) -> AlertOut:
    """Lezárás bármely nyitott állapotból, kötelező indoklással. A nem
    kötelező betegüzenetből értesítés lesz (a beteg a jelzései közt látja).
    Újranyitás nincs: a lezárás után az új kiváltó adat új riasztást nyit."""
    alert = _load(db, user, alert_id)
    try:
        alerts.close_alert(db, alert, user, reason=body.reason, message=body.message)
    except AlertError as error:
        raise _error(error) from error
    db.commit()
    return _alert_out(db, alert_id)


@router.get("/alerts", responses={422: {"description": "Ismeretlen állapot a szűrőben"}})
def my_alerts(
    db: DbSession,
    user: DoctorUser,
    alert_status: Literal["new", "seen", "assigned"] | None = Query(
        default=None, alias="status", description="Szűrés állapotra (üresen: minden nyitott)."
    ),
) -> list[AlertListItemOut]:
    """Az orvos éppen hozzárendelt betegeinek NYITOTT riasztásai (Riasztások
    oldal): elöl a súlyosabb, azon belül a frissebb. Soronként a beteg, a
    felelős, a kártya-adatok és a legutóbbi kiváltó adat."""
    rows = alerts.list_doctor_alerts(
        db,
        user.doctor_profile.id,
        AlertStatus(alert_status) if alert_status else None,
    )
    patients = {
        p.id: p
        for p in db.scalars(
            select(PatientProfile).where(PatientProfile.id.in_({a.patient_id for a in rows}))
        )
    }
    names = alerts.user_names(db, alerts.alert_user_ids(rows))
    result = []
    for alert in rows:
        explanations = alerts.explain_alert(db, alert)
        out = alert_out(alert, explanations, names)
        # A legutóbbi kiváltó adat (mint a latest_trigger, de a már kész magyarázatból).
        trigger = next((e.triggers[-1] for e in reversed(explanations) if e.triggers), None)
        patient = patients[alert.patient_id]
        result.append(
            AlertListItemOut(
                **out.model_dump(),
                patient=PatientRefOut(id=patient.id, name=patient.name),
                trigger=trigger_out(trigger) if trigger else None,
            )
        )
    return result
