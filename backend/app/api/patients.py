import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Query

from app.api.deps import DoctorUser, ensure_patient_access
from app.core.db import DbSession
from app.models import DoctorProfile, PatientProfile
from app.schemas.patients import (
    AlertOut,
    PatientSummaryOut,
    UserRefOut,
    alert_out,
    patient_summary_out,
)
from app.schemas.tasks import task_out
from app.services.access import assigned_doctors_query
from app.services.alerts import (
    TriggerExplanation,
    alert_user_ids,
    explain_alert,
    latest_trigger,
    list_patient_alerts,
    occurrence_triggers,
    user_names,
)
from app.services.status import PatientStatusResult, compute_status, doctor_patient_list
from app.services.tasks import patient_tasks

router = APIRouter(tags=["patients"])

FORBIDDEN = {403: {"description": "A felhasználó nem érheti el a beteg adatait"}}


def _summary(
    db: DbSession, patient: PatientProfile, result: PatientStatusResult
) -> PatientSummaryOut:
    triggers = {r.alert.id: latest_trigger(db, r.alert) for r in result.reasons if r.alert}
    # Az elmulasztott alkalom okainál az alkalom a célpontjával (mit, mikorra).
    missed = [r.occurrence.id for r in result.reasons if r.occurrence]
    for occurrence in occurrence_triggers(db, missed):
        triggers[occurrence.occurrence.id] = TriggerExplanation(occurrence=occurrence)
    # A Kezelve okoknál a lezáró orvos neve (csak ha van ilyen ok: plusz egy lekérdezés).
    names = user_names(db, {r.actor_id for r in result.reasons})
    summary = patient_summary_out(patient, result, triggers, names)
    summary.tasks = [task_out(t) for t in patient_tasks(db, patient.id)]
    return summary


@router.get("/doctor/patients")
def my_patients(db: DbSession, user: DoctorUser) -> list[PatientSummaryOut]:
    """Az orvos priorizált beteglistája (F9): csak az éppen hozzá rendelt
    betegek, státusszal és az okával."""
    rows = doctor_patient_list(db, user.doctor_profile.id)
    summaries = [_summary(db, patient, result) for patient, result in rows]
    db.commit()  # a teendők a hiányzó alkalmakat megnyitják
    return summaries


@router.get("/patients/{patient_id}", responses=FORBIDDEN)
def patient_detail(patient_id: uuid.UUID, db: DbSession, user: DoctorUser) -> PatientSummaryOut:
    """A beteg adatlapjának fejléce az orvosnak: név, születési dátum, státusz
    és okai."""
    ensure_patient_access(db, user, patient_id)
    patient = db.get(PatientProfile, patient_id)
    summary = _summary(db, patient, compute_status(db, patient_id))
    db.commit()  # a teendők a hiányzó alkalmakat megnyitják
    return summary


@router.get("/patients/{patient_id}/alerts", responses=FORBIDDEN)
def patient_alerts(
    patient_id: uuid.UUID,
    db: DbSession,
    user: DoctorUser,
    include_closed: bool = Query(default=False),
) -> list[AlertOut]:
    """A beteg riasztásai magyarázattal (F10, F17): melyik szabályverzió,
    mely mérések alapján, melyik határt lépte át. Csak az orvos látja."""
    ensure_patient_access(db, user, patient_id)
    alerts = list_patient_alerts(db, patient_id, open_only=not include_closed)
    names = user_names(db, alert_user_ids(alerts))
    return [alert_out(alert, explain_alert(db, alert), names) for alert in alerts]


@router.get("/patients/{patient_id}/doctors", responses=FORBIDDEN)
def patient_doctors(patient_id: uuid.UUID, db: DbSession, user: DoctorUser) -> list[UserRefOut]:
    """A beteghez ÉPPEN hozzárendelt orvosok (a riasztás felelős-választójához,
    M3, A6 D2), név szerint. Az id a FELHASZNÁLÓ-azonosító (users.id), mint a
    POST /alerts/{id}/assign doctor_id-je. Csak a beteg hozzárendelt orvosa éri el."""
    ensure_patient_access(db, user, patient_id)
    doctors = db.scalars(
        assigned_doctors_query(patient_id, datetime.now(UTC)).order_by(
            DoctorProfile.name, DoctorProfile.id
        )
    )
    return [UserRefOut(id=d.user_id, name=d.name) for d in doctors]
