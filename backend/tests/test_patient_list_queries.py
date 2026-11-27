"""Az orvosi beteglista (GET /api/doctor/patients) SQL-utasításainak száma ne
nőjön a betegek számával (N+1 lekérdezés).

A mérés módja (a dolgozat ezt idézi): minden beteg ugyanazt a forgatókönyvet
kapja (napi vérnyomás-előírás 10 napja, heti kérdőív, egy nyitott közepes
riasztás, és a „kezelt" változatban egy lezárt riasztás, amely megerősítő
adatra vár). A számlálás a SQLAlchemy before_cursor_execute eseményével
történik a teszt kapcsolatán, üres identity mappel (mint egy új kérésnél), a
végpont MÁSODIK hívásán: az első hívás a teendőlistán át még hiányzó
alkalmakat nyit meg (INSERT), így annak száma az előzményektől függ.
A számok kiírása: uv run pytest -q -s tests/test_patient_list_queries.py
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event

from app.core.security import create_access_token
from app.models import Frequency, Severity
from app.services.alerts import close_alert
from app.services.measurements import get_type_by_code, record_measurement
from app.services.questionnaires import assign_questionnaire, create_template
from app.services.tasks import assign_measurement
from seed.questionnaires import WELLBEING_CODE, WELLBEING_NAME, WELLBEING_V1
from tests.factories import assign, make_doctor, make_patient, make_threshold_rule, record_bp


def auth(user):
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def build_patients(db, doctor, count: int, template, prefix: str, handled: bool) -> None:
    now = datetime.now(UTC)
    start = (now - timedelta(days=10)).date()
    for i in range(count):
        patient = make_patient(
            db, email=f"{prefix}beteg{i}@test.example", name=f"{prefix}Beteg {i:02d}"
        )
        assign(db, doctor, patient, valid_from=now - timedelta(days=30))
        assign_measurement(
            db,
            patient_id=patient.patient_profile.id,
            measurement_type=get_type_by_code(db, "blood_pressure"),
            assigned_by=doctor.id,
            start_date=start,
            frequency=Frequency.DAILY,
        )
        assign_questionnaire(
            db,
            patient_id=patient.patient_profile.id,
            template=template,
            assigned_by=doctor.id,
            start_date=start,
        )
        # Nyitott közepes riasztás (Figyelem).
        make_threshold_rule(db, patient, doctor)
        record_bp(db, patient, 160, 95, at=now - timedelta(hours=2))
        if not handled:
            continue
        # Lezárt riasztás, utána nincs rendben lévő adat (Kezelve).
        make_threshold_rule(
            db,
            patient,
            doctor,
            limits={"value": {"max": 100}},
            severity=Severity.SEVERE,
            measurement_type="heart_rate",
        )
        _, alerts = record_measurement(
            db,
            patient_id=patient.patient_profile.id,
            type_code="heart_rate",
            values={"value": 130},
            measured_at=now - timedelta(hours=3),
            now=now - timedelta(hours=3),
        )
        close_alert(db, alerts[0], doctor, "Telefonon egyeztetve.", now=now - timedelta(hours=1))
    db.flush()


def count_statements(client, db, headers: dict) -> tuple[int, list[dict]]:
    """Egy listahívás utasításszáma és válasza, üres identity mappel (a tesztben
    létrehozott objektumok különben lekérdezés nélkül jönnének a sessionből)."""
    db.expunge_all()
    statements: list[str] = []

    def count(conn, cursor, statement, *args):
        statements.append(statement)

    connection = db.connection()
    event.listen(connection, "before_cursor_execute", count)
    try:
        response = client.get("/api/doctor/patients", headers=headers)
    finally:
        event.remove(connection, "before_cursor_execute", count)
    assert response.status_code == 200
    return len(statements), response.json()


@pytest.fixture
def template(db, measurement_types):
    creator = make_doctor(db, email="kerdoiv@test.example", name="Dr. Kérdőív")
    return create_template(
        db, code=WELLBEING_CODE, name=WELLBEING_NAME, created_by=creator.id, spec=WELLBEING_V1
    )


def measure(client, db, template, count: int, prefix: str, handled: bool):
    """Az első és a második hívás utasításszáma, és a második hívás válasza."""
    doctor = make_doctor(db, email=f"{prefix}orvos@test.example")
    build_patients(db, doctor, count, template, prefix, handled)
    headers = auth(doctor)
    first, _ = count_statements(client, db, headers)
    second, body = count_statements(client, db, headers)
    return first, second, body


@pytest.mark.parametrize("handled", [False, True])
@pytest.mark.parametrize("count", [2, 5, 10])
def test_report_statement_counts(client, db, template, count, handled):
    first, second, body = measure(client, db, template, count, "x", handled)
    assert len(body) == count
    # A forgatókönyv bejárja a nyitott riasztás, a teendők és a Kezelve ágát.
    for row in body:
        codes = {r["code"] for r in row["reasons"]}
        assert "open_alert" in codes
        assert ("closed_awaiting_data" in codes) is handled
        assert len(row["tasks"]) == 2
    print(f"\nkezelt={handled} betegek={count} elso_hivas={first} masodik_hivas={second}")


def test_statement_count_does_not_grow_with_patients(client, db, template):
    _, two, _ = measure(client, db, template, 2, "a", handled=False)
    _, ten, _ = measure(client, db, template, 10, "b", handled=False)
    assert ten == two, (two, ten)


def test_handled_check_is_the_only_per_patient_statement(client, db, template):
    # A Kezelve ok ellenőrzése (status.ok_data_since: jött-e a lezárás óta rendben
    # lévő adat) szabályonként egy lekérdezés marad; ezen kívül minden állandó.
    _, two, _ = measure(client, db, template, 2, "a", handled=True)
    _, ten, _ = measure(client, db, template, 10, "b", handled=True)
    assert ten - two == 8, (two, ten)


def test_list_rows_match_the_patient_header(client, db, template):
    # A lista (több beteg egyszerre) és az adatlap fejléce (egy beteg) ugyanazt adja.
    doctor = make_doctor(db, email="corvos@test.example")
    build_patients(db, doctor, 3, template, "c", handled=True)
    headers = auth(doctor)
    rows = client.get("/api/doctor/patients", headers=headers).json()
    assert len(rows) == 3
    for row in rows:
        detail = client.get(f"/api/patients/{row['id']}", headers=headers)
        assert detail.status_code == 200
        assert detail.json() == row
