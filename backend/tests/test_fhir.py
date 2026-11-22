"""FHIR R4 kiadás (M3, K1; NF9): a csomag szerkezete, a kódok és egységek, a
helyi időeltolás (az óraátállítás két napján is), a kérdőívverzió-hivatkozás
és a végpont jogosultsága (F2, F3)."""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

from app.core.security import create_access_token
from app.services.fhir import fhir_datetime, patient_bundle
from app.services.measurements import record_measurement
from app.services.questionnaires import (
    VersionSpec,
    add_version,
    assign_questionnaire,
    create_template,
    submit_questionnaire,
)
from seed.questionnaires import WELLBEING_CODE, WELLBEING_NAME, WELLBEING_V1
from tests.factories import assign, make_admin, make_doctor, make_patient

LOINC = "http://loinc.org"
UCUM = "http://unitsofmeasure.org"


def auth(user):
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def record(db, patient, type_code, values, at):
    measurement, _ = record_measurement(
        db,
        patient_id=patient.patient_profile.id,
        type_code=type_code,
        values=values,
        measured_at=at,
        now=at + timedelta(minutes=2),
    )
    return measurement


def resources(bundle, resource_type):
    return [
        e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == resource_type
    ]


def observation(bundle, measurement):
    [found] = [o for o in resources(bundle, "Observation") if o["id"] == str(measurement.id)]
    return found


@pytest.fixture
def setup(db, measurement_types):
    doctor = make_doctor(db)
    patient = make_patient(db)
    foreign = make_patient(db, email="idegen@test.example", name="Idegen Beteg")
    link = assign(db, doctor, patient)
    return {
        "doctor": doctor,
        "patient": patient,
        "foreign": foreign,
        "admin": make_admin(db),
        "link": link,
    }


# --- A csomag és az Observation ------------------------------------------------------------


def test_bundle_is_a_collection_with_the_patient_first(db, setup):
    patient = setup["patient"]
    now = datetime(2026, 10, 30, 11, 0, tzinfo=UTC)
    bundle = patient_bundle(db, patient.patient_profile.id, now=now)
    assert bundle["resourceType"] == "Bundle"
    assert bundle["type"] == "collection"
    assert bundle["timestamp"] == "2026-10-30T12:00:00+01:00"
    assert bundle["meta"]["tag"][0]["code"] == "HTEST"  # mesterséges adat
    first = bundle["entry"][0]
    assert first["resource"] == {
        "resourceType": "Patient",
        "id": str(patient.patient_profile.id),
        "name": [{"text": "Teszt Beteg"}],
        "birthDate": "1960-01-01",
    }
    assert first["fullUrl"].endswith(f"/Patient/{patient.patient_profile.id}")


def test_blood_pressure_is_a_panel_with_two_components(db, setup):
    patient = setup["patient"]
    at = datetime(2026, 10, 20, 5, 30, tzinfo=UTC)
    m = record(db, patient, "blood_pressure", {"systolic": 146, "diastolic": 92}, at)
    obs = observation(patient_bundle(db, patient.patient_profile.id), m)

    assert obs["status"] == "final"
    assert obs["meta"]["profile"] == ["http://hl7.org/fhir/StructureDefinition/bp"]
    assert obs["category"][0]["coding"][0]["code"] == "vital-signs"
    assert obs["code"]["coding"] == [
        {
            "system": LOINC,
            "code": "85354-9",
            "display": "Blood pressure panel with all children optional",
        }
    ]
    assert obs["subject"] == {"reference": f"Patient/{patient.patient_profile.id}"}
    # Többértékű mérés: nincs közvetlen érték, csak a két component.
    assert "valueQuantity" not in obs
    assert [(c["code"]["coding"][0]["code"], c["valueQuantity"]) for c in obs["component"]] == [
        ("8480-6", {"value": 146, "unit": "mmHg", "system": UCUM, "code": "mm[Hg]"}),
        ("8462-4", {"value": 92, "unit": "mmHg", "system": UCUM, "code": "mm[Hg]"}),
    ]


@pytest.mark.parametrize(
    ("type_code", "value", "loinc", "ucum", "profile"),
    [
        ("heart_rate", 74, "8867-4", "/min", "heartrate"),
        ("body_weight", 85.8, "29463-7", "kg", "bodyweight"),
        ("blood_glucose", 6.2, "14743-9", "mmol/L", None),
    ],
)
def test_single_value_types_have_a_value_quantity(
    db, setup, type_code, value, loinc, ucum, profile
):
    patient = setup["patient"]
    m = record(db, patient, type_code, {"value": value}, datetime(2026, 10, 20, 5, 30, tzinfo=UTC))
    obs = observation(patient_bundle(db, patient.patient_profile.id), m)

    assert obs["code"]["coding"][0]["code"] == loinc
    assert "component" not in obs
    assert obs["valueQuantity"]["value"] == value
    assert (obs["valueQuantity"]["system"], obs["valueQuantity"]["code"]) == (UCUM, ucum)
    if profile:
        assert obs["meta"]["profile"] == [f"http://hl7.org/fhir/StructureDefinition/{profile}"]
        assert obs["category"][0]["coding"][0]["code"] == "vital-signs"
    else:
        # A vércukor nem vitális jel: profil és kategória nélkül.
        assert "meta" not in obs and "category" not in obs


def test_integer_values_are_written_without_decimal_point(db, setup):
    patient = setup["patient"]
    m = record(
        db, patient, "heart_rate", {"value": 74.0}, datetime(2026, 10, 20, 5, 30, tzinfo=UTC)
    )
    value = observation(patient_bundle(db, patient.patient_profile.id), m)["valueQuantity"]["value"]
    assert value == 74 and isinstance(value, int)


def test_observations_are_in_time_order_and_only_the_patients_own(db, setup):
    patient, foreign = setup["patient"], setup["foreign"]
    base = datetime(2026, 10, 20, 5, 30, tzinfo=UTC)
    later = record(db, patient, "heart_rate", {"value": 70}, base + timedelta(days=1))
    earlier = record(db, patient, "heart_rate", {"value": 72}, base)
    record(db, foreign, "heart_rate", {"value": 99}, base)
    ids = [
        o["id"] for o in resources(patient_bundle(db, patient.patient_profile.id), "Observation")
    ]
    assert ids == [str(earlier.id), str(later.id)]


# --- Helyi időeltolás ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("utc", "local"),
    [
        # Nyári idő: +02:00.
        (datetime(2026, 10, 20, 5, 30, tzinfo=UTC), "2026-10-20T07:30:00+02:00"),
        # Az M2-es próba esete: UTC-ben még előző nap, helyi idő szerint már
        # a következő; a helyi eltolással a CQL `date from` a helyi napot adja.
        (datetime(2026, 10, 19, 22, 30, tzinfo=UTC), "2026-10-20T00:30:00+02:00"),
        # Téli időszámítás: +01:00.
        (datetime(2026, 11, 2, 6, 30, tzinfo=UTC), "2026-11-02T07:30:00+01:00"),
        # Az őszi óraátállítás napja (2026. okt. 25., 3:00 → 2:00): ugyanaz a
        # helyi falióra-idő kétszer, két különböző eltolással.
        (datetime(2026, 10, 25, 0, 30, tzinfo=UTC), "2026-10-25T02:30:00+02:00"),
        (datetime(2026, 10, 25, 1, 30, tzinfo=UTC), "2026-10-25T02:30:00+01:00"),
        # A tavaszi óraátállítás napja (2026. márc. 29., 2:00 → 3:00).
        (datetime(2026, 3, 29, 0, 30, tzinfo=UTC), "2026-03-29T01:30:00+01:00"),
        (datetime(2026, 3, 29, 1, 30, tzinfo=UTC), "2026-03-29T03:30:00+02:00"),
    ],
)
def test_effective_time_has_the_local_offset(db, setup, utc, local):
    patient = setup["patient"]
    m = record(db, patient, "heart_rate", {"value": 70}, utc)
    obs = observation(patient_bundle(db, patient.patient_profile.id), m)
    assert obs["effectiveDateTime"] == local
    # A kiírt időpont ugyanaz a pillanat, mint a tárolt.
    assert datetime.fromisoformat(obs["effectiveDateTime"]) == utc
    issued = datetime.fromisoformat(obs["issued"])
    assert issued == utc + timedelta(minutes=2) and issued.utcoffset() is not None


def test_dst_boundary_offsets_are_what_zoneinfo_says(db):
    # A fenti esetek az óraátállítás napjaira épülnek; itt a feltevést magát
    # ellenőrizzük, nem a dátumokat hisszük el.
    assert fhir_datetime(datetime(2026, 10, 25, 0, 59, tzinfo=UTC)).endswith("+02:00")
    assert fhir_datetime(datetime(2026, 10, 25, 1, 0, tzinfo=UTC)).endswith("+01:00")
    assert fhir_datetime(datetime(2026, 3, 29, 0, 59, tzinfo=UTC)).endswith("+01:00")
    assert fhir_datetime(datetime(2026, 3, 29, 1, 0, tzinfo=UTC)).endswith("+02:00")


def test_fractional_seconds_are_kept_to_milliseconds():
    # A CQL DateTime ezredmásodperc-pontosságú; pontosabbat nem írunk ki.
    at = datetime(2026, 10, 20, 5, 30, 15, 123456, tzinfo=UTC)
    assert fhir_datetime(at) == "2026-10-20T07:30:15.123+02:00"
    assert fhir_datetime(at.replace(microsecond=0)) == "2026-10-20T07:30:15+02:00"


# --- Kérdőív és kitöltés -------------------------------------------------------------------


def _wellbeing(db, doctor, patient, start):
    template = create_template(
        db, code=WELLBEING_CODE, name=WELLBEING_NAME, created_by=doctor.id, spec=WELLBEING_V1
    )
    assign_questionnaire(
        db,
        patient_id=patient.patient_profile.id,
        template=template,
        assigned_by=doctor.id,
        start_date=start,
    )
    return template


def _submit(db, patient, version_questions, values, at):
    submission, _ = submit_questionnaire(
        db,
        patient_id=patient.patient_profile.id,
        template_code=WELLBEING_CODE,
        answers={str(q.id): v for q, v in zip(version_questions, values, strict=True)},
        now=at,
    )
    return submission


def test_response_refers_to_the_version_it_was_filled_in(db, setup):
    """A v1-en kitöltött válasz a sablon új verziója után is a v1-re hivatkozik;
    a csomagban mindkét hivatkozott verzió benne van, a régi visszavonva."""
    doctor, patient = setup["doctor"], setup["patient"]
    template = _wellbeing(db, doctor, patient, date(2026, 10, 5))
    first_at = datetime(2026, 10, 6, 17, 0, tzinfo=UTC)
    v1 = template.versions[0]
    first = _submit(db, patient, v1.questions, ["4", 2, "never"], first_at)

    spec = WELLBEING_V1.model_copy(deep=True)
    spec.questions[2].options[1].score = 4
    spec.scoring_thresholds[0].max = 3
    spec.scoring_thresholds[1].min = 4
    v2 = add_version(db, template, VersionSpec.model_validate(spec.model_dump()))
    # A következő heti időszak alkalma már a v2-t kapja.
    second = _submit(db, patient, v2.questions, ["3", "3", "rarely"], first_at + timedelta(days=7))

    bundle = patient_bundle(db, patient.patient_profile.id)
    url = "https://example.org/pulse/fhir/Questionnaire/wellbeing"
    responses = {r["id"]: r for r in resources(bundle, "QuestionnaireResponse")}
    assert responses[str(first.id)]["questionnaire"] == f"{url}|1"
    assert responses[str(second.id)]["questionnaire"] == f"{url}|2"

    questionnaires = {q["version"]: q for q in resources(bundle, "Questionnaire")}
    assert set(questionnaires) == {"1", "2"}
    assert {q["url"] for q in questionnaires.values()} == {url}
    assert questionnaires["1"]["id"] == str(v1.id)
    assert (questionnaires["1"]["status"], questionnaires["2"]["status"]) == ("retired", "active")
    # Minden válasz linkId-je a hivatkozott verzió kérdésére mutat.
    for response in responses.values():
        version = questionnaires[response["questionnaire"].rsplit("|", 1)[1]]
        assert [i["linkId"] for i in response["item"]] == [i["linkId"] for i in version["item"]]


def test_response_answers_and_authored_time(db, setup):
    doctor, patient = setup["doctor"], setup["patient"]
    template = _wellbeing(db, doctor, patient, date(2026, 10, 5))
    questions = template.versions[0].questions
    at = datetime(2026, 10, 6, 17, 0, tzinfo=UTC)
    submission = _submit(db, patient, questions, [4, "2", "rarely"], at)

    bundle = patient_bundle(db, patient.patient_profile.id)
    [response] = resources(bundle, "QuestionnaireResponse")
    assert response["id"] == str(submission.id)
    assert response["status"] == "completed"
    assert response["subject"] == {"reference": f"Patient/{patient.patient_profile.id}"}
    assert response["authored"] == "2026-10-06T19:00:00+02:00"
    assert [(i["linkId"], i["answer"]) for i in response["item"]] == [
        (str(questions[0].id), [{"valueCoding": {"code": "4", "display": "4"}}]),
        (str(questions[1].id), [{"valueCoding": {"code": "2", "display": "2"}}]),
        (str(questions[2].id), [{"valueCoding": {"code": "rarely", "display": "Ritkán"}}]),
    ]
    # A pontszám nem kerül a csomagba (a beteg sem látja a felületen).
    assert "score" not in str(bundle).lower()


def test_questionnaire_items_and_multi_choice_answers(db, setup):
    doctor, patient = setup["doctor"], setup["patient"]
    spec = VersionSpec.model_validate(
        {
            "questions": [
                {
                    "question_type": "scale",
                    "text": "Alvás",
                    "scale_min": 1,
                    "scale_max": 3,
                    "good_end": "max",
                    "min_label": "rossz",
                },
                {
                    "question_type": "multi",
                    "text": "Panaszok",
                    "options": [
                        {"value": "headache", "label": "Fejfájás", "score": 1},
                        {"value": "dizziness", "label": "Szédülés", "score": 2},
                    ],
                },
            ],
            "scoring_thresholds": [{"band": "normal", "min": 0, "max": 5}],
        }
    )
    template = create_template(
        db, code=WELLBEING_CODE, name="Próba", created_by=doctor.id, spec=spec
    )
    assign_questionnaire(
        db,
        patient_id=patient.patient_profile.id,
        template=template,
        assigned_by=doctor.id,
        start_date=date(2026, 10, 5),
    )
    questions = template.versions[0].questions
    _submit(
        db,
        patient,
        questions,
        ["1", ["headache", "dizziness"]],
        datetime(2026, 10, 6, 17, 0, tzinfo=UTC),
    )

    bundle = patient_bundle(db, patient.patient_profile.id)
    [questionnaire] = resources(bundle, "Questionnaire")
    scale, multi = questionnaire["item"]
    assert (questionnaire["title"], questionnaire["version"]) == ("Próba", "1")
    assert scale["type"] == "choice" and "repeats" not in scale
    assert [o["valueCoding"] for o in scale["answerOption"]] == [
        {"code": "1", "display": "1 – rossz"},
        {"code": "2", "display": "2"},
        {"code": "3", "display": "3"},
    ]
    assert multi["repeats"] is True
    [response] = resources(bundle, "QuestionnaireResponse")
    assert response["item"][1]["answer"] == [
        {"valueCoding": {"code": "headache", "display": "Fejfájás"}},
        {"valueCoding": {"code": "dizziness", "display": "Szédülés"}},
    ]


def test_unknown_patient_is_a_lookup_error(db):
    with pytest.raises(LookupError):
        patient_bundle(db, uuid.uuid4())


# --- Végpont és jogosultság ----------------------------------------------------------------


def url(user) -> str:
    return f"/api/patients/{user.patient_profile.id}/fhir"


def test_patient_downloads_own_bundle(client, setup):
    patient = setup["patient"]
    response = client.get(url(patient), headers=auth(patient))
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/fhir+json")
    assert response.json()["entry"][0]["resource"]["id"] == str(patient.patient_profile.id)


def test_assigned_doctor_downloads_the_bundle(client, db, setup):
    patient = setup["patient"]
    m = record(db, patient, "heart_rate", {"value": 70}, datetime.now(UTC) - timedelta(hours=1))
    response = client.get(url(patient), headers=auth(setup["doctor"]))
    assert response.status_code == 200
    assert str(m.id) in {e["resource"]["id"] for e in response.json()["entry"]}


@pytest.mark.parametrize("who", ["patient", "doctor", "admin"])
def test_others_cannot_download_a_foreign_bundle(client, setup, who):
    # A beteg más betegét, az orvos a nem hozzá rendelt beteget, az admin
    # semmilyen beteg adatát nem kérheti le (F2).
    assert client.get(url(setup["foreign"]), headers=auth(setup[who])).status_code == 403


def test_admin_cannot_download_even_an_assigned_patients_bundle(client, setup):
    assert client.get(url(setup["patient"]), headers=auth(setup["admin"])).status_code == 403


def test_unknown_patient_is_403_not_404(client, setup):
    response = client.get(f"/api/patients/{uuid.uuid4()}/fhir", headers=auth(setup["doctor"]))
    assert response.status_code == 403


def test_bundle_requires_login(client, setup):
    assert client.get(url(setup["patient"])).status_code == 401


def test_ending_assignment_revokes_bundle_access_immediately(client, db, setup):
    doctor = setup["doctor"]
    assert client.get(url(setup["patient"]), headers=auth(doctor)).status_code == 200
    setup["link"].valid_to = datetime.now(UTC)
    db.flush()
    assert client.get(url(setup["patient"]), headers=auth(doctor)).status_code == 403


def test_new_assignment_grants_bundle_access_immediately(client, db, setup):
    doctor = setup["doctor"]
    assert client.get(url(setup["foreign"]), headers=auth(doctor)).status_code == 403
    assign(db, doctor, setup["foreign"])
    assert client.get(url(setup["foreign"]), headers=auth(doctor)).status_code == 200
