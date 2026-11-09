import uuid

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, PatientUser, ensure_patient_access
from app.core.db import DbSession
from app.schemas.measurements import (
    MeasurementCorrection,
    MeasurementCreate,
    MeasurementOut,
    MeasurementTypeOut,
    measurement_out,
    measurement_type_out,
)
from app.services.measurements import (
    MeasurementError,
    correct_measurement,
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


@router.post(
    "/patients/{patient_id}/measurements/{measurement_id}/correction",
    status_code=status.HTTP_201_CREATED,
    responses={
        403: {
            "description": "Csak a beteg javíthat, és csak a saját mérését (nem létező "
            "mérésre is 403)"
        },
        409: {"description": "A mérést már javították (already_corrected): a lánc végét kell"},
        422: {"description": "Érvénytelen érték (a detail.code adja meg az okát)"},
    },
)
def correct(
    patient_id: uuid.UUID,
    measurement_id: uuid.UUID,
    body: MeasurementCorrection,
    db: DbSession,
    user: PatientUser,
) -> MeasurementOut:
    """Mérés javítása (F7; M3, A7): új mérés-sor a javított értékekkel, az
    eredetire hivatkozva; a mérés ideje az eredetié marad, és nincs időkorlát.
    Az érintett riasztások „kiváltó adat javítva" eseményt kapnak (a nyitottak
    felülvizsgálat-jelölést is), a javított érték a szokásos kiértékelésen megy
    át. Csak a lánc vége javítható; a felülírt mérésre 409. Nem létező vagy más
    beteghez tartozó mérésre 403, mint a többi erőforrásnál: a válaszból nem
    derül ki, létezik-e az azonosító."""
    ensure_patient_access(db, user, patient_id)
    try:
        measurement, _alerts = correct_measurement(
            db,
            patient_id=patient_id,
            measurement_id=measurement_id,
            values=body.values,
            actor_id=user.id,
        )
    except MeasurementError as error:
        if error.code == "not_found":
            forbidden = HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
            raise forbidden from error
        code = (
            status.HTTP_409_CONFLICT
            if error.code == "already_corrected"
            else status.HTTP_422_UNPROCESSABLE_CONTENT
        )
        raise HTTPException(
            status_code=code, detail={"code": error.code, "component": error.component}
        ) from error
    db.commit()
    return measurement_out(measurement)
