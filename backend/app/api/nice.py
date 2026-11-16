"""A NICE NG136 szerinti otthoni vérnyomásátlag kiértékelése gombnyomásra
(M3, K2, (A) mélység): a CQL-szolgáltatás és a PULSE saját számítása
ugyanazon az időszakon, egyezés-jelöléssel.

Csak a beteghez éppen hozzárendelt orvos hívhatja (D8a); a beteg, az admin, a
másik orvos és a megszűnt összerendelés 403, mint a többi betegadat-végpontnál.
Semmit nem tárol, riasztást nem nyit, státuszt nem változtat. Ha a
szolgáltatás nem érhető el, nem válaszol időben vagy nem értelmezhető választ
ad: 503, detail.code = cql_unavailable (D7a, újrapróbálás nélkül); az ok
(CqlServiceError.reason) betegadat nélkül a naplóba kerül.

A tranzakció a beolvasás után, a HTTP-hívás előtt lezárul (commit; a kérés csak
olvas), így a lassú szolgáltatás alatt nincs nyitott adatbázis-tranzakció."""

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import DoctorUser, ensure_patient_access
from app.core.db import DbSession
from app.schemas.nice import NiceEvaluationOut, evaluation_out
from app.services import cql_client
from app.services.cql_client import CqlServiceError
from app.services.nice import CqlEvaluate, finish_evaluation, prepare_evaluation

router = APIRouter(tags=["nice"])
log = logging.getLogger("pulse.nice")


def get_cql_evaluate() -> CqlEvaluate:
    """A szolgáltatás hívója; a tesztek ezt cserélik ki (dependency_overrides)."""
    return cql_client.evaluate


def get_clock() -> Callable[[], datetime]:
    """Az óra; a tesztek rögzített időponttal cserélik ki, hogy az ablak ne
    függjön attól, mikor fut a teszt (éjfél körül sem)."""
    return lambda: datetime.now(UTC)


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
    clock: Annotated[Callable[[], datetime], Depends(get_clock)],
) -> NiceEvaluationOut:
    """Az utolsó 7 lezárt helyi nap (a mai nélkül, [ma-7, ma)) otthoni
    vérnyomásátlaga a NICE NG136 szerint: az első nap kizárva, legalább 3
    figyelembe vett nap kell, a célérték az életkor szerint (az utolsó lezárt
    napon). A válaszban az alkalmazott időszak és paraméterek, a CQL-motor és a
    saját számítás eredménye, az egyezés és az eltérő mezők, a könyvtár és a
    motor verziója."""
    ensure_patient_access(db, user, patient_id)
    prepared = prepare_evaluation(db, patient_id, now=clock())
    db.commit()  # csak olvastunk: a tranzakció ne maradjon nyitva a hívás alatt
    try:
        evaluation = finish_evaluation(prepared, cql_evaluate(prepared.request))
    except CqlServiceError as error:
        # Csak a gépi ok: se a beteg azonosítója, se neve, se mérési érték.
        log.warning("A CQL-szolgáltatás nem adott használható választ: %s", error.reason)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"code": "cql_unavailable"}
        ) from error
    return evaluation_out(patient_id, evaluation)
