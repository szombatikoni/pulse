import uuid
from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.models import AssignmentTarget, Frequency
from app.services.plans import PlanEntry, PlanParams


class PlanParamsIn(BaseModel):
    """Az előírás paraméterei; a modell ellenőrzéseivel összhangban (N naponta
    csak pozitív időközzel, napi és heti előírásnál időköz nélkül)."""

    frequency: Frequency
    interval_days: int | None = Field(default=None, ge=1, le=365)
    due_time: time = Field(examples=["10:00"])
    suggested_time: time | None = Field(default=None, examples=["07:30"])
    # Üresen új előírásnál a mai nap, módosításnál a mai nap (vagy a még el nem
    # kezdett régi kezdete). Múltbeli kezdet nem adható meg.
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def check_interval(self) -> "PlanParamsIn":
        if self.frequency is Frequency.EVERY_N_DAYS and self.interval_days is None:
            raise ValueError("N napos előírásnál kötelező az időköz (interval_days)")
        if self.frequency is not Frequency.EVERY_N_DAYS and self.interval_days is not None:
            raise ValueError("időköz (interval_days) csak N napos előírásnál adható meg")
        return self

    def params(self) -> PlanParams:
        return PlanParams(
            frequency=self.frequency,
            interval_days=self.interval_days,
            due_time=self.due_time,
            suggested_time=self.suggested_time,
            start_date=self.start_date,
            end_date=self.end_date,
        )


class AssignmentCreate(PlanParamsIn):
    kind: AssignmentTarget
    # A méréstípus vagy a kérdőív kódja, a kind szerint.
    code: str = Field(min_length=1, max_length=50, examples=["blood_pressure"])


class AssignmentReplace(PlanParamsIn):
    """Módosítás: a cél a régi előírásé, csak a paraméterek újak."""


class AssignmentOut(BaseModel):
    id: uuid.UUID
    kind: AssignmentTarget
    code: str
    name: str
    frequency: Frequency
    interval_days: int | None
    due_time: time
    suggested_time: time | None
    start_date: date
    end_date: date | None
    revoked_at: datetime | None
    assigned_by: str = Field(description="Az előíró orvos neve.")
    status: Literal["active", "upcoming", "ended", "revoked"]
    # Módosításnál az az előírás, amely ennek a helyébe lépett (az adatból
    # kiolvasva: ugyanaz a cél, és a kezdete ott van, ahol ez véget ért).
    replaced_by: uuid.UUID | None


def assignment_out(entry: PlanEntry) -> AssignmentOut:
    a = entry.assignment
    return AssignmentOut(
        id=a.id,
        kind=a.target_kind,
        code=entry.code,
        name=entry.name,
        frequency=a.frequency,
        interval_days=a.interval_days,
        due_time=a.due_time,
        suggested_time=a.suggested_time,
        start_date=a.start_date,
        end_date=a.end_date,
        revoked_at=a.revoked_at,
        assigned_by=entry.assigned_by,
        status=entry.status,
        replaced_by=entry.replaced_by,
    )
