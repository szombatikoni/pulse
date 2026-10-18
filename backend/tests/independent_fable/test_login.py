"""F1, NF1, spec 1–4: POST /api/auth/login."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH
from app.models import User
from tests.independent_fable.helpers import (
    DEFAULT_PASSWORD,
    LOGIN_URL,
    login,
    make_admin,
    make_doctor,
    make_patient,
)

# --- 1. sikeres belépés ---------------------------------------------------------


def test_login_success_response_shape(client, db: Session):
    account = make_patient(db)
    response = login(client, account.email, account.password)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"access_token", "token_type", "expires_in"}
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 3600
    assert body["expires_in"] == settings.access_token_expire_minutes * 60
    # A token valódi, a beállítás szerinti kulccsal ellenőrizhető JWT.
    payload = jwt.decode(body["access_token"], settings.jwt_secret_key, algorithms=["HS256"])
    assert payload["sub"] == str(account.user.id)


@pytest.mark.parametrize("role_factory", [make_patient, make_doctor, make_admin])
def test_login_works_for_all_three_roles(client, db: Session, role_factory):
    account = role_factory(db)
    assert login(client, account.email, account.password).status_code == 200


def test_login_email_is_case_insensitive(client, db: Session):
    account = make_patient(db, email="Kiss.Anna@Pulse-Teszt.hu")
    assert account.email == "kiss.anna@pulse-teszt.hu"
    assert login(client, "KISS.ANNA@PULSE-TESZT.HU", account.password).status_code == 200
    assert login(client, "kiss.anna@pulse-teszt.hu", account.password).status_code == 200


def test_login_email_surrounding_whitespace_ignored(client, db: Session):
    account = make_doctor(db, email="dr.nagy@pulse-teszt.hu")
    assert login(client, "   dr.nagy@pulse-teszt.hu \t\n", account.password).status_code == 200


def test_login_password_is_case_sensitive_and_not_trimmed(client, db: Session):
    account = make_patient(db, password="Jelszo-Abc-1")
    assert login(client, account.email, "jelszo-abc-1").status_code == 401
    assert login(client, account.email, " Jelszo-Abc-1").status_code == 401
    assert login(client, account.email, "Jelszo-Abc-1 ").status_code == 401


def test_login_response_does_not_leak_sensitive_data(client, db: Session):
    account = make_patient(db)
    response = login(client, account.email, account.password)
    text = response.text
    assert account.password not in text
    assert account.user.password_hash not in text


# --- 2. sikertelen belépés: egységes válasz ------------------------------------


def _failure_signature(response) -> tuple:
    headers = {k.lower(): v for k, v in response.headers.items() if k.lower() != "date"}
    return response.status_code, response.json(), headers


def test_failed_login_responses_are_indistinguishable(client, db: Session):
    """Ismeretlen e-mail, rossz jelszó és letiltott fiók (jó és rossz jelszóval is):
    ugyanaz a státusz, törzs és fejlécek."""
    existing = make_patient(db)
    disabled = make_doctor(db, active=False)

    unknown = login(client, "senki@pulse-teszt.hu", DEFAULT_PASSWORD)
    wrong_pw = login(client, existing.email, "rossz-jelszo")
    disabled_ok_pw = login(client, disabled.email, disabled.password)
    disabled_bad_pw = login(client, disabled.email, "rossz-jelszo")

    signatures = {
        "ismeretlen": _failure_signature(unknown),
        "rossz_jelszo": _failure_signature(wrong_pw),
        "letiltott_jo_jelszo": _failure_signature(disabled_ok_pw),
        "letiltott_rossz_jelszo": _failure_signature(disabled_bad_pw),
    }
    for name, sig in signatures.items():
        assert sig[0] == 401, name
    assert len(set(map(repr, signatures.values()))) == 1, signatures


def test_failed_login_body_does_not_name_the_cause(client, db: Session):
    existing = make_patient(db)
    for response in (
        login(client, "senki@pulse-teszt.hu", DEFAULT_PASSWORD),
        login(client, existing.email, "rossz-jelszo"),
    ):
        text = response.text.lower()
        for word in ("not found", "unknown", "disabled", "inactive", "letilt", "nem létez"):
            assert word not in text, f"árulkodó szó a válaszban: {word!r}"


def test_disabled_account_cannot_login_even_with_correct_password(client, db: Session):
    account = make_patient(db, active=False)
    assert login(client, account.email, account.password).status_code == 401


def test_login_with_other_users_password_fails(client, db: Session):
    a = make_patient(db, password="Jelszo-A-111")
    b = make_patient(db, password="Jelszo-B-222")
    assert login(client, a.email, b.password).status_code == 401
    assert login(client, b.email, a.password).status_code == 401


def test_login_with_password_hash_as_password_fails(client, db: Session):
    """A tárolt hash nem használható jelszóként (pass-the-hash)."""
    account = make_patient(db)
    assert login(client, account.email, account.user.password_hash).status_code == 401


@pytest.mark.parametrize(
    "body",
    [
        {"email": "valaki@pulse-teszt.hu"},
        {"password": DEFAULT_PASSWORD},
        {},
        {"email": "valaki@pulse-teszt.hu", "password": ""},
        {"email": "", "password": DEFAULT_PASSWORD},
        {"email": None, "password": DEFAULT_PASSWORD},
        {"email": "valaki@pulse-teszt.hu", "password": None},
    ],
)
def test_login_malformed_body_is_rejected(client, db: Session, body):
    response = client.post(LOGIN_URL, json=body)
    assert response.status_code in (400, 401, 422)
    assert "access_token" not in response.text


def test_login_requires_json_body_not_form(client, db: Session):
    account = make_patient(db)
    response = client.post(LOGIN_URL, data={"email": account.email, "password": account.password})
    assert response.status_code != 200
    assert "access_token" not in response.text


def test_login_empty_password_against_real_account_is_not_200(client, db: Session):
    account = make_patient(db)
    response = login(client, account.email, "")
    assert response.status_code in (401, 422)


# --- 4. last_login_at -----------------------------------------------------------


def test_successful_login_sets_last_login_at(client, db: Session):
    account = make_patient(db)
    assert account.user.last_login_at is None
    before = datetime.now(UTC)
    assert login(client, account.email, account.password).status_code == 200
    db.refresh(account.user)
    assert account.user.last_login_at is not None
    assert account.user.last_login_at.tzinfo is not None
    assert (
        before - timedelta(seconds=5)
        <= account.user.last_login_at
        <= datetime.now(UTC) + timedelta(seconds=5)
    )


def test_failed_login_does_not_set_last_login_at(client, db: Session):
    account = make_patient(db)
    assert login(client, account.email, "rossz-jelszo").status_code == 401
    db.refresh(account.user)
    assert account.user.last_login_at is None


def test_failed_login_does_not_overwrite_previous_last_login_at(client, db: Session):
    account = make_patient(db)
    assert login(client, account.email, account.password).status_code == 200
    db.refresh(account.user)
    first = account.user.last_login_at
    assert first is not None
    assert login(client, account.email, "rossz-jelszo").status_code == 401
    db.refresh(account.user)
    assert account.user.last_login_at == first


def test_disabled_account_login_attempt_does_not_set_last_login_at(client, db: Session):
    account = make_patient(db, active=False)
    assert login(client, account.email, account.password).status_code == 401
    db.refresh(account.user)
    assert account.user.last_login_at is None


def test_second_login_moves_last_login_at_forward(client, db: Session):
    account = make_patient(db)
    assert login(client, account.email, account.password).status_code == 200
    db.refresh(account.user)
    first = account.user.last_login_at
    assert login(client, account.email, account.password).status_code == 200
    db.refresh(account.user)
    assert account.user.last_login_at >= first


# --- a létrehozás és a belépés szabályainak összhangja ---------------------------
# [MÓDOSÍTVA 2026-10-10] Új spec: a létrehozás 10–255 karaktert enged (ValueError
# különben), a belépés szándékosan 1–255-öt, hogy a szabályt ne árulja el.


@pytest.mark.parametrize("length", [PASSWORD_MIN_LENGTH, PASSWORD_MAX_LENGTH, 128])
def test_password_within_creation_rule_can_login(client, db: Session, length):
    """Ami létrehozható, azzal be is lehet lépni (határértékek: 10 és 255)."""
    password = ("Pw-" + "x" * length)[:length]
    assert len(password) == length
    account = make_patient(db, password=password)
    response = login(client, account.email, password)
    assert response.status_code == 200, (length, response.status_code, response.text)


@pytest.mark.parametrize("length", [0, 1, PASSWORD_MIN_LENGTH - 1, PASSWORD_MAX_LENGTH + 1, 1000])
def test_password_outside_creation_rule_is_rejected_at_creation(client, db: Session, length):
    """9 vagy 256 karakteres (és üres) jelszóval a fiók nem jön létre."""
    email = "hossz-" + str(length) + "@pulse-teszt.hu"
    with pytest.raises(ValueError):
        make_patient(db, email=email, password="x" * length)
    # Nem maradt félkész felhasználó, és belépni sem lehet vele.
    assert db.scalar(select(User).where(User.email == email)) is None
    assert login(client, email, "x" * length).status_code != 200


def test_constants_match_spec(client, db: Session):
    assert PASSWORD_MIN_LENGTH == 10
    assert PASSWORD_MAX_LENGTH == 255


def test_login_does_not_reveal_password_rule(client, db: Session):
    """1–9 karakteres jelszó belépéskor a szokásos 401, nem séma-hiba (422): a
    válaszból nem derül ki a létrehozási minimum."""
    account = make_patient(db)
    for short in ("x", "x" * 9):
        response = login(client, account.email, short)
        assert response.status_code == 401, (short, response.status_code)
        assert response.json() == login(client, "senki@pulse-teszt.hu", short).json()


# --- a belépés 401-es válaszának fejléce (spec 4. változás) ------------------------


def test_failed_login_sends_www_authenticate_bearer(client, db: Session):
    """[ÚJ 2026-10-10] RFC 9110: a 401-hez WWW-Authenticate fejléc jár a loginon is."""
    existing = make_patient(db)
    for response in (
        login(client, "senki@pulse-teszt.hu", DEFAULT_PASSWORD),
        login(client, existing.email, "rossz-jelszo-99"),
        login(client, make_doctor(db, active=False).email, DEFAULT_PASSWORD),
    ):
        assert response.status_code == 401
        assert response.headers.get("www-authenticate") == "Bearer"
