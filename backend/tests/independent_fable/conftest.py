"""Saját fixture-ök a független tesztkészlethez.

A `db` és `client` fixture a tests/conftest.py-ból jön (infrastruktúra). Itt egy
KÜLÖN mini FastAPI-alkalmazás készül, amely az app.api.deps függőségeit
(CurrentUser, require_roles) és az app.services.access.can_access_patient
függvényt egy-egy próbavégponton keresztül teszi HTTP-n tesztelhetővé.
Az éles alkalmazást (app.main.app) nem módosítja."""

import uuid
from collections.abc import Iterator
from typing import Annotated

import pytest
from fastapi import APIRouter, Depends, FastAPI, HTTPException, status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, require_roles
from app.core.db import DbSession, get_db
from app.models import User, UserRole
from app.services.access import can_access_patient


def _build_probe_app() -> FastAPI:
    probe = FastAPI()
    router = APIRouter()

    def _whoami(user: User) -> dict[str, str]:
        return {"id": str(user.id), "role": user.role.value}

    @router.get("/doctor-only")
    def doctor_only(user: Annotated[User, Depends(require_roles(UserRole.DOCTOR))]):
        return _whoami(user)

    @router.get("/admin-only")
    def admin_only(user: Annotated[User, Depends(require_roles(UserRole.ADMIN))]):
        return _whoami(user)

    @router.get("/patient-or-doctor")
    def patient_or_doctor(
        user: Annotated[User, Depends(require_roles(UserRole.PATIENT, UserRole.DOCTOR))],
    ):
        return _whoami(user)

    @router.get("/no-role-allowed")
    def no_role_allowed(user: Annotated[User, Depends(require_roles())]):
        return _whoami(user)

    @router.get("/patients/{patient_id}/data")
    def patient_data(patient_id: uuid.UUID, user: CurrentUser, db: DbSession):
        """Betegadat-végpont mintája: a hozzáférést a szolgáltatásréteg dönti el."""
        if not can_access_patient(db, user, patient_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        return {"patient_id": str(patient_id), "viewer": str(user.id)}

    probe.include_router(router)
    return probe


@pytest.fixture
def probe(db: Session) -> Iterator[TestClient]:
    """Kliens a próbavégpontokhoz; ugyanazt a (visszagörgetett) sessiont kapja,
    mint a teszt és az éles `client`, így a tokenek és adatok közösek."""
    probe_app = _build_probe_app()
    probe_app.dependency_overrides[get_db] = lambda: db
    with TestClient(probe_app) as test_client:
        yield test_client
    probe_app.dependency_overrides.clear()
