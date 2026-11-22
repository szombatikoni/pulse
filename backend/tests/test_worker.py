"""A háttérfolyamat ciklusa (M3, A2, A9): futás, hibatűrés, leállítás, a két ütem."""

import logging
import signal
import threading
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import worker
from app.core.config import settings
from app.models import AssignmentOccurrence, DeliveryStatus, NotificationDelivery
from app.services.measurements import get_type_by_code
from app.services.occurrences import OccurrenceCheck
from app.services.tasks import assign_measurement
from tests.factories import (
    assign,
    make_doctor,
    make_measurement_types,
    make_patient,
    make_threshold_rule,
    record_bp,
)


@pytest.fixture(autouse=True)
def worker_logging(monkeypatch):
    """A tesztek elején futó migráció (alembic fileConfig) letiltja a már
    létrehozott loggereket; a worker naplóját itt visszakapcsoljuk."""
    monkeypatch.setattr(worker.log, "disabled", False)


@pytest.fixture
def session_factory(db):
    """A worker saját sessiont nyit; a tesztben ez a teszt tranzakciójához
    kapcsolódik, így a commitja is visszagörgetődik a végén."""
    return lambda: Session(bind=db.connection(), join_transaction_mode="create_savepoint")


def test_run_once_commits_and_logs_the_result(db, session_factory, caplog):
    make_measurement_types(db)
    doctor, patient = make_doctor(db), make_patient(db)
    assign(db, doctor, patient)
    assign_measurement(
        db,
        patient_id=patient.patient_profile.id,
        measurement_type=get_type_by_code(db, "blood_pressure"),
        assigned_by=doctor.id,
        start_date=datetime.now(settings.tz).date() - timedelta(days=1),
    )
    db.commit()

    with caplog.at_level(logging.INFO, logger="pulse.worker"):
        result = worker.run_once(session_factory)

    assert result is not None and result.opened == 2
    assert len(db.scalars(select(AssignmentOccurrence)).all()) == 2
    assert f"{result.opened} megnyitva, {result.missed} elmulasztva" in caplog.text


def test_failed_run_is_logged_and_does_not_stop_the_loop(session_factory, monkeypatch, caplog):
    def broken(_db):
        raise RuntimeError("az adatbázis nem érhető el")

    monkeypatch.setattr(worker, "run_occurrence_check", broken)
    with caplog.at_level(logging.INFO, logger="pulse.worker"):
        assert worker.run_once(session_factory) is None
    [record] = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert "az adatbázis nem érhető el" in record.exc_text


def test_loop_runs_immediately_then_repeats_until_stopped(monkeypatch):
    stop = threading.Event()
    runs = []

    def fake_run_once(_factory):
        runs.append(1)
        if len(runs) == 3:
            stop.set()
        return OccurrenceCheck(0, 0)

    monkeypatch.setattr(worker, "run_once", fake_run_once)
    monkeypatch.setattr(worker, "deliver_once", lambda _f: None)
    worker.run_forever(stop, interval=0)
    assert len(runs) == 3


def test_stopped_loop_does_not_run(monkeypatch):
    stop = threading.Event()
    stop.set()
    monkeypatch.setattr(worker, "run_once", lambda _f: pytest.fail("nem futhat"))
    monkeypatch.setattr(worker, "deliver_once", lambda _f: pytest.fail("nem futhat"))
    worker.run_forever(stop, interval=3600)


def test_sigterm_requests_a_clean_stop(monkeypatch):
    """A main a SIGTERM-re (docker compose stop) leállítást kér; a két ütem a
    beállításból (OCCURRENCE_CHECK_INTERVAL_SECONDS, DELIVERY_INTERVAL_SECONDS) jön."""
    handlers = {}
    monkeypatch.setattr(signal, "signal", lambda sig, handler: handlers.setdefault(sig, handler))
    seen = {}

    def fake_run_forever(stop, interval, *, delivery_interval):
        handlers[signal.SIGTERM](signal.SIGTERM, None)
        seen.update(stopped=stop.is_set(), interval=interval, delivery=delivery_interval)

    monkeypatch.setattr(worker, "run_forever", fake_run_forever)
    worker.main()
    assert seen == {
        "stopped": True,
        "interval": settings.occurrence_check_interval_seconds,
        "delivery": settings.delivery_interval_seconds,
    }
    assert signal.SIGINT in handlers


def test_interval_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("OCCURRENCE_CHECK_INTERVAL_SECONDS", "20")
    assert type(settings)().occurrence_check_interval_seconds == 20
    monkeypatch.setenv("OCCURRENCE_CHECK_INTERVAL_SECONDS", "0")
    with pytest.raises(ValueError):
        type(settings)()


# --- Kézbesítő kör (M3, A9) -----------------------------------------------------------


class SimulatedTime:
    """Szimulált óra és leállítási esemény: a várakozás az órát lépteti, és
    `until` után a ciklus leáll."""

    def __init__(self, until: float) -> None:
        self.now = 0.0
        self.until = until
        self.waits: list[float] = []

    def clock(self) -> float:
        return self.now

    def is_set(self) -> bool:
        return self.now >= self.until

    def wait(self, timeout: float) -> bool:
        self.waits.append(timeout)
        self.now += timeout
        return self.is_set()


def _queued_delivery(db):
    """Egy új riasztás egy hozzárendelt orvossal; visszaadja az időt és a sort."""
    now = datetime(2026, 10, 12, 8, 0, tzinfo=UTC)
    make_measurement_types(db)
    doctor, patient = make_doctor(db), make_patient(db)
    assign(db, doctor, patient, valid_from=now - timedelta(days=30))
    make_threshold_rule(db, patient, doctor)
    record_bp(db, patient, 150, 95, at=now)
    db.commit()
    [row] = db.scalars(select(NotificationDelivery)).all()
    return now, row


def test_delivery_runs_every_wake_and_the_check_only_on_its_own_interval(monkeypatch):
    sim = SimulatedTime(until=7200 + 60)
    checks, deliveries = [], []
    monkeypatch.setattr(worker, "run_once", lambda _f: checks.append(sim.now))
    monkeypatch.setattr(worker, "deliver_once", lambda _f: deliveries.append(sim.now))

    worker.run_forever(sim, interval=3600, delivery_interval=30, clock=sim.clock)

    assert checks == [0, 3600, 7200]
    assert deliveries == [30 * i for i in range(7260 // 30)]
    assert set(sim.waits) == {30}


def test_check_interval_shorter_than_delivery_interval_wakes_for_the_check(monkeypatch):
    sim = SimulatedTime(until=60)
    checks = []
    monkeypatch.setattr(worker, "run_once", lambda _f: checks.append(sim.now))
    monkeypatch.setattr(worker, "deliver_once", lambda _f: None)

    worker.run_forever(sim, interval=20, delivery_interval=30, clock=sim.clock)

    assert checks == [0, 20, 40]


def test_failing_delivery_round_does_not_stop_the_loop_or_the_check(monkeypatch, caplog):
    """A kézbesítő kör hibája (itt: minden kör kivételt dob) naplózódik, a
    ciklus fut tovább, és az alkalom-ellenőrzés a saját ütemében lefut."""
    sim = SimulatedTime(until=3600 + 30)
    checks = []
    monkeypatch.setattr(settings, "smtp_host", "mailpit")
    monkeypatch.setattr(worker, "run_once", lambda _f: checks.append(sim.now))

    def broken(_db, _now, _send):
        raise RuntimeError("az SMTP-kiszolgáló elérhetetlen")

    monkeypatch.setattr(worker, "deliver_due", broken)
    with caplog.at_level(logging.INFO, logger="pulse.worker"):
        worker.run_forever(
            sim, interval=3600, session_factory=Session, delivery_interval=30, clock=sim.clock
        )

    assert checks == [0, 3600]
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 3600 // 30 + 1
    assert "az SMTP-kiszolgáló elérhetetlen" in errors[0].exc_text


def test_failing_check_does_not_stop_the_delivery(monkeypatch):
    sim = SimulatedTime(until=90)
    deliveries = []

    def broken(_db):
        raise RuntimeError("az adatbázis nem érhető el")

    monkeypatch.setattr(worker, "run_occurrence_check", broken)
    monkeypatch.setattr(worker, "deliver_once", lambda _f: deliveries.append(sim.now))
    worker.run_forever(
        sim, interval=3600, session_factory=Session, delivery_interval=30, clock=sim.clock
    )
    assert deliveries == [0, 30, 60]


def test_stop_during_the_round_ends_the_loop_without_waiting(monkeypatch):
    stop = threading.Event()
    monkeypatch.setattr(worker, "run_once", lambda _f: None)
    monkeypatch.setattr(worker, "deliver_once", lambda _f: stop.set())
    worker.run_forever(stop, interval=3600, delivery_interval=3600)
    assert stop.is_set()


def test_disabled_sending_leaves_rows_untouched_and_logs_once(db, monkeypatch, caplog):
    """Üres SMTP_HOST: a kör a sorokhoz nem nyúl (pending marad, kísérlet nem
    számolódik); a ciklus indulásakor egy naplósor jelzi."""
    monkeypatch.setattr(settings, "smtp_host", "")
    _, row = _queued_delivery(db)

    assert worker.deliver_once(lambda: pytest.fail("nem nyithat sessiont")) is None
    assert (row.status, row.attempts) == (DeliveryStatus.PENDING, 0)

    sim = SimulatedTime(until=90)
    monkeypatch.setattr(worker, "run_once", lambda _f: None)
    with caplog.at_level(logging.INFO, logger="pulse.worker"):
        worker.run_forever(sim, interval=3600, delivery_interval=30, clock=sim.clock)
    assert caplog.text.count("Az e-mail-küldés ki van kapcsolva") == 1


def test_deliver_once_sends_commits_and_logs(db, session_factory, monkeypatch, caplog):
    monkeypatch.setattr(settings, "smtp_host", "mailpit")
    now, row = _queued_delivery(db)
    sent = []

    with caplog.at_level(logging.INFO, logger="pulse.worker"):
        result = worker.deliver_once(session_factory, send=lambda *mail: sent.append(mail), now=now)

    assert result is not None and result.sent == 1
    assert [to for to, _, _ in sent] == ["orvos@test.example"]
    db.refresh(row)
    assert row.status is DeliveryStatus.SENT
    assert "Kézbesítés: 1 elküldve, 0 újrapróbálandó, 0 sikertelen, 0 kihagyva" in caplog.text


def test_deliver_once_with_nothing_due_is_quiet(db, session_factory, monkeypatch, caplog):
    monkeypatch.setattr(settings, "smtp_host", "mailpit")
    with caplog.at_level(logging.INFO, logger="pulse.worker"):
        result = worker.deliver_once(session_factory, send=lambda *_: pytest.fail("nincs mit"))
    assert result is not None and result.processed == 0
    assert "Kézbesítés" not in caplog.text
