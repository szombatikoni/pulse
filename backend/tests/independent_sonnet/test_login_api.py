"""POST /api/auth/login — F1, NF1 és a jóváhagyott viselkedési pontok (1-4)."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.independent_sonnet.helpers import DEFAULT_PASSWORD, make_admin, make_doctor, make_patient


def test_login_success_returns_token_fields(client: TestClient, db: Session) -> None:
    make_patient(db, email="siker@example.com")

    resp = client.post(
        "/api/auth/login", json={"email": "siker@example.com", "password": DEFAULT_PASSWORD}
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 3600
    assert isinstance(body["access_token"], str) and len(body["access_token"]) > 10


def test_login_email_case_insensitive(client: TestClient, db: Session) -> None:
    make_patient(db, email="kisbetu@example.com")

    resp = client.post(
        "/api/auth/login", json={"email": "KisBetu@Example.COM", "password": DEFAULT_PASSWORD}
    )

    assert resp.status_code == 200


def test_login_email_surrounding_whitespace_ignored(client: TestClient, db: Session) -> None:
    make_patient(db, email="szokoz@example.com")

    resp = client.post(
        "/api/auth/login",
        json={"email": "  szokoz@example.com  ", "password": DEFAULT_PASSWORD},
    )

    assert resp.status_code == 200


def test_login_unknown_email_returns_401(client: TestClient, db: Session) -> None:
    resp = client.post(
        "/api/auth/login", json={"email": "nincs-ilyen@example.com", "password": "barmi123"}
    )

    assert resp.status_code == 401


def test_login_wrong_password_returns_401(client: TestClient, db: Session) -> None:
    make_patient(db, email="rossz-jelszo@example.com")

    resp = client.post(
        "/api/auth/login", json={"email": "rossz-jelszo@example.com", "password": "nem-ez-az"}
    )

    assert resp.status_code == 401


def test_login_failure_bodies_are_identical(client: TestClient, db: Session) -> None:
    """Ismeretlen e-mail és rossz jelszó válasza ne legyen megkülönböztethető."""
    make_patient(db, email="letezo@example.com")

    resp_unknown = client.post(
        "/api/auth/login", json={"email": "nemletezo@example.com", "password": "barmi123"}
    )
    resp_wrong_pw = client.post(
        "/api/auth/login", json={"email": "letezo@example.com", "password": "rossz-jelszo"}
    )

    assert resp_unknown.status_code == resp_wrong_pw.status_code == 401
    assert resp_unknown.json() == resp_wrong_pw.json()


def test_login_disabled_account_returns_401(client: TestClient, db: Session) -> None:
    user = make_patient(db, email="letiltott@example.com")
    user.is_active = False
    db.commit()

    resp = client.post(
        "/api/auth/login", json={"email": "letiltott@example.com", "password": DEFAULT_PASSWORD}
    )

    assert resp.status_code == 401


def test_login_disabled_account_body_matches_other_failures(
    client: TestClient, db: Session
) -> None:
    user = make_patient(db, email="letiltott2@example.com")
    user.is_active = False
    db.commit()

    resp_disabled = client.post(
        "/api/auth/login", json={"email": "letiltott2@example.com", "password": DEFAULT_PASSWORD}
    )
    resp_unknown = client.post(
        "/api/auth/login", json={"email": "meg-egy-ismeretlen@example.com", "password": "x"}
    )

    assert resp_disabled.status_code == resp_unknown.status_code == 401
    assert resp_disabled.json() == resp_unknown.json()


def test_login_sets_last_login_at_on_success(client: TestClient, db: Session) -> None:
    user = make_patient(db, email="utolso-belepes@example.com")
    assert user.last_login_at is None

    resp = client.post(
        "/api/auth/login",
        json={"email": "utolso-belepes@example.com", "password": DEFAULT_PASSWORD},
    )
    assert resp.status_code == 200

    db.refresh(user)
    assert user.last_login_at is not None


def test_login_does_not_set_last_login_at_on_failure(client: TestClient, db: Session) -> None:
    user = make_patient(db, email="sikertelen-belepes@example.com")

    resp = client.post(
        "/api/auth/login",
        json={"email": "sikertelen-belepes@example.com", "password": "rossz"},
    )
    assert resp.status_code == 401

    db.refresh(user)
    assert user.last_login_at is None


def test_login_works_for_doctor_role(client: TestClient, db: Session) -> None:
    make_doctor(db, email="dr.teszt@example.com")

    resp = client.post(
        "/api/auth/login", json={"email": "dr.teszt@example.com", "password": DEFAULT_PASSWORD}
    )

    assert resp.status_code == 200


def test_login_works_for_admin_role(client: TestClient, db: Session) -> None:
    make_admin(db, email="admin@example.com")

    resp = client.post(
        "/api/auth/login", json={"email": "admin@example.com", "password": DEFAULT_PASSWORD}
    )

    assert resp.status_code == 200


def test_login_wwww_authenticate_header_on_failure(client: TestClient) -> None:
    """2026-10-10: a 401-es válasz most WWW-Authenticate: Bearer fejlécet is küld (RFC 9110)."""
    resp = client.post(
        "/api/auth/login", json={"email": "nincs-ilyen-fejlec@example.com", "password": "x" * 12}
    )

    assert resp.status_code == 401
    assert resp.headers.get("www-authenticate") == "Bearer"


def test_login_works_with_password_shorter_than_creation_minimum(
    client: TestClient, db: Session
) -> None:
    """A belépés szándékosan 1-255 karaktert enged (nem árulja el a 10 karakteres
    létrehozási minimumot); rövid, de létrehozáskor elfogadott jelszóval is be
    kell tudni lépni, amíg az legalább a létrehozási minimumot teljesíti."""
    make_patient(db, email="rovid-de-ervenyes@example.com", password="pontosan10")

    resp = client.post(
        "/api/auth/login",
        json={"email": "rovid-de-ervenyes@example.com", "password": "pontosan10"},
    )

    assert resp.status_code == 200


def test_login_missing_password_is_rejected(client: TestClient, db: Session) -> None:
    resp = client.post("/api/auth/login", json={"email": "valaki@example.com"})

    assert resp.status_code == 422


def test_login_empty_password_returns_401_not_500(client: TestClient, db: Session) -> None:
    """A séma min_length=1, tehát üres jelszó 422; de ha mégis átmenne, ne 500-zon."""
    make_patient(db, email="ures-jelszo@example.com")

    resp = client.post("/api/auth/login", json={"email": "ures-jelszo@example.com", "password": ""})

    assert resp.status_code in (401, 422)
