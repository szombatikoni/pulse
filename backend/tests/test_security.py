import uuid
from datetime import timedelta

import jwt

from app.core.config import settings
from app.core.security import (
    JWT_ALGORITHM,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_hash_is_argon2_and_verifies():
    hashed = hash_password("titok123")
    assert hashed.startswith("$argon2id$")
    assert hashed != "titok123"
    assert verify_password("titok123", hashed)
    assert not verify_password("titok124", hashed)


def test_same_password_gets_different_hashes():
    # A só miatt két azonos jelszó hash-e sem egyezik.
    assert hash_password("titok123") != hash_password("titok123")


def test_token_roundtrip_returns_user_id():
    user_id = uuid.uuid4()
    assert decode_access_token(create_access_token(user_id)) == user_id


def test_expired_token_is_rejected():
    token = create_access_token(uuid.uuid4(), expires_delta=timedelta(seconds=-1))
    assert decode_access_token(token) is None


def test_token_signed_with_other_key_is_rejected():
    forged = jwt.encode(
        {"sub": str(uuid.uuid4()), "exp": 9999999999},
        "attacker-key-attacker-key-attacker-key",
        algorithm=JWT_ALGORITHM,
    )
    assert decode_access_token(forged) is None


def test_garbage_token_is_rejected():
    assert decode_access_token("not-a-token") is None


def test_token_without_expiry_is_rejected():
    # Helyes aláírás, de nincs lejárati idő: egy örökké érvényes tokent nem fogadunk el.
    no_exp = jwt.encode(
        {"sub": str(uuid.uuid4())}, settings.jwt_secret_key, algorithm=JWT_ALGORITHM
    )
    assert decode_access_token(no_exp) is None
