"""A háttérfolyamat (worker konténer; M3, A2, A9): időközönként lefuttatja az
alkalom-ellenőrzést (services/occurrences.py, run_occurrence_check), és
kézbesíti a várakozó e-maileket (services/deliveries.py, deliver_due).

Indítás: `python -m app.worker` (a compose `worker` szolgáltatása, ugyanabból az
image-ből, mint az API). Szándékosan egyszerű ciklus, ütemező-könyvtár nélkül,
két ütemmel: DELIVERY_INTERVAL_SECONDS másodpercenként (alapból 30) ébred, és
mindig lefuttat egy kézbesítő kört; az alkalom-ellenőrzés induláskor azonnal,
utána csak a saját ütemében (OCCURRENCE_CHECK_INTERVAL_SECONDS, alapból
óránként) fut. Ez azért elég, mert az ellenőrzés idempotens: egy kimaradt
vagy ismételt futás nem ront el semmit, a következő pótolja a hiányt.
"""

import logging
import signal
import threading
import time
from collections.abc import Callable
from datetime import datetime
from types import FrameType

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import SessionLocal
from app.services.deliveries import DeliveryRound, SendFn, deliver_due
from app.services.mailer import send_email, sending_enabled
from app.services.occurrences import OccurrenceCheck, run_occurrence_check

log = logging.getLogger("pulse.worker")


def run_once(session_factory: Callable[[], Session] = SessionLocal) -> OccurrenceCheck | None:
    """Egy ellenőrzés saját sessionben, egy tranzakcióban. Hibánál naplóz és
    None-t ad, nem dob tovább: egy átmeneti hiba (pl. az adatbázis újraindul)
    ne állítsa le a ciklust; a félbemaradt futás visszagörgetődik."""
    try:
        with session_factory() as db:
            result = run_occurrence_check(db)
            db.commit()
    except Exception:
        log.exception("Az alkalom-ellenőrzés hibával leállt; a következő futás újrapróbálja")
        return None
    log.info("Alkalom-ellenőrzés kész: %d megnyitva, %d elmulasztva", result.opened, result.missed)
    return result


def deliver_once(
    session_factory: Callable[[], Session] = SessionLocal,
    send: SendFn = send_email,
    now: datetime | None = None,
) -> DeliveryRound | None:
    """Egy kézbesítő kör saját sessionben (a deliver_due soronként commitol).
    Kikapcsolt küldésnél (üres SMTP_HOST) nem nyúl a sorokhoz: azok
    `pending`-ben várnak, kísérlet nem számolódik. Hibánál naplóz és None-t
    ad, mint a run_once: a kör hibája nem állítja le a ciklust, és az
    alkalom-ellenőrzést sem érinti."""
    if not sending_enabled():
        return None
    try:
        with session_factory() as db:
            result = deliver_due(db, now, send)
    except Exception:
        log.exception("A kézbesítő kör hibával leállt; a következő kör újrapróbálja")
        return None
    if result.processed:
        log.info(
            "Kézbesítés: %d elküldve, %d újrapróbálandó, %d sikertelen, %d kihagyva",
            result.sent,
            result.retrying,
            result.failed,
            result.skipped,
        )
    return result


def run_forever(
    stop: threading.Event,
    interval: float,
    session_factory: Callable[[], Session] = SessionLocal,
    *,
    delivery_interval: float | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> None:
    """Futás, amíg leállítást nem kér valaki. `delivery_interval`
    másodpercenként ébred és kézbesít; az alkalom-ellenőrzés induláskor és
    utána `interval` másodpercenként fut (ha az a rövidebb, arra ébred). Az
    eseményen várakozik (nem time.sleep-pel), így a leállítási jelzés azonnal
    hat, nem kell kivárni a következő ébredést. A két feladat hibái egymástól
    függetlenek (run_once és deliver_once is maga kezeli a sajátját)."""
    if delivery_interval is None:
        delivery_interval = settings.delivery_interval_seconds
    log.info(
        "A háttérfolyamat elindult; alkalom-ellenőrzés %s, kézbesítés %s másodpercenként",
        interval,
        delivery_interval,
    )
    if not sending_enabled():
        log.info("Az e-mail-küldés ki van kapcsolva (üres SMTP_HOST); a kézbesítési sorok várnak")
    next_check = clock()
    while not stop.is_set():
        if clock() >= next_check:
            run_once(session_factory)
            next_check = clock() + interval
        deliver_once(session_factory)
        stop.wait(max(0.0, min(delivery_interval, next_check - clock())))
    log.info("A háttérfolyamat leállt")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    stop = threading.Event()

    def request_stop(signum: int, _frame: FrameType | None) -> None:
        # A docker compose stop SIGTERM-et küld: a futó ellenőrzés vagy
        # kézbesítő kör még befejeződik (a tranzakció nem szakad félbe), utána
        # a ciklus kilép.
        log.info("Leállítási jelzés: %s", signal.Signals(signum).name)
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    run_forever(
        stop,
        settings.occurrence_check_interval_seconds,
        delivery_interval=settings.delivery_interval_seconds,
    )


if __name__ == "__main__":
    main()
