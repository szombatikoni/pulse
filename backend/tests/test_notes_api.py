"""Orvosi megjegyzések (M3, A8; F16): csak a beteghez éppen hozzárendelt orvos
írhatja és olvashatja (a beteg és az admin nem), a legújabb elöl, a szerző
nevével; csak hozzáírható (A8 D2). A hozzáférés az összerendeléssel együtt
szűnik meg és nyílik ki (F3)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.security import create_access_token
from app.models import Note
from app.models.note import NOTE_TEXT_MAX
from app.services.notes import add_note
from tests.factories import assign, make_admin, make_doctor, make_patient


def auth(user):
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


@pytest.fixture
def setup(db, measurement_types):
    """Orvos a saját betegével; egy második orvos ugyanahhoz a beteghez; egy
    idegen orvos (a beteg nincs hozzá rendelve) és egy admin."""
    doctor = make_doctor(db, name="Dr. Első")
    second = make_doctor(db, email="masodik@test.example", name="Dr. Második")
    foreign = make_doctor(db, email="idegen@test.example", name="Dr. Idegen")
    patient = make_patient(db)
    link = assign(db, doctor, patient, valid_from=datetime.now(UTC) - timedelta(days=30))
    assign(db, second, patient, valid_from=datetime.now(UTC) - timedelta(days=30))
    return {
        "doctor": doctor,
        "second": second,
        "foreign": foreign,
        "patient": patient,
        "admin": make_admin(db),
        "link": link,
        "pid": patient.patient_profile.id,
    }


def url(setup):
    return f"/api/patients/{setup['pid']}/notes"


def test_assigned_doctor_writes_and_reads_newest_first_with_author(client, db, setup):
    first = client.post(
        url(setup), json={"text": "  Telefonon egyeztetve.  "}, headers=auth(setup["doctor"])
    )
    assert first.status_code == 201
    body = first.json()
    # A szélső szóközök nélkül tárolódik; a válasz a szerzőt is adja.
    assert body["text"] == "Telefonon egyeztetve."
    assert body["author"] == {"id": str(setup["doctor"].id), "name": "Dr. Első"}

    # Egy korábbi megjegyzés közvetlenül (a végpont mindig a mostani időt adja).
    add_note(
        db,
        patient_id=setup["pid"],
        author_id=setup["doctor"].id,
        text="Régebbi megjegyzés.",
        now=datetime.now(UTC) - timedelta(days=1),
    )
    second = client.post(
        url(setup), json={"text": "Kontroll két hét múlva."}, headers=auth(setup["doctor"])
    )
    assert second.status_code == 201

    response = client.get(url(setup), headers=auth(setup["doctor"]))
    assert response.status_code == 200
    assert [n["text"] for n in response.json()] == [
        "Kontroll két hét múlva.",
        "Telefonon egyeztetve.",
        "Régebbi megjegyzés.",
    ]
    assert {n["author"]["name"] for n in response.json()} == {"Dr. Első"}


def test_a_second_assigned_doctor_sees_the_first_doctors_note(client, setup):
    client.post(url(setup), json={"text": "Az első orvos jegyzete."}, headers=auth(setup["doctor"]))
    response = client.get(url(setup), headers=auth(setup["second"]))
    assert response.status_code == 200
    [note] = response.json()
    assert note["text"] == "Az első orvos jegyzete."
    assert note["author"]["name"] == "Dr. Első"
    # A második orvos is írhat; a listában mindkettő látszik, a saját szerzőjével.
    client.post(url(setup), json={"text": "A második válasza."}, headers=auth(setup["second"]))
    names = [
        n["author"]["name"] for n in client.get(url(setup), headers=auth(setup["doctor"])).json()
    ]
    assert names == ["Dr. Második", "Dr. Első"]


@pytest.mark.parametrize("who", ["foreign", "patient", "admin"])
def test_others_get_403_for_read_and_write(client, db, setup, who):
    add_note(db, patient_id=setup["pid"], author_id=setup["doctor"].id, text="Belső jegyzet.")
    user = setup[who]
    assert client.get(url(setup), headers=auth(user)).status_code == 403
    response = client.post(url(setup), json={"text": "Kísérlet."}, headers=auth(user))
    assert response.status_code == 403
    assert db.scalars(select(Note.text)).all() == ["Belső jegyzet."]


def test_notes_require_login(client, setup):
    assert client.get(url(setup)).status_code == 401
    assert client.post(url(setup), json={"text": "Bejelentkezés nélkül."}).status_code == 401


@pytest.mark.parametrize(
    "text", ["", "   ", "\n\t ", "x" * (NOTE_TEXT_MAX + 1), " " + "x" * (NOTE_TEXT_MAX + 1)]
)
def test_empty_or_too_long_text_is_422(client, db, setup, text):
    response = client.post(url(setup), json={"text": text}, headers=auth(setup["doctor"]))
    assert response.status_code == 422
    assert db.scalars(select(Note)).all() == []


def test_the_longest_allowed_text_is_accepted(client, setup):
    # A szélső szóközök nem számítanak bele a hosszba.
    text = "x" * NOTE_TEXT_MAX
    response = client.post(url(setup), json={"text": f"  {text}  "}, headers=auth(setup["doctor"]))
    assert response.status_code == 201
    assert response.json()["text"] == text


def test_missing_text_is_422(client, setup):
    assert client.post(url(setup), json={}, headers=auth(setup["doctor"])).status_code == 422


def test_notes_cannot_be_edited_or_deleted(client, db, setup):
    """Csak hozzáírható: a megjegyzésnek nincs módosító vagy törlő végpontja."""
    note = add_note(db, patient_id=setup["pid"], author_id=setup["doctor"].id, text="Marad.")
    headers = auth(setup["doctor"])
    for method in ("PUT", "PATCH", "DELETE"):
        assert client.request(method, url(setup), headers=headers).status_code == 405
        response = client.request(method, f"{url(setup)}/{note.id}", headers=headers)
        assert response.status_code in (404, 405)
    assert db.scalars(select(Note.text)).all() == ["Marad."]


def test_access_ends_with_the_assignment_and_opens_with_a_new_one(client, db, setup):
    add_note(db, patient_id=setup["pid"], author_id=setup["doctor"].id, text="Előzmény.")
    setup["link"].valid_to = datetime.now(UTC) - timedelta(seconds=1)
    db.flush()
    headers = auth(setup["doctor"])
    assert client.get(url(setup), headers=headers).status_code == 403
    assert client.post(url(setup), json={"text": "Már nem."}, headers=headers).status_code == 403

    # Új összerendelés: a hozzáférés azonnal kinyílik, a korábbi megjegyzésekkel együtt.
    assign(db, setup["doctor"], setup["patient"], valid_from=datetime.now(UTC))
    response = client.get(url(setup), headers=headers)
    assert response.status_code == 200
    assert [n["text"] for n in response.json()] == ["Előzmény."]
    assert client.post(url(setup), json={"text": "Újra."}, headers=headers).status_code == 201


def test_patient_facing_endpoints_expose_no_note(client, db, setup):
    """A beteg a saját adatai közt sehol nem látja a megjegyzést."""
    secret = "BELSO-MEGJEGYZES-SZOVEGE"
    add_note(db, patient_id=setup["pid"], author_id=setup["doctor"].id, text=secret)
    headers = auth(setup["patient"])
    pid = setup["pid"]
    for path in (
        "/api/auth/me",
        f"/api/patients/{pid}/tasks",
        f"/api/patients/{pid}/plan-notices",
        f"/api/patients/{pid}/measurements",
        f"/api/patients/{pid}/questionnaires",
        f"/api/patients/{pid}/fhir",
    ):
        response = client.get(path, headers=headers)
        assert response.status_code == 200, path
        assert secret not in response.text, path


def test_unknown_patient_is_403_not_404(client, setup):
    """Nem létező betegre is 403 jön: a válaszból nem derül ki, létezik-e."""
    path = f"/api/patients/{uuid.uuid4()}/notes"
    headers = auth(setup["doctor"])
    assert client.get(path, headers=headers).status_code == 403
    assert client.post(path, json={"text": "Senkinek."}, headers=headers).status_code == 403


def test_assignment_starting_in_the_future_gives_no_access_yet(client, db, setup):
    """A még el nem kezdődött összerendelés nem ad hozzáférést (F3)."""
    later = make_patient(db, email="kesobb@test.example", name="Későbbi Beteg")
    assign(db, setup["doctor"], later, valid_from=datetime.now(UTC) + timedelta(days=1))
    path = f"/api/patients/{later.patient_profile.id}/notes"
    headers = auth(setup["doctor"])
    assert client.get(path, headers=headers).status_code == 403
    assert client.post(path, json={"text": "Még nem."}, headers=headers).status_code == 403


@pytest.mark.parametrize("text", ["", "   ", "\t\n "])
def test_database_rejects_blank_text(db, setup, text):
    """A séma ellenőrzése mellett az adatbázis is kizárja az üres szöveget
    (ck_notes_text_not_blank), ha valami a végpont nélkül írna."""
    with pytest.raises(IntegrityError, match="ck_notes_text_not_blank"):
        with db.begin_nested():
            add_note(db, patient_id=setup["pid"], author_id=setup["doctor"].id, text=text)
