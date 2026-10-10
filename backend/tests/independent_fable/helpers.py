"""Független segédfüggvények a bejelentkezés- és jogosultság-tesztekhez.

Szándékosan NEM használja a tests/factories.py-t: a felhasználókat közvetlenül
a szolgáltatásrétegen (create_user) keresztül hozza létre, a tokeneket pedig a
PyJWT-vel kézzel is elő tudja állítani (támadó-tesztekhez)."""

import base64
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

import jwt
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import DoctorPatient, User, UserRole
from app.services.users import create_user

LOGIN_URL = "/api/auth/login"
ME_URL = "/api/auth/me"

DEFAULT_PASSWORD = "Nagyon-titkos-jelszo-42"


@dataclass
class Account:
    user: User
    password: str

    @property
    def email(self) -> str:
        return self.user.email


def unique_email(prefix: str = "user") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}@pulse-teszt.hu"


def make_patient(
    db: Session,
    *,
    email: str | None = None,
    password: str = DEFAULT_PASSWORD,
    name: str = "Teszt Beteg",
    birth_date: date = date(1970, 5, 17),
    active: bool = True,
) -> Account:
    user = create_user(
        db,
        email=email or unique_email("beteg"),
        password=password,
        role=UserRole.PATIENT,
        name=name,
        birth_date=birth_date,
    )
    if not active:
        user.is_active = False
        db.flush()
    return Account(user=user, password=password)


def make_doctor(
    db: Session,
    *,
    email: str | None = None,
    password: str = DEFAULT_PASSWORD,
    name: str = "Dr. Teszt Orvos",
    active: bool = True,
) -> Account:
    user = create_user(
        db,
        email=email or unique_email("orvos"),
        password=password,
        role=UserRole.DOCTOR,
        name=name,
    )
    if not active:
        user.is_active = False
        db.flush()
    return Account(user=user, password=password)


def make_admin(
    db: Session,
    *,
    email: str | None = None,
    password: str = DEFAULT_PASSWORD,
    active: bool = True,
) -> Account:
    user = create_user(
        db, email=email or unique_email("admin"), password=password, role=UserRole.ADMIN
    )
    if not active:
        user.is_active = False
        db.flush()
    return Account(user=user, password=password)


def assign(
    db: Session,
    doctor: Account,
    patient: Account,
    *,
    valid_from: datetime | None = None,
    valid_to: datetime | None = None,
) -> DoctorPatient:
    """Orvos–beteg összerendelés; valid_from alapból 'most' (explicit, hogy ne
    a tranzakció-kezdeti now()-tól függjön)."""
    assert doctor.user.doctor_profile is not None
    assert patient.user.patient_profile is not None
    link = DoctorPatient(
        doctor_id=doctor.user.doctor_profile.id,
        patient_id=patient.user.patient_profile.id,
        valid_from=valid_from or datetime.now(UTC),
        valid_to=valid_to,
    )
    db.add(link)
    db.flush()
    return link


def login(client: TestClient, email: str, password: str):
    return client.post(LOGIN_URL, json={"email": email, "password": password})


def login_token(client: TestClient, account: Account) -> str:
    response = login(client, account.email, account.password)
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def forge_token(
    payload: dict[str, Any],
    *,
    key: str | None = None,
    algorithm: str = "HS256",
    headers: dict[str, Any] | None = None,
) -> str:
    """Tetszőleges tartalmú token; alapból a valódi kulccsal és HS256-tal aláírva."""
    return jwt.encode(
        payload,
        key if key is not None else settings.jwt_secret_key,
        algorithm=algorithm,
        headers=headers,
    )


def unsigned_token(payload: dict[str, Any]) -> str:
    """'alg: none' token kézzel összerakva (üres aláírással), hogy a könyvtár
    saját védelme ne akadályozza a támadó-teszt előállítását."""
    header = {"alg": "none", "typ": "JWT"}
    return (
        _b64url(json.dumps(header, separators=(",", ":")).encode())
        + "."
        + _b64url(json.dumps(payload, separators=(",", ":")).encode())
        + "."
    )


def standard_payload(user_id: uuid.UUID, minutes: int = 60) -> dict[str, Any]:
    now = datetime.now(UTC)
    return {"sub": str(user_id), "iat": now, "exp": now + timedelta(minutes=minutes)}
