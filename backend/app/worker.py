"""A háttérfolyamat (worker konténer; M3, A2): időközönként lefuttatja az
alkalom-ellenőrzést (services/occurrences.py, run_occurrence_check).

Indítás: `python -m app.worker` (a compose `worker` szolgáltatása, ugyanabból az
image-ből, mint az API). Szándékosan egyszerű ciklus, ütemező-könyvtár nélkül:
induláskor azonnal fut egyet, utána OCCURRENCE_CHECK_INTERVAL_SECONDS
másodpercet vár. Ez azért elég, mert az ellenőrzés idempotens: egy kimaradt
vagy ismételt futás nem ront el semmit, a következő pótolja a hiányt.
"""

import logging
import signal
import threading
from collections.abc import Callable
from types import FrameType

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import SessionLocal
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


def run_forever(
    stop: threading.Event,
    interval: float,
    session_factory: Callable[[], Session] = SessionLocal,
) -> None:
    """Futás induláskor, majd `interval` másodpercenként, amíg leállítást nem
    kér valaki. Az eseményen várakozik (nem time.sleep-pel), így a leállítási
    jelzés azonnal hat, nem kell kivárni a következő futást."""
    log.info("A háttérfolyamat elindult; ellenőrzés %s másodpercenként", interval)
    while not stop.is_set():
        run_once(session_factory)
        stop.wait(interval)
    log.info("A háttérfolyamat leállt")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    stop = threading.Event()

    def request_stop(signum: int, _frame: FrameType | None) -> None:
        # A docker compose stop SIGTERM-et küld: a futó ellenőrzés még befejeződik
        # (a tranzakció nem szakad félbe), utána a ciklus kilép.
        log.info("Leállítási jelzés: %s", signal.Signals(signum).name)
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    run_forever(stop, settings.occurrence_check_interval_seconds)


if __name__ == "__main__":
    main()
