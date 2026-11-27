"""A 422-es válasz nem küldi vissza a beküldött értéket (app/main.py): a hibás
belépési vagy felhasználó-létrehozási kérés jelszava a válaszban sehol nem
jelenhet meg, a hibák helye (loc) és oka (msg) viszont megmarad."""

import pytest

from app.core.security import PASSWORD_MAX_LENGTH, create_access_token
from tests.factories import make_admin

SECRET = "Titkos-Jelszo-7f3a91"


def auth(user):
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def assert_no_secret(response):
    assert response.status_code == 422
    assert SECRET not in response.text
    detail = response.json()["detail"]
    assert detail
    for error in detail:
        assert "input" not in error
        assert error["loc"] and error["msg"]


LOGIN_BODIES = [
    # Rossz típusú e-mail: a hiba a mellette álló jelszót nem hozhatja vissza.
    {"email": 12345, "password": SECRET},
    # Hiányzó e-mail: a FastAPI az inputban a teljes törzset küldené vissza.
    {"password": SECRET},
    # Túl hosszú jelszó (string_too_long).
    {"email": "beteg@test.example", "password": SECRET * 20},
    # Rossz típusú jelszó.
    {"email": "beteg@test.example", "password": [SECRET]},
    # A törzs nem objektum, hanem lista.
    [{"email": "beteg@test.example", "password": SECRET}],
    # A törzs egy szöveg.
    SECRET,
]


@pytest.mark.parametrize("body", LOGIN_BODIES)
def test_invalid_login_does_not_echo_the_password(client, body):
    assert len(SECRET * 20) > PASSWORD_MAX_LENGTH
    assert_no_secret(client.post("/api/auth/login", json=body))


def test_malformed_json_login_does_not_echo_the_password(client):
    # Hibás JSON (json_invalid): a ctx csak a dekóder üzenetét adja.
    response = client.post(
        "/api/auth/login",
        content='{"email": "beteg@test.example", "password": "' + SECRET + '",',
        headers={"Content-Type": "application/json"},
    )
    assert_no_secret(response)


@pytest.mark.parametrize(
    "body",
    [
        {"password": SECRET, "role": "patient", "name": "Új Beteg"},
        {"email": "uj@test.example", "password": SECRET, "role": "nincs-ilyen"},
        {"email": "uj@test.example", "password": SECRET * 100, "role": "patient"},
        {"email": "uj@test.example", "password": {"x": SECRET}, "role": "patient"},
    ],
)
def test_invalid_user_creation_does_not_echo_the_password(client, db, body):
    admin = make_admin(db)
    assert_no_secret(client.post("/api/admin/users", json=body, headers=auth(admin)))


def test_non_secret_validation_error_still_names_the_field(client):
    response = client.post("/api/auth/login", json={"email": "x", "password": "jelszo"})
    assert response.status_code == 422
    (error,) = response.json()["detail"]
    assert error["loc"] == ["body", "email"]
    assert error["type"] == "string_too_short"
    assert error["msg"]
    assert error["ctx"] == {"min_length": 3}
