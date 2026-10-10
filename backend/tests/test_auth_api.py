from datetime import timedelta

from app.core.security import create_access_token
from tests.factories import PASSWORD, make_admin, make_doctor, make_patient


def login(client, email, password=PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def test_login_returns_bearer_token(client, db):
    make_doctor(db, email="orvos@test.example")
    response = login(client, "orvos@test.example")
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 60 * 60
    assert body["access_token"]


def test_login_email_is_case_insensitive(client, db):
    make_patient(db, email="Kiss.Anna@Test.Example")
    assert login(client, "  KISS.ANNA@test.example ").status_code == 200


def test_wrong_password_and_unknown_email_get_the_same_answer(client, db):
    make_patient(db, email="beteg@test.example")
    wrong_password = login(client, "beteg@test.example", "rossz-jelszo")
    unknown_email = login(client, "nincs-ilyen@test.example")
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()
    # RFC 9110: a 401-es válaszban kötelező a WWW-Authenticate fejléc.
    assert wrong_password.headers["WWW-Authenticate"] == "Bearer"


def test_inactive_user_cannot_log_in(client, db):
    user = make_patient(db)
    user.is_active = False
    db.flush()
    assert login(client, user.email).status_code == 401


def test_me_requires_token(client):
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_me_returns_current_user_with_profile_name(client, db):
    make_doctor(db, email="orvos@test.example", name="Dr. Teszt Elek")
    token = login(client, "orvos@test.example").json()["access_token"]
    response = client.get("/api/auth/me", headers=auth_header(token))
    assert response.status_code == 200
    assert response.json()["role"] == "doctor"
    assert response.json()["name"] == "Dr. Teszt Elek"


def test_me_for_admin_has_no_name(client, db):
    admin = make_admin(db)
    response = client.get("/api/auth/me", headers=auth_header(create_access_token(admin.id)))
    assert response.status_code == 200
    assert response.json()["role"] == "admin"
    assert response.json()["name"] is None


def test_expired_token_is_rejected_by_api(client, db):
    user = make_patient(db)
    token = create_access_token(user.id, expires_delta=timedelta(seconds=-1))
    assert client.get("/api/auth/me", headers=auth_header(token)).status_code == 401


def test_deactivation_takes_effect_immediately_with_a_valid_token(client, db):
    # A token még érvényes, de a fiókot közben letiltották: azonnal 401.
    user = make_patient(db)
    token = create_access_token(user.id)
    assert client.get("/api/auth/me", headers=auth_header(token)).status_code == 200
    user.is_active = False
    db.flush()
    assert client.get("/api/auth/me", headers=auth_header(token)).status_code == 401


def test_successful_login_records_last_login_time(client, db):
    user = make_patient(db)
    assert user.last_login_at is None
    assert login(client, user.email).status_code == 200
    db.refresh(user)
    assert user.last_login_at is not None


def test_failed_login_does_not_record_last_login_time(client, db):
    user = make_patient(db)
    assert login(client, user.email, "rossz-jelszo").status_code == 401
    db.refresh(user)
    assert user.last_login_at is None
