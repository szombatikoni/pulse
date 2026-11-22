"""A NICE-kiértékelés végpontjának sémái (M3, K2). Magyarázó mondat nincs
benne: azt a felület rakja össze a számokból (D12)."""

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.services.nice import NiceEvaluation, NiceResult


class NicePeriodOut(BaseModel):
    start: datetime = Field(description="Az időszak kezdete (zárt), helyi eltolással.")
    end: datetime = Field(description="Az időszak vége (nyitott), helyi eltolással.")
    start_closed: bool = True
    end_closed: bool = False


class NiceResultOut(BaseModel):
    """Egy számítás eredménye; a két oldal (CQL, saját) ugyanezekkel a mezőkkel."""

    excluded_first_day: date | None = Field(description="A kizárt első nap (null: nincs).")
    excluded_reading_ids: list[str]
    included_reading_ids: list[str]
    included_days: list[date]
    included_day_count: int | None
    enough_data: bool | None
    mean_systolic: float | None
    mean_diastolic: float | None
    age_in_years: int | None
    target_systolic: float | None
    target_diastolic: float | None
    target_met: bool | None = Field(description="null = nincs elég adat (sosem kedvező).")


class NiceEvaluationOut(BaseModel):
    patient_id: uuid.UUID
    evaluation_time: datetime
    period: NicePeriodOut
    parameters: dict[str, Any] = Field(
        description="A szolgáltatásnak átadott paraméterek, a CQL nevével (a Series Period is)."
    )
    cql: NiceResultOut = Field(description="A CQL-motor eredménye (a szolgáltatás válaszából).")
    own: NiceResultOut = Field(description="A PULSE saját számítása (pontos törtekkel).")
    matches: bool
    mismatched_fields: list[str] = Field(
        description="Az eltérő mezők (az átlagoknál 1e-9 tűréssel, a többinél pontosan)."
    )
    library: dict[str, Any] = Field(description="A CQL-könyvtár (id, version, sha256), továbbadva.")
    engine: dict[str, Any] = Field(description="A motor verziói, továbbadva.")
    duration_ms: float | None = Field(description="A kiértékelés ideje a szolgáltatásban (ms).")


def _float(value: Any) -> float | None:
    return None if value is None else float(value)


def result_out(result: NiceResult) -> NiceResultOut:
    return NiceResultOut(
        excluded_first_day=result.excluded_first_day,
        excluded_reading_ids=result.excluded_reading_ids,
        included_reading_ids=result.included_reading_ids,
        included_days=result.included_days,
        included_day_count=result.included_day_count,
        enough_data=result.enough_data,
        mean_systolic=_float(result.mean_systolic),
        mean_diastolic=_float(result.mean_diastolic),
        age_in_years=result.age_in_years,
        target_systolic=_float(result.target_systolic),
        target_diastolic=_float(result.target_diastolic),
        target_met=result.target_met,
    )


def evaluation_out(patient_id: uuid.UUID, evaluation: NiceEvaluation) -> NiceEvaluationOut:
    return NiceEvaluationOut(
        patient_id=patient_id,
        evaluation_time=evaluation.evaluation_time,
        period=NicePeriodOut(start=evaluation.period.start, end=evaluation.period.end),
        parameters=evaluation.parameters,
        cql=result_out(evaluation.cql),
        own=result_out(evaluation.own),
        matches=evaluation.matches,
        mismatched_fields=evaluation.mismatched_fields,
        library=evaluation.library,
        engine=evaluation.engine,
        duration_ms=evaluation.duration_ms,
    )
