"""Spec 5–7, NF1: GET /api/auth/me és a token tulajdonságai."""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from sqlalchemy import text, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token
from app.models import User, UserRole
from tests.independent_fable.helpers import (
    ME_URL,
    bearer,
    forge_token,
    login_token,
    make_admin,
    make_doctor,
    make_patient,
    standard_payload,
    unsigned_token,
)

# --- 5. /me siker ---------------------------------------------------------------


def test_me_patient(client, db: Session):
    account = make_patient(db, name="Kovács Anna")
    response = client.get(ME_URL, headers=bearer(login_token(client, account)))
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"id", "email", "role", "name"}
    assert body == {
        "id": str(account.user.id),
        "email": account.email,
        "role": "patient",
        "name": "Kovács Anna",
    }


def test_me_doctor(client, db: Session):
    account = make_doctor(db, name="Dr. Szabó Péter")
    body = client.get(ME_URL, headers=bearer(login_token(client, account))).json()
    assert body["role"] == "doctor"
    assert body["name"] == "Dr. Szabó Péter"
    assert body["id"] == str(account.user.id)


def test_me_admin_has_null_name(client, db: Session):
    account = make_admin(db)
    body = client.get(ME_URL, headers=bearer(login_token(client, account))).json()
    assert body["role"] == "admin"
    assert body["name"] is None


def test_me_does_not_expose_password_hash(client, db: Session):
    account = make_patient(db)
    response = client.get(ME_URL, headers=bearer(login_token(client, account)))
    assert "password" not in response.text.lower()
    assert "argon2" not in response.text


# --- 5. /me 401-esetek ----------------------------------------------------------


def _assert_unauthorized(response):
    assert response.status_code == 401, response.text
    assert response.headers.get("www-authenticate") == "Bearer"
    assert "access_token" not in response.text


def test_me_without_header(client, db: Session):
    _assert_unauthorized(client.get(ME_URL))


@pytest.mark.parametrize(
    "header",
    [
        "Bearer",
        "Bearer ",
        "bearer-nincs-szokoz",
        "Basic dXNlcjpwYXNz",
        "Token abc.def.ghi",
        "abc.def.ghi",
        "Bearer nem.egy.jwt",
        "Bearer ...",
        "Bearer " + "x" * 300,
    ],
)
def test_me_malformed_authorization_header(client, db: Session, header):
    _assert_unauthorized(client.get(ME_URL, headers={"Authorization": header}))


def test_me_wrong_signature_key(client, db: Session):
    account = make_patient(db)
    token = forge_token(standard_payload(account.user.id), key="masik-kulcs-" + "x" * 40)
    _assert_unauthorized(client.get(ME_URL, headers=bearer(token)))


def test_me_expired_token(client, db: Session):
    account = make_patient(db)
    token = create_access_token(account.user.id, expires_delta=timedelta(seconds=-1))
    _assert_unauthorized(client.get(ME_URL, headers=bearer(token)))


def test_me_token_without_exp(client, db: Session):
    account = make_patient(db)
    token = forge_token({"sub": str(account.user.id), "iat": datetime.now(UTC)})
    _assert_unauthorized(client.get(ME_URL, headers=bearer(token)))


def test_me_token_without_sub(client, db: Session):
    payload = standard_payload(uuid.uuid4())
    del payload["sub"]
    _assert_unauthorized(client.get(ME_URL, headers=bearer(forge_token(payload))))


def test_me_token_sub_not_uuid(client, db: Session):
    payload = standard_payload(uuid.uuid4())
    payload["sub"] = "nem-uuid"
    _assert_unauthorized(client.get(ME_URL, headers=bearer(forge_token(payload))))


def test_me_token_for_nonexistent_user(client, db: Session):
    token = forge_token(standard_payload(uuid.uuid4()))
    _assert_unauthorized(client.get(ME_URL, headers=bearer(token)))


def test_me_token_for_deleted_user(client, db: Session):
    account = make_admin(db)
    token = login_token(client, account)
    db.delete(account.user)
    db.flush()
    _assert_unauthorized(client.get(ME_URL, headers=bearer(token)))


def test_me_alg_none_rejected(client, db: Session):
    account = make_patient(db)
    now = int(datetime.now(UTC).timestamp())
    token = unsigned_token({"sub": str(account.user.id), "iat": now, "exp": now + 3600})
    _assert_unauthorized(client.get(ME_URL, headers=bearer(token)))


def test_me_other_hmac_algorithm_rejected(client, db: Session):
    """Ugyanaz a kulcs, de HS512: a szerver csak HS256-ot fogadhat el."""
    account = make_patient(db)
    token = forge_token(standard_payload(account.user.id), algorithm="HS512")
    _assert_unauthorized(client.get(ME_URL, headers=bearer(token)))


def test_me_tampered_payload_rejected(client, db: Session):
    """Valódi token, de a törzsben a sub egy másik felhasználóra cserélve."""
    victim = make_doctor(db)
    attacker = make_patient(db)
    token = login_token(client, attacker)
    header_b64, _payload_b64, signature_b64 = token.split(".")
    forged = forge_token(standard_payload(victim.user.id))
    _, forged_payload_b64, _ = forged.split(".")
    tampered = f"{header_b64}.{forged_payload_b64}.{signature_b64}"
    _assert_unauthorized(client.get(ME_URL, headers=bearer(tampered)))


def test_me_signature_stripped_rejected(client, db: Session):
    account = make_patient(db)
    header_b64, payload_b64, _ = login_token(client, account).split(".")
    _assert_unauthorized(client.get(ME_URL, headers=bearer(f"{header_b64}.{payload_b64}.")))


# --- 6. a letiltás azonnal hat; szerepkör az adatbázisból ----------------------


def test_disabling_user_invalidates_live_token(client, db: Session):
    account = make_patient(db)
    token = login_token(client, account)
    assert client.get(ME_URL, headers=bearer(token)).status_code == 200
    account.user.is_active = False
    db.flush()
    _assert_unauthorized(client.get(ME_URL, headers=bearer(token)))


def test_disabling_via_sql_from_another_session_invalidates_live_token(client, db: Session):
    """Mintha egy másik folyamat tiltotta volna le: SQL-frissítés, majd a session
    gyorsítótárát eldobjuk (élesben minden kérés friss sessiont kap)."""
    account = make_doctor(db)
    token = login_token(client, account)
    db.execute(update(User).where(User.id == account.user.id).values(is_active=False))
    db.expire_all()
    _assert_unauthorized(client.get(ME_URL, headers=bearer(token)))


def test_reenabling_user_restores_access_with_same_token(client, db: Session):
    account = make_patient(db)
    token = login_token(client, account)
    account.user.is_active = False
    db.flush()
    assert client.get(ME_URL, headers=bearer(token)).status_code == 401
    account.user.is_active = True
    db.flush()
    assert client.get(ME_URL, headers=bearer(token)).status_code == 200


def test_role_change_in_db_is_reflected_with_same_token(client, db: Session):
    account = make_doctor(db)
    token = login_token(client, account)
    assert client.get(ME_URL, headers=bearer(token)).json()["role"] == "doctor"
    account.user.role = UserRole.ADMIN
    db.flush()
    assert client.get(ME_URL, headers=bearer(token)).json()["role"] == "admin"


def test_role_claim_in_token_is_ignored(client, db: Session):
    """Valódi kulccsal aláírt token hamis 'role' igénnyel: a szerepkör az adatbázisból jön."""
    account = make_patient(db)
    payload = standard_payload(account.user.id)
    payload["role"] = "admin"
    response = client.get(ME_URL, headers=bearer(forge_token(payload)))
    assert response.status_code == 200
    assert response.json()["role"] == "patient"


# --- 7. token tartalma ----------------------------------------------------------


def test_token_header_is_hs256(client, db: Session):
    token = login_token(client, make_patient(db))
    header = jwt.get_unverified_header(token)
    assert header["alg"] == "HS256"


def test_token_claims(client, db: Session):
    account = make_patient(db)
    before = int(datetime.now(UTC).timestamp())
    token = login_token(client, account)
    after = int(datetime.now(UTC).timestamp())
    payload = jwt.decode(token, settings.jwt_secret_key, algorithms=["HS256"])
    assert {"sub", "iat", "exp"} <= set(payload)
    assert payload["sub"] == str(account.user.id)
    assert before <= payload["iat"] <= after
    assert payload["exp"] - payload["iat"] == 60 * 60
    assert payload["exp"] - payload["iat"] == settings.access_token_expire_minutes * 60


def test_token_contains_no_role_or_personal_data(client, db: Session):
    account = make_doctor(db, name="Dr. Titkos Név")
    token = login_token(client, account)
    payload = jwt.decode(token, settings.jwt_secret_key, algorithms=["HS256"])
    assert "role" not in payload
    assert "roles" not in payload
    assert "email" not in payload
    assert "name" not in payload
    # A token nyers (base64) szövegében sem szerepelhet a szerepkör, az e-mail vagy a név.
    assert "doctor" not in token
    assert account.email not in token


def test_token_signed_with_configured_key_and_rejected_by_other_key(client, db: Session):
    token = login_token(client, make_patient(db))
    jwt.decode(token, settings.jwt_secret_key, algorithms=["HS256"])  # nem dob
    with pytest.raises(jwt.InvalidSignatureError):
        jwt.decode(token, "nem-ez-a-kulcs-" + "y" * 40, algorithms=["HS256"])


def test_two_logins_give_tokens_for_the_same_user(client, db: Session):
    account = make_patient(db)
    t1 = login_token(client, account)
    t2 = login_token(client, account)
    p1 = jwt.decode(t1, settings.jwt_secret_key, algorithms=["HS256"])
    p2 = jwt.decode(t2, settings.jwt_secret_key, algorithms=["HS256"])
    assert p1["sub"] == p2["sub"] == str(account.user.id)


def test_token_of_one_user_does_not_identify_another(client, db: Session):
    a = make_patient(db)
    b = make_patient(db)
    body = client.get(ME_URL, headers=bearer(login_token(client, a))).json()
    assert body["id"] == str(a.user.id)
    assert body["id"] != str(b.user.id)


def test_jwt_secret_key_is_not_stored_in_database(client, db: Session):
    """Egészségügyi ellenőrzés: a kulcs csak beállítás, nem adat."""
    make_patient(db)
    rows = db.execute(text("select row_to_json(u)::text from users u")).scalars().all()
    for row in rows:
        assert settings.jwt_secret_key not in row
