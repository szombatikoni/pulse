import uuid
from datetime import datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.models import Measurement, MeasurementType


class ComponentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str
    loinc_code: str
    unit: str = Field(description="UCUM-egységkód, pl. mm[Hg].")
    min_value: float
    max_value: float


class MeasurementTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str
    loinc_code: str
    components: list[ComponentOut]


class MeasurementCreate(BaseModel):
    type_code: str = Field(max_length=50, examples=["blood_pressure"])
    # Időzónával együtt kell megadni, hogy a mérés ideje egyértelmű legyen.
    measured_at: AwareDatetime
    values: dict[str, float] = Field(
        min_length=1, max_length=10, examples=[{"systolic": 152, "diastolic": 95}]
    )


class ValueOut(BaseModel):
    component: str
    value: float
    unit: str


class MeasurementOut(BaseModel):
    id: uuid.UUID
    type_code: str
    measured_at: datetime
    recorded_at: datetime
    values: list[ValueOut]


def measurement_out(measurement: Measurement) -> MeasurementOut:
    values = sorted(measurement.values, key=lambda v: v.component.order_no)
    return MeasurementOut(
        id=measurement.id,
        type_code=measurement.type.code,
        measured_at=measurement.measured_at,
        recorded_at=measurement.recorded_at,
        values=[
            ValueOut(component=v.component.code, value=v.value, unit=v.component.unit)
            for v in values
        ],
    )


def measurement_type_out(measurement_type: MeasurementType) -> MeasurementTypeOut:
    return MeasurementTypeOut.model_validate(measurement_type)
