"""require_roles — a 12. jóváhagyott pont, és F2 a végponti rétegben.

Mivel betegadatot adó végpont még nincs, egy saját, külön routeren definiált
mini-végponttal teszteljük a függőség-gyárat; az alkalmazás route-jait nem
módosítjuk.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.main import app
from app.models import UserRole
from tests.independent_sonnet.helpers import DEFAULT_PASSWORD, make_admin, make_doctor, make_patient

_router = APIRouter()
_doctor_or_admin = require_roles(UserRole.DOCTOR, UserRole.ADMIN)


@_router.get("/__test-only/doctor-or-admin")
def _doctor_or_admin_endpoint(user=Depends(_doctor_or_admin)) -> dict:  # noqa: B008
    return {"id": str(user.id)}


app.include_router(_router)


def _login(client: TestClient, email: str, password: str = DEFAULT_PASSWORD) -> str:
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def test_allowed_role_gets_200(client: TestClient, db: Session) -> None:
    make_doctor(db, email="szerepkor-orvos@example.com")
    token = _login(client, "szerepkor-orvos@example.com")

    resp = client.get("/__test-only/doctor-or-admin", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200


def test_disallowed_role_gets_403(client: TestClient, db: Session) -> None:
    make_patient(db, email="szerepkor-beteg@example.com")
    token = _login(client, "szerepkor-beteg@example.com")

    resp = client.get("/__test-only/doctor-or-admin", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 403


def test_second_allowed_role_also_gets_200(client: TestClient, db: Session) -> None:
    make_admin(db, email="szerepkor-admin@example.com")
    token = _login(client, "szerepkor-admin@example.com")

    resp = client.get("/__test-only/doctor-or-admin", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200


def test_unauthenticated_request_gets_401_not_403(client: TestClient) -> None:
    """A szerepkör-ellenőrzés előtt a hitelesítésnek kell lefutnia."""
    resp = client.get("/__test-only/doctor-or-admin")

    assert resp.status_code == 401
