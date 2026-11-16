"""A dolgozat 7. fejezetének (docs/dolgozat/07_mukodes.md) dátumozott példái
tesztként (M3, K4).

A megfeleltetés: docs/files/tervezet/k4_megfeleltetes_2026-11-16.md. Ami a
példából már pontosan ugyanazokkal az adatokkal tesztelve volt, az itt nem
ismétlődik (a táblázat a meglévő tesztre mutat). Ahol a példa és a kód
viselkedése eltér, a teszt a DOLGOZAT szerinti elvárást rögzíti, és
xfail(strict=True) jelöli: a döntés (a kód vagy a szöveg változzon) nem a
teszté.

Az azonosítók: P1 = „A beteg státusza" (lezárás, majd megerősítő mérés),
P2 = „Esedékesség és elmaradás" (alkalom-táblázat), P3 = „Riasztás,
deduplikáció és szabálymódosítás", P4 = „Kérdőív-pontozás" (demóbeállítás),
P5 = „Integrációs próba" (hét beállítás)."""

import json
from datetime import date, datetime, time, timedelta
from fractions import Fraction
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models import (
    Alert,
    AlertEvent,
    AlertEventType,
    AlertStatus,
    AssignmentOccurrence,
    OccurrenceStatus,
    RuleType,
    Severity,
)
from app.services.alerts import close_alert
from app.services.measurements import get_type_by_code, record_measurement
from app.services.nice import parse_cql_result
from app.services.occurrences import open_due_occurrences, run_occurrence_check
from app.services.rules import add_rule_version, create_rule
from app.services.status import PatientStatus, compute_status
from app.services.tasks import assign_measurement
from app.services.users import get_user_by_email
from seed.demo import DEMO_RULES, seed_demo_data
from tests.factories import assign, make_doctor, make_patient, record_bp


def local(y, m, d, hh=0, mm=0):
    """Időpont a rendszer időzónájában (Europe/Budapest)."""
    return datetime(y, m, d, hh, mm, tzinfo=settings.tz)


SINCE = local(2026, 8, 1)


@pytest.fixture
def doctor(db):
    return make_doctor(db, name="Dr. Szabó")


@pytest.fixture
def patient(db, measurement_types, doctor):
    patient = make_patient(db)
    assign(db, doctor, patient, valid_from=SINCE)
    return patient


def status_of(db, patient, now):
    return compute_status(db, patient.patient_profile.id, now)


def codes(result):
    return [r.code for r in result.reasons]


def events(db, alert):
    query = select(AlertEvent).where(AlertEvent.alert_id == alert.id)
    return list(db.scalars(query.order_by(AlertEvent.created_at, AlertEvent.id)))


def record(db, patient, systolic, diastolic, measured_at, recorded_at):
    """Vérnyomás a mérés és a rögzítés külön idejével (a pótláshoz)."""
    measurement, _ = record_measurement(
        db,
        patient_id=patient.patient_profile.id,
        type_code="blood_pressure",
        values={"systolic": systolic, "diastolic": diastolic},
        measured_at=measured_at,
        now=recorded_at,
    )
    return measurement


def daily_bp_plan(db, patient, doctor, start):
    """„Vérnyomásmérés naponta, 10:00-ig, 10 napig" (07, Esedékesség)."""
    plan = assign_measurement(
        db,
        patient_id=patient.patient_profile.id,
        measurement_type=get_type_by_code(db, "blood_pressure"),
        assigned_by=doctor.id,
        start_date=start,
        due_time=time(10, 0),
    )
    plan.end_date = start + timedelta(days=9)
    db.flush()
    return plan


def occurrences_of(db, plan):
    return list(
        db.scalars(
            select(AssignmentOccurrence)
            .where(AssignmentOccurrence.assignment_id == plan.id)
            .order_by(AssignmentOccurrence.due_at)
        )
    )


# --- P1: lezárás, majd megerősítő mérés -------------------------------------------------


def window_rule(db, patient, doctor, limit=140, severity=Severity.MODERATE):
    """≥3 szisztolés érték a határ felett 7 napon belül."""
    return create_rule(
        db,
        patient_id=patient.patient_profile.id,
        created_by=doctor.id,
        rule_type=RuleType.WINDOW,
        params={
            "measurement_type": "blood_pressure",
            "limits": {"systolic": {"max": limit}},
            "count": 3,
            "window_days": 7,
        },
        severity=severity,
    )


def p1_closed_alert(db, patient, doctor):
    """P1 szept. 16-ig és a lezárásig: a 7 napon belüli harmadik 140 feletti
    érték (szept. 12., 14., 16.) közepes riasztást nyit; az orvos szept. 21.
    10:02-kor lezárja. (A korábbi mérések napja nincs a dolgozatban.)"""
    window_rule(db, patient, doctor)
    record_bp(db, patient, 146, 88, at=local(2026, 9, 12, 7, 40))
    record_bp(db, patient, 146, 88, at=local(2026, 9, 14, 7, 40))
    _, [alert] = record_bp(db, patient, 148, 92, at=local(2026, 9, 16, 7, 40))
    assert alert.severity is Severity.MODERATE
    assert status_of(db, patient, local(2026, 9, 16, 8)).status is PatientStatus.ATTENTION
    close_alert(
        db,
        alert,
        doctor,
        "Telefonon egyeztettem, gyógyszer módosítva.",
        now=local(2026, 9, 21, 10, 2),
    )
    return alert


def test_p1_closing_then_confirming_measurement(db, patient, doctor):
    """P1 táblázat, pontosan a dolgozat soraival: szept. 16. Figyelem; szept.
    21. 10:02 lezárás → Kezelve; szept. 22. 07:40 128/82 → Rendben. A meglévő
    test_alert_lifecycle.py egy szept. 18-i plusz méréssel futtatja."""
    alert = p1_closed_alert(db, patient, doctor)
    handled = status_of(db, patient, local(2026, 9, 21, 10, 3))
    assert handled.status is PatientStatus.HANDLED
    assert codes(handled) == ["closed_awaiting_data"]
    assert handled.reasons[0].alert.id == alert.id

    assert record_bp(db, patient, 128, 82, at=local(2026, 9, 22, 7, 40))[1] == []
    ok = status_of(db, patient, local(2026, 9, 22, 7, 41))
    assert ok.status is PatientStatus.OK
    assert codes(ok) == ["fresh_data"]


@pytest.mark.xfail(
    strict=True,
    reason=(
        "07, P1 szövege: ha a lezárás után elmarad a mérés, a következő alkalom "
        "HATÁRIDEJE után a státusz Adathiány. A kód szerint a mérés alkalma csak "
        "az időszak vége + 48 óra után (szept. 25. 0:00) lesz elmulasztott, és a "
        "státusz csak a tárolt elmulasztást olvassa: szept. 22. 10:15-kor Kezelve."
    ),
)
def test_p1_missed_measurement_after_closing_gives_no_data_after_the_deadline(db, patient, doctor):
    p1_closed_alert(db, patient, doctor)
    daily_bp_plan(db, patient, doctor, start=date(2026, 9, 22))
    now = local(2026, 9, 22, 10, 15)  # a szept. 22-i alkalom határideje után
    run_occurrence_check(db, now)
    result = status_of(db, patient, now)
    assert result.status is PatientStatus.NO_DATA
    assert "missed_occurrence" in codes(result)


# --- P2: esedékesség és elmaradás (alkalom-táblázat) ----------------------------------------


def test_p2_occurrence_table_rows_1_2_4_5(db, patient, doctor):
    """P2 táblázat 1., 2., 4. és 5. sora: szept. 22. 0:00 a háttérfolyamat
    megnyitja a 22-i alkalmat (határidő 10:00), 07:40 m1 → #1 teljesítve; szept.
    24. 08:10 a beteg rögzíti a „tegnap 19:00-kor" mért m2-t → #2 késve
    teljesítve; 08:12 a mai (07:30-as) m3 → #3 teljesítve. A 3. sor (szept. 23.
    10:15, elmulasztás) külön, xfail-lel."""
    plan = daily_bp_plan(db, patient, doctor, start=date(2026, 9, 22))

    assert open_due_occurrences(db, local(2026, 9, 22, 0, 0)) == 1
    [first] = occurrences_of(db, plan)
    assert first.due_at == local(2026, 9, 22, 10, 0)
    assert first.status is OccurrenceStatus.DUE

    m1 = record(db, patient, 128, 82, local(2026, 9, 22, 7, 40), local(2026, 9, 22, 7, 40))
    assert (first.status, first.measurement_id) == (OccurrenceStatus.FULFILLED, m1.id)

    # A worker szept. 23. 10:15-kor is fut; a 23-i alkalom a kód szerint még esedékes.
    run_occurrence_check(db, local(2026, 9, 23, 10, 15))

    m2 = record(db, patient, 131, 84, local(2026, 9, 23, 19, 0), local(2026, 9, 24, 8, 10))
    m3 = record(db, patient, 127, 81, local(2026, 9, 24, 7, 30), local(2026, 9, 24, 8, 12))
    first, second, third = occurrences_of(db, plan)
    assert second.due_at == local(2026, 9, 23, 10, 0)
    assert (second.status, second.measurement_id) == (OccurrenceStatus.FULFILLED_LATE, m2.id)
    assert second.fulfilled_at == local(2026, 9, 24, 8, 10)
    # A 24-i alkalom határideje (10:00) előtt rögzítve: időben teljesítve.
    assert third.due_at == local(2026, 9, 24, 10, 0)
    assert (third.status, third.measurement_id) == (OccurrenceStatus.FULFILLED, m3.id)
    assert status_of(db, patient, local(2026, 9, 24, 8, 13)).status is PatientStatus.OK


P2_ROW_3_REASON = (
    "07, P2 táblázat 3. sora: szept. 23. 10:15-kor a határidőig nem jött mérés → "
    "#2 elmulasztva → Adathiány („az első elmulasztás a státuszt azonnal "
    "Adathiányra állítja”). A kód szerint a mérés alkalma az időszak vége + 48 óra "
    "(szept. 26. 0:00) előtt nem elmulasztott, hanem esedékes (DUE), és a státusz "
    "Rendben (fresh_data)."
)


def p2_until_row_3(db, patient, doctor):
    plan = daily_bp_plan(db, patient, doctor, start=date(2026, 9, 22))
    open_due_occurrences(db, local(2026, 9, 22, 0, 0))
    record(db, patient, 128, 82, local(2026, 9, 22, 7, 40), local(2026, 9, 22, 7, 40))
    now = local(2026, 9, 23, 10, 15)
    run_occurrence_check(db, now)
    return plan, now


@pytest.mark.xfail(strict=True, reason=P2_ROW_3_REASON)
def test_p2_row_3_occurrence_is_missed_after_the_deadline(db, patient, doctor):
    plan, _ = p2_until_row_3(db, patient, doctor)
    _, second = occurrences_of(db, plan)
    assert second.due_at == local(2026, 9, 23, 10, 0)
    assert second.status is OccurrenceStatus.MISSED


@pytest.mark.xfail(strict=True, reason=P2_ROW_3_REASON)
def test_p2_row_3_first_miss_gives_no_data_at_once(db, patient, doctor):
    _, now = p2_until_row_3(db, patient, doctor)
    result = status_of(db, patient, now)
    assert result.status is PatientStatus.NO_DATA
    assert codes(result) == ["missed_occurrence"]


# --- P3: szabálymódosítás (kiegészítés a meglévő dátumozott teszthez) ---------------------


def test_p3_rule_change_keeps_the_meaning_of_the_alert(db, patient, doctor):
    """P3 szept. 16. és 19.: a v2 (>140, közepes) nyitja a riasztást m1, m2, m3
    kiváltóval; a szept. 19-i v3 (>135, súlyos) „szabály módosult" eseményt ad,
    de a riasztás v2 szerinti jelentése (verzió, kiváltók, súlyosság) nem
    változik. A további sorokat a test_measurement_correction.py
    test_dated_example_of_section_3 teszt ugyanezekkel az adatokkal ellenőrzi."""
    rule = window_rule(db, patient, doctor, limit=150)
    v2 = add_rule_version(
        db,
        rule,
        created_by=doctor.id,
        rule_type=RuleType.WINDOW,
        params={
            "measurement_type": "blood_pressure",
            "limits": {"systolic": {"max": 140}},
            "count": 3,
            "window_days": 7,
        },
        severity=Severity.MODERATE,
    )
    m1, _ = record_bp(db, patient, 145, 88, local(2026, 9, 12, 8))
    m2, _ = record_bp(db, patient, 148, 92, local(2026, 9, 14, 8))
    m3, [alert] = record_bp(db, patient, 151, 90, local(2026, 9, 16, 8))
    v3 = add_rule_version(
        db,
        rule,
        created_by=doctor.id,
        rule_type=RuleType.WINDOW,
        params={
            "measurement_type": "blood_pressure",
            "limits": {"systolic": {"max": 135}},
            "count": 3,
            "window_days": 7,
        },
        severity=Severity.SEVERE,
        now=local(2026, 9, 19, 9),
    )
    created, changed = events(db, alert)
    assert (created.event_type, created.rule_version_id) == (AlertEventType.CREATED, v2.id)
    assert (changed.event_type, changed.rule_version_id) == (AlertEventType.RULE_CHANGED, v3.id)
    assert (changed.actor_id, changed.created_at) == (doctor.id, local(2026, 9, 19, 9))
    assert alert.rule_version_id == v2.id
    assert alert.trigger_data_ids == [str(m.id) for m in (m1, m2, m3)]
    assert alert.severity is Severity.MODERATE
    assert alert.status is AlertStatus.NEW


# --- P3: deduplikáció a demóadatokban (Szabó János) ----------------------------------------


def seeded_szabo_bp_alerts(db):
    # Mint a test_seed.py-ban: az összerendelés a valódi „most"-tól érvényes,
    # ezért a seed holnapi időponttal fut.
    tomorrow = datetime.now(settings.tz).date() + timedelta(days=1)
    seed_demo_data(db, now=datetime.combine(tomorrow, time(9), tzinfo=settings.tz))
    szabo = get_user_by_email(db, "szabo.janos@pulse.example").patient_profile
    alerts = db.scalars(select(Alert).where(Alert.patient_id == szabo.id)).all()
    return [a for a in alerts if a.rule_version.params.get("measurement_type") == "blood_pressure"]


def test_p3_seed_szabo_has_one_window_alert_with_two_events(db):
    """07, P3: Szabó Jánosnál a harmadik 140/90 feletti mérés megnyitja az
    időablakos szabály riasztását, a negyedik ugyanahhoz kapcsolódik: egy
    riasztás, két esemény (keletkezett, ismételt aktiválódás)."""
    [alert] = seeded_szabo_bp_alerts(db)
    assert alert.rule_version.rule_type is RuleType.WINDOW
    created, re_triggered = alert.events
    assert created.event_type is AlertEventType.CREATED
    assert re_triggered.event_type is AlertEventType.RE_TRIGGERED
    assert len(created.trigger_data_ids) == 3
    assert len(re_triggered.trigger_data_ids) == 4


# --- P4: a demó vérnyomás-beállítása --------------------------------------------------------


@pytest.fixture
def demo_rules(db, patient, doctor):
    for rule_type, severity, params in DEMO_RULES:
        if rule_type in (RuleType.THRESHOLD, RuleType.WINDOW):
            create_rule(
                db,
                patient_id=patient.patient_profile.id,
                created_by=doctor.id,
                rule_type=rule_type,
                params=params,
                severity=severity,
            )


def test_p4_demo_gives_severe_alert_above_180_at_once(db, patient, demo_rules):
    """07, P4: a demóban 180 Hgmm szisztolés felett azonnal (az első ilyen
    mérésre) súlyos riasztás; a 180 még nem."""
    assert record_bp(db, patient, 180, 95, at=local(2026, 9, 1, 8))[1] == []
    _, [alert] = record_bp(db, patient, 181, 95, at=local(2026, 9, 2, 8))
    assert alert.severity is Severity.SEVERE
    assert alert.rule_version.rule_type is RuleType.THRESHOLD


def test_p4_demo_moderate_alert_after_three_above_140_90_in_7_days(db, patient, demo_rules):
    """07, P4: a demóban 7 napon belül három 140/90 feletti mérés után közepes
    riasztás; az első kettő után még nincs."""
    assert record_bp(db, patient, 150, 95, at=local(2026, 9, 1, 8))[1] == []
    assert record_bp(db, patient, 145, 85, at=local(2026, 9, 4, 8))[1] == []
    _, [alert] = record_bp(db, patient, 132, 92, at=local(2026, 9, 8, 8))
    assert alert.severity is Severity.MODERATE
    assert alert.rule_version.rule_type is RuleType.WINDOW


# --- P5: az integrációs próba hét beállítása ------------------------------------------------

INTEGRATION = Path(__file__).resolve().parents[2] / "integration"
SCENARIOS = {
    s["id"]: s
    for s in json.loads((INTEGRATION / "eredmeny" / "eredmeny.json").read_text(encoding="utf-8"))[
        "forgatokonyvek"
    ]
}

# A dolgozat táblázata: (mérésszám, szisztolés átlag, diasztolés átlag, cél,
# teljesül: True / False / None = nincs elég adat). A 84,42 a pontos 1013/12
# kerekítve, a 86,625 = 693/8; a motor lebegőpontos, ezért tűréssel vetjük össze.
D_A, D_B = Fraction(1013, 12), Fraction(693, 8)
P5_TABLE = [
    ("A-alap", 12, Fraction(135), D_A, (135, 85), False),
    ("B-elso-nap-nelkul", 16, Fraction(138), D_B, (135, 85), False),
    ("C-eleg-az-egyik", 12, Fraction(135), D_A, (135, 85), True),
    ("D-kerekites-egeszre", 12, Fraction(135), D_A, (135, 85), False),
    ("E-min-4-nap", 12, Fraction(135), D_A, (135, 85), None),
    ("F-80-ev-feletti", 12, Fraction(135), D_A, (145, 85), True),
    ("G-kirendeles-kezdonapja", 16, Fraction(138), D_B, (135, 85), False),
]


@pytest.mark.parametrize(
    ("scenario", "count", "systolic", "diastolic", "target", "met"),
    P5_TABLE,
    ids=[row[0] for row in P5_TABLE],
)
def test_p5_table_matches_the_engine_results(scenario, count, systolic, diastolic, target, met):
    """07, P5 táblázat: a hét beállítás mérésszáma, átlaga, célja és eredménye a
    motor rögzített kimenetéből (integration/eredmeny/eredmeny.json). A saját
    számítás és a motor egyezését a test_nice.py ellenőrzi."""
    result = parse_cql_result(SCENARIOS[scenario]["eredmeny"])
    assert len(result.included_reading_ids) == count
    assert abs(result.mean_systolic - systolic) < 1e-9
    assert abs(result.mean_diastolic - diastolic) < 1e-9
    assert (result.target_systolic, result.target_diastolic) == target
    assert result.target_met is met
    assert result.enough_data is (met is not None)


def test_p5_default_setting_details():
    """07, P5 szövege: az alapbeállításnál az első nap (okt. 5.) négy mérése
    kiesik, 12 mérés marad három napról (okt. 6–8.), a beteg 68 éves, a pontos
    diasztolés átlag 1013/12, a cél 135/85 alatt, és nem teljesül."""
    result = parse_cql_result(SCENARIOS["A-alap"]["eredmeny"])
    assert result.excluded_first_day == date(2026, 10, 5)
    assert len(result.excluded_reading_ids) == 4
    assert result.included_days == [date(2026, 10, d) for d in (6, 7, 8)]
    assert result.age_in_years == 68
    assert abs(result.mean_diastolic - Fraction(1013, 12)) < 1e-9
    assert result.target_met is False
