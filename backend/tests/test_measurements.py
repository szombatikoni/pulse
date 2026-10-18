"""Mérésrögzítés a szolgáltatásrétegben (F4, F7): érvényesség és tárolás."""

from datetime import UTC, datetime, timedelta

import pytest

from app.services.measurements import (
    CLOCK_SKEW,
    MAX_BACKDATE,
    MeasurementError,
    list_measurements,
    list_types,
    record_measurement,
)
from tests.factories import make_patient

NOW = datetime(2026, 10, 12, 8, 0, tzinfo=UTC)


@pytest.fixture
def patient(db, measurement_types):
    return make_patient(db)


def record(db, patient, values=None, measured_at=NOW, type_code="blood_pressure"):
    return record_measurement(
        db,
        patient_id=patient.patient_profile.id,
        type_code=type_code,
        values=values if values is not None else {"systolic": 128, "diastolic": 82},
        measured_at=measured_at,
        now=NOW,
    )


def error_code(excinfo) -> str:
    return excinfo.value.code


def test_types_have_loinc_and_ucum_codes(db, measurement_types):
    types = {t.code: t for t in list_types(db)}
    assert set(types) == {"blood_pressure", "heart_rate", "body_weight", "blood_glucose"}
    bp = types["blood_pressure"]
    assert bp.loinc_code == "85354-9"
    assert [(c.code, c.loinc_code, c.unit) for c in bp.components] == [
        ("systolic", "8480-6", "mm[Hg]"),
        ("diastolic", "8462-4", "mm[Hg]"),
    ]
    assert types["heart_rate"].components[0].unit == "/min"
    assert types["blood_glucose"].loinc_code == "14743-9"


def test_blood_pressure_is_stored_as_two_values(db, patient):
    measurement, _ = record(db, patient, {"systolic": 131, "diastolic": 84})
    stored = {v.component.code: v.value for v in measurement.values}
    assert stored == {"systolic": 131, "diastolic": 84}
    assert measurement.recorded_at == NOW


def test_single_value_type(db, patient):
    measurement, _ = record(db, patient, {"value": 72}, type_code="heart_rate")
    assert [v.value for v in measurement.values] == [72]


def test_backdating_limit_is_two_days(db, patient):
    record(db, patient, measured_at=NOW - MAX_BACKDATE)  # pont a határon: még jó
    with pytest.raises(MeasurementError) as excinfo:
        record(db, patient, measured_at=NOW - MAX_BACKDATE - timedelta(seconds=1))
    assert error_code(excinfo) == "too_old"


def test_future_measurement_is_rejected_beyond_clock_skew(db, patient):
    record(db, patient, measured_at=NOW + CLOCK_SKEW)
    with pytest.raises(MeasurementError) as excinfo:
        record(db, patient, measured_at=NOW + CLOCK_SKEW + timedelta(seconds=1))
    assert error_code(excinfo) == "in_future"


def test_naive_datetime_is_rejected(db, patient):
    with pytest.raises(MeasurementError) as excinfo:
        record(db, patient, measured_at=NOW.replace(tzinfo=None))
    assert error_code(excinfo) == "timezone_required"


@pytest.mark.parametrize(
    ("values", "code", "component"),
    [
        ({"systolic": 128}, "missing_value", "diastolic"),
        ({"systolic": 128, "diastolic": 82, "pulse": 70}, "unknown_component", "pulse"),
        ({"systolic": 1400, "diastolic": 82}, "out_of_range", "systolic"),
        ({"systolic": 128, "diastolic": 10}, "out_of_range", "diastolic"),
    ],
)
def test_invalid_values_are_rejected(db, patient, values, code, component):
    with pytest.raises(MeasurementError) as excinfo:
        record(db, patient, values)
    assert (excinfo.value.code, excinfo.value.component) == (code, component)


def test_unknown_type_is_rejected(db, patient):
    with pytest.raises(MeasurementError) as excinfo:
        record(db, patient, {"value": 1}, type_code="cholesterol")
    assert error_code(excinfo) == "unknown_type"


def test_rejected_measurement_is_not_stored(db, patient):
    with pytest.raises(MeasurementError):
        record(db, patient, {"systolic": 1400, "diastolic": 82})
    assert list_measurements(db, patient.patient_profile.id) == []


def test_list_is_newest_first_and_filterable_by_type(db, patient):
    record(db, patient, measured_at=NOW - timedelta(days=1))
    record(db, patient, measured_at=NOW)
    record(db, patient, {"value": 72}, measured_at=NOW - timedelta(hours=1), type_code="heart_rate")
    patient_id = patient.patient_profile.id
    times = [m.measured_at for m in list_measurements(db, patient_id)]
    assert times == sorted(times, reverse=True)
    assert len(list_measurements(db, patient_id, type_code="blood_pressure")) == 2


def test_list_contains_only_the_patients_own_measurements(db, patient):
    other = make_patient(db, email="masik@test.example")
    record(db, other)
    assert list_measurements(db, patient.patient_profile.id) == []
