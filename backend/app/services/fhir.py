"""FHIR R4 kiadás a PULSE adataiból (M3, K1; NF9).

Egy beteg adatai egy `collection` típusú Bundle-ben, kézzel épített JSON-ként
(nincs FHIR-könyvtár; a szerkezet az integration/ M2-es próbacsomagját követi):

- Patient: azonosító, név, születési dátum (a NICE-szabály életkorához kell);
- Observation mérésenként: a méréstípus LOINC-kódja, UCUM-egység; többértékű
  mérésnél (vérnyomás) a panel kódja alatt értékenként egy component, egyértékűnél
  egy valueQuantity;
- Questionnaire kérdőívverziónként (a beteg kitöltései által hivatkozottak):
  a canonical url a sablon kódjából, a version a verziószám;
- QuestionnaireResponse kitöltésenként, a kitöltéskori verzióra hivatkozva
  (`<url>|<verziószám>`), így egy későbbi sablonmódosítás nem írja át a jelentését.

Az időpontok a rendszer időzónájának (settings.tz) HELYI eltolásával kerülnek ki.
Az M2-es próba mutatta meg, miért: a CQL `date from` a tárolt eltolás szerinti
napot adja, így egy UTC-ben (Z) kiírt éjfél utáni mérés az előző napra csúszna.
A tört másodperc legfeljebb ezredmásodpercig marad meg, mert a CQL DateTime
ennél pontosabbat nem tárol (a cql-execution a mikroszekundumot levágja).

A pontszámok és a kiértékelési sávok nem kerülnek a csomagba: a beteg a saját
pontjait a felületen sem látja, és a csomagot ő is letöltheti.

Demonstrációs kiadás, kizárólag mesterséges adathoz: a Bundle ezt jelöli is
(HTEST címke). A HL7-validátorral nem ellenőriztük.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models import (
    Answer,
    Measurement,
    MeasurementType,
    MeasurementValue,
    PatientProfile,
    QuestionnaireTemplate,
    QuestionnaireVersion,
    QuestionType,
    Submission,
)

# A teljes URL-ek alapja (fullUrl, kérdőív-canonical); ugyanaz, mint az M2-es
# próbacsomagban. A PULSE nem FHIR-szerver, a cím csak azonosító.
BASE_URL = "https://example.org/pulse/fhir"

LOINC = "http://loinc.org"
UCUM = "http://unitsofmeasure.org"

# A LOINC-kódok angol neve (Long Common Name), a hallgató ellenőrzése szerint
# (docs/files/kutatas/loinc_kodok.md, 2026-10-11). Ismeretlen kódnál nincs display.
LOINC_DISPLAY = {
    "85354-9": "Blood pressure panel with all children optional",
    "8480-6": "Systolic blood pressure",
    "8462-4": "Diastolic blood pressure",
    "8867-4": "Heart rate",
    "29463-7": "Body weight",
    "14743-9": "Glucose [Moles/volume] in Capillary blood by Glucometer",
}

# A FHIR R4 vitális jel profiljai (observation-vitalsigns): ezeknél a mérés
# vital-signs kategóriát és profilt kap. A vércukor nem vitális jel, ezért
# kategória és profil nélkül megy ki.
VITAL_SIGNS_PROFILES = {
    "85354-9": "http://hl7.org/fhir/StructureDefinition/bp",
    "8867-4": "http://hl7.org/fhir/StructureDefinition/heartrate",
    "29463-7": "http://hl7.org/fhir/StructureDefinition/bodyweight",
}

# Az egység olvasható alakja; a gépi jelentést a UCUM-kód (code) adja.
UNIT_DISPLAY = {"mm[Hg]": "mmHg"}

# Mesterséges (teszt-) egészségügyi adat jelölése (HL7 v3 ActReason).
TEST_DATA_TAG = {
    "system": "http://terminology.hl7.org/CodeSystem/v3-ActReason",
    "code": "HTEST",
    "display": "test health data",
}


def fhir_datetime(at: datetime) -> str:
    """Időpont FHIR dateTime-ként, a rendszer időzónájának helyi eltolásával
    (pl. 2026-10-05T07:30:00+02:00). Tört másodperc csak akkor, ha van, és
    legfeljebb ezredmásodpercig."""
    local = at.astimezone(settings.tz)
    return local.isoformat(timespec="milliseconds" if local.microsecond else "seconds")


def _number(value: float) -> int | float:
    """Egész érték egészként (150, nem 150.0), a tört érték változatlanul."""
    return int(value) if value.is_integer() else value


def _loinc(code: str, text: str | None = None) -> dict[str, Any]:
    coding: dict[str, Any] = {"system": LOINC, "code": code}
    if code in LOINC_DISPLAY:
        coding["display"] = LOINC_DISPLAY[code]
    concept: dict[str, Any] = {"coding": [coding]}
    if text:
        concept["text"] = text
    return concept


def _quantity(value: float, unit: str) -> dict[str, Any]:
    return {
        "value": _number(value),
        "unit": UNIT_DISPLAY.get(unit, unit),
        "system": UCUM,
        "code": unit,
    }


def _entry(resource: dict[str, Any]) -> dict[str, Any]:
    return {
        "fullUrl": f"{BASE_URL}/{resource['resourceType']}/{resource['id']}",
        "resource": resource,
    }


def patient_resource(patient: PatientProfile) -> dict[str, Any]:
    # A név egyben tárolt; a családi és utónévre bontást nem találgatjuk.
    return {
        "resourceType": "Patient",
        "id": str(patient.id),
        "name": [{"text": patient.name}],
        "birthDate": patient.birth_date.isoformat(),
    }


def observation_resource(measurement: Measurement) -> dict[str, Any]:
    """Egy mérés Observation-ként. A státusz mindig final: a mérésjavítás
    (corrected_from) folyamata az M3 A7 tétele, a kiadása vele együtt dől el."""
    mtype = measurement.type
    values = {v.component_id: v.value for v in measurement.values}
    resource: dict[str, Any] = {"resourceType": "Observation", "id": str(measurement.id)}
    profile = VITAL_SIGNS_PROFILES.get(mtype.loinc_code)
    if profile:
        resource["meta"] = {"profile": [profile]}
    resource["status"] = "final"
    if profile:
        resource["category"] = [
            {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                        "code": "vital-signs",
                        "display": "Vital Signs",
                    }
                ]
            }
        ]
    resource["code"] = _loinc(mtype.loinc_code, mtype.name)
    resource["subject"] = {"reference": f"Patient/{measurement.patient_id}"}
    resource["effectiveDateTime"] = fhir_datetime(measurement.measured_at)
    resource["issued"] = fhir_datetime(measurement.recorded_at)
    components = sorted(mtype.components, key=lambda c: c.order_no)
    if len(components) == 1:
        # Egyértékű mérés: az érték közvetlenül az Observationé.
        resource["valueQuantity"] = _quantity(values[components[0].id], components[0].unit)
    else:
        # Többértékű mérés (vérnyomás): a panel kódja alatt értékenként egy component.
        resource["component"] = [
            {
                "code": _loinc(c.loinc_code, c.name),
                "valueQuantity": _quantity(values[c.id], c.unit),
            }
            for c in components
            if c.id in values
        ]
    return resource


def questionnaire_url(template: QuestionnaireTemplate) -> str:
    """A kérdőív canonical url-je: a sablonhoz tartozik, minden verziójánál ugyanaz;
    a verziót a version mező (és a hivatkozás `|verziószám` része) adja."""
    return f"{BASE_URL}/Questionnaire/{template.code}"


def questionnaire_resource(version: QuestionnaireVersion, latest_no: int) -> dict[str, Any]:
    """Egy kérdőívverzió. A válaszlehetőség Coding: a code a verzióban tárolt
    érték (skálánál is szöveg, pl. "4"), a display a felirata; system nélkül,
    mert a jelentését maga a kérdőívverzió adja. A pontok nem kerülnek ki. A
    linkId a kérdés azonosítója (a kérdés a verzióhoz tartozik, így egyedi).
    Aktív csak az aktív sablon legújabb verziója, a korábbiak visszavontak."""
    template = version.template
    active = template.is_active and version.version_no == latest_no
    items = []
    for question in sorted(version.questions, key=lambda q: q.order_no):
        item: dict[str, Any] = {
            "linkId": str(question.id),
            "text": question.text,
            "type": "choice",
            "required": True,
        }
        if question.question_type is QuestionType.MULTI:
            item["repeats"] = True
        item["answerOption"] = [
            {"valueCoding": {"code": o["value"], "display": o["label"]}}
            for o in question.options_scores
        ]
        items.append(item)
    return {
        "resourceType": "Questionnaire",
        "id": str(version.id),
        "url": questionnaire_url(template),
        "version": str(version.version_no),
        "title": template.name,
        "status": "active" if active else "retired",
        "date": fhir_datetime(version.created_at),
        "item": items,
    }


def questionnaire_response_resource(submission: Submission) -> dict[str, Any]:
    """Egy kitöltés, a kitöltéskori kérdőívverzióra hivatkozva."""
    version = submission.version
    answers = sorted(submission.answers, key=lambda a: a.question.order_no)
    return {
        "resourceType": "QuestionnaireResponse",
        "id": str(submission.id),
        "questionnaire": f"{questionnaire_url(version.template)}|{version.version_no}",
        "status": "completed",
        "subject": {"reference": f"Patient/{submission.patient_id}"},
        "authored": fhir_datetime(submission.submitted_at),
        "item": [
            {
                "linkId": str(a.question_id),
                "text": a.question.text,
                "answer": [{"valueCoding": coding} for coding in _answer_codings(a)],
            }
            for a in answers
        ],
    }


def _answer_codings(answer: Answer) -> list[dict[str, str]]:
    """A válasz Coding-ként, a kérdőívverzió válaszlehetőségével azonos alakban.
    Többválasztósnál a lista minden eleme külön answer (repeats)."""
    labels = {o["value"]: o["label"] for o in answer.question.options_scores}
    values = answer.value if isinstance(answer.value, list) else [answer.value]
    return [{"code": str(v), "display": labels.get(str(v), str(v))} for v in values]


def patient_bundle(
    db: Session, patient_id: uuid.UUID, now: datetime | None = None
) -> dict[str, Any]:
    """A beteg teljes FHIR-csomagja: Patient, a hivatkozott kérdőívverziók, a
    mérések (időrendben) és a kitöltések (időrendben). Csak olvas."""
    patient = db.get(PatientProfile, patient_id)
    if patient is None:
        raise LookupError(f"Nincs ilyen beteg: {patient_id}")
    measurements = db.scalars(
        select(Measurement)
        .where(Measurement.patient_id == patient_id)
        .options(
            selectinload(Measurement.type).selectinload(MeasurementType.components),
            selectinload(Measurement.values).selectinload(MeasurementValue.component),
        )
        .order_by(Measurement.measured_at, Measurement.id)
    ).all()
    submissions = db.scalars(
        select(Submission)
        .where(Submission.patient_id == patient_id)
        .options(
            selectinload(Submission.version).options(
                selectinload(QuestionnaireVersion.template),
                selectinload(QuestionnaireVersion.questions),
            ),
            selectinload(Submission.answers).selectinload(Answer.question),
        )
        .order_by(Submission.submitted_at, Submission.id)
    ).all()
    versions = {s.version.id: s.version for s in submissions}
    ordered_versions = sorted(versions.values(), key=lambda v: (v.template.code, v.version_no))
    latest_no = dict(
        db.execute(
            select(QuestionnaireVersion.template_id, func.max(QuestionnaireVersion.version_no))
            .where(QuestionnaireVersion.template_id.in_({v.template_id for v in ordered_versions}))
            .group_by(QuestionnaireVersion.template_id)
        ).all()
    )

    resources = (
        [patient_resource(patient)]
        + [questionnaire_resource(v, latest_no[v.template_id]) for v in ordered_versions]
        + [observation_resource(m) for m in measurements]
        + [questionnaire_response_resource(s) for s in submissions]
    )
    return {
        "resourceType": "Bundle",
        "meta": {"tag": [TEST_DATA_TAG]},
        "type": "collection",
        "timestamp": fhir_datetime(now or datetime.now(UTC)),
        "entry": [_entry(r) for r in resources],
    }
