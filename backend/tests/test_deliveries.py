"""Az orvosnak szóló e-mail-értesítés (M3, A9; F19, NF3): sorba állítás a
riasztással egy tranzakcióban, kézbesítés újrapróbálkozással, a levél
tartalma betegadat nélkül. A küldő hamis függvény vagy zárt helyi port; valódi
SMTP-kiszolgálóhoz a tesztek nem kapcsolódnak."""

import socket
import uuid
from datetime import UTC, date, datetime, time, timedelta
from email import message_from_bytes
from email.policy import default as default_policy

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import engine
from app.core.security import create_access_token
from app.models import (
    Alert,
    DeliveryKind,
    DeliveryStatus,
    NotificationDelivery,
    Rule,
    RuleType,
    RuleVersion,
    Severity,
    User,
)
from app.services import deliveries, mailer
from app.services.alerts import close_alert
from app.services.deliveries import alert_email, deliver_due, hungarian_datetime
from app.services.measurements import correct_measurement, get_type_by_code
from app.services.occurrences import run_occurrence_check
from app.services.questionnaires import (
    assign_questionnaire,
    create_template,
    current_version,
    submit_questionnaire,
)
from app.services.rules import add_rule_version, create_rule
from app.services.tasks import assign_measurement
from seed.questionnaires import WELLBEING_CODE, WELLBEING_NAME, WELLBEING_V1
from tests.factories import assign, make_doctor, make_patient, make_threshold_rule, record_bp

NOW = datetime(2026, 10, 12, 8, 0, tzinfo=UTC)  # helyi idő: 10:00 (nyári időszámítás)
# Az összerendelések jóval a szimulált idő előtt kezdődnek (a címzett a riasztás
# pillanatában érvényes összerendelésből jön).
SINCE = datetime(2026, 1, 1, tzinfo=UTC)


class FakeSender:
    """Hamis küldő: rögzíti a leveleket; `failures` darab hívásig hibát dob."""

    def __init__(self, failures: int = 0) -> None:
        self.failures = failures
        self.sent: list[tuple[str, str, str]] = []
        self.calls = 0

    def __call__(self, to: str, subject: str, body: str) -> None:
        self.calls += 1
        if self.calls <= self.failures:
            raise ConnectionRefusedError(111, "Connection refused")
        self.sent.append((to, subject, body))


def rows(db: Session) -> list[NotificationDelivery]:
    return list(
        db.scalars(
            select(NotificationDelivery).order_by(
                NotificationDelivery.created_at, NotificationDelivery.id
            )
        )
    )


@pytest.fixture
def setup(db, measurement_types):
    """Beteg két hozzárendelt orvossal, súlyos küszöbszabállyal (szisztolés > 180)."""
    patient = make_patient(db, name="Kovács Zsófia")
    first = make_doctor(db, email="elso@test.example", name="Dr. Első")
    second = make_doctor(db, email="masodik@test.example", name="Dr. Második")
    assign(db, first, patient, valid_from=SINCE)
    assign(db, second, patient, valid_from=SINCE)
    rule = make_threshold_rule(
        db, patient, first, limits={"systolic": {"max": 180}}, severity=Severity.SEVERE
    )
    return {"patient": patient, "first": first, "second": second, "rule": rule}


def raise_alert(db, setup, at=NOW, systolic=187) -> Alert:
    _, [alert] = record_bp(db, setup["patient"], systolic, 95, at=at)
    return alert


# --- Sorba állítás a riasztás tranzakciójában ---------------------------------------


def test_new_alert_queues_one_pending_row_per_assigned_doctor(db, setup):
    alert = raise_alert(db, setup)

    queued = rows(db)
    assert {r.recipient_user_id for r in queued} == {setup["first"].id, setup["second"].id}
    for row in queued:
        assert row.kind is DeliveryKind.ALERT_CREATED
        assert row.alert_id == alert.id
        assert row.status is DeliveryStatus.PENDING
        assert row.attempts == 0
        assert row.next_attempt_at == NOW
        assert row.created_at == NOW
        assert row.last_attempt_at is None and row.last_error is None


def test_unassigned_inactive_and_former_doctors_get_no_row(db, setup):
    patient = setup["patient"]
    make_doctor(db, email="idegen@test.example")  # nincs összerendelve
    inactive = make_doctor(db, email="tiltott@test.example")
    assign(db, inactive, patient, valid_from=SINCE)
    inactive.is_active = False
    former = make_doctor(db, email="korabbi@test.example")
    assign(db, former, patient, valid_from=SINCE, valid_to=NOW - timedelta(days=1))
    later = make_doctor(db, email="kesobbi@test.example")
    assign(db, later, patient, valid_from=NOW + timedelta(hours=1))

    raise_alert(db, setup)

    assert {r.recipient_user_id for r in rows(db)} == {setup["first"].id, setup["second"].id}


def test_alert_without_assigned_doctor_queues_nothing(db, measurement_types):
    patient, doctor = make_patient(db), make_doctor(db)
    make_threshold_rule(db, patient, doctor)
    _, [alert] = record_bp(db, patient, 150, 95, at=NOW)
    assert alert.id is not None
    assert rows(db) == []


def test_re_triggered_alert_queues_no_new_row(db, setup):
    """Nyitott riasztás mellett az újabb kiváltó adat ismételt aktiválódás:
    levél nem megy (D1)."""
    first = raise_alert(db, setup)
    second = raise_alert(db, setup, at=NOW + timedelta(hours=1), systolic=195)
    assert first.id == second.id
    assert len(rows(db)) == 2


def test_severity_escalation_on_re_trigger_queues_no_new_row(db, setup):
    """Közepes riasztás nyitva, a szabály új verziója súlyos: a következő
    határsértés ugyanazt a riasztást aktiválja újra, a súlyossága emelkedik,
    de új levél nem megy (D1: csak az új riasztás)."""
    patient, doctor = setup["patient"], setup["first"]
    rule = make_threshold_rule(db, patient, doctor, limits={"systolic": {"max": 140}})
    _, touched = record_bp(db, patient, 150, 85, at=NOW)
    [moderate] = [a for a in touched if a.rule_id == rule.id]
    assert moderate.severity is Severity.MODERATE
    assert len(rows(db)) == 2

    add_rule_version(
        db,
        rule,
        created_by=doctor.id,
        rule_type=RuleType.THRESHOLD,
        params={"measurement_type": "blood_pressure", "limits": {"systolic": {"max": 140}}},
        severity=Severity.SEVERE,
        now=NOW + timedelta(minutes=30),
    )
    _, touched = record_bp(db, patient, 155, 85, at=NOW + timedelta(hours=1))
    [again] = [a for a in touched if a.rule_id == rule.id]

    assert again.id == moderate.id
    assert again.severity is Severity.SEVERE
    assert len(rows(db)) == 2


def test_questionnaire_submission_alert_queues_rows(db, setup):
    patient, doctor = setup["patient"], setup["first"]
    template = create_template(
        db, code=WELLBEING_CODE, name=WELLBEING_NAME, created_by=doctor.id, spec=WELLBEING_V1
    )
    assign_questionnaire(
        db,
        patient_id=patient.patient_profile.id,
        template=template,
        assigned_by=doctor.id,
        start_date=NOW.date() - timedelta(days=7),
    )
    create_rule(
        db,
        patient_id=patient.patient_profile.id,
        created_by=doctor.id,
        rule_type=RuleType.QUESTIONNAIRE,
        params={"questionnaire": WELLBEING_CODE, "bands": ["critical"]},
        severity=Severity.SEVERE,
    )
    q1, q2, q3 = current_version(db, template.id).questions
    _, [alert] = submit_questionnaire(
        db,
        patient_id=patient.patient_profile.id,
        template_code=WELLBEING_CODE,
        answers={str(q1.id): 1, str(q2.id): 5, str(q3.id): "daily"},  # 13 pont
        now=NOW,
    )

    queued = rows(db)
    assert {r.alert_id for r in queued} == {alert.id}
    assert {r.recipient_user_id for r in queued} == {setup["first"].id, setup["second"].id}


def test_alert_from_a_corrected_measurement_queues_rows(db, setup):
    """A javított érték a szokásos úton értékelődik (A7): ha határsértő, új
    riasztás és vele új levél."""
    original, touched = record_bp(db, setup["patient"], 130, 80, at=NOW)
    assert touched == [] and rows(db) == []

    _, [alert] = correct_measurement(
        db,
        patient_id=setup["patient"].patient_profile.id,
        measurement_id=original.id,
        values={"systolic": 187, "diastolic": 95},
        actor_id=setup["patient"].id,
        now=NOW + timedelta(hours=1),
    )

    queued = rows(db)
    assert len(queued) == 2
    assert {r.alert_id for r in queued} == {alert.id}


def test_measurement_posted_through_the_api_queues_rows(client, db, setup):
    """A végponton át: a mérés, a riasztás és a kézbesítési sor a kérés
    tranzakciójában commitolódik."""
    patient = setup["patient"]
    measured_at = datetime.now(UTC) - timedelta(minutes=1)
    response = client.post(
        f"/api/patients/{patient.patient_profile.id}/measurements",
        json={
            "type_code": "blood_pressure",
            "measured_at": measured_at.isoformat(),
            "values": {"systolic": 187, "diastolic": 95},
        },
        headers={"Authorization": f"Bearer {create_access_token(patient.id)}"},
    )
    assert response.status_code == 201

    queued = rows(db)
    assert {r.recipient_user_id for r in queued} == {setup["first"].id, setup["second"].id}
    [alert_id] = {r.alert_id for r in queued}
    assert db.get(Alert, alert_id).patient_id == patient.patient_profile.id
    assert all(r.status is DeliveryStatus.PENDING for r in queued)


def test_alert_created_row_without_alert_is_rejected_by_the_database(db, setup):
    with pytest.raises(IntegrityError, match="alert_created_has_alert"):
        with db.begin_nested():
            db.add(
                NotificationDelivery(
                    kind=DeliveryKind.ALERT_CREATED,
                    recipient_user_id=setup["first"].id,
                    status=DeliveryStatus.PENDING,
                    attempts=0,
                    next_attempt_at=NOW,
                )
            )


def test_new_alert_after_closing_queues_again(db, setup):
    """A lezárt riasztás után a következő határsértés új riasztás: új levél."""
    alert = raise_alert(db, setup)
    close_alert(
        db, alert, actor=setup["first"], reason="Ellenőrizve.", now=NOW + timedelta(minutes=5)
    )
    raise_alert(db, setup, at=NOW + timedelta(hours=1))
    assert len(rows(db)) == 4


def test_rolled_back_evaluation_leaves_no_row(db, setup):
    """A sor a riasztással egy tranzakcióban születik: ha a kiértékelés utáni
    commit elmarad (hiba, visszagördülés), se riasztás, se kézbesítési sor."""
    db.commit()
    raise_alert(db, setup)
    assert len(rows(db)) == 2
    db.rollback()
    assert rows(db) == []
    assert db.scalar(select(func.count()).select_from(Alert)) == 0


def test_missed_data_alert_from_the_occurrence_check_queues_rows(db, setup):
    """Az elmaradt adat riasztását a háttérfolyamat alkalom-ellenőrzése hozza
    létre (run_occurrence_check); ugyanúgy kerül sorba a levele."""
    patient, doctor = setup["patient"], setup["first"]
    assign_measurement(
        db,
        patient_id=patient.patient_profile.id,
        measurement_type=get_type_by_code(db, "blood_pressure"),
        assigned_by=doctor.id,
        start_date=date(2026, 10, 1),
        due_time=time(10, 0),
    )
    create_rule(
        db,
        patient_id=patient.patient_profile.id,
        created_by=doctor.id,
        rule_type=RuleType.MISSING_DATA,
        params={"measurement_type": "blood_pressure", "consecutive_missed": 2},
        severity=Severity.MODERATE,
    )
    local = settings.tz
    run_occurrence_check(db, datetime(2026, 10, 4, tzinfo=local))
    assert rows(db) == []
    run_occurrence_check(db, datetime(2026, 10, 5, tzinfo=local))

    queued = rows(db)
    assert len(queued) == 2
    alert = db.get(Alert, queued[0].alert_id)
    assert alert.severity is Severity.MODERATE


# --- Kézbesítés és hibaág (NF3) -------------------------------------------------------


def test_due_rows_are_sent_to_the_doctors_address(db, setup):
    raise_alert(db, setup)
    sender = FakeSender()

    result = deliver_due(db, NOW, sender)

    assert (result.sent, result.retrying, result.failed, result.skipped) == (2, 0, 0, 0)
    assert sorted(to for to, _, _ in sender.sent) == ["elso@test.example", "masodik@test.example"]
    for row in rows(db):
        assert row.status is DeliveryStatus.SENT
        assert row.attempts == 1
        assert row.last_attempt_at == NOW
    # Az elküldött sort a következő kör nem veszi fel újra.
    assert deliver_due(db, NOW + timedelta(hours=1), sender).processed == 0
    assert len(sender.sent) == 2


def test_rows_not_yet_due_wait(db, setup):
    raise_alert(db, setup)
    sender = FakeSender()
    assert deliver_due(db, NOW - timedelta(seconds=1), sender).processed == 0
    assert sender.calls == 0


def test_failed_sends_are_retried_after_1_and_5_minutes_then_marked_failed(db, setup):
    alert = raise_alert(db, setup)
    db.commit()
    broken = FakeSender(failures=100)

    # 1. kísérlet: hiba → a riasztás megvan, a sor vár, 1 perc múlva újra.
    result = deliver_due(db, NOW, broken)
    assert result.retrying == 2
    assert db.get(Alert, alert.id) is not None
    for row in rows(db):
        assert row.status is DeliveryStatus.PENDING
        assert row.attempts == 1
        assert row.last_attempt_at == NOW
        assert row.next_attempt_at == NOW + timedelta(minutes=1)
        assert row.last_error.startswith("ConnectionRefusedError")

    # Az 1 perc letelte előtt nem próbálkozik.
    assert deliver_due(db, NOW + timedelta(seconds=59), broken).processed == 0

    # 2. kísérlet: hiba → 5 perc múlva újra.
    second_try = NOW + timedelta(minutes=1)
    assert deliver_due(db, second_try, broken).retrying == 2
    for row in rows(db):
        assert row.attempts == 2
        assert row.next_attempt_at == second_try + timedelta(minutes=5)

    # 3. kísérlet: hiba → végleg sikertelen, a sor naplóként megmarad.
    third_try = second_try + timedelta(minutes=5)
    assert deliver_due(db, third_try, broken).failed == 2
    for row in rows(db):
        assert row.status is DeliveryStatus.FAILED
        assert row.attempts == 3
        assert row.last_attempt_at == third_try

    # A sikertelen sort később működő küldővel sem küldi újra.
    working = FakeSender()
    assert deliver_due(db, third_try + timedelta(days=1), working).processed == 0
    assert working.calls == 0
    assert broken.calls == 6


def test_a_later_successful_round_sends_the_waiting_rows(db, setup):
    raise_alert(db, setup)
    sender = FakeSender(failures=2)  # az első kör mindkét levele elbukik

    deliver_due(db, NOW, sender)
    result = deliver_due(db, NOW + timedelta(minutes=1), sender)

    assert result.sent == 2
    for row in rows(db):
        assert row.status is DeliveryStatus.SENT
        assert row.attempts == 2
        # Az előző hiba leírása a naplóban marad.
        assert row.last_error.startswith("ConnectionRefusedError")


def test_real_smtplib_against_a_closed_port_counts_as_a_failed_attempt(db, setup, monkeypatch):
    """Hamisítás nélkül: a valódi smtplib egy zárt helyi portra kapcsolódna."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        closed_port = probe.getsockname()[1]
    monkeypatch.setattr(settings, "smtp_host", "127.0.0.1")
    monkeypatch.setattr(settings, "smtp_port", closed_port)
    raise_alert(db, setup)

    result = deliver_due(db, NOW, mailer.send_email)

    assert result.retrying == 2
    for row in rows(db):
        assert row.status is DeliveryStatus.PENDING
        assert row.attempts == 1
        assert row.next_attempt_at == NOW + timedelta(minutes=1)
        assert row.last_error.startswith("ConnectionRefusedError")


def test_inactive_recipient_is_closed_without_sending(db, setup):
    """A sorba állítás után letiltott orvos nem kap levelet; a sora küldés és
    kísérlet nélkül lezárul (különben minden körben újra előkerülne)."""
    raise_alert(db, setup)
    setup["second"].is_active = False
    sender = FakeSender()

    result = deliver_due(db, NOW, sender)

    assert (result.sent, result.skipped) == (1, 1)
    assert [to for to, _, _ in sender.sent] == ["elso@test.example"]
    [skipped] = [r for r in rows(db) if r.recipient_user_id == setup["second"].id]
    assert skipped.status is DeliveryStatus.FAILED
    assert skipped.attempts == 0
    assert skipped.last_attempt_at is None
    assert "nem aktív" in skipped.last_error


def test_round_limit_leaves_the_rest_for_the_next_round(db, setup):
    raise_alert(db, setup)
    sender = FakeSender()
    assert deliver_due(db, NOW, sender, limit=1).sent == 1
    assert deliver_due(db, NOW, sender, limit=1).sent == 1
    assert deliver_due(db, NOW, sender, limit=1).processed == 0


def test_unexpected_error_while_preparing_a_row_counts_as_failed_attempt(db, setup, monkeypatch):
    """Ha a levél összeállítása váratlanul hibát dob (itt: hiányzó súlyosság-
    felirat), az is sikertelen kísérlet: a sor a jövőbe kerül, és a kör a
    többi sort is kézbesíti; egy hibás sor nem tartja fel a sort."""
    make_threshold_rule(db, setup["patient"], setup["first"], limits={"systolic": {"max": 140}})
    _, touched = record_bp(db, setup["patient"], 187, 95, at=NOW)
    assert {a.severity for a in touched} == {Severity.SEVERE, Severity.MODERATE}
    monkeypatch.setattr(deliveries, "SEVERITY_LABELS", {Severity.SEVERE: "Súlyos"})
    sender = FakeSender()

    result = deliver_due(db, NOW, sender)

    assert (result.sent, result.retrying) == (2, 2)
    assert all(subject.endswith("(Súlyos)") for _, subject, _ in sender.sent)
    stuck = [r for r in rows(db) if r.status is DeliveryStatus.PENDING]
    assert len(stuck) == 2
    for row in stuck:
        assert row.attempts == 1
        assert row.next_attempt_at == NOW + timedelta(minutes=1)
        assert row.last_error.startswith("KeyError")
    # A következő körben (még a várakozási időn belül) nincs mit felvenni.
    assert deliver_due(db, NOW + timedelta(seconds=30), sender).processed == 0


def test_missing_alert_counts_as_failed_attempt(db, setup, monkeypatch):
    raise_alert(db, setup)
    original_get = db.get
    monkeypatch.setattr(
        db, "get", lambda model, ident: None if model is Alert else original_get(model, ident)
    )

    result = deliver_due(db, NOW, FakeSender())

    assert result.retrying == 2
    assert all("nem tartozik riasztás" in r.last_error for r in rows(db))


def test_without_a_fixed_time_each_attempt_uses_the_actual_time(db, setup):
    """A háttérfolyamat idő nélkül hívja: a kísérlet ideje és az újrapróbálás
    a tényleges időhöz igazodik, nem a kör kezdetéhez."""
    raise_alert(db, setup)
    before = datetime.now(UTC)

    deliver_due(db, None, FakeSender(failures=100), limit=1)

    after = datetime.now(UTC)
    [tried] = [r for r in rows(db) if r.attempts == 1]
    assert before <= tried.last_attempt_at <= after
    assert tried.next_attempt_at == tried.last_attempt_at + timedelta(minutes=1)


# --- A levél tartalma (D4) -------------------------------------------------------------


def test_email_has_severity_time_link_and_disclaimer_but_no_patient_data(db, setup, monkeypatch):
    monkeypatch.setattr(settings, "app_base_url", "https://pulse.test/")
    alert = raise_alert(db, setup)
    sender = FakeSender()
    deliver_due(db, NOW, sender)
    [(_, subject, body), _] = sender.sent

    assert subject == "PULSE: új riasztás (Súlyos)"
    assert "Súlyosság: Súlyos" in body
    # 8:00 UTC, Budapesten nyári időszámítás; a hónap neve a területi beállítástól független.
    assert "Időpont: 2026. október 12. 10:00 (magyar idő szerint)\n" in body
    assert "https://pulse.test/doctor/alerts" in body
    for phrase in ("demonstrációs", "automatikus", "mesterséges", "nem orvosi eszköz"):
        assert phrase in body

    patient = setup["patient"]
    forbidden = [
        "Kovács",
        "Zsófia",
        "1960",
        "187",
        "95",
        "Hgmm",
        "Vérnyomás",
        "vérnyomás",
        "Szisztolés",
        "180",
        "Küszöb",
        "küszöb",
        str(patient.id),
        str(patient.patient_profile.id),
        str(alert.id),
        str(alert.rule_id),
        str(alert.rule_version_id),
        *alert.trigger_data_ids,
        "/patients/",
    ]
    for fragment in forbidden:
        assert fragment not in subject, fragment
        assert fragment not in body, fragment


@pytest.mark.parametrize(
    ("at", "text"),
    [
        (datetime(2026, 1, 5, 7, 3, tzinfo=UTC), "2026. január 5. 08:03"),  # téli idő
        (datetime(2026, 10, 25, 1, 30, tzinfo=UTC), "2026. október 25. 02:30"),  # átállás
        (datetime(2026, 12, 31, 23, 0, tzinfo=UTC), "2027. január 1. 00:00"),  # évváltás
        (datetime(2026, 5, 9, 22, 59, tzinfo=UTC), "2026. május 10. 00:59"),
    ],
)
def test_hungarian_datetime(at, text):
    assert hungarian_datetime(at) == text


def test_moderate_severity_label():
    alert = Alert(severity=Severity.MODERATE, created_at=NOW)
    subject, body = alert_email(alert)
    assert subject == "PULSE: új riasztás (Közepes)"
    assert "Súlyosság: Közepes" in body


def test_send_email_builds_a_utf8_message_for_the_configured_server(monkeypatch):
    """A valódi küldő a beállított kiszolgálóhoz kapcsolódik, és a magyar
    ékezetes tárgyat és törzset kódolva küldi (hamis SMTP-osztállyal)."""
    seen = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            seen.update(host=host, port=port, timeout=timeout)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def send_message(self, message):
            seen["raw"] = message.as_bytes()

    monkeypatch.setattr(settings, "smtp_host", "mailpit")
    monkeypatch.setattr(settings, "smtp_port", 1025)
    monkeypatch.setattr(settings, "mail_from", "pulse@pulse.example")
    monkeypatch.setattr(mailer, "SMTP", FakeSMTP)

    mailer.send_email("orvos@test.example", "PULSE: új riasztás (Súlyos)", "Árvíztűrő tükörfúrógép")

    assert (seen["host"], seen["port"], seen["timeout"]) == ("mailpit", 1025, 10)
    parsed = message_from_bytes(seen["raw"], policy=default_policy)
    assert parsed["From"] == "pulse@pulse.example"
    assert parsed["To"] == "orvos@test.example"
    assert parsed["Subject"] == "PULSE: új riasztás (Súlyos)"
    assert parsed["Date"]
    assert parsed.get_content().strip() == "Árvíztűrő tükörfúrógép"


def test_sending_enabled_follows_smtp_host(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "")
    assert mailer.sending_enabled() is False
    monkeypatch.setattr(settings, "smtp_host", "  ")
    assert mailer.sending_enabled() is False
    monkeypatch.setattr(settings, "smtp_host", "mailpit")
    assert mailer.sending_enabled() is True


def test_mail_settings_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "mailpit")
    monkeypatch.setenv("SMTP_PORT", "2525")
    monkeypatch.setenv("MAIL_FROM", "demo@pulse.example")
    monkeypatch.setenv("APP_BASE_URL", "https://demo.example")
    monkeypatch.setenv("DELIVERY_INTERVAL_SECONDS", "5")
    loaded = type(settings)()
    assert (loaded.smtp_host, loaded.smtp_port, loaded.mail_from) == (
        "mailpit",
        2525,
        "demo@pulse.example",
    )
    assert (loaded.app_base_url, loaded.delivery_interval_seconds) == ("https://demo.example", 5)
    monkeypatch.setenv("DELIVERY_INTERVAL_SECONDS", "0")
    with pytest.raises(ValueError):
        type(settings)()


# --- Két egyidejű kör ------------------------------------------------------------------

# A párhuzamos teszt saját, a valódi időnél jóval korábbi ideje: a kör csak az
# ekkorra esedékes sorokat veszi fel, így a teszt-adatbázisban esetleg ottmaradt,
# más idejű várakozó sorok nem zavarják.
LONG_AGO = datetime(2000, 1, 1, 8, 0, tzinfo=UTC)


def _commit_alert_with_two_rows(ids: dict) -> None:
    """Ténylegesen commitolt adat (a másik kapcsolat csak így látja): orvos,
    beteg, szabály, riasztás és két kézbesítési sor az orvosnak. Az
    azonosítókat létrehozás közben gyűjti, hogy félbemaradt létrehozás után is
    takarítható legyen."""
    suffix = uuid.uuid4().hex[:8]
    with Session(engine) as db:
        doctor = make_doctor(db, email=f"egyideju-orvos-{suffix}@test.example")
        patient = make_patient(db, email=f"egyideju-beteg-{suffix}@test.example")
        ids.update(doctor=doctor.id, patient=patient.id, profile=patient.patient_profile.id)
        db.commit()
        # A szabály közvetlenül, a szolgáltatás nélkül: annak ellenőrzése a
        # méréstípus-törzsadatot keresné, ami itt (commitolva) nincs, és a
        # riasztás kiértékelése sem kell, csak egy létező szabályverzió.
        rule = Rule(patient_id=patient.patient_profile.id, created_by=doctor.id)
        db.add(rule)
        db.flush()
        version = RuleVersion(
            rule_id=rule.id,
            version_no=1,
            rule_type=RuleType.THRESHOLD,
            params={"measurement_type": "blood_pressure", "limits": {"systolic": {"max": 180}}},
            severity=Severity.SEVERE,
            created_by=doctor.id,
        )
        db.add(version)
        db.flush()
        alert = Alert(
            patient_id=patient.patient_profile.id,
            rule_id=rule.id,
            rule_version_id=version.id,
            severity=Severity.SEVERE,
            trigger_data_ids=[],
            created_at=LONG_AGO,
        )
        db.add(alert)
        db.flush()
        queued = [
            NotificationDelivery(
                kind=DeliveryKind.ALERT_CREATED,
                alert_id=alert.id,
                recipient_user_id=doctor.id,
                status=DeliveryStatus.PENDING,
                attempts=0,
                next_attempt_at=LONG_AGO,
                created_at=LONG_AGO,
            )
            for _ in range(2)
        ]
        db.add_all(queued)
        db.commit()
        ids["rows"] = {d.id for d in queued}


def _remove_committed(ids: dict) -> None:
    """A commitolt tesztadat törlése egy tranzakcióban. A szabályverzió csak
    hozzáírható (trigger); a törlés idejére a trigger ki van kapcsolva, és mivel
    a PostgreSQL-ben a DDL is tranzakciós, hiba esetén a visszagördülés a
    triggert is visszakapcsolja."""
    if "doctor" not in ids:
        return
    params = {"profile": ids["profile"], "users": [ids["doctor"], ids["patient"]]}
    statements = [
        "DELETE FROM notification_deliveries WHERE recipient_user_id = ANY(:users)",
        "DELETE FROM alerts WHERE patient_id = :profile",
        "ALTER TABLE rule_versions DISABLE TRIGGER rule_versions_append_only",
        "DELETE FROM rule_versions WHERE rule_id IN "
        "(SELECT id FROM rules WHERE patient_id = :profile)",
        "ALTER TABLE rule_versions ENABLE TRIGGER rule_versions_append_only",
        "DELETE FROM rules WHERE patient_id = :profile",
        "DELETE FROM patient_profiles WHERE id = :profile",
        "DELETE FROM doctor_profiles WHERE user_id = ANY(:users)",
        "DELETE FROM users WHERE id = ANY(:users)",
    ]
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement), params)


def test_two_concurrent_rounds_never_send_the_same_row_twice():
    """Két külön kapcsolat (két worker-példány) egyszerre kézbesít: amíg az
    első kör az első sort küldi (zárolva tartja), a második kör azt átugorja
    (FOR UPDATE SKIP LOCKED), és a másikat küldi el. Minden sor pontosan egyszer
    megy ki. A teszt csak a saját sorait nézi, és a végén mindent töröl."""
    ids: dict = {}
    try:
        _commit_alert_with_two_rows(ids)
        sent = {"first": 0, "second": 0}
        with Session(engine) as first, Session(engine) as second:

            def send_second(to, subject, body):
                sent["second"] += 1

            def send_first(to, subject, body):
                sent["first"] += 1
                if sent["first"] == 1:
                    # Az első sor itt még zárolva van az első kör tranzakciójában.
                    assert deliver_due(second, LONG_AGO, send_second).sent == 1

            assert deliver_due(first, LONG_AGO, send_first).sent == 1

        assert sent == {"first": 1, "second": 1}
        with Session(engine) as check:
            mine = check.scalars(
                select(NotificationDelivery).where(NotificationDelivery.id.in_(ids["rows"]))
            ).all()
            assert [(r.status, r.attempts) for r in mine] == [(DeliveryStatus.SENT, 1)] * 2
    finally:
        _remove_committed(ids)
    with Session(engine) as check:
        assert check.get(User, ids["doctor"]) is None
