"""NICE NG136 szerinti otthoni vérnyomásátlag: a PULSE saját számítása és az
összevetés a CQL-szolgáltatás eredményével (M3, K2, (A) mélység: gombos
kiértékelés, tárolás nélkül).

A szabály forrása az integration/cql/PulseHbpmAverage.cql (0.1.0); ez a modul
ugyanazt számolja Pythonban, pontos törtekkel (fractions.Fraction), az
adatbázis érvényes (nem felülírt) vérnyomásméréseiből. A logika a K1 független
ellenőrzéséé (integration/ellenorzes/kiadas_ellenorzes.py, nice_ellenorzes),
két ponton a CQL-fájlt követve, nem azt:

- az „első nap" az IDŐSZAKON BELÜLI első mérés napja (a CQL a sorozat, azaz a
  Series Period méréseiből veszi a minimumot);
- az életkor a sorozat végének napján számít (`date from end of "Series
  Period"`); a félig nyílt [kezdet, vég) időszak vége a cql-execution szerint a
  vég előtti ezredmásodperc, így a napja a vég előtti nap, azaz az utolsó
  lezárt nap (tegnap). A február 29-i születésnap nem szökőévben február 28-án
  számít betöltöttnek, mint a motorban (age_in_years).

Időszak (a hallgató döntése, D2b, a 7 nap a NICE-hoz igazítva): az utolsó 7
LEZÁRT helyi naptári nap, [ma-7 0:00, ma 0:00) a settings.tz szerint; a mai,
még folyamatban lévő nap nem számít bele. Az első nap kizárva, legalább 3
figyelembe vett nap kell (a CQL alapértékei). A NICE egyszeri sorozatról szól,
itt az ablak gördül: a legrégebbi mérést tartalmazó nap minden futásnál kiesik.

A motor nem a beteg teljes előzményét kapja, hanem egy szűkített csomagot: a
Patient és a vérnyomásmérések az időszakból, mindkét irányban 1 nap
ráhagyással (BUNDLE_MARGIN), hogy az ablakszéleken a szűrést valóban a CQL
végezze, és a csomag a szolgáltatás 1 MiB-os korlátja alatt maradjon.

Semmit nem tárol, riasztást nem nyit, státuszt nem változtat.
"""

import math
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from fractions import Fraction
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models import (
    Measurement,
    MeasurementType,
    MeasurementValue,
    PatientProfile,
    not_superseded,
)
from app.services.cql_client import CqlServiceError
from app.services.fhir import measurement_bundle

# A vérnyomás-panel és a két érték LOINC-kódja, és az egység (UCUM), mint a
# CQL-ben: csak az a mérés számít, amelyben mindkét érték megvan Hgmm-ben.
BP_PANEL = "85354-9"
SYSTOLIC = "8480-6"
DIASTOLIC = "8462-4"
MMHG = "mm[Hg]"

# Az időszak hossza napban: ennyi lezárt nap, a mai nélkül (D2b).
WINDOW_DAYS = 7

# A motornak küldött csomag ráhagyása az időszak két szélén.
BUNDLE_MARGIN = timedelta(days=1)

# Az átlagok egyezésének tűrése: a motor lebegőpontosan számol, mi törtekkel.
# Ismert eltérés (S1): tizedes értékeknél, ha a pontos átlag éppen a célérték,
# a motor lebegőpontos átlaga a határ másik oldalára eshet (pl. 138,6, 131,2,
# 134,8, 137,0, 133,4: pontosan 135, a motornál 134.99999999999997), így a
# target_met eltér, és a felület eltérést mutat. Szándékosan nem simítjuk el
# (test_known_difference_float_mean_at_the_target).
MEAN_TOLERANCE = Fraction(1, 10**9)

FIRST_READING_DAY = "FirstReadingDay"
PERIOD_START_DAY = "PeriodStartDay"


@dataclass(frozen=True)
class NiceParams:
    """A CQL-könyvtár paraméterei a CQL alapértékeivel (a nevük a CQL-ben
    zárójelben). A backend mindet kifejezetten átadja a szolgáltatásnak, így a
    két oldal biztosan ugyanazzal számol; a CQL-fájl alapértékeivel való
    egyezést egy teszt őrzi."""

    exclude_first_day: bool = True  # "Exclude First Day"
    first_day_definition: str = FIRST_READING_DAY  # "First Day Definition"
    min_included_days: int = 3  # "Min Included Days"
    age_threshold_years: int = 80  # "Age Threshold Years"
    target_systolic_below: Fraction = Fraction(135)
    target_diastolic_below: Fraction = Fraction(85)
    target_systolic_at_or_above: Fraction = Fraction(145)
    target_diastolic_at_or_above: Fraction = Fraction(85)
    both_components_must_be_below_target: bool = True
    comparison_rounding_precision: int | None = None  # null = nincs kerekítés

    def cql_parameters(self) -> dict[str, Any]:
        """A paraméterek a CQL nevével, JSON-értékkel (a null értékű kimarad,
        mert a CQL alapértéke úgyis null)."""
        values: dict[str, Any] = {
            "Exclude First Day": self.exclude_first_day,
            "First Day Definition": self.first_day_definition,
            "Min Included Days": self.min_included_days,
            "Age Threshold Years": self.age_threshold_years,
            "Target Systolic Below Age Threshold": float(self.target_systolic_below),
            "Target Diastolic Below Age Threshold": float(self.target_diastolic_below),
            "Target Systolic At Or Above Age Threshold": float(self.target_systolic_at_or_above),
            "Target Diastolic At Or Above Age Threshold": float(self.target_diastolic_at_or_above),
            "Both Components Must Be Below Target": self.both_components_must_be_below_target,
            "Comparison Rounding Precision": self.comparison_rounding_precision,
        }
        return {k: v for k, v in values.items() if v is not None}


@dataclass(frozen=True)
class Reading:
    """Egy érvényes vérnyomásmérés a számításhoz: azonosító, helyi nap, értékek."""

    id: str
    local_day: date
    systolic: Fraction
    diastolic: Fraction


@dataclass(frozen=True)
class Period:
    """A sorozat időszaka: [start, end), helyi eltolással."""

    start: datetime
    end: datetime


@dataclass
class NiceResult:
    """A szabály eredménye (a CQL `Evaluation Result` mezőinek részhalmaza).
    Az átlagok és a célértékek törtek; a target_met None = nincs elég adat."""

    excluded_first_day: date | None
    excluded_reading_ids: list[str]
    included_reading_ids: list[str]
    included_days: list[date]
    included_day_count: int
    enough_data: bool
    mean_systolic: Fraction | None
    mean_diastolic: Fraction | None
    age_in_years: int | None
    target_systolic: Fraction | None
    target_diastolic: Fraction | None
    target_met: bool | None


# A mezők, amelyeket az összevetés néz (a felület ebben a sorrendben írja ki).
COMPARED_FIELDS = (
    "excluded_first_day",
    "excluded_reading_ids",
    "included_reading_ids",
    "included_days",
    "included_day_count",
    "enough_data",
    "mean_systolic",
    "mean_diastolic",
    "age_in_years",
    "target_systolic",
    "target_diastolic",
    "target_met",
)
MEAN_FIELDS = {"mean_systolic", "mean_diastolic"}
ID_FIELDS = {"excluded_reading_ids", "included_reading_ids"}


def age_in_years(birth_date: date, on: date) -> int:
    """Betöltött életkor az adott napon, a cql-execution AgeInYearsAt szerint:
    a február 29-én születettnél nem szökőévben február 28. a születésnap
    (a motoron kipróbálva: 1944-02-29 2026-02-28-án már 82 éves)."""
    try:
        birthday = birth_date.replace(year=on.year)
    except ValueError:  # február 29., nem szökőév
        birthday = date(on.year, 2, 28)
    return on.year - birth_date.year - (on < birthday)


def _round_half_up(value: Fraction, precision: int) -> Fraction:
    """A cql-execution kerekítése (Math.round: a fél felfelé)."""
    scale = Fraction(10) ** precision
    return Fraction(math.floor(value * scale + Fraction(1, 2))) / scale


def _and(a: bool | None, b: bool | None) -> bool | None:
    """Háromértékű ÉS, mint a CQL-ben."""
    if a is False or b is False:
        return False
    if a is None or b is None:
        return None
    return True


def _or(a: bool | None, b: bool | None) -> bool | None:
    """Háromértékű VAGY, mint a CQL-ben."""
    if a is True or b is True:
        return True
    if a is None or b is None:
        return None
    return False


def _below(value: Fraction | None, target: Fraction) -> bool | None:
    return None if value is None else value < target


def compute(
    readings: list[Reading],
    *,
    birth_date: date,
    period_start_day: date | None,
    age_reference_day: date,
    params: NiceParams | None = None,
) -> NiceResult:
    """A szabály a már időszakra szűrt, érvényes mérésekből. Tiszta függvény
    (adatbázis nélkül), így a kézi csomag forgatókönyvein is futtatható."""
    params = params or NiceParams()
    if not params.exclude_first_day:
        excluded_day = None
    elif params.first_day_definition == PERIOD_START_DAY:
        excluded_day = period_start_day
    elif params.first_day_definition == FIRST_READING_DAY:
        excluded_day = min((r.local_day for r in readings), default=None)
    else:
        raise ValueError(f"Ismeretlen First Day Definition: {params.first_day_definition}")

    if excluded_day is None:
        first_day, included = [], list(readings)
    else:
        first_day = [r for r in readings if r.local_day <= excluded_day]
        included = [r for r in readings if r.local_day > excluded_day]

    mean_sys = (
        sum((r.systolic for r in included), Fraction(0)) / len(included) if included else None
    )
    mean_dia = (
        sum((r.diastolic for r in included), Fraction(0)) / len(included) if included else None
    )
    days = sorted({r.local_day for r in included})
    enough = len(days) >= params.min_included_days

    age = age_in_years(birth_date, age_reference_day)
    if age >= params.age_threshold_years:
        target_sys, target_dia = (
            params.target_systolic_at_or_above,
            params.target_diastolic_at_or_above,
        )
    else:
        target_sys, target_dia = params.target_systolic_below, params.target_diastolic_below

    precision = params.comparison_rounding_precision
    compared_sys, compared_dia = mean_sys, mean_dia
    if precision is not None:
        compared_sys = None if mean_sys is None else _round_half_up(mean_sys, precision)
        compared_dia = None if mean_dia is None else _round_half_up(mean_dia, precision)
    sys_below, dia_below = _below(compared_sys, target_sys), _below(compared_dia, target_dia)
    if not enough:
        target_met = None
    elif params.both_components_must_be_below_target:
        target_met = _and(sys_below, dia_below)
    else:
        target_met = _or(sys_below, dia_below)

    return NiceResult(
        excluded_first_day=excluded_day,
        excluded_reading_ids=[r.id for r in first_day],
        included_reading_ids=[r.id for r in included],
        included_days=days,
        included_day_count=len(days),
        enough_data=enough,
        mean_systolic=mean_sys,
        mean_diastolic=mean_dia,
        age_in_years=age,
        target_systolic=target_sys,
        target_diastolic=target_dia,
        target_met=target_met,
    )


def series_period(now: datetime | None = None) -> Period:
    """Az utolsó 7 lezárt helyi nap, a mai nélkül: [ma-7 0:00, ma 0:00), a
    rendszer időzónájában. A két határ eltolása óraátállás körül eltérhet (az
    éjfél Budapesten mindig létezik, az átállás hajnali 2 és 3 óra között van)."""
    today = (now or datetime.now(UTC)).astimezone(settings.tz).date()
    return Period(
        start=datetime.combine(today - timedelta(days=WINDOW_DAYS), time(), settings.tz),
        end=datetime.combine(today, time(), settings.tz),
    )


def cql_datetime(at: datetime) -> str:
    """Időpont a szolgáltatásnak: helyi eltolással, ezredmásodpercig (mint a
    futtatas.mjs rögzített időpontjai)."""
    return at.astimezone(settings.tz).isoformat(timespec="milliseconds")


def load_measurements(
    db: Session, patient_id: uuid.UUID, start: datetime, end: datetime
) -> list[Measurement]:
    """A beteg érvényes vérnyomásmérései a [start, end) időszakból: a felülírt
    (javított) mérés nélkül (not_superseded), a mérés ideje szerint, a típusukkal
    és az értékeikkel együtt (a FHIR-leképezéshez is). A kiértékelés EGYSZER
    hívja (ablak ± BUNDLE_MARGIN), és ebből a listából épül a motor csomagja és
    a saját számítás is, így párhuzamos rögzítésnél sem láthatnak más halmazt."""
    return list(
        db.scalars(
            select(Measurement)
            .join(MeasurementType, MeasurementType.id == Measurement.type_id)
            .where(
                Measurement.patient_id == patient_id,
                MeasurementType.loinc_code == BP_PANEL,
                Measurement.measured_at >= start,
                Measurement.measured_at < end,
                not_superseded(),
            )
            .options(
                selectinload(Measurement.type).selectinload(MeasurementType.components),
                selectinload(Measurement.values).selectinload(MeasurementValue.component),
            )
            .order_by(Measurement.measured_at, Measurement.id)
        ).all()
    )


def readings_in(measurements: Sequence[Measurement], period: Period) -> list[Reading]:
    """A betöltött mérésekből az időszakba esők (félig nyílt: [start, end), mint
    az adatbázis-szűrés), a sorrendet megtartva. Csak az a mérés számít, amelyben
    a szisztolés és a diasztolés érték is megvan Hgmm-ben (a CQL "Valid
    Readings" definíciója)."""
    readings = []
    for m in measurements:
        if not period.start <= m.measured_at < period.end:
            continue
        values = {
            v.component.loinc_code: Fraction(str(v.value))
            for v in m.values
            if v.component.unit == MMHG
        }
        if SYSTOLIC in values and DIASTOLIC in values:
            readings.append(
                Reading(
                    id=str(m.id),
                    local_day=m.measured_at.astimezone(settings.tz).date(),
                    systolic=values[SYSTOLIC],
                    diastolic=values[DIASTOLIC],
                )
            )
    return readings


def load_readings(db: Session, patient_id: uuid.UUID, period: Period) -> list[Reading]:
    """A beteg érvényes vérnyomásmérései az időszakban (a saját számítás
    bemenete, ha csak ez kell)."""
    return readings_in(load_measurements(db, patient_id, period.start, period.end), period)


def own_result(
    db: Session, patient: PatientProfile, period: Period, params: NiceParams
) -> NiceResult:
    """A saját számítás az adatbázisból."""
    return own_result_from(load_readings(db, patient.id, period), patient, period, params)


def own_result_from(
    readings: list[Reading], patient: PatientProfile, period: Period, params: NiceParams
) -> NiceResult:
    """A saját számítás a már időszakra szűrt mérésekből. Az életkor a sorozat
    végének napján: a félig nyílt időszak vége a cql-execution szerint
    end - 1 ms (tegnap)."""
    return compute(
        readings,
        birth_date=patient.birth_date,
        period_start_day=period.start.date(),
        age_reference_day=(period.end - timedelta(milliseconds=1)).date(),
        params=params,
    )


def _fraction(value: Any) -> Fraction | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"szám kell: {value!r}")
    # Véges, lebegőpontosan is ábrázolható szám kell (a válasz float-ként megy
    # tovább): Infinity és 1e999 (a json.loads szerint inf) ValueError, az
    # óriási egész float()-ja OverflowError.
    if not math.isfinite(float(value)):
        raise ValueError(f"nem véges szám: {value!r}")
    return Fraction(value)


def _id_list(value: Any) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        raise TypeError(f"azonosítólista kell: {value!r}")
    return value


def _optional(value: Any, kind: type[bool] | type[int]) -> Any:
    """Null vagy a megadott típus (a bool nem számít egésznek)."""
    if value is None:
        return None
    ok = isinstance(value, bool) if kind is bool else type(value) is int
    if not ok:
        raise TypeError(f"{kind.__name__} kell: {value!r}")
    return value


def parse_cql_result(result: Any) -> NiceResult:
    """A szolgáltatás `result` mezője (a CQL `Evaluation Result` JSON-alakja)
    NiceResult-ként. Hiányzó mező vagy rossz típus: CqlServiceError
    (invalid_response), mert az ilyen választ nem lehet összevetni."""
    try:
        if not isinstance(result, dict):
            raise TypeError("a result nem objektum")
        first = result["excludedFirstDay"]
        days = result["includedDays"]
        if not isinstance(days, list):
            raise TypeError(f"a napok listája kell: {days!r}")
        return NiceResult(
            excluded_first_day=None if first is None else date.fromisoformat(first),
            excluded_reading_ids=_id_list(result["excludedReadingIds"]),
            included_reading_ids=_id_list(result["includedReadingIds"]),
            included_days=[date.fromisoformat(d) for d in days],
            included_day_count=_optional(result["includedDayCount"], int),
            enough_data=_optional(result["enoughData"], bool),
            mean_systolic=_fraction(result["meanSystolic"]),
            mean_diastolic=_fraction(result["meanDiastolic"]),
            age_in_years=_optional(result["ageInYears"], int),
            target_systolic=_fraction(result["targetSystolic"]),
            target_diastolic=_fraction(result["targetDiastolic"]),
            target_met=_optional(result["targetMet"], bool),
        )
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        raise CqlServiceError("invalid_response", f"a result nem értelmezhető: {error}") from error


def mismatched_fields(cql: NiceResult, own: NiceResult) -> list[str]:
    """Az eltérő mezők neve. Az átlagoknál 1e-9 tűréssel (a motor lebegőpontos),
    az azonosítólistáknál sorrendtől függetlenül, a többinél pontosan."""
    different = []
    for name in COMPARED_FIELDS:
        a, b = getattr(cql, name), getattr(own, name)
        if name in MEAN_FIELDS:
            same = (a is None and b is None) or (
                a is not None and b is not None and abs(a - b) < MEAN_TOLERANCE
            )
        elif name in ID_FIELDS:
            same = sorted(a) == sorted(b)
        else:
            same = a == b
        if not same:
            different.append(name)
    return different


@dataclass
class NiceEvaluation:
    """A végpont eredménye: az alkalmazott időszak és paraméterek, a két
    számítás, az összevetés, és a szolgáltatás verzióadatai (továbbadva)."""

    evaluation_time: datetime
    period: Period
    parameters: dict[str, Any]
    cql: NiceResult
    own: NiceResult
    mismatched_fields: list[str]
    library: dict[str, Any]
    engine: dict[str, Any]
    duration_ms: float | None

    @property
    def matches(self) -> bool:
        return not self.mismatched_fields


CqlEvaluate = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass
class PreparedEvaluation:
    """Az adatbázisból kiolvasott rész: az időszak, a paraméterek, a saját
    számítás és a szolgáltatásnak szóló kérés. Ezután az adatbázisra már nincs
    szükség, így a hívó a HTTP-hívás előtt lezárhatja a tranzakciót."""

    now: datetime
    period: Period
    parameters: dict[str, Any]
    own: NiceResult
    request: dict[str, Any]


def prepare_evaluation(
    db: Session,
    patient_id: uuid.UUID,
    now: datetime | None = None,
    params: NiceParams | None = None,
) -> PreparedEvaluation:
    """A kiértékelés adatbázis-oldali része (csak olvas). A motor szűkített
    csomagot kap: Patient + a vérnyomásmérések az időszakból, BUNDLE_MARGIN
    ráhagyással (a felülírt mérések nélkül)."""
    now = now or datetime.now(UTC)
    params = params or NiceParams()
    patient = db.get(PatientProfile, patient_id)
    if patient is None:
        raise LookupError(f"Nincs ilyen beteg: {patient_id}")
    period = series_period(now)
    # Egyetlen lekérdezés: a csomag és a saját számítás ugyanabból a listából.
    measurements = load_measurements(
        db, patient.id, period.start - BUNDLE_MARGIN, period.end + BUNDLE_MARGIN
    )
    own = own_result_from(readings_in(measurements, period), patient, period, params)

    parameters = {
        "Series Period": {
            "low": cql_datetime(period.start),
            "high": cql_datetime(period.end),
            "lowClosed": True,
            "highClosed": False,
        },
        **params.cql_parameters(),
    }
    bundle = measurement_bundle(patient, measurements, now=now)
    request = {"bundle": bundle, "parameters": parameters, "evaluationTime": cql_datetime(now)}
    return PreparedEvaluation(now, period, parameters, own, request)


def finish_evaluation(prepared: PreparedEvaluation, response: dict[str, Any]) -> NiceEvaluation:
    """A szolgáltatás válaszának értelmezése és az összevetés (adatbázis nélkül)."""
    cql = parse_cql_result(response.get("result"))
    library, engine = response.get("library"), response.get("engine")
    duration = response.get("durationMs")
    if not isinstance(library, dict) or not isinstance(engine, dict):
        raise CqlServiceError("invalid_response", "hiányzik a library vagy az engine")
    try:
        _fraction(duration)  # null, vagy véges szám (mint az átlagoknál)
    except (TypeError, ValueError, OverflowError) as error:
        raise CqlServiceError("invalid_response", "a durationMs nem véges szám") from error
    return NiceEvaluation(
        evaluation_time=prepared.now.astimezone(settings.tz),
        period=prepared.period,
        parameters=prepared.parameters,
        cql=cql,
        own=prepared.own,
        mismatched_fields=mismatched_fields(cql, prepared.own),
        library=library,
        engine=engine,
        duration_ms=duration,
    )


def evaluate_patient(
    db: Session,
    patient_id: uuid.UUID,
    cql_evaluate: CqlEvaluate,
    now: datetime | None = None,
    params: NiceParams | None = None,
) -> NiceEvaluation:
    """A beteg NICE-kiértékelése mindkét úton. A jogosultságot a hívó
    ellenőrzi. A szolgáltatás hibája CqlServiceError (a végpont 503-at ad);
    vérnyomás-méréstípus vagy mérés hiánya nem hiba, hanem „nincs elég adat".
    A végpont a két lépést külön hívja, hogy közben lezárja a tranzakciót."""
    prepared = prepare_evaluation(db, patient_id, now, params)
    return finish_evaluation(prepared, cql_evaluate(prepared.request))
