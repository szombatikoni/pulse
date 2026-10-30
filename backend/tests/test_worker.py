"""A háttérfolyamat ciklusa (M3, A2): futás, hibatűrés, leállítás."""

import logging
import signal
import threading
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import worker
from app.core.config import settings
from app.models import AssignmentOccurrence
from app.services.measurements import get_type_by_code
from app.services.occurrences import OccurrenceCheck
from app.services.tasks import assign_measurement
from tests.factories import assign, make_doctor, make_measurement_types, make_patient


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
    worker.run_forever(stop, interval=0)
    assert len(runs) == 3


def test_stopped_loop_does_not_run(monkeypatch):
    stop = threading.Event()
    stop.set()
    monkeypatch.setattr(worker, "run_once", lambda _f: pytest.fail("nem futhat"))
    worker.run_forever(stop, interval=3600)


def test_sigterm_requests_a_clean_stop(monkeypatch):
    """A main a SIGTERM-re (docker compose stop) leállítást kér; az intervallum a
    beállításból (OCCURRENCE_CHECK_INTERVAL_SECONDS) jön."""
    handlers = {}
    monkeypatch.setattr(signal, "signal", lambda sig, handler: handlers.setdefault(sig, handler))
    seen = {}

    def fake_run_forever(stop, interval):
        handlers[signal.SIGTERM](signal.SIGTERM, None)
        seen.update(stopped=stop.is_set(), interval=interval)

    monkeypatch.setattr(worker, "run_forever", fake_run_forever)
    worker.main()
    assert seen == {"stopped": True, "interval": settings.occurrence_check_interval_seconds}
    assert signal.SIGINT in handlers


def test_interval_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("OCCURRENCE_CHECK_INTERVAL_SECONDS", "20")
    assert type(settings)().occurrence_check_interval_seconds == 20
    monkeypatch.setenv("OCCURRENCE_CHECK_INTERVAL_SECONDS", "0")
    with pytest.raises(ValueError):
        type(settings)()
