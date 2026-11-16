"""A NICE-szerinti vérnyomásátlag saját számítása és az összevetés (M3, K2):
a tiszta számítás a kézi csomag 7 forgatókönyvén (az M2-es motor-eredmény az
elvárás), az időszak (7 lezárt nap, a mai nélkül) szélei (határon lévő mérés,
budapesti napváltás, óraátállás), az első nap kizárása, a kevés nap, a javított
mérés, az életkor szerinti célérték (február 29. is), a motornak küldött
szűkített csomag, a CQL-válasz értelmezése, az eltérő mezők listája, és hogy a
kiértékelés semmit nem ír. Az ELM és a CQL-forrás egyezését is ellenőrzi."""

import json
import re
import uuid
from datetime import UTC, date, datetime, timedelta
from fractions import Fraction
from pathlib import Path

import pytest
from sqlalchemy import event, func, select

from app.core.config import settings
from app.models import (
    Alert,
    AlertEvent,
    Measurement,
    MeasurementType,
    MeasurementValue,
    Notification,
)
from app.services.cql_client import CqlServiceError
from app.services.measurements import correct_measurement, record_measurement
from app.services.nice import (
    BP_PANEL,
    COMPARED_FIELDS,
    NiceParams,
    NiceResult,
    Reading,
    age_in_years,
    compute,
    evaluate_patient,
    mismatched_fields,
    own_result,
    parse_cql_result,
    prepare_evaluation,
    series_period,
)
from app.services.status import compute_status
from tests.factories import assign, make_doctor, make_patient, record_bp

INTEGRATION = Path(__file__).resolve().parents[2] / "integration"
TZ = settings.tz


def local(*args) -> datetime:
    return datetime(*args, tzinfo=TZ)


def cql_json(result: NiceResult) -> dict:
    """Egy elvárt eredmény a szolgáltatás JSON-alakjában (a hamis klienshez)."""

    def num(x):
        return None if x is None else float(x)

    return {
        "excludedFirstDay": result.excluded_first_day and result.excluded_first_day.isoformat(),
        "excludedReadingIds": list(result.excluded_reading_ids),
        "includedReadingIds": list(result.included_reading_ids),
        "includedDays": [d.isoformat() for d in result.included_days],
        "includedDayCount": result.included_day_count,
        "enoughData": result.enough_data,
        "meanSystolic": num(result.mean_systolic),
        "meanDiastolic": num(result.mean_diastolic),
        "ageInYears": result.age_in_years,
        "targetSystolic": num(result.target_systolic),
        "targetDiastolic": num(result.target_diastolic),
        "targetMet": result.target_met,
    }


class EchoCql:
    """Hamis szolgáltatás: elmenti a kérést, és a megadott eredményt adja vissza
    (alapból a saját számítás eredményét, amelyet a teszt előre kiszámol)."""

    def __init__(self, result: dict | None = None):
        self.result = result
        self.payloads: list[dict] = []

    def __call__(self, payload: dict) -> dict:
        self.payloads.append(payload)
        return {
            "library": {"id": "PulseHbpmAverage", "version": "0.1.0", "sha256": "abc"},
            "engine": {"cql-execution": "3.3.2", "cql-exec-fhir": "2.2.0", "node": "v24.21.0"},
            "evaluationTime": payload["evaluationTime"],
            "result": self.result,
            "durationMs": 12.5,
        }


# --- A CQL-fájl alapértékei ----------------------------------------------------------------


def test_default_parameters_are_the_cql_defaults():
    """A backend mindent kifejezetten átad, de az alapértékeinek a CQL-fájléval
    kell egyezniük (ha a CQL változik, ez a teszt jelez)."""
    source = (INTEGRATION / "cql" / "PulseHbpmAverage.cql").read_text(encoding="utf-8")
    defaults = dict(re.findall(r'^parameter "([^"]+)" [\w<>]+ default (.+)$', source, re.M))
    sent = NiceParams().cql_parameters()
    assert defaults.pop("Series Period") == "null"
    assert defaults.pop("Comparison Rounding Precision") == "null"
    assert "Comparison Rounding Precision" not in sent
    assert set(defaults) == set(sent)
    for name, text in defaults.items():
        expected = {"true": True, "false": False}.get(text, text.strip("'"))
        if isinstance(sent[name], bool) or isinstance(sent[name], str):
            assert sent[name] == expected, name
        else:
            assert Fraction(text) == Fraction(sent[name]), name


def _annotation_text(node) -> str:
    """Az ELM-annotáció (a fordító EnableAnnotations kapcsolója) forrásszövege."""
    if isinstance(node, dict):
        children = "".join(_annotation_text(x) for x in node.get("s", []))
        return "".join(node.get("value", [])) + children
    if isinstance(node, list):
        return "".join(_annotation_text(x) for x in node)
    return ""


def test_elm_is_compiled_from_the_cql_source():
    """Az elm/PulseHbpmAverage-0.1.0.json a .cql mostani szövegéből készült:
    az ELM a fordításkor minden elemhez eltárolja a forrásszöveget, ezeket
    összefűzve (a szóközöket egységesítve) a .cql fájlt kapjuk vissza. Az
    egyetlen kivétel a `context Patient` sor, amelyhez a fordító nem tesz
    annotációt. Ha a .cql változik, és az ELM-et nem fordítják újra, ez a teszt
    jelez (fordító nélkül; a fordítás maga a forditas.mjs dolga)."""
    elm = json.loads(
        (INTEGRATION / "elm" / "PulseHbpmAverage-0.1.0.json").read_text(encoding="utf-8")
    )["library"]
    source = (INTEGRATION / "cql" / "PulseHbpmAverage.cql").read_text(encoding="utf-8")

    def texts(node):
        return [
            _annotation_text(a["s"])
            for a in node.get("annotation", [])
            if a.get("type") == "Annotation"
        ]

    parts = texts(elm)
    for section in ("usings", "includes", "codeSystems", "codes", "parameters", "statements"):
        for item in elm.get(section, {}).get("def", []):
            parts += texts(item)

    def norm(text):
        return re.sub(r"\s+", " ", text).strip()

    assert norm(" ".join(parts)) == norm(source.replace("context Patient", "", 1))
    # A könyvtár azonosítója és a paraméterlista is ugyanaz.
    library = re.search(r"^library (\w+) version '([^']+)'$", source, re.M)
    assert (elm["identifier"]["id"], elm["identifier"]["version"]) == library.groups()
    params = re.findall(r'^parameter "([^"]+)"', source, re.M)
    assert [p["name"] for p in elm["parameters"]["def"]] == params


# --- A kézi csomag 7 forgatókönyve (integration/eredmeny/eredmeny.json) --------------------

SCENARIO_PARAMS = {
    "Exclude First Day": "exclude_first_day",
    "Both Components Must Be Below Target": "both_components_must_be_below_target",
    "Comparison Rounding Precision": "comparison_rounding_precision",
    "Min Included Days": "min_included_days",
    "First Day Definition": "first_day_definition",
}
SCENARIOS = json.loads((INTEGRATION / "eredmeny" / "eredmeny.json").read_text(encoding="utf-8"))
BUNDLE = json.loads((INTEGRATION / "adat" / "beteg_hbpm_bundle.json").read_text(encoding="utf-8"))
BIRTH_DATES = {"F-80-ev-feletti": date(1944, 3, 14)}


def bundle_readings(low: datetime, high: datetime) -> list[Reading]:
    """A kézi csomag vérnyomásmérései az időszakban, a helyi nappal (a tárolt
    eltolás szerint, mint a CQL `date from`)."""
    readings = []
    for entry in BUNDLE["entry"]:
        r = entry["resource"]
        if r["resourceType"] != "Observation":
            continue
        at = datetime.fromisoformat(r["effectiveDateTime"])
        if not low <= at < high:
            continue
        values = {
            c["code"]["coding"][0]["code"]: Fraction(str(c["valueQuantity"]["value"]))
            for c in r["component"]
        }
        readings.append(Reading(r["id"], at.date(), values["8480-6"], values["8462-4"]))
    return readings


@pytest.mark.parametrize("scenario", SCENARIOS["forgatokonyvek"], ids=lambda s: s["id"])
def test_scenarios_of_the_manual_bundle_match_the_engine(scenario):
    """Ugyanaz az adat, más paraméter: a saját számítás minden mezője egyezik
    az M2-es motorfuttatás eredményével."""
    params = dict(scenario["parameterek"])
    period = params.pop("Series Period")
    assert (period["lowClosed"], period["highClosed"]) == (True, False)
    low, high = datetime.fromisoformat(period["low"]), datetime.fromisoformat(period["high"])
    nice_params = NiceParams(**{SCENARIO_PARAMS[k]: v for k, v in params.items()})
    patient = next(
        e["resource"] for e in BUNDLE["entry"] if e["resource"]["id"].startswith("pulse")
    )
    birth = BIRTH_DATES.get(scenario["id"], date.fromisoformat(patient["birthDate"]))

    own = compute(
        bundle_readings(low, high),
        birth_date=birth,
        period_start_day=low.date(),
        age_reference_day=(high - timedelta(milliseconds=1)).date(),
        params=nice_params,
    )
    engine = parse_cql_result(scenario["eredmeny"])
    assert mismatched_fields(engine, own) == []
    # A pontos tört is az, amit kézzel számolunk (A: 1620/12 és 1013/12).
    if scenario["id"] == "A-alap":
        assert (own.mean_systolic, own.mean_diastolic) == (Fraction(135), Fraction(1013, 12))
        assert own.target_met is False  # 135 nem kisebb 135-nél


# --- Tiszta számítás ----------------------------------------------------------------------


def reading(rid: str, day: date, sys: int, dia: int) -> Reading:
    return Reading(rid, day, Fraction(sys), Fraction(dia))


def test_no_readings_is_not_enough_data():
    result = compute(
        [], birth_date=date(1960, 1, 1), period_start_day=None, age_reference_day=date(2026, 11, 15)
    )
    assert result.excluded_first_day is None
    assert (result.mean_systolic, result.mean_diastolic) == (None, None)
    assert (result.included_day_count, result.enough_data, result.target_met) == (0, False, None)
    assert (result.target_systolic, result.target_diastolic) == (135, 85)


def test_min_zero_days_without_readings_gives_null_not_a_favourable_result():
    # Háromértékű logika: üres átlaggal a feltétel null, nem igaz.
    for both in (True, False):
        result = compute(
            [],
            birth_date=date(1960, 1, 1),
            period_start_day=None,
            age_reference_day=date(2026, 11, 15),
            params=NiceParams(min_included_days=0, both_components_must_be_below_target=both),
        )
        assert (result.enough_data, result.target_met) == (True, None)


def test_rounding_is_half_up_like_the_engine():
    days = [date(2026, 11, d) for d in (10, 11, 12, 13)]
    # 134,5 / 84,5 egészre kerekítve 135 / 85: a cél nem teljesül.
    readings = [reading("x", days[0], 200, 200)] + [
        Reading(f"r{i}", d, Fraction(269, 2), Fraction(169, 2)) for i, d in enumerate(days[1:])
    ]
    kw = {"birth_date": date(1960, 1, 1), "period_start_day": None}
    plain = compute(readings, age_reference_day=days[-1], **kw)
    rounded = compute(
        readings,
        age_reference_day=days[-1],
        params=NiceParams(comparison_rounding_precision=0),
        **kw,
    )
    assert plain.target_met is True and rounded.target_met is False


def test_one_component_below_is_enough_when_configured():
    days = [date(2026, 11, d) for d in (10, 11, 12, 13)]
    readings = [reading(f"r{i}", d, 140, 80) for i, d in enumerate(days)]
    kw = {"birth_date": date(1960, 1, 1), "period_start_day": None, "age_reference_day": days[-1]}
    assert compute(readings, **kw).target_met is False
    either = NiceParams(both_components_must_be_below_target=False)
    assert compute(readings, params=either, **kw).target_met is True
    both_high = [reading(f"h{i}", d, 140, 90) for i, d in enumerate(days)]
    assert compute(both_high, params=either, **kw).target_met is False


def test_unknown_first_day_definition_is_an_error():
    with pytest.raises(ValueError):
        compute(
            [],
            birth_date=date(1960, 1, 1),
            period_start_day=None,
            age_reference_day=date(2026, 11, 15),
            params=NiceParams(first_day_definition="Valami"),
        )


# --- Az időszak ---------------------------------------------------------------------------


def test_period_is_the_last_seven_closed_local_days_without_today():
    # Budapesten már nov. 15., UTC-ben még nov. 14.: a mai nap a nov. 15.
    period = series_period(datetime(2026, 11, 14, 23, 30, tzinfo=UTC))
    assert period.start.isoformat() == "2026-11-08T00:00:00+01:00"
    assert period.end.isoformat() == "2026-11-15T00:00:00+01:00"
    # Éjfél előtt egy perccel még a nov. 14. a mai nap.
    period = series_period(datetime(2026, 11, 14, 22, 59, tzinfo=UTC))
    assert period.end.isoformat() == "2026-11-14T00:00:00+01:00"


def test_period_across_the_autumn_clock_change_has_two_offsets():
    # 2026. okt. 25-én 3:00 → 2:00: a kezdet még nyári, a vég már téli idő.
    period = series_period(local(2026, 10, 28, 12))
    assert period.start.isoformat() == "2026-10-21T00:00:00+02:00"
    assert period.end.isoformat() == "2026-10-28T00:00:00+01:00"
    # A falióra szerint 7 nap, valójában 7 nap + 1 óra.
    assert period.end.astimezone(UTC) - period.start.astimezone(UTC) == timedelta(days=7, hours=1)


# --- Az adatbázisból: szélek, első nap, javítás, életkor ----------------------------------


@pytest.fixture
def patient(db, measurement_types):
    return make_patient(db)


def bp(db, patient, at, sys=130, dia=80):
    measurement, _ = record_bp(db, patient, sys, dia, at)
    return measurement


def own(db, patient, now):
    """A saját számítás eredménye, és a szolgáltatásnak küldött kérés (egy
    végponttal azonos futásból, a saját eredményt visszaadó hamis klienssel)."""
    result = own_result(db, patient.patient_profile, series_period(now), NiceParams())
    fake = EchoCql(cql_json(result))
    evaluation = evaluate_patient(db, patient.patient_profile.id, fake, now=now)
    assert evaluation.matches
    return result, fake.payloads[0]


NOW = local(2026, 11, 15, 12)  # az időszak: [nov. 8. 0:00, nov. 15. 0:00)


def test_boundary_readings(db, patient):
    """A kezdet zárt, a vég nyitott: a pont nov. 8. 0:00-s mérés bent van, az
    egy mikroszekundummal korábbi és a mai (nov. 15.) 0:00-s nincs."""
    inside = bp(db, patient, local(2026, 11, 8))
    bp(db, patient, local(2026, 11, 8) - timedelta(microseconds=1))
    bp(db, patient, local(2026, 11, 15))
    last = bp(db, patient, local(2026, 11, 14, 23, 59, 59, 999999))
    result, _ = own(db, patient, NOW)
    assert result.excluded_reading_ids == [str(inside.id)]
    assert result.included_reading_ids == [str(last.id)]


def test_todays_readings_do_not_count(db, patient):
    """A mai, még folyamatban lévő nap mérései nem számítanak bele."""
    for d in (11, 12, 13, 14):
        bp(db, patient, local(2026, 11, d, 8), 130, 80)
    today = bp(db, patient, local(2026, 11, 15, 8), 190, 120)
    result, _ = own(db, patient, NOW)
    assert str(today.id) not in result.included_reading_ids + result.excluded_reading_ids
    assert (result.mean_systolic, result.included_day_count) == (130, 3)


def test_local_day_change_is_by_budapest_time(db, patient):
    """UTC-ben nov. 9. 23:30, Budapesten már nov. 10.: a nov. 10-i nap része,
    így nem esik ki első napként a nov. 9-ivel együtt."""
    first = bp(db, patient, local(2026, 11, 9, 8))
    late = bp(db, patient, datetime(2026, 11, 9, 23, 30, tzinfo=UTC))
    result, _ = own(db, patient, NOW)
    assert result.excluded_first_day == date(2026, 11, 9)
    assert result.excluded_reading_ids == [str(first.id)]
    assert result.included_reading_ids == [str(late.id)]
    assert result.included_days == [date(2026, 11, 10)]


def test_window_across_the_clock_change(db, patient):
    """Okt. 21. 0:00 nyári idő szerint UTC 20-án 22:00: ez még bent van, az
    UTC 21:59-es (helyi okt. 20. 23:59) már nem. Az óraátállás napján (okt. 25.)
    a kétszer előforduló 2:30 két külön mérés, ugyanazon a helyi napon."""
    now = local(2026, 10, 28, 12)
    start = bp(db, patient, datetime(2026, 10, 20, 22, 0, tzinfo=UTC))
    bp(db, patient, datetime(2026, 10, 20, 21, 59, tzinfo=UTC))
    twice = [
        bp(db, patient, datetime(2026, 10, 25, 0, 30, tzinfo=UTC), 140, 90),  # 2:30 +02:00
        bp(db, patient, datetime(2026, 10, 25, 1, 30, tzinfo=UTC), 120, 70),  # 2:30 +01:00
    ]
    other = [bp(db, patient, local(2026, 10, d, 8), 130, 80) for d in (26, 27)]
    result, payload = own(db, patient, now)
    assert result.excluded_reading_ids == [str(start.id)]
    assert result.included_reading_ids == [str(m.id) for m in twice + other]
    assert result.included_days == [date(2026, 10, d) for d in (25, 26, 27)]
    assert result.mean_systolic == 130 and result.target_met is True
    assert payload["parameters"]["Series Period"] == {
        "low": "2026-10-21T00:00:00.000+02:00",
        "high": "2026-10-28T00:00:00.000+01:00",
        "lowClosed": True,
        "highClosed": False,
    }


def test_first_day_is_the_first_reading_day_inside_the_window(db, patient):
    """A legrégebbi mérés NAPJA esik ki, nem az időszak kezdőnapja, és az
    időszak előtti mérés nem számít bele (a CQL a sorozatból veszi)."""
    bp(db, patient, local(2026, 11, 5, 8))  # az időszak előtt
    first = [bp(db, patient, local(2026, 11, 11, h)) for h in (8, 20)]
    rest = [bp(db, patient, local(2026, 11, d, 8), 140, 90) for d in (12, 13, 14)]
    result, _ = own(db, patient, NOW)
    assert result.excluded_first_day == date(2026, 11, 11)
    assert result.excluded_reading_ids == [str(m.id) for m in first]
    assert result.included_reading_ids == [str(m.id) for m in rest]
    assert (result.included_day_count, result.enough_data) == (3, True)
    assert (result.mean_systolic, result.mean_diastolic) == (140, 90)
    assert result.target_met is False


def test_few_days_is_not_enough_data(db, patient):
    for d in (12, 13, 14):  # az első kiesik, két nap marad
        bp(db, patient, local(2026, 11, d, 8), 120, 70)
    result, _ = own(db, patient, NOW)
    assert (result.included_day_count, result.enough_data, result.target_met) == (2, False, None)
    assert result.mean_systolic == 120  # az átlag megvan, de nem minősít


def test_no_blood_pressure_at_all_is_not_enough_data(db, patient):
    record_measurement(
        db,
        patient_id=patient.patient_profile.id,
        type_code="heart_rate",
        values={"value": 70},
        measured_at=local(2026, 11, 12, 8),
        now=local(2026, 11, 12, 8),
    )
    result, _ = own(db, patient, NOW)
    assert result.included_reading_ids == [] and result.excluded_first_day is None
    assert result.target_met is None


def test_only_the_end_of_the_correction_chain_counts(db, patient):
    for d in (10, 11, 12):
        bp(db, patient, local(2026, 11, d, 8), 130, 80)
    original = bp(db, patient, local(2026, 11, 13, 8), 190, 110)
    pid = patient.patient_profile.id
    middle, _ = correct_measurement(
        db,
        patient_id=pid,
        measurement_id=original.id,
        values={"systolic": 180, "diastolic": 100},
        now=local(2026, 11, 13, 9),
    )
    end, _ = correct_measurement(
        db,
        patient_id=pid,
        measurement_id=middle.id,
        values={"systolic": 130.5, "diastolic": 80.5},
        now=local(2026, 11, 13, 10),
    )
    result, payload = own(db, patient, NOW)
    assert str(end.id) in result.included_reading_ids
    assert str(original.id) not in result.included_reading_ids
    assert str(middle.id) not in result.included_reading_ids
    # A nov. 10-i első nap kiesik: (130 + 130 + 130,5) / 3.
    assert result.mean_systolic == Fraction(781, 6)
    # A csomagban is csak a lánc vége van.
    ids = {e["resource"]["id"] for e in payload["bundle"]["entry"]}
    assert str(end.id) in ids and str(original.id) not in ids


@pytest.mark.parametrize(
    ("birth", "age", "target"),
    [
        (date(1946, 11, 15), 79, (135, 85)),  # ma tölti a 80-at: ez még nem számít
        (date(1946, 11, 14), 80, (145, 85)),  # tegnap, az utolsó lezárt napon töltötte
        (date(1960, 1, 1), 66, (135, 85)),
    ],
)
def test_target_depends_on_age_at_the_end_of_the_period(db, patient, birth, age, target):
    """Az életkor a sorozat végének napján (az utolsó lezárt nap, tegnap)
    számít, a 80. életévtől a célérték 145/85."""
    patient.patient_profile.birth_date = birth
    db.flush()
    for d in (11, 12, 13, 14):
        bp(db, patient, local(2026, 11, d, 8), 140, 80)
    result, _ = own(db, patient, NOW)
    assert result.age_in_years == age
    assert (result.target_systolic, result.target_diastolic) == target
    assert result.target_met is (target[0] == 145)


# --- A teljes kiértékelés (hamis klienssel) -----------------------------------------------


def test_request_to_the_service_and_matching_result(db, patient):
    for d in (10, 11, 12, 13):
        bp(db, patient, local(2026, 11, d, 8), 136, 84)
    expected, _ = own(db, patient, NOW)
    fake = EchoCql(cql_json(expected))
    evaluation = evaluate_patient(db, patient.patient_profile.id, fake, now=NOW)

    [payload] = fake.payloads
    assert payload["evaluationTime"] == "2026-11-15T12:00:00.000+01:00"
    assert payload["parameters"] == {
        "Series Period": {
            "low": "2026-11-08T00:00:00.000+01:00",
            "high": "2026-11-15T00:00:00.000+01:00",
            "lowClosed": True,
            "highClosed": False,
        },
        "Exclude First Day": True,
        "First Day Definition": "FirstReadingDay",
        "Min Included Days": 3,
        "Age Threshold Years": 80,
        "Target Systolic Below Age Threshold": 135.0,
        "Target Diastolic Below Age Threshold": 85.0,
        "Target Systolic At Or Above Age Threshold": 145.0,
        "Target Diastolic At Or Above Age Threshold": 85.0,
        "Both Components Must Be Below Target": True,
    }
    assert payload["bundle"]["resourceType"] == "Bundle"
    assert evaluation.matches and evaluation.mismatched_fields == []
    assert evaluation.library["version"] == "0.1.0" and evaluation.duration_ms == 12.5


def test_float_mean_within_tolerance_still_matches(db, patient):
    """A motor lebegőpontos átlaga a tűrésen (1e-9) belül eltérhet a törttől."""
    for d in (10, 11, 12, 13):
        bp(db, patient, local(2026, 11, d, 8), 135, 84)
    bp(db, patient, local(2026, 11, 13, 20), 135, 85)
    expected, _ = own(db, patient, NOW)
    data = cql_json(expected)
    data["meanDiastolic"] = float(expected.mean_diastolic) + 1e-12
    evaluation = evaluate_patient(db, patient.patient_profile.id, EchoCql(data), now=NOW)
    assert evaluation.matches


def test_known_difference_float_mean_at_the_target(db, patient):
    """ISMERT ELTÉRÉS (S1, kódváltoztatás nélkül rögzítve): tizedes értékeknél
    a motor lebegőpontos átlaga a célérték határán a másik oldalra eshet. A
    138,6 + 131,2 + 134,8 + 137,0 + 133,4 pontos átlaga 135 (a cél nem
    teljesül, 135 nem kisebb 135-nél), a motoré 134.99999999999997 (teljesül).
    Az átlag a tűrésen belül egyezik, a target_met nem: a felület eltérést
    mutat. A motor kimenetét a valódi szolgáltatáson mértük (2026-11-16), a
    sorrend a mérések időrendje."""
    bp(db, patient, local(2026, 11, 9, 8), 120, 80)  # az első nap, kiesik
    values = (138.6, 131.2, 134.8, 137.0, 133.4)
    for day, value in zip((10, 11, 12, 13, 14), values, strict=True):
        bp(db, patient, local(2026, 11, day, 8), value, 80)
    expected = own_result(db, patient.patient_profile, series_period(NOW), NiceParams())
    assert expected.mean_systolic == 135 and expected.target_met is False
    engine = cql_json(expected)
    engine.update(meanSystolic=134.99999999999997, targetMet=True)  # a motor válasza
    evaluation = evaluate_patient(db, patient.patient_profile.id, EchoCql(engine), now=NOW)
    assert evaluation.mismatched_fields == ["target_met"]


def test_deliberate_difference_is_listed(db, patient):
    for d in (10, 11, 12, 13):
        bp(db, patient, local(2026, 11, d, 8), 136, 84)
    expected, _ = own(db, patient, NOW)
    data = cql_json(expected)
    data["meanSystolic"] = 136.001
    data["includedReadingIds"] = data["includedReadingIds"][1:]
    evaluation = evaluate_patient(db, patient.patient_profile.id, EchoCql(data), now=NOW)
    assert not evaluation.matches
    assert evaluation.mismatched_fields == ["included_reading_ids", "mean_systolic"]


def test_reading_id_order_does_not_matter(db, patient):
    for d in (10, 11, 12, 13):
        bp(db, patient, local(2026, 11, d, 8))
    expected, _ = own(db, patient, NOW)
    data = cql_json(expected)
    data["includedReadingIds"].reverse()
    assert evaluate_patient(db, patient.patient_profile.id, EchoCql(data), now=NOW).matches


def test_every_field_is_compared():
    base = NiceResult(
        excluded_first_day=date(2026, 11, 10),
        excluded_reading_ids=["a"],
        included_reading_ids=["b"],
        included_days=[date(2026, 11, 11)],
        included_day_count=1,
        enough_data=False,
        mean_systolic=Fraction(130),
        mean_diastolic=Fraction(80),
        age_in_years=66,
        target_systolic=Fraction(135),
        target_diastolic=Fraction(85),
        target_met=None,
    )
    changed = {
        "excluded_first_day": None,
        "excluded_reading_ids": [],
        "included_reading_ids": ["c"],
        "included_days": [],
        "included_day_count": 2,
        "enough_data": True,
        "mean_systolic": None,
        "mean_diastolic": Fraction(81),
        "age_in_years": 67,
        "target_systolic": Fraction(145),
        "target_diastolic": Fraction(90),
        "target_met": False,
    }
    assert set(changed) == set(COMPARED_FIELDS)
    for name, value in changed.items():
        other = NiceResult(**{**base.__dict__, name: value})
        assert mismatched_fields(other, base) == [name]


VALID = cql_json(
    NiceResult(None, [], [], [], 0, False, None, None, 66, Fraction(135), Fraction(85), None)
)


@pytest.mark.parametrize(
    "result",
    [
        None,
        "nem objektum",
        {"targetMet": None},  # hiányzó mezők
        {**VALID, "meanSystolic": "135"},  # szöveg szám helyett
        {**VALID, "includedReadingIds": None},
        {**VALID, "includedDays": "2026-11-10"},
        {**VALID, "excludedFirstDay": "nem dátum"},
        {**VALID, "ageInYears": 66.5},
        {**VALID, "enoughData": 1},
        {**VALID, "includedDayCount": True},
        # Nem véges vagy float-ként nem ábrázolható szám (korábban 500 lett belőle).
        {**VALID, "meanSystolic": float("inf")},
        {**VALID, "meanDiastolic": json.loads("1e999")},
        {**VALID, "targetSystolic": json.loads("-Infinity")},
        {**VALID, "targetDiastolic": 10**400},
    ],
)
def test_unparsable_result_is_a_service_error(result):
    assert parse_cql_result(VALID).target_met is None  # az alap érvényes
    with pytest.raises(CqlServiceError) as error:
        parse_cql_result(result)
    assert error.value.reason == "invalid_response"


@pytest.mark.parametrize(
    "change",
    [
        {"library": None},
        {"engine": "x"},
        {"durationMs": "12"},
        {"durationMs": True},
        {"durationMs": float("inf")},
        {"durationMs": 10**400},
    ],
)
def test_missing_version_data_is_a_service_error(db, patient, change):
    expected, _ = own(db, patient, NOW)

    def fake(payload):
        return {**EchoCql(cql_json(expected))(payload), **change}

    with pytest.raises(CqlServiceError):
        evaluate_patient(db, patient.patient_profile.id, fake, now=NOW)


def test_unknown_patient_is_a_lookup_error(db):
    import uuid

    with pytest.raises(LookupError):
        evaluate_patient(db, uuid.uuid4(), EchoCql(), now=NOW)


def _snapshot(db, patient_id):
    """Az érintett táblák sorszáma és a beteg státusza."""
    counts = {
        model.__name__: db.scalar(select(func.count()).select_from(model))
        for model in (Measurement, MeasurementValue, Alert, AlertEvent, Notification)
    }
    return counts, compute_status(db, patient_id, now=NOW).status


def test_evaluation_writes_nothing(db, patient, measurement_types):
    """Nem tárol, riasztást és értesítést nem nyit, a státuszt nem változtatja:
    a táblák sorszáma és a státusz a hívás előtt és után ugyanaz, a session
    tiszta marad. A mérések kiugróak, és a CQL-oldal szándékosan eltér, hogy az
    eltérés se írjon semmit."""
    doctor = make_doctor(db)
    assign(db, doctor, patient)
    for d in (10, 11, 12, 13):
        bp(db, patient, local(2026, 11, d, 8), 190, 120)
    db.flush()
    pid = patient.patient_profile.id
    expected = own_result(db, patient.patient_profile, series_period(NOW), NiceParams())
    before = _snapshot(db, pid)
    data = cql_json(expected)
    data["targetMet"] = True
    evaluation = evaluate_patient(db, pid, EchoCql(data), now=NOW)
    assert evaluation.mismatched_fields == ["target_met"]
    assert not db.new and not db.dirty and not db.deleted
    assert _snapshot(db, pid) == before


# --- Február 29. (a motor viselkedése szerint) --------------------------------------------


@pytest.mark.parametrize(
    ("birth", "on", "age"),
    [
        (date(1944, 2, 29), date(2026, 2, 27), 81),
        (date(1944, 2, 29), date(2026, 2, 28), 82),  # nem szökőév: febr. 28. a születésnap
        (date(1944, 2, 29), date(2026, 3, 1), 82),
        (date(1948, 2, 29), date(2028, 2, 28), 79),  # szökőév: febr. 29. a születésnap
        (date(1948, 2, 29), date(2028, 2, 29), 80),
        (date(1948, 2, 29), date(2028, 3, 1), 80),
        (date(1946, 2, 28), date(2026, 2, 27), 79),
        (date(1946, 2, 28), date(2026, 2, 28), 80),
        (date(1946, 3, 1), date(2026, 2, 28), 79),
    ],
)
def test_age_matches_the_engine_on_leap_day_birthdays(birth, on, age):
    """A cql-execution AgeInYearsAt értékei (a motoron kipróbálva; a
    szolgaltatas.test.mjs ugyanezt rögzíti a valódi motoron)."""
    assert age_in_years(birth, on) == age


def test_leap_day_birthday_counts_on_february_28(db, patient):
    """2026. márc. 1-jén az időszak utolsó (lezárt) napja febr. 28.: az
    1944-02-29-i születésű ekkor már 82 éves, 82-es küszöbbel a magasabb
    célérték jár (a motor ugyanígy számol)."""
    patient.patient_profile.birth_date = date(1944, 2, 29)
    db.flush()
    period = series_period(local(2026, 3, 1, 12))
    params = NiceParams(age_threshold_years=82)
    result = own_result(db, patient.patient_profile, period, params)
    assert (result.age_in_years, result.target_systolic) == (82, 145)
    # Egy nappal korábban (utolsó lezárt nap febr. 27.) még 81.
    period = series_period(local(2026, 2, 28, 12))
    result = own_result(db, patient.patient_profile, period, params)
    assert (result.age_in_years, result.target_systolic) == (81, 135)


# --- A motornak küldött szűkített csomag --------------------------------------------------


def _bulk_bp(db, patient, start: datetime, count: int) -> None:
    """Sok régi vérnyomásmérés közvetlenül a táblákba (a rögzítés útja
    mérésenként lefuttatná a szabályokat, ami 2000 mérésnél lassú lenne)."""
    bp_type = db.scalar(select(MeasurementType).where(MeasurementType.loinc_code == BP_PANEL))
    components = {c.code: c for c in bp_type.components}
    pid = patient.patient_profile.id
    for i in range(count):
        at = start + timedelta(hours=6 * i)
        db.add(
            Measurement(
                id=uuid.uuid4(),
                patient_id=pid,
                type_id=bp_type.id,
                measured_at=at,
                recorded_at=at,
                values=[
                    MeasurementValue(component_id=components["systolic"].id, value=130),
                    MeasurementValue(component_id=components["diastolic"].id, value=80),
                ],
            )
        )
    db.flush()


def test_engine_gets_only_the_window_with_one_day_margin(db, patient):
    """2000 régi mérés mellett is kicsi a csomag (a teljes előzmény 1 MiB fölött
    413-at kapna a szolgáltatástól): csak a Patient és a vérnyomásmérések az
    időszakból, mindkét irányban 1 nap ráhagyással (az ablak széleit a CQL
    szűri); más méréstípus nem kerül bele."""
    _bulk_bp(db, patient, local(2025, 1, 1, 8), 2000)  # 500 nap, 2026. máj. közepéig
    margin_before = bp(db, patient, local(2026, 11, 7, 8))  # az ablak előtti nap
    too_early = bp(db, patient, local(2026, 11, 6, 23, 59))
    inside = [bp(db, patient, local(2026, 11, d, 8)) for d in (8, 10, 12, 14)]
    margin_after = bp(db, patient, local(2026, 11, 15, 23, 59))  # a mai nap: ráhagyás
    too_late = bp(db, patient, local(2026, 11, 16, 0, 0))
    record_measurement(
        db,
        patient_id=patient.patient_profile.id,
        type_code="heart_rate",
        values={"value": 70},
        measured_at=local(2026, 11, 12, 8),
        now=local(2026, 11, 12, 8),
    )
    fake = EchoCql(VALID)
    evaluate_patient(db, patient.patient_profile.id, fake, now=NOW)
    [payload] = fake.payloads
    entries = [e["resource"] for e in payload["bundle"]["entry"]]
    assert entries[0]["resourceType"] == "Patient"
    sent = [r["id"] for r in entries[1:]]
    assert sent == [str(m.id) for m in [margin_before, *inside, margin_after]]
    assert str(too_early.id) not in sent and str(too_late.id) not in sent
    assert all(r["code"]["coding"][0]["code"] == BP_PANEL for r in entries[1:])
    assert len(json.dumps(payload).encode()) < 20_000


def test_bundle_and_own_result_come_from_one_query(db, patient):
    """A mérések EGY lekérdezéssel töltődnek be (ablak ± 1 nap), és ebből épül a
    csomag és a saját számítás is: párhuzamos rögzítésnél sem láthatnak más
    halmazt. A saját számításba bevont (és kizárt első napi) mérések mind a
    csomagban vannak."""
    bp(db, patient, local(2026, 11, 7, 8))  # ráhagyás: csak a csomagba
    window = [bp(db, patient, local(2026, 11, d, 8), 140, 90) for d in (9, 10, 12, 14)]
    bp(db, patient, local(2026, 11, 15, 8))  # a mai nap: csak a csomagba
    db.flush()

    statements = []

    def count(conn, cursor, statement, *args):
        if re.search(r"\bFROM measurements\b", statement):
            statements.append(statement)

    connection = db.connection()
    event.listen(connection, "before_cursor_execute", count)
    try:
        prepared = prepare_evaluation(db, patient.patient_profile.id, now=NOW)
    finally:
        event.remove(connection, "before_cursor_execute", count)

    assert len(statements) == 1
    used = prepared.own.excluded_reading_ids + prepared.own.included_reading_ids
    assert used == [str(m.id) for m in window]
    sent = {
        e["resource"]["id"]
        for e in prepared.request["bundle"]["entry"]
        if e["resource"]["resourceType"] == "Observation"
    }
    assert set(used) <= sent and len(sent) == 6
