"""A token felépítése — a 7. jóváhagyott pont közvetlen ellenőrzése."""

from __future__ import annotations

import uuid

import jwt
import pytest

from app.core.config import settings
from app.core.security import JWT_ALGORITHM, create_access_token, decode_access_token


def test_token_is_hs256() -> None:
    user_id = uuid.uuid4()
    token = create_access_token(user_id)

    header = jwt.get_unverified_header(token)

    assert header["alg"] == "HS256"
    assert JWT_ALGORITHM == "HS256"


def test_token_payload_contains_sub_iat_exp_only() -> None:
    user_id = uuid.uuid4()
    token = create_access_token(user_id)

    payload = jwt.decode(token, settings.jwt_secret_key, algorithms=["HS256"])

    assert set(payload.keys()) == {"sub", "iat", "exp"}
    assert payload["sub"] == str(user_id)


def test_token_does_not_contain_role() -> None:
    token = create_access_token(uuid.uuid4())
    payload = jwt.decode(token, settings.jwt_secret_key, algorithms=["HS256"])

    assert "role" not in payload


def test_decode_valid_token_returns_user_id() -> None:
    user_id = uuid.uuid4()
    token = create_access_token(user_id)

    assert decode_access_token(token) == user_id


def test_decode_rejects_wrong_algorithm() -> None:
    """HS512-vel aláírt (de ugyanazzal a kulccsal készült) token ne menjen át."""
    payload = {"sub": str(uuid.uuid4())}
    import datetime as dt

    now = dt.datetime.now(dt.UTC)
    payload["iat"] = now
    payload["exp"] = now + dt.timedelta(minutes=10)
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm="HS512")

    assert decode_access_token(token) is None


def test_decode_rejects_garbage() -> None:
    assert decode_access_token("teljesen.hibas.token") is None
    assert decode_access_token("") is None


@pytest.mark.parametrize("exp_minutes", [60])
def test_default_expiry_is_60_minutes(exp_minutes: int) -> None:
    import datetime as dt

    token = create_access_token(uuid.uuid4())
    payload = jwt.decode(token, settings.jwt_secret_key, algorithms=["HS256"])

    iat = dt.datetime.fromtimestamp(payload["iat"], tz=dt.UTC)
    exp = dt.datetime.fromtimestamp(payload["exp"], tz=dt.UTC)
    delta_minutes = (exp - iat).total_seconds() / 60

    assert abs(delta_minutes - exp_minutes) < 0.1
