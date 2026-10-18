"""GET /api/auth/me — a jóváhagyott 5-6. pont."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import JWT_ALGORITHM, create_access_token
from tests.independent_sonnet.helpers import make_admin, make_doctor, make_patient


def _login(client: TestClient, email: str, password: str) -> str:
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def test_me_success_for_patient(client: TestClient, db: Session) -> None:
    from tests.independent_sonnet.helpers import DEFAULT_PASSWORD

    user = make_patient(db, email="beteg.me@example.com", name="Kovács Anna")
    token = _login(client, "beteg.me@example.com", DEFAULT_PASSWORD)

    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(user.id)
    assert body["email"] == "beteg.me@example.com"
    assert body["role"] == "patient"
    assert body["name"] == "Kovács Anna"


def test_me_success_for_doctor(client: TestClient, db: Session) -> None:
    from tests.independent_sonnet.helpers import DEFAULT_PASSWORD

    make_doctor(db, email="orvos.me@example.com", name="Dr. Szabó")
    token = _login(client, "orvos.me@example.com", DEFAULT_PASSWORD)

    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    assert resp.json()["name"] == "Dr. Szabó"
    assert resp.json()["role"] == "doctor"


def test_me_admin_has_null_name(client: TestClient, db: Session) -> None:
    from tests.independent_sonnet.helpers import DEFAULT_PASSWORD

    make_admin(db, email="admin.me@example.com")
    token = _login(client, "admin.me@example.com", DEFAULT_PASSWORD)

    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == "admin"
    assert body["name"] is None


def test_me_missing_token_returns_401_with_www_authenticate(client: TestClient) -> None:
    resp = client.get("/api/auth/me")

    assert resp.status_code == 401
    assert resp.headers.get("www-authenticate") == "Bearer"


def test_me_malformed_token_returns_401(client: TestClient) -> None:
    resp = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-real-jwt-token"})

    assert resp.status_code == 401
    assert resp.headers.get("www-authenticate") == "Bearer"


def test_me_wrong_signature_returns_401(client: TestClient, db: Session) -> None:
    user = make_patient(db, email="rossz-alairas@example.com")
    now = datetime.now(UTC)
    payload = {"sub": str(user.id), "iat": now, "exp": now + timedelta(minutes=10)}
    bad_token = jwt.encode(payload, "teljesen-mas-titkos-kulcs", algorithm=JWT_ALGORITHM)

    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {bad_token}"})

    assert resp.status_code == 401


def test_me_expired_token_returns_401(client: TestClient, db: Session) -> None:
    user = make_patient(db, email="lejart@example.com")
    token = create_access_token(user.id, expires_delta=timedelta(minutes=-1))

    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 401


def test_me_token_without_exp_returns_401(client: TestClient, db: Session) -> None:
    user = make_patient(db, email="nincs-lejarat@example.com")
    payload = {"sub": str(user.id), "iat": datetime.now(UTC)}
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=JWT_ALGORITHM)

    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 401


def test_me_token_without_sub_returns_401(client: TestClient) -> None:
    now = datetime.now(UTC)
    payload = {"iat": now, "exp": now + timedelta(minutes=10)}
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=JWT_ALGORITHM)

    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 401


def test_me_token_with_none_algorithm_rejected(client: TestClient, db: Session) -> None:
    user = make_patient(db, email="none-algo@example.com")
    now = datetime.now(UTC)
    payload = {"sub": str(user.id), "iat": now, "exp": now + timedelta(minutes=10)}
    # "alg: none" tokent kézzel állítjuk össze, aláírás nélkül.
    import base64
    import json

    def b64url(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    header = b64url(json.dumps({"alg": "none", "typ": "JWT"}).encode())
    body = b64url(json.dumps(payload, default=str).encode())
    none_token = f"{header}.{body}."

    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {none_token}"})

    assert resp.status_code == 401


def test_me_nonexistent_user_returns_401(client: TestClient) -> None:
    fake_id = uuid.uuid4()
    token = create_access_token(fake_id)

    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 401


def test_me_disabled_user_rejected_even_with_valid_token(client: TestClient, db: Session) -> None:
    """A letiltás azonnal hat: a token önmagában még érvényes lenne."""
    user = make_patient(db, email="kesobb-letiltott@example.com")
    token = create_access_token(user.id)

    user.is_active = False
    db.commit()

    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 401


def test_me_role_change_reflected_immediately(client: TestClient, db: Session) -> None:
    """A szerepkör nincs a tokenben: adatbázis-váltás azonnal látszik /me-ben."""
    from app.models import UserRole

    user = make_patient(db, email="szerepkor-valt@example.com")
    token = create_access_token(user.id)

    user.role = UserRole.ADMIN
    db.commit()

    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"


def test_me_token_missing_bearer_prefix_rejected(client: TestClient, db: Session) -> None:
    user = make_patient(db, email="nincs-bearer@example.com")
    token = create_access_token(user.id)

    resp = client.get("/api/auth/me", headers={"Authorization": token})

    assert resp.status_code == 401
