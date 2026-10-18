"""Mérések rögzítése és lekérdezése (F4, F5).

A rögzítés és a kiértékelés egy tranzakcióban történik (F19): ha a mérés
elmentődik, a belőle keletkező riasztás is. A véglegesítést (commit) a hívó
végzi, így a demóadatok betöltése is ugyanezt az utat használja.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Alert, Measurement, MeasurementType, MeasurementValue
from app.services.rules import evaluate_measurement

# Mérést legfeljebb két napra visszamenőleg lehet rögzíteni (F7).
MAX_BACKDATE = timedelta(days=2)
# A beteg órája kissé siethet a szerverhez képest; ennyi jövőbeli időt még elfogadunk.
CLOCK_SKEW = timedelta(minutes=5)


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

    components = {c.code: c for c in measurement_type.components}
    for code in values:
        if code not in components:
            raise MeasurementError("unknown_component", code)
    for code, component in components.items():
        if code not in values:
            raise MeasurementError("missing_value", code)
        if not component.min_value <= values[code] <= component.max_value:
            raise MeasurementError("out_of_range", code)

    measurement = Measurement(
        patient_id=patient_id,
        type=measurement_type,
        measured_at=measured_at,
        recorded_at=now,
        values=[
            MeasurementValue(component=component, value=values[code])
            for code, component in components.items()
        ],
    )
    db.add(measurement)
    db.flush()
    alerts = evaluate_measurement(db, measurement, now=now)
    return measurement, alerts


def list_measurements(
    db: Session, patient_id: uuid.UUID, type_code: str | None = None, limit: int = 100
) -> list[Measurement]:
    """A beteg mérései, a legújabb elöl (a mérés ideje szerint)."""
    query = (
        select(Measurement)
        .where(Measurement.patient_id == patient_id)
        .options(
            selectinload(Measurement.values).selectinload(MeasurementValue.component),
            selectinload(Measurement.type),
        )
        .order_by(Measurement.measured_at.desc())
        .limit(limit)
    )
    if type_code is not None:
        query = query.join(MeasurementType).where(MeasurementType.code == type_code)
    return list(db.scalars(query))


def get_measurements(db: Session, ids: list[uuid.UUID]) -> list[Measurement]:
    query = (
        select(Measurement)
        .where(Measurement.id.in_(ids))
        .options(
            selectinload(Measurement.values).selectinload(MeasurementValue.component),
            selectinload(Measurement.type),
        )
        .order_by(Measurement.measured_at)
    )
    return list(db.scalars(query))
