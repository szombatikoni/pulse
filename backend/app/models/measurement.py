import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, SmallInteger, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class MeasurementType(Base):
    """Méréstípus-törzsadat (F4, F20), pl. vérnyomás, pulzus.

    A jelentést a nemzetközi kódok teszik egyértelművé (FHIR R4 Observation):
    a loinc_code az egész mérés kódja. Többértékű mérésnél (vérnyomás) ez a
    panel kódja, az egyes értékek kódja a komponenseknél van.
    """

    __tablename__ = "measurement_types"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # Programon belüli, beszédes azonosító (pl. "blood_pressure"); a felület
    # ebből fordítja le a nevet.
    code: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    loinc_code: Mapped[str] = mapped_column(String(20))

    components: Mapped[list["MeasurementComponent"]] = relationship(
        back_populates="type", order_by="MeasurementComponent.order_no"
    )


class MeasurementComponent(Base):
    """A mérés egy értéke. Egyértékű mérésnek egy komponense van, a
    vérnyomásnak kettő (szisztolés, diasztolés)."""

    __tablename__ = "measurement_components"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    type_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("measurement_types.id"))
    code: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(100))
    order_no: Mapped[int] = mapped_column(SmallInteger)
    loinc_code: Mapped[str] = mapped_column(String(20))
    # UCUM-egységkód (pl. "mm[Hg]", "/min"); a felület ebből írja ki a
    # magyar jelölést (Hgmm, /perc).
    unit: Mapped[str] = mapped_column(String(20))
    # A rögzíthető érték tartománya: a nyilvánvaló elírást (pl. 1400 Hgmm)
    # szűri ki, nem orvosi határérték — azt a szabályok adják.
    min_value: Mapped[float] = mapped_column(Float)
    max_value: Mapped[float] = mapped_column(Float)

    type: Mapped[MeasurementType] = relationship(back_populates="components")

    __table_args__ = (UniqueConstraint("type_id", "code"),)


class Measurement(Base):
    """Egy mérés (F4). Az értékei komponensenként a MeasurementValue-ban vannak
    (normalizált tárolás, 03_adatmodell.md)."""

    __tablename__ = "measurements"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patient_profiles.id"), index=True)
    type_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("measurement_types.id"))
    # A mérés ideje a beteg szerint (legfeljebb két napra vissza), és a
    # rögzítés tényleges ideje; a kettő eltérhet.
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Javításkor az új mérés hivatkozik az eredetire (az eredeti megmarad).
    # A javítás folyamata az M3-ban jön; az oszlop már most a helyén van.
    corrected_from: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("measurements.id"))

    type: Mapped[MeasurementType] = relationship()
    values: Mapped[list["MeasurementValue"]] = relationship(
        back_populates="measurement", cascade="all, delete-orphan"
    )


class MeasurementValue(Base):
    __tablename__ = "measurement_values"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    measurement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("measurements.id"))
    component_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("measurement_components.id"))
    value: Mapped[float] = mapped_column(Float)

    measurement: Mapped[Measurement] = relationship(back_populates="values")
    component: Mapped[MeasurementComponent] = relationship()

    __table_args__ = (UniqueConstraint("measurement_id", "component_id"),)
