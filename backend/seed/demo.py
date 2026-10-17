"""Demóadatok: felhasználók, orvos–beteg összerendelések, szabályok és mérések.

Minden név és adat kitalált (mesterséges). A közös jelszó CSAK helyi és
bemutató célra való.

A mérések ugyanazon az úton kerülnek be, mint a felületről (rögzítés +
kiértékelés), így a riasztásokat a valódi szabálykiértékelés hozza létre. Az
időpontok a futtatás idejéhez képest relatívak, hogy a bemutatón mindig friss
adat legyen. Kovács doktor listáján így minden M2-beli státusz megjelenik:
Varga Béla Súlyos, Szabó János Figyelem, Kiss Ilona Adathiány, Molnár Katalin
Rendben. A „Közérzet" kérdőívet minden demóbeteg megkapja; Szabó János
legutóbbi kitöltése a figyelmeztető sávba esik.
"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    Assignment,
    DoctorPatient,
    Measurement,
    QuestionnaireTemplate,
    Rule,
    RuleType,
    Severity,
    Submission,
    User,
    UserRole,
)
from app.services.measurements import record_measurement
from app.services.questionnaires import (
    assign_questionnaire,
    create_template,
    current_version,
    submit_questionnaire,
)
from app.services.rules import create_rule
from app.services.users import create_user, get_user_by_email
from seed.questionnaires import WELLBEING_CODE, WELLBEING_NAME, WELLBEING_V1
from seed.reference import seed_measurement_types

DEMO_PASSWORD = "pulse-demo-2026"

USERS = [
    {"email": "admin@pulse.example", "role": UserRole.ADMIN},
    {"email": "dr.kovacs@pulse.example", "role": UserRole.DOCTOR, "name": "Dr. Kovács Éva"},
    {"email": "dr.nagy@pulse.example", "role": UserRole.DOCTOR, "name": "Dr. Nagy Péter"},
    {
        "email": "szabo.janos@pulse.example",
        "role": UserRole.PATIENT,
        "name": "Szabó János",
        "birth_date": date(1958, 3, 14),
    },
    {
        "email": "toth.maria@pulse.example",
        "role": UserRole.PATIENT,
        "name": "Tóth Mária",
        "birth_date": date(1962, 11, 2),
    },
    {
        "email": "varga.bela@pulse.example",
        "role": UserRole.PATIENT,
        "name": "Varga Béla",
        "birth_date": date(1949, 7, 21),
    },
    {
        "email": "kiss.ilona@pulse.example",
        "role": UserRole.PATIENT,
        "name": "Kiss Ilona",
        "birth_date": date(1971, 5, 9),
    },
    {
        "email": "molnar.katalin@pulse.example",
        "role": UserRole.PATIENT,
        "name": "Molnár Katalin",
        "birth_date": date(1966, 1, 30),
    },
]

# Nagy doktor csak Tóth Máriát látja, Kovács doktor őt nem: így a bemutatón
# látszik, hogy az orvos idegen beteg adatát nem éri el.
ASSIGNMENTS = [
    ("dr.kovacs@pulse.example", "szabo.janos@pulse.example"),
    ("dr.kovacs@pulse.example", "varga.bela@pulse.example"),
    ("dr.kovacs@pulse.example", "kiss.ilona@pulse.example"),
    ("dr.kovacs@pulse.example", "molnar.katalin@pulse.example"),
    ("dr.nagy@pulse.example", "toth.maria@pulse.example"),
]

# Minden demóbeteg két vérnyomás-küszöbszabályt és két kérdőívszabályt kap a
# kezelőorvosától (bemutató-beállítás; a szabályszerkesztő az M3-ban jön).
DEMO_RULES = [
    (
        RuleType.THRESHOLD,
        Severity.MODERATE,
        {
            "measurement_type": "blood_pressure",
            "limits": {"systolic": {"max": 140}, "diastolic": {"max": 90}},
        },
    ),
    (
        RuleType.THRESHOLD,
        Severity.SEVERE,
        {"measurement_type": "blood_pressure", "limits": {"systolic": {"max": 180}}},
    ),
    (
        RuleType.QUESTIONNAIRE,
        Severity.MODERATE,
        {"questionnaire": WELLBEING_CODE, "bands": ["warning", "critical"]},
    ),
    (
        RuleType.QUESTIONNAIRE,
        Severity.SEVERE,
        {"questionnaire": WELLBEING_CODE, "bands": ["critical"]},
    ),
]

# Kérdőív-kitöltések: (hány napja, alvás 1–5, fáradtság 1–5, szédülés).
# Pontok: alvás 5 − válasz, fáradtság válasz − 1, szédülés 0/2/5.
DEMO_SUBMISSIONS = {
    # 1 + 1 + 0 = 2 (rendben), majd 2 + 2 + 2 = 6 (figyelmeztető sáv → riasztás)
    "szabo.janos@pulse.example": [(10, 4, 2, "never"), (3, 3, 3, "rarely")],
    "molnar.katalin@pulse.example": [(5, 5, 1, "never")],
    # A legutóbbi adata így is 12 napos marad (Adathiány).
    "kiss.ilona@pulse.example": [(13, 4, 2, "never")],
}

# Vérnyomás-méréssorok: (hány napja, szisztolés, diasztolés).
# fmt: off
DEMO_BLOOD_PRESSURE = {
    # Két 140 feletti érték: az első riasztást nyit, a második ugyanahhoz
    # kapcsolódik, ismételt aktiválódásként (deduplikáció).
    "szabo.janos@pulse.example": [
        (9, 132, 84), (8, 128, 82), (7, 135, 86), (6, 130, 83), (5, 134, 85),
        (4, 129, 81), (3, 146, 92), (2, 138, 88), (1, 136, 86), (0, 152, 95),
    ],
    # Tartósan magas, egyszer 180 felett: közepes és súlyos riasztás is.
    "varga.bela@pulse.example": [
        (6, 148, 92), (5, 151, 94), (4, 149, 91), (3, 155, 96),
        (2, 158, 97), (1, 186, 104), (0, 162, 98),
    ],
    # Rendben lévő értékek, de a legutóbbi 12 napos: nincs friss adat.
    "kiss.ilona@pulse.example": [(15, 128, 80), (14, 131, 82), (13, 126, 79), (12, 129, 81)],
    "molnar.katalin@pulse.example": [
        (6, 122, 78), (5, 125, 80), (4, 119, 76), (3, 124, 79),
        (2, 121, 77), (1, 123, 78), (0, 120, 76),
    ],
    "toth.maria@pulse.example": [
        (6, 126, 80), (5, 129, 82), (4, 124, 78), (3, 127, 81),
        (2, 125, 79), (1, 128, 80), (0, 124, 79),
    ],
}

# Szabó János a vérnyomás mellett pulzust és testsúlyt is mér.
DEMO_OTHER = {
    "szabo.janos@pulse.example": [
        (6, "heart_rate", 74), (4, "heart_rate", 71), (2, "heart_rate", 76),
        (0, "heart_rate", 78),
        (6, "body_weight", 86.4), (3, "body_weight", 86.1), (0, "body_weight", 85.8),
    ],
}
# fmt: on


def _get(db: Session, email: str) -> User:
    user = get_user_by_email(db, email)
    assert user is not None, email
    return user


def seed_demo_data(db: Session, now: datetime | None = None) -> list[str]:
    """Létrehozza a hiányzó törzsadatokat, demófiókokat, összerendeléseket,
    szabályokat és méréseket; a meglévőket kihagyja (ismételten futtatható).
    Visszaadja, mi történt (soronként)."""
    log: list[str] = seed_measurement_types(db)
    for spec in USERS:
        if get_user_by_email(db, spec["email"]) is None:
            create_user(db, password=DEMO_PASSWORD, **spec)
            log.append(f"létrehozva: {spec['email']} ({spec['role']})")
        else:
            log.append(f"már létezik: {spec['email']}")

    for doctor_email, patient_email in ASSIGNMENTS:
        doctor = _get(db, doctor_email).doctor_profile
        patient = _get(db, patient_email).patient_profile
        active = db.scalar(
            select(DoctorPatient).where(
                DoctorPatient.doctor_id == doctor.id,
                DoctorPatient.patient_id == patient.id,
                DoctorPatient.valid_to.is_(None),
            )
        )
        if active is None:
            db.add(DoctorPatient(doctor_id=doctor.id, patient_id=patient.id))
            log.append(f"összerendelve: {doctor.name} – {patient.name}")

    db.flush()
    now = now or datetime.now(UTC)
    log += _seed_questionnaire(db, now)
    log += _seed_rules(db)
    log += _seed_measurements(db, now)
    log += _seed_submissions(db, now)
    db.commit()
    return log


def _seed_questionnaire(db: Session, now: datetime) -> list[str]:
    """A „Közérzet" kérdőív, és kirendelése minden demóbetegnek (hetente)."""
    log: list[str] = []
    template = db.scalar(
        select(QuestionnaireTemplate).where(QuestionnaireTemplate.code == WELLBEING_CODE)
    )
    if template is None:
        template = create_template(
            db,
            code=WELLBEING_CODE,
            name=WELLBEING_NAME,
            created_by=_get(db, "dr.kovacs@pulse.example").id,
            spec=WELLBEING_V1,
        )
        log.append(f"kérdőív: {WELLBEING_NAME}")
    start = (now.astimezone(settings.tz) - timedelta(days=14)).date()
    for doctor_email, patient_email in ASSIGNMENTS:
        patient = _get(db, patient_email).patient_profile
        assigned = db.scalar(
            select(
                exists().where(
                    Assignment.patient_id == patient.id,
                    Assignment.questionnaire_template_id == template.id,
                )
            )
        )
        if not assigned:
            assign_questionnaire(
                db,
                patient_id=patient.id,
                template=template,
                assigned_by=_get(db, doctor_email).id,
                start_date=start,
            )
            log.append(f"kirendelés: {WELLBEING_NAME} – {patient.name}")
    return log


def _seed_submissions(db: Session, now: datetime) -> list[str]:
    """Kitöltések este 19:00-kor (helyi idő), ahogy a beteg rögzítené."""
    template = db.scalar(
        select(QuestionnaireTemplate).where(QuestionnaireTemplate.code == WELLBEING_CODE)
    )
    q_sleep, q_fatigue, q_dizziness = current_version(db, template.id).questions
    local_now = now.astimezone(settings.tz)
    anchor = local_now.replace(hour=19, minute=0, second=0, microsecond=0)
    if anchor > local_now:
        anchor -= timedelta(days=1)

    log: list[str] = []
    for email, series in DEMO_SUBMISSIONS.items():
        patient = _get(db, email).patient_profile
        if db.scalar(select(exists().where(Submission.patient_id == patient.id))):
            continue
        events = 0
        for days, sleep, fatigue, dizziness in sorted(series, reverse=True):
            _, touched = submit_questionnaire(
                db,
                patient_id=patient.id,
                template_code=WELLBEING_CODE,
                answers={
                    str(q_sleep.id): sleep,
                    str(q_fatigue.id): fatigue,
                    str(q_dizziness.id): dizziness,
                },
                now=anchor - timedelta(days=days),
            )
            events += len(touched)
        log.append(f"kitöltések: {patient.name} ({len(series)} db, {events} riasztási esemény)")
    return log


def _seed_rules(db: Session) -> list[str]:
    log: list[str] = []
    for doctor_email, patient_email in ASSIGNMENTS:
        doctor = _get(db, doctor_email)
        patient = _get(db, patient_email).patient_profile
        if db.scalar(select(exists().where(Rule.patient_id == patient.id))):
            continue
        for rule_type, severity, params in DEMO_RULES:
            create_rule(
                db,
                patient_id=patient.id,
                created_by=doctor.id,
                rule_type=rule_type,
                params=params,
                severity=severity,
            )
        log.append(f"szabályok: {patient.name} ({len(DEMO_RULES)} db)")
    return log


def _seed_measurements(db: Session, now: datetime) -> list[str]:
    """A méréssorok betöltése azoknál a betegeknél, akiknek még nincs mérésük.
    A mérések helyi idő szerint reggel 7:30-kor készülnek (a rendszer
    időzónájában, így az óraátállítás után is); a 0. nap a legutóbbi ilyen
    időpont, és a rögzítés két perccel a mérés után történik."""
    local_now = now.astimezone(settings.tz)
    anchor = local_now.replace(hour=7, minute=30, second=0, microsecond=0)
    if anchor > local_now:
        anchor -= timedelta(days=1)

    log: list[str] = []
    for email, series in DEMO_BLOOD_PRESSURE.items():
        patient = _get(db, email).patient_profile
        if db.scalar(select(exists().where(Measurement.patient_id == patient.id))):
            continue
        entries = [
            (days, "blood_pressure", {"systolic": sys, "diastolic": dia})
            for days, sys, dia in series
        ] + [(days, code, {"value": value}) for days, code, value in DEMO_OTHER.get(email, [])]
        entries.sort(key=lambda e: e[0], reverse=True)  # időrendben, ahogy a beteg rögzítené
        events = 0
        for days, type_code, values in entries:
            measured_at = anchor - timedelta(days=days)
            _, touched = record_measurement(
                db,
                patient_id=patient.id,
                type_code=type_code,
                values=values,
                measured_at=measured_at,
                now=measured_at + timedelta(minutes=2),
            )
            events += len(touched)
        log.append(f"mérések: {patient.name} ({len(entries)} db, {events} riasztási esemény)")
    return log
