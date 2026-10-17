import uuid

from fastapi import APIRouter, Query

from app.api.deps import DoctorUser, ensure_patient_access
from app.core.db import DbSession
from app.models import PatientProfile
from app.schemas.patients import AlertOut, PatientSummaryOut, alert_out, patient_summary_out
from app.schemas.tasks import task_out
from app.services.alerts import explain_alert, latest_trigger, list_patient_alerts
from app.services.status import PatientStatusResult, compute_status, doctor_patient_list
from app.services.tasks import patient_tasks

router = APIRouter(tags=["patients"])

FORBIDDEN = {403: {"description": "A felhasználó nem érheti el a beteg adatait"}}


def _summary(
    db: DbSession, patient: PatientProfile, result: PatientStatusResult
) -> PatientSummaryOut:
    triggers = {r.alert.id: latest_trigger(db, r.alert) for r in result.reasons if r.alert}
    summary = patient_summary_out(patient, result, triggers)
    summary.tasks = [task_out(t) for t in patient_tasks(db, patient.id)]
    return summary


@router.get("/doctor/patients")
def my_patients(db: DbSession, user: DoctorUser) -> list[PatientSummaryOut]:
    """Az orvos priorizált beteglistája (F9): csak az éppen hozzá rendelt
    betegek, státusszal és az okával."""
    rows = doctor_patient_list(db, user.doctor_profile.id)
    return [_summary(db, patient, result) for patient, result in rows]


@router.get("/patients/{patient_id}", responses=FORBIDDEN)
def patient_detail(patient_id: uuid.UUID, db: DbSession, user: DoctorUser) -> PatientSummaryOut:
    """A beteg adatlapjának fejléce az orvosnak: név, születési dátum, státusz
    és okai."""
    ensure_patient_access(db, user, patient_id)
    patient = db.get(PatientProfile, patient_id)
    return _summary(db, patient, compute_status(db, patient_id))


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
    return [alert_out(alert, explain_alert(db, alert)) for alert in alerts]
