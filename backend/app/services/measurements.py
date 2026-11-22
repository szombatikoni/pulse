"""Mérések rögzítése, javítása és lekérdezése (F4, F5, F7).

A rögzítés és a kiértékelés egy tranzakcióban történik (F19): ha a mérés
elmentődik, a belőle keletkező riasztás is. A véglegesítést (commit) a hívó
végzi, így a demóadatok betöltése is ugyanezt az utat használja.

A javítás (M3, A7; 07_mukodesi_szabalyok.md 3. rész) új mérés-sor, amely a
corrected_from-mal az eredetire hivatkozik; az eredeti megmarad, és a régi
riasztás-események továbbra is rá mutatnak. A felülírt mérést a kiértékelés és
a státusz a közös not_superseded() feltétellel hagyja ki.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import exists, select
from sqlalchemy.orm import Session, selectinload

from app.models import Alert, Measurement, MeasurementType, MeasurementValue
from app.services.rules import evaluate_measurement, flag_corrected_trigger

# Mérést legfeljebb két napra visszamenőleg lehet rögzíteni (F7).
MAX_BACKDATE = timedelta(days=2)
# A beteg órája kissé siethet a szerverhez képest; ennyi jövőbeli időt még elfogadunk.
CLOCK_SKEW = timedelta(minutes=5)
# A javítás utáni újrakiértékelés ennyivel a „kiváltó adat javítva" esemény
# után kap időbélyeget, hogy az eseménytörténet sorrendje egyértelmű legyen
# (az események created_at, majd UUID szerint rendeződnek).
AFTER_CORRECTION = timedelta(microseconds=1)


class MeasurementError(ValueError):
    """Érvénytelen mérés. A `code` alapján a felület a saját nyelvén írja ki az okot."""

    def __init__(self, code: str, component: str | None = None) -> None:
        super().__init__(code if component is None else f"{code}: {component}")
        self.code = code
        self.component = component


def list_types(db: Session) -> list[MeasurementType]:
    query = (
        select(MeasurementType)
        .options(selectinload(MeasurementType.components))
        .order_by(MeasurementType.name)
    )
    return list(db.scalars(query))


def get_type_by_code(db: Session, code: str) -> MeasurementType | None:
    return db.scalar(
        select(MeasurementType)
        .where(MeasurementType.code == code)
        .options(selectinload(MeasurementType.components))
    )


def _checked_values(
    measurement_type: MeasurementType, values: dict[str, float]
) -> list[MeasurementValue]:
    """Az értékek ellenőrzése a típus komponensei szerint (rögzítésnél és
    javításnál ugyanígy): minden komponens pontosan egyszer, a rögzíthető
    tartományon belül. Hibánál MeasurementError a komponens kódjával."""
    components = {c.code: c for c in measurement_type.components}
    for code in values:
        if code not in components:
            raise MeasurementError("unknown_component", code)
    for code, component in components.items():
        if code not in values:
            raise MeasurementError("missing_value", code)
        if not component.min_value <= values[code] <= component.max_value:
            raise MeasurementError("out_of_range", code)
    return [
        MeasurementValue(component=component, value=values[code])
        for code, component in components.items()
    ]


def record_measurement(
    db: Session,
    *,
    patient_id: uuid.UUID,
    type_code: str,
    values: dict[str, float],
    measured_at: datetime,
    now: datetime | None = None,
) -> tuple[Measurement, list[Alert]]:
    """Ellenőrzi és elmenti a mérést, majd kiértékeli a beteg szabályaival.
    Visszaadja a mérést és az általa megnyitott vagy újra aktivált riasztásokat.

    A `now` a rögzítés ideje; a tesztek és a demóadatok szimulált időt adnak meg.
    """
    now = now or datetime.now(UTC)
    if measured_at.tzinfo is None:
        raise MeasurementError("timezone_required")
    if measured_at > now + CLOCK_SKEW:
        raise MeasurementError("in_future")
    if measured_at < now - MAX_BACKDATE:
        raise MeasurementError("too_old")

    measurement_type = get_type_by_code(db, type_code)
    if measurement_type is None:
        raise MeasurementError("unknown_type")

    measurement = Measurement(
        patient_id=patient_id,
        type=measurement_type,
        measured_at=measured_at,
        recorded_at=now,
        values=_checked_values(measurement_type, values),
    )
    db.add(measurement)
    db.flush()
    # Az előírás alkalmának teljesítése (M3); körkörös import elkerülése.
    from app.services.occurrences import fulfil_with_measurement

    fulfil_with_measurement(db, measurement)
    alerts = evaluate_measurement(db, measurement, now=now)
    return measurement, alerts


def correct_measurement(
    db: Session,
    *,
    patient_id: uuid.UUID,
    measurement_id: uuid.UUID,
    values: dict[str, float],
    actor_id: uuid.UUID | None = None,
    now: datetime | None = None,
) -> tuple[Measurement, list[Alert]]:
    """A mérés értékeinek javítása (F7; M3, A7, a hallgató döntései D1–D4).

    - Csak az értékek javíthatók, a mérés ideje az eredetié marad (D1); ezért a
      kétnapos visszadátum-korlát itt nem él, és időkorlát sincs (D3).
    - Az értékek ellenőrzése a rögzítésével azonos (komponensek, tartomány).
    - Láncban javítható, de mindig csak a lánc vége (D2): felülírt mérésre
      MeasurementError("already_corrected"). Az eredeti sora zárolódik (SELECT …
      FOR UPDATE), így két egyidejű javítás egymás után fut, és a második már a
      felülírtat látja; a corrected_from egyedi indexe az adatbázisban is őrzi.
    - Alkalmat NEM teljesít újra (fulfil_with_measurement nem hívódik): az
      eredeti teljesítése áll, a javítás csak az értéket módosítja.
    - Az érintett riasztásokba „kiváltó adat javítva" esemény kerül
      (rules.flag_corrected_trigger), utána a javított érték a szokásos úton
      kiértékelődik (evaluate_measurement): ha maga is határsértő, riasztást
      nyithat vagy ismételt aktiválódást adhat.

    Nem létező vagy más beteghez tartozó mérésre MeasurementError("not_found").
    Visszaadja az új mérést és a kiértékelés által megnyitott vagy újra aktivált
    riasztásokat."""
    now = now or datetime.now(UTC)
    original = db.scalar(
        select(Measurement)
        .where(Measurement.id == measurement_id, Measurement.patient_id == patient_id)
        .options(
            selectinload(Measurement.type).selectinload(MeasurementType.components),
            selectinload(Measurement.values).selectinload(MeasurementValue.component),
        )
        .with_for_update(of=Measurement)
        .execution_options(populate_existing=True)
    )
    if original is None:
        raise MeasurementError("not_found")
    if db.scalar(select(exists().where(Measurement.corrected_from == original.id))):
        raise MeasurementError("already_corrected")

    correction = Measurement(
        patient_id=patient_id,
        type=original.type,
        measured_at=original.measured_at,
        recorded_at=now,
        corrected_from=original.id,
        values=_checked_values(original.type, values),
    )
    db.add(correction)
    db.flush()
    flag_corrected_trigger(db, original, correction, actor_id=actor_id, now=now)
    alerts = evaluate_measurement(db, correction, now=now + AFTER_CORRECTION)
    return correction, alerts


def _with_details() -> tuple:
    """A kiíráshoz kellő kapcsolatok előtöltése (értékek, típus, felülíró javítás)."""
    return (
        selectinload(Measurement.values).selectinload(MeasurementValue.component),
        selectinload(Measurement.type),
        selectinload(Measurement.correction),
    )


def list_measurements(
    db: Session, patient_id: uuid.UUID, type_code: str | None = None, limit: int = 100
) -> list[Measurement]:
    """A beteg mérései, a legújabb elöl (a mérés ideje szerint).

    A felülírt (javított) mérések is benne vannak: az előzmény-lista jelölve
    mutatja őket (a kiírásban a corrected_by), a grafikon pedig kihagyja. Az
    eredeti és a javítása mérési ideje azonos; köztük a későbbi rögzítés áll elöl."""
    query = (
        select(Measurement)
        .where(Measurement.patient_id == patient_id)
        .options(*_with_details())
        .order_by(Measurement.measured_at.desc(), Measurement.recorded_at.desc(), Measurement.id)
        .limit(limit)
        # A javítás után ugyanabban a sessionben is a friss felülírás-jelölés kell.
        .execution_options(populate_existing=True)
    )
    if type_code is not None:
        query = query.join(MeasurementType).where(MeasurementType.code == type_code)
    return list(db.scalars(query))


def get_measurements(db: Session, ids: list[uuid.UUID]) -> list[Measurement]:
    """A mérések azonosító szerint, a felülírtakkal együtt: a riasztás régi
    eseményei az eredetire hivatkoznak, a magyarázatnak azt kell mutatnia."""
    query = (
        select(Measurement)
        .where(Measurement.id.in_(ids))
        .options(*_with_details())
        .order_by(Measurement.measured_at, Measurement.recorded_at, Measurement.id)
        .execution_options(populate_existing=True)
    )
    return list(db.scalars(query))
