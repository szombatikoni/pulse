import uuid
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.api.deps import CurrentUser, ensure_patient_access
from app.core.db import DbSession
from app.services.fhir import patient_bundle

router = APIRouter(tags=["fhir"])

FHIR_JSON = "application/fhir+json"


class FhirJSONResponse(JSONResponse):
    media_type = FHIR_JSON


@router.get(
    "/patients/{patient_id}/fhir",
    response_class=FhirJSONResponse,
    responses={
        200: {"description": "FHIR R4 Bundle (collection)", "content": {FHIR_JSON: {}}},
        403: {"description": "A felhasználó nem érheti el a beteg adatait"},
    },
)
def patient_fhir_bundle(patient_id: uuid.UUID, db: DbSession, user: CurrentUser) -> Any:
    """A beteg adatai FHIR R4 csomagként (NF9): mérések Observation-ként (LOINC,
    UCUM, helyi időeltolás), kérdőívverziók és kitöltések. A beteg a sajátját,
    az orvos a hozzá rendelt betegéét kérheti le; az admin nem (egészségügyi
    adat, F2). Csak olvas."""
    ensure_patient_access(db, user, patient_id)
    return FhirJSONResponse(patient_bundle(db, patient_id))
