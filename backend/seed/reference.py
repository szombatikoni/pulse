"""Törzsadatok: a rögzíthető méréstípusok (F4, F20).

A jelentésüket nemzetközi kódok rögzítik (FHIR R4 Observation): LOINC a mérés
és az egyes értékek kódja, UCUM a mértékegység. A kódokat a hallgató a
loinc.org-on ellenőrizte (2026-10-11).

A min/max a rögzíthető tartomány: a nyilvánvaló elírást szűri ki (pl. 1400
Hgmm), nem orvosi határérték — azt a szabályok adják.
"""

from sqlalchemy.orm import Session

from app.models import MeasurementComponent, MeasurementType
from app.services.measurements import get_type_by_code

MEASUREMENT_TYPES = [
    {
        "code": "blood_pressure",
        "name": "Vérnyomás",
        "loinc_code": "85354-9",  # Blood pressure panel with all children optional
        "components": [
            ("systolic", "Szisztolés", "8480-6", "mm[Hg]", 50, 300),
            ("diastolic", "Diasztolés", "8462-4", "mm[Hg]", 30, 200),
        ],
    },
    {
        "code": "heart_rate",
        "name": "Pulzus",
        "loinc_code": "8867-4",
        "components": [("value", "Pulzus", "8867-4", "/min", 20, 250)],
    },
    {
        "code": "body_weight",
        "name": "Testsúly",
        "loinc_code": "29463-7",
        "components": [("value", "Testsúly", "29463-7", "kg", 20, 350)],
    },
    {
        "code": "blood_glucose",
        "name": "Vércukor",
        # Glucose [Moles/volume] in Capillary blood by Glucometer: az otthoni,
        # ujjbegyes mérés, mmol/L-ben (a magyar gyakorlat szerint).
        "loinc_code": "14743-9",
        "components": [("value", "Vércukor", "14743-9", "mmol/L", 1, 35)],
    },
]


def seed_measurement_types(db: Session) -> list[str]:
    """Létrehozza a hiányzó méréstípusokat (ismételten futtatható)."""
    log: list[str] = []
    for spec in MEASUREMENT_TYPES:
        if get_type_by_code(db, spec["code"]) is not None:
            continue
        measurement_type = MeasurementType(
            code=spec["code"], name=spec["name"], loinc_code=spec["loinc_code"]
        )
        measurement_type.components = [
            MeasurementComponent(
                code=code,
                name=name,
                order_no=order_no,
                loinc_code=loinc,
                unit=unit,
                min_value=min_value,
                max_value=max_value,
            )
            for order_no, (code, name, loinc, unit, min_value, max_value) in enumerate(
                spec["components"], start=1
            )
        ]
        db.add(measurement_type)
        log.append(f"méréstípus: {spec['name']} ({spec['loinc_code']})")
    db.flush()
    return log
