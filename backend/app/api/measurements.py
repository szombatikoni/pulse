import uuid

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, PatientUser, ensure_patient_access
from app.core.db import DbSession
from app.schemas.measurements import (
    MeasurementCreate,
    MeasurementOut,
    MeasurementTypeOut,
    measurement_out,
    measurement_type_out,
)
from app.services.measurements import (
    MeasurementError,
    list_measurements,
    list_types,
    record_measurement,
)

router = APIRouter(tags=["measurements"])


@router.get("/measurement-types")
def measurement_types(db: DbSession, _user: CurrentUser) -> list[MeasurementTypeOut]:
    """A rögzíthető méréstípusok komponenseikkel, LOINC- és UCUM-kódjukkal."""
    return [measurement_type_out(t) for t in list_types(db)]


@router.get(
    "/patients/{patient_id}/measurements",
    responses={403: {"description": "A felhasználó nem érheti el a beteg adatait"}},
)
def patient_measurements(
    patient_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
    type_code: str | None = Query(
        default=None, alias="type", max_length=50, description="Méréstípus kódja"
    ),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[MeasurementOut]:
    """A beteg mérései, a legújabb elöl. A beteg a sajátjait, az orvos a hozzá
    rendelt betegéit látja (F2)."""
    ensure_patient_access(db, user, patient_id)
    return [measurement_out(m) for m in list_measurements(db, patient_id, type_code, limit)]


@router.post(
    "/patients/{patient_id}/measurements",
    status_code=status.HTTP_201_CREATED,
    responses={
        403: {"description": "Csak a beteg rögzíthet, és csak a saját mérését"},
        422: {"description": "Érvénytelen mérés (a detail.code adja meg az okát)"},
    },
)
def create_measurement(
    patient_id: uuid.UUID, body: MeasurementCreate, db: DbSession, user: PatientUser
) -> MeasurementOut:
    """Mérés rögzítése (F4). A mentéssel egy tranzakcióban lefut a beteg
    szabályainak kiértékelése, és szükség esetén riasztás keletkezik (F19)."""
    ensure_patient_access(db, user, patient_id)
    try:
        measurement, _alerts = record_measurement(
            db,
            patient_id=patient_id,
            type_code=body.type_code,
            values=body.values,
            measured_at=body.measured_at,
        )
    except MeasurementError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": error.code, "component": error.component},
        ) from error
    db.commit()
    return measurement_out(measurement)
