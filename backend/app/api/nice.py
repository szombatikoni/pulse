"""A NICE NG136 szerinti otthoni vérnyomásátlag kiértékelése gombnyomásra
(M3, K2, (A) mélység): a CQL-szolgáltatás és a PULSE saját számítása
ugyanazon az időszakon, egyezés-jelöléssel.

Csak a beteghez éppen hozzárendelt orvos hívhatja (D8a); a beteg, az admin, a
másik orvos és a megszűnt összerendelés 403, mint a többi betegadat-végpontnál.
Semmit nem tárol, riasztást nem nyit, státuszt nem változtat. Ha a
szolgáltatás nem érhető el, nem válaszol időben vagy nem értelmezhető választ
ad: 503, detail.code = cql_unavailable (D7a, újrapróbálás nélkül)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import DoctorUser, ensure_patient_access
from app.core.db import DbSession
from app.schemas.nice import NiceEvaluationOut, evaluation_out
from app.services import cql_client
from app.services.cql_client import CqlServiceError
from app.services.nice import CqlEvaluate, evaluate_patient

router = APIRouter(tags=["nice"])


def get_cql_evaluate() -> CqlEvaluate:
    """A szolgáltatás hívója; a tesztek ezt cserélik ki (dependency_overrides)."""
    return cql_client.evaluate


@router.post(
    "/patients/{patient_id}/nice-evaluation",
    responses={
        403: {"description": "Csak a beteg hozzárendelt orvosa"},
        503: {"description": "A CQL-szolgáltatás nem érhető el (cql_unavailable)"},
    },
)
def nice_evaluation(
    patient_id: uuid.UUID,
    db: DbSession,
    user: DoctorUser,
    cql_evaluate: Annotated[CqlEvaluate, Depends(get_cql_evaluate)],
) -> NiceEvaluationOut:
    """Az utolsó 7 helyi nap (a mai nappal együtt) otthoni vérnyomásátlaga a
    NICE NG136 szerint: az első nap kizárva, legalább 3 figyelembe vett nap
    kell, a célérték az életkor szerint. A válaszban az alkalmazott időszak és
    paraméterek, a CQL-motor és a saját számítás eredménye, az egyezés és az
    eltérő mezők, a könyvtár és a motor verziója."""
    ensure_patient_access(db, user, patient_id)
    try:
        evaluation = evaluate_patient(db, patient_id, cql_evaluate)
    except CqlServiceError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"code": "cql_unavailable"}
        ) from error
    return evaluation_out(patient_id, evaluation)
