"""Az admin-felület végpontjai (M3, A1; F2, F3, F20): felhasználók,
összerendelések, a méréstípusok rögzíthető tartománya. A terv:
docs/files/tervezet/a1_terv_2026-11-16.md, 6. rész."""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.core.security import create_access_token
from app.models import (
    Alert,
    DoctorPatient,
    Measurement,
    MeasurementComponent,
    RuleVersion,
    User,
    UserRole,
)
from app.models.user import UserDisabledPeriod
from app.services import admin
from app.services.admin import AdminError
from tests.factories import (
    PASSWORD,
    assign,
    make_admin,
    make_doctor,
    make_measurement_types,
    make_patient,
    make_threshold_rule,
)

USER_FIELDS = {
    "id",
    "email",
    "role",
    "name",
    "profile_id",
    "is_active",
    "created_at",
    "last_login_at",
}
ASSIGNMENT_FIELDS = {
    "id",
    "doctor_id",
    "doctor_name",
    "patient_id",
    "patient_name",
    "valid_from",
    "valid_to",
}


def auth(user):
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def login(client, email, password=PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


@pytest.fixture
def s(db):
    make_measurement_types(db)
    doctor = make_doctor(db)
    patient = make_patient(db)
    return {
        "doctor": doctor,
        "patient": patient,
        "admin": make_admin(db),
        "pid": patient.patient_profile.id,
        "did": doctor.doctor_profile.id,
    }


def snapshot(db):
    """Az admin-végpontok által írható állapot (a tiltott hívás után változatlan)."""
    db.expire_all()
    return (
        sorted((u.email, u.is_active, u.password_hash, u.role) for u in db.scalars(select(User))),
        sorted(
            (str(p.user_id), p.disabled_at, p.enabled_at)
            for p in db.scalars(select(UserDisabledPeriod))
        ),
        sorted(
            (str(link.id), link.valid_from, link.valid_to)
            for link in db.scalars(select(DoctorPatient))
        ),
        sorted(
            (c.code, c.min_value, c.max_value) for c in db.scalars(select(MeasurementComponent))
        ),
    )


def calls(s):
    """Minden admin-végpont egy érvényes kéréssel."""
    new_user = {
        "email": "uj@test.example",
        "password": "hosszu-jelszo-1",
        "role": "doctor",
        "name": "Dr. Új",
    }
    ranges = {"components": [{"code": "value", "min_value": 30, "max_value": 220}]}
    return [
        ("get", "/api/admin/users", None),
        ("post", "/api/admin/users", new_user),
        ("patch", f"/api/admin/users/{s['patient'].id}", {"name": "Új Név"}),
        ("post", f"/api/admin/users/{s['patient'].id}/disable", None),
        ("post", f"/api/admin/users/{s['patient'].id}/enable", None),
        ("get", "/api/admin/assignments", None),
        (
            "post",
            "/api/admin/assignments",
            {"doctor_id": str(s["did"]), "patient_id": str(s["pid"])},
        ),
        ("post", f"/api/admin/assignments/{uuid.uuid4()}/end", None),
        ("put", "/api/admin/measurement-types/heart_rate/ranges", ranges),
    ]


@pytest.mark.parametrize("role", ["patient", "doctor"])
def test_only_the_admin_reaches_the_admin_endpoints(client, db, s, role):
    before = snapshot(db)
    for method, url, body in calls(s):
        response = client.request(method, url, json=body, headers=auth(s[role]))
        assert response.status_code == 403, (method, url)
    assert snapshot(db) == before


def test_admin_endpoints_require_login(client, db, s):
    before = snapshot(db)
    for method, url, body in calls(s):
        assert client.request(method, url, json=body).status_code == 401, (method, url)
    assert snapshot(db) == before


# --- Felhasználók -----------------------------------------------------------------


def test_user_list_has_only_identifying_data(client, db, s):
    response = client.get("/api/admin/users", headers=auth(s["admin"]))
    assert response.status_code == 200
    rows = response.json()
    # Admin, orvos, beteg sorrendben; a mezők listája rögzített: betegadat
    # (születési dátum, státusz, mérés) nincs benne.
    assert [r["role"] for r in rows] == ["admin", "doctor", "patient"]
    assert all(set(r) == USER_FIELDS for r in rows)
    by_role = {r["role"]: r for r in rows}
    assert by_role["admin"]["name"] is None and by_role["admin"]["profile_id"] is None
    assert by_role["doctor"]["profile_id"] == str(s["did"])
    assert by_role["patient"]["profile_id"] == str(s["pid"])
    assert by_role["patient"]["name"] == "Teszt Beteg"
    assert by_role["patient"]["last_login_at"] is None


@pytest.mark.parametrize(
    ("body", "role"),
    [
        ({"role": "patient", "name": " Új Beteg ", "birth_date": "1955-03-04"}, "patient"),
        ({"role": "doctor", "name": "Dr. Új"}, "doctor"),
        ({"role": "admin", "name": "figyelmen kívül", "birth_date": "1955-03-04"}, "admin"),
    ],
)
def test_admin_creates_users_who_can_log_in(client, db, s, body, role):
    payload = {"email": "Uj.Felhasznalo@Test.Example", "password": "kezdeti-jelszo", **body}
    response = client.post("/api/admin/users", json=payload, headers=auth(s["admin"]))
    assert response.status_code == 201
    created = response.json()
    assert set(created) == USER_FIELDS
    assert created["email"] == "uj.felhasznalo@test.example"
    assert created["role"] == role
    assert created["is_active"] is True
    user = db.get(User, uuid.UUID(created["id"]))
    if role == "patient":
        assert created["name"] == "Új Beteg"
        assert user.patient_profile.birth_date == date(1955, 3, 4)
    elif role == "doctor":
        assert created["name"] == "Dr. Új"
    else:
        assert created["name"] is None
        assert user.patient_profile is None and user.doctor_profile is None

    assert login(client, "uj.felhasznalo@test.example", "kezdeti-jelszo").status_code == 200


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ({"password": "rovid"}, "password_length"),
        ({"password": "x" * 256}, "password_length"),
        ({"email": "nem-email"}, "email_invalid"),
        ({"email": "valaki@domain"}, "email_invalid"),
        ({"email": "a b@test.example"}, "email_invalid"),
        ({"name": None}, "name_required"),
        ({"name": "   "}, "name_required"),
        ({"name": "x" * 201}, "name_too_long"),
        ({"birth_date": None}, "birth_date_required"),
        ({"birth_date": "1899-12-31"}, "birth_date_invalid"),
        ({"birth_date": (date.today() + timedelta(days=2)).isoformat()}, "birth_date_invalid"),
    ],
)
def test_create_rejects_invalid_data(client, db, s, body, code):
    payload = {
        "email": "uj@test.example",
        "password": "kezdeti-jelszo",
        "role": "patient",
        "name": "Új Beteg",
        "birth_date": "1955-03-04",
        **body,
    }
    before = snapshot(db)
    response = client.post("/api/admin/users", json=payload, headers=auth(s["admin"]))
    assert response.status_code == 422
    assert response.json()["detail"] == {"code": code}
    assert snapshot(db) == before


def test_doctor_needs_a_name(client, db, s):
    payload = {"email": "uj@test.example", "password": "kezdeti-jelszo", "role": "doctor"}
    response = client.post("/api/admin/users", json=payload, headers=auth(s["admin"]))
    assert response.status_code == 422
    assert response.json()["detail"] == {"code": "name_required"}


def test_taken_email_is_a_conflict_in_any_case(client, db, s):
    payload = {
        "email": "  BETEG@test.EXAMPLE ",
        "password": "kezdeti-jelszo",
        "role": "doctor",
        "name": "Dr. Másik",
    }
    before = snapshot(db)
    response = client.post("/api/admin/users", json=payload, headers=auth(s["admin"]))
    assert response.status_code == 409
    assert response.json()["detail"] == {"code": "email_taken"}
    assert snapshot(db) == before


def test_concurrent_duplicate_email_maps_to_conflict(db, s, monkeypatch):
    """Ha a két kérés egyszerre ellenőriz, az egyedi index dönt: 409, és a
    session használható marad (mentési pont)."""
    monkeypatch.setattr(admin, "get_user_by_email", lambda _db, _email: None)
    with pytest.raises(AdminError) as error:
        admin.create_account(
            db, email="beteg@test.example", password="kezdeti-jelszo", role=UserRole.ADMIN
        )
    assert (error.value.code, error.value.conflict) == ("email_taken", True)
    assert db.scalar(select(func.count()).select_from(User)) == 3


def test_admin_renames_patient_and_doctor_only(client, db, s):
    for user in (s["patient"], s["doctor"]):
        response = client.patch(
            f"/api/admin/users/{user.id}",
            json={"name": "  Javított Név "},
            headers=auth(s["admin"]),
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Javított Név"
    # E-mail és szerepkör nem változik (a kérés figyelmen kívül hagyja).
    response = client.patch(
        f"/api/admin/users/{s['patient'].id}",
        json={"name": "Név", "email": "mas@test.example", "role": "admin"},
        headers=auth(s["admin"]),
    )
    assert response.json()["email"] == "beteg@test.example"
    assert response.json()["role"] == "patient"

    response = client.patch(
        f"/api/admin/users/{s['admin'].id}", json={"name": "Admin"}, headers=auth(s["admin"])
    )
    assert response.status_code == 422
    assert response.json()["detail"] == {"code": "no_name"}
    response = client.patch(
        f"/api/admin/users/{s['doctor'].id}", json={"name": " "}, headers=auth(s["admin"])
    )
    assert response.json()["detail"] == {"code": "name_required"}


def test_unknown_user_is_404(client, db, s):
    unknown = uuid.uuid4()
    for method, url, body in [
        ("patch", f"/api/admin/users/{unknown}", {"name": "X"}),
        ("post", f"/api/admin/users/{unknown}/disable", None),
        ("post", f"/api/admin/users/{unknown}/enable", None),
    ]:
        response = client.request(method, url, json=body, headers=auth(s["admin"]))
        assert response.status_code == 404


def test_disable_hits_issued_token_and_login_until_enabled(client, db, s):
    headers = auth(s["patient"])
    assert client.get("/api/auth/me", headers=headers).status_code == 200

    response = client.post(f"/api/admin/users/{s['patient'].id}/disable", headers=auth(s["admin"]))
    assert response.status_code == 200
    assert response.json()["is_active"] is False
    # A már kiadott token a következő kérésnél érvénytelen; belépni sem lehet.
    assert client.get("/api/auth/me", headers=headers).status_code == 401
    assert login(client, "beteg@test.example").status_code == 403  # account_disabled
    # Ismételt letiltás: nem változik semmi.
    again = client.post(f"/api/admin/users/{s['patient'].id}/disable", headers=auth(s["admin"]))
    assert again.status_code == 200 and again.json()["is_active"] is False

    response = client.post(f"/api/admin/users/{s['patient'].id}/enable", headers=auth(s["admin"]))
    assert response.status_code == 200
    assert response.json()["is_active"] is True
    (period,) = db.scalars(select(UserDisabledPeriod)).all()
    assert period.user_id == s["patient"].id
    assert period.enabled_at is not None and period.enabled_at > period.disabled_at
    assert client.get("/api/auth/me", headers=headers).status_code == 200
    assert login(client, "beteg@test.example").status_code == 200


def test_disabled_doctor_loses_access_but_keeps_assignment(client, db, s):
    link = assign(db, s["doctor"], s["patient"])
    client.post(f"/api/admin/users/{s['doctor'].id}/disable", headers=auth(s["admin"]))
    assert client.get(f"/api/patients/{s['pid']}", headers=auth(s["doctor"])).status_code == 401
    db.refresh(link)
    assert link.valid_to is None
    client.post(f"/api/admin/users/{s['doctor'].id}/enable", headers=auth(s["admin"]))
    assert client.get(f"/api/patients/{s['pid']}", headers=auth(s["doctor"])).status_code == 200


def test_admin_cannot_disable_own_account(client, db, s):
    before = snapshot(db)
    response = client.post(f"/api/admin/users/{s['admin'].id}/disable", headers=auth(s["admin"]))
    assert response.status_code == 409
    assert response.json()["detail"] == {"code": "self_disable"}
    assert snapshot(db) == before


def test_admin_disables_another_admin(client, db, s):
    other = make_admin(db, email="admin2@test.example")
    response = client.post(f"/api/admin/users/{other.id}/disable", headers=auth(s["admin"]))
    assert response.status_code == 200 and response.json()["is_active"] is False


def test_last_active_admin_cannot_be_disabled(db, s):
    """Két admin egyszerre tiltaná le egymást: a második kérés már a friss
    állapotot látja (a saját fiókja közben letiltva), így az utolsó aktív admin
    nem tiltható le. Az API-n ez csak ilyen versenyhelyzetben fordulhat elő,
    mert a hívó maga is aktív admin."""
    other = make_admin(db, email="admin2@test.example")
    s["admin"].is_active = False  # az egyidejű kérés már letiltotta
    db.flush()
    with pytest.raises(AdminError) as error:
        admin.disable_user(db, s["admin"], other)
    assert (error.value.code, error.value.conflict) == ("last_admin", True)
    assert other.is_active is True


# --- Összerendelések --------------------------------------------------------------


def create_link(client, s, doctor_id=None, patient_id=None):
    body = {"doctor_id": str(doctor_id or s["did"]), "patient_id": str(patient_id or s["pid"])}
    return client.post("/api/admin/assignments", json=body, headers=auth(s["admin"]))


def test_assignment_gives_and_ending_removes_access_immediately(client, db, s):
    doctor_headers = auth(s["doctor"])
    assert client.get(f"/api/patients/{s['pid']}", headers=doctor_headers).status_code == 403

    response = create_link(client, s)
    assert response.status_code == 201
    link = response.json()
    assert set(link) == ASSIGNMENT_FIELDS
    assert link["doctor_name"] == "Dr. Teszt" and link["patient_name"] == "Teszt Beteg"
    assert link["valid_to"] is None
    # Azonnal: a következő kérésnél eléri, és a listáján is ott van.
    assert client.get(f"/api/patients/{s['pid']}", headers=doctor_headers).status_code == 200
    listed = client.get("/api/doctor/patients", headers=doctor_headers).json()
    assert [p["id"] for p in listed] == [str(s["pid"])]

    ended = client.post(f"/api/admin/assignments/{link['id']}/end", headers=auth(s["admin"]))
    assert ended.status_code == 200
    assert ended.json()["valid_to"] is not None
    assert client.get(f"/api/patients/{s['pid']}", headers=doctor_headers).status_code == 403
    assert client.get("/api/doctor/patients", headers=doctor_headers).json() == []

    # Újra-összerendelés: új sor, a régi a történetben marad.
    again = create_link(client, s)
    assert again.status_code == 201 and again.json()["id"] != link["id"]
    rows = client.get("/api/admin/assignments", headers=auth(s["admin"])).json()
    assert all(set(r) == ASSIGNMENT_FIELDS for r in rows)
    assert [(r["id"], r["valid_to"] is None) for r in rows] == [
        (link["id"], False),
        (again.json()["id"], True),
    ]
    assert client.get(f"/api/patients/{s['pid']}", headers=doctor_headers).status_code == 200


def test_duplicate_active_assignment_is_a_conflict(client, db, s):
    assert create_link(client, s).status_code == 201
    before = snapshot(db)
    response = create_link(client, s)
    assert response.status_code == 409
    assert response.json()["detail"] == {"code": "already_assigned"}
    assert snapshot(db) == before


def test_assignment_needs_active_doctor_and_patient(client, db, s):
    other_patient = make_patient(db, email="beteg2@test.example", name="Másik Beteg")
    cases = [
        ({"doctor_id": s["pid"]}, "not_a_doctor"),  # betegprofil orvosként
        ({"patient_id": s["did"]}, "not_a_patient"),  # orvosprofil betegként
        ({"doctor_id": uuid.uuid4()}, "not_a_doctor"),
    ]
    for override, code in cases:
        response = create_link(client, s, **override)
        assert response.status_code == 422
        assert response.json()["detail"] == {"code": code}

    other_patient.is_active = False
    db.flush()
    response = create_link(client, s, patient_id=other_patient.patient_profile.id)
    assert response.json()["detail"] == {"code": "inactive_user"}
    other_patient.is_active = True
    s["doctor"].is_active = False
    db.flush()
    response = create_link(client, s, patient_id=other_patient.patient_profile.id)
    assert response.status_code == 422
    assert response.json()["detail"] == {"code": "inactive_user"}
    assert db.scalars(select(DoctorPatient)).all() == []


def test_end_twice_and_unknown(client, db, s):
    link = create_link(client, s).json()
    url = f"/api/admin/assignments/{link['id']}/end"
    assert client.post(url, headers=auth(s["admin"])).status_code == 200
    response = client.post(url, headers=auth(s["admin"]))
    assert response.status_code == 409
    assert response.json()["detail"] == {"code": "already_ended"}
    unknown = client.post(f"/api/admin/assignments/{uuid.uuid4()}/end", headers=auth(s["admin"]))
    assert unknown.status_code == 404


def test_future_row_cannot_be_ended(db, s):
    """A felületről nem jön létre ilyen; a modell megengedi (valid_from jövőbeli)."""
    link = assign(db, s["doctor"], s["patient"], valid_from=datetime.now(UTC) + timedelta(days=1))
    with pytest.raises(AdminError) as error:
        admin.end_assignment(db, link.id)
    assert error.value.code == "not_started"


def test_assignment_with_planned_end_can_be_ended_now(db, s):
    link = assign(
        db,
        s["doctor"],
        s["patient"],
        valid_from=datetime.now(UTC) - timedelta(days=1),
        valid_to=datetime.now(UTC) + timedelta(days=5),
    )
    now = datetime.now(UTC)
    row = admin.end_assignment(db, link.id, now=now)
    assert row.link.valid_to == now


def test_concurrent_assignment_maps_to_conflict(db, s):
    """Két admin egyszerre rendelné össze ugyanazt a párt: az átfedést tiltó
    megszorítás dönt (409), a session használható marad."""
    admin.create_assignment(db, s["did"], s["pid"])
    with pytest.raises(AdminError) as error:
        admin.create_assignment(db, s["did"], s["pid"])
    assert (error.value.code, error.value.conflict) == ("already_assigned", True)
    assert db.scalar(select(func.count()).select_from(DoctorPatient)) == 1


# --- Méréstípusok -----------------------------------------------------------------


def put_ranges(client, s, code, components):
    return client.put(
        f"/api/admin/measurement-types/{code}/ranges",
        json={"components": components},
        headers=auth(s["admin"]),
    )


def record(client, s, systolic, diastolic):
    return client.post(
        f"/api/patients/{s['pid']}/measurements",
        json={
            "type_code": "blood_pressure",
            "measured_at": datetime.now(UTC).isoformat(),
            "values": {"systolic": systolic, "diastolic": diastolic},
        },
        headers=auth(s["patient"]),
    )


def test_range_edit_applies_to_new_recordings(client, db, s):
    assert record(client, s, 320, 90).status_code == 422  # a seed szerint max. 300
    response = put_ranges(
        client, s, "blood_pressure", [{"code": "systolic", "min_value": 60, "max_value": 330}]
    )
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "blood_pressure"
    systolic, diastolic = body["components"]
    assert (systolic["min_value"], systolic["max_value"]) == (60, 330)
    assert (diastolic["min_value"], diastolic["max_value"]) == (30, 200)  # nem változott
    # A közös típuslista (a beteg űrlapja is ezt kéri) az új tartományt adja.
    types = client.get("/api/measurement-types", headers=auth(s["patient"])).json()
    bp = next(t for t in types if t["code"] == "blood_pressure")
    assert bp["components"][0]["max_value"] == 330
    assert record(client, s, 320, 90).status_code == 201
    response = record(client, s, 55, 40)
    assert response.status_code == 422
    assert response.json()["detail"] == {"code": "out_of_range", "component": "systolic"}


@pytest.mark.parametrize(
    ("components", "code"),
    [
        ([{"code": "value", "min_value": 100, "max_value": 100}], "range_invalid"),
        ([{"code": "value", "min_value": 120, "max_value": 100}], "range_invalid"),
        ([{"code": "value", "min_value": -1, "max_value": 100}], "range_invalid"),
        ([{"code": "value", "min_value": 10, "max_value": 1001}], "range_invalid"),
        ([{"code": "systolic", "min_value": 10, "max_value": 100}], "unknown_component"),
    ],
)
def test_invalid_range_is_rejected(client, db, s, components, code):
    before = snapshot(db)
    response = put_ranges(client, s, "heart_rate", components)
    assert response.status_code == 422
    assert response.json()["detail"] == {"code": code}
    assert snapshot(db) == before


def test_partial_invalid_range_changes_nothing(client, db, s):
    before = snapshot(db)
    response = put_ranges(
        client,
        s,
        "blood_pressure",
        [
            {"code": "systolic", "min_value": 60, "max_value": 250},
            {"code": "diastolic", "min_value": 90, "max_value": 80},
        ],
    )
    assert response.status_code == 422
    assert snapshot(db) == before


def test_range_edit_rejects_non_numbers_and_unknown_type(client, db, s):
    response = put_ranges(
        client, s, "heart_rate", [{"code": "value", "min_value": "x", "max_value": 1}]
    )
    assert response.status_code == 422
    response = put_ranges(client, s, "heart_rate", [])
    assert response.status_code == 422
    response = put_ranges(
        client, s, "nincs_ilyen", [{"code": "value", "min_value": 1, "max_value": 2}]
    )
    assert response.status_code == 404


def test_range_edit_does_not_change_existing_measurements_rules_or_alerts(client, db, s):
    assign(db, s["doctor"], s["patient"])
    rule = make_threshold_rule(db, s["patient"], s["doctor"])
    response = record(client, s, 170, 95)
    assert response.status_code == 201
    measurement_id = response.json()["id"]
    doctor_headers = auth(s["doctor"])
    alerts_before = client.get(f"/api/patients/{s['pid']}/alerts", headers=doctor_headers).json()
    patient_before = client.get(f"/api/patients/{s['pid']}", headers=doctor_headers).json()
    measurements_before = client.get(
        f"/api/patients/{s['pid']}/measurements", headers=doctor_headers
    ).json()
    versions_before = [(v.version_no, v.params) for v in db.scalars(select(RuleVersion))]
    assert len(alerts_before) == 1

    # A tartomány szűkül: a 170-es szisztolés kívül esik rajta.
    response = put_ranges(
        client, s, "blood_pressure", [{"code": "systolic", "min_value": 60, "max_value": 160}]
    )
    assert response.status_code == 200

    db.expire_all()
    assert client.get(f"/api/patients/{s['pid']}/alerts", headers=doctor_headers).json() == (
        alerts_before
    )
    patient_after = client.get(f"/api/patients/{s['pid']}", headers=doctor_headers).json()
    assert patient_after["status"] == patient_before["status"] == "attention"
    assert patient_after["reasons"] == patient_before["reasons"]
    assert (
        client.get(f"/api/patients/{s['pid']}/measurements", headers=doctor_headers).json()
        == measurements_before
    )
    assert [(v.version_no, v.params) for v in db.scalars(select(RuleVersion))] == versions_before
    stored = db.get(Measurement, uuid.UUID(measurement_id))
    assert sorted(v.value for v in stored.values) == [95, 170]
    assert db.scalar(select(func.count()).select_from(Alert)) == 1
    assert rule.is_active
    # Új rögzítés ugyanazzal az értékkel már nem megy át.
    response = record(client, s, 170, 95)
    assert response.status_code == 422
    assert response.json()["detail"] == {"code": "out_of_range", "component": "systolic"}


def test_rename_ignores_other_fields(client, db, s):
    """A PATCH csak a nevet változtatja: az e-mail, a szerepkör, a jelszó és az
    aktív állapot a kérésben hiába szerepel."""
    before = snapshot(db)
    response = client.patch(
        f"/api/admin/users/{s['patient'].id}",
        json={
            "name": "Teszt Beteg",
            "email": "mas@test.example",
            "role": "admin",
            "password": "uj-jelszo-12345",
            "is_active": False,
        },
        headers=auth(s["admin"]),
    )
    assert response.status_code == 200
    assert snapshot(db) == before
    assert login(client, "beteg@test.example").status_code == 200


def test_invalid_role_is_rejected(client, db, s):
    before = snapshot(db)
    payload = {"email": "uj@test.example", "password": "kezdeti-jelszo", "role": "superuser"}
    response = client.post("/api/admin/users", json=payload, headers=auth(s["admin"]))
    assert response.status_code == 422
    assert snapshot(db) == before


def test_disabled_admin_token_is_refused(client, db, s):
    other = make_admin(db, email="admin2@test.example")
    headers = auth(other)
    assert client.get("/api/admin/users", headers=headers).status_code == 200
    client.post(f"/api/admin/users/{other.id}/disable", headers=auth(s["admin"]))
    before = snapshot(db)
    for method, url, body in calls(s):
        assert client.request(method, url, json=body, headers=headers).status_code == 401
    assert snapshot(db) == before
