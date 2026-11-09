"""Szabályok és kiértékelés (F11, F12, F17, F18).

A négy szabálytípus:
- egyszeri küszöbátlépés: ha egy mérés valamelyik értéke a szabályverzióban
  megadott határon kívül esik, riasztás keletkezik. A határ maga még rendben
  van (szigorú összehasonlítás: a „140 feletti" szisztolés a 141-től kezdődik);
- időablakos ismétlődés: ha az új mérés határon kívül esik, és vele együtt
  legalább N határsértő mérés van az utolsó M napban (mindkét szél beleértve);
- kérdőív-pontszám, egy szabály = egy feltétel: vagy a kitöltés összpontszáma
  esik a megadott kiértékelési sávok egyikébe (pl. figyelmeztető sáv), vagy az
  utolsó K azonos verziójú kitöltés pontszáma szigorúan nő (romló trend);
- elmaradt adatküldés: egy célpont (méréstípus vagy kérdőív) utolsó N lezárt
  alkalma mind elmulasztott. Ezt az alkalmak lezárása értékeli ki
  (occurrences.close_missed_occurrences), nem az adat mentése.
"""

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Alert,
    AlertEvent,
    AlertEventType,
    AlertStatus,
    Assignment,
    AssignmentOccurrence,
    Measurement,
    MeasurementType,
    MeasurementValue,
    OccurrenceStatus,
    QuestionnaireTemplate,
    QuestionnaireVersion,
    Rule,
    RuleType,
    RuleVersion,
    Severity,
    Submission,
    not_superseded,
)
from app.services.questionnaires import band_for
from app.services.questionnaires import current_version as questionnaire_version

SEVERITY_RANK = {Severity.MODERATE: 1, Severity.SEVERE: 2}


class RuleError(ValueError):
    """Érvénytelen szabály vagy módosítás; a `code` alapján a felület a saját
    nyelvén írja ki (mint a PlanError). Az üzenet a fejlesztőnek szól. A
    paraméterek szerkezeti hibái (pydantic ValidationError) külön jönnek."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class Limit(BaseModel):
    min: float | None = None
    max: float | None = None

    @model_validator(mode="after")
    def at_least_one_bound(self) -> "Limit":
        if self.min is None and self.max is None:
            raise ValueError("min vagy max megadása kötelező")
        if self.min is not None and self.max is not None and self.min >= self.max:
            raise ValueError("min < max kell")
        return self


class ThresholdParams(BaseModel):
    """Az egyszeri küszöbátlépés paraméterei: méréstípus és komponensenkénti
    határok. Pl. vérnyomás: {"systolic": {"max": 140}, "diastolic": {"max": 90}}
    — bármelyik érték határon kívül esése riasztást vált ki."""

    measurement_type: str
    limits: dict[str, Limit] = Field(min_length=1)


class WindowParams(ThresholdParams):
    """Az időablakos ismétlődés paraméterei: a küszöbszabály határai, és hogy
    hány határsértő mérés (count) kell legfeljebb hány napon (window_days)
    belül. Pl. „≥3 érték 140 felett 7 napon belül"."""

    count: int = Field(ge=2)
    window_days: int = Field(ge=1)


class QuestionnaireParams(BaseModel):
    """A kérdőívszabály paraméterei: melyik kérdőív, és PONTOSAN az egyik
    feltétel (egy szabály = egy feltétel):
    - bands: mely kiértékelési sávok váltanak ki riasztást (pl. ["warning",
      "critical"]); a sávok határai a kérdőívverzióban vannak, így az új
      verzió a saját határait hozza;
    - trend_count: romló trend, az utolsó K azonos verziójú kitöltés
      pontszáma szigorúan nő (több pont = rosszabb)."""

    questionnaire: str
    bands: list[str] | None = Field(default=None, min_length=1)
    trend_count: int | None = Field(default=None, ge=2)

    @model_validator(mode="after")
    def exactly_one_condition(self) -> "QuestionnaireParams":
        if (self.bands is None) == (self.trend_count is None):
            raise ValueError("a sávok (bands) és a trend (trend_count) közül pontosan egy kell")
        return self


class MissingDataParams(BaseModel):
    """Az elmaradt adatküldés paraméterei: a célpont (PONTOSAN az egyik: a
    méréstípus vagy a kérdőív kódja), és hány egymást követő elmulasztott
    alkalom vált ki riasztást (a felületen 2 az alapértelmezés)."""

    measurement_type: str | None = None
    questionnaire: str | None = None
    consecutive_missed: int = Field(ge=1)

    @model_validator(mode="after")
    def exactly_one_target(self) -> "MissingDataParams":
        if (self.measurement_type is None) == (self.questionnaire is None):
            raise ValueError("a méréstípus és a kérdőív közül pontosan egy kell")
        return self


PARAMS_BY_TYPE: dict[RuleType, type[BaseModel]] = {
    RuleType.THRESHOLD: ThresholdParams,
    RuleType.WINDOW: WindowParams,
    RuleType.QUESTIONNAIRE: QuestionnaireParams,
    RuleType.MISSING_DATA: MissingDataParams,
}


@dataclass(frozen=True)
class Violation:
    """Egy érték határon kívül: melyik komponens, mennyi, melyik határ."""

    component: str
    value: float
    bound: str  # "max" vagy "min"
    limit: float


def _validated_params(db: Session, rule_type: RuleType, params: dict[str, Any]) -> dict[str, Any]:
    validated = PARAMS_BY_TYPE[rule_type].model_validate(params)
    # A WindowParams a ThresholdParams leszármazottja: ez az ág mindkettőt ellenőrzi.
    if isinstance(validated, ThresholdParams):
        _check_threshold_params(db, validated)
    elif isinstance(validated, QuestionnaireParams):
        _check_questionnaire_params(db, validated)
    elif isinstance(validated, MissingDataParams):
        _check_missing_data_params(db, validated)
    return validated.model_dump(exclude_none=True)


def _template_by_code(db: Session, code: str) -> QuestionnaireTemplate:
    template = db.scalar(select(QuestionnaireTemplate).where(QuestionnaireTemplate.code == code))
    if template is None:
        raise RuleError("unknown_questionnaire", f"Ismeretlen kérdőív: {code}")
    return template


def _check_questionnaire_params(db: Session, params: QuestionnaireParams) -> None:
    """A kérdőív létezik, és a megadott sávok az aktuális verziójában vannak —
    különben egy elgépelt sávnév miatt a szabály csendben soha nem riasztana
    (Fable-átnézés, 2026-10-12). Trendszabálynál csak a kérdőív léte számít."""
    template = _template_by_code(db, params.questionnaire)
    if params.bands is None:
        return
    version = questionnaire_version(db, template.id)
    known = {band["band"] for band in version.scoring_thresholds}
    unknown = [band for band in params.bands if band not in known]
    if unknown:
        raise RuleError("unknown_band", f"A kérdőívben nincs ilyen sáv: {', '.join(unknown)}")


def _measurement_type_by_code(db: Session, code: str | None) -> MeasurementType:
    known = db.scalar(
        select(MeasurementType)
        .where(MeasurementType.code == code)
        .options(selectinload(MeasurementType.components))
    )
    if known is None:
        raise RuleError("unknown_measurement_type", f"Ismeretlen méréstípus: {code}")
    return known


def _check_threshold_params(db: Session, params: ThresholdParams) -> None:
    """A küszöb- és az időablakos szabály méréstípusa létezik, és a határok
    kulcsai a típus létező komponensei (pl. vérnyomásnál systolic, diastolic;
    egyértékű mérésnél value). Elgépelt kódnál a szabály csendben soha nem
    riasztana, mint a kérdőívszabály elgépelt sávjánál (A4, a hallgató
    jóváhagyásával)."""
    measurement_type = _measurement_type_by_code(db, params.measurement_type)
    known = {component.code for component in measurement_type.components}
    unknown = [code for code in params.limits if code not in known]
    if unknown:
        raise RuleError(
            "unknown_component",
            f"A(z) {params.measurement_type} típusnak nincs ilyen értéke: {', '.join(unknown)}",
        )


def _check_missing_data_params(db: Session, params: MissingDataParams) -> None:
    """A célpont létező méréstípus vagy kérdőív: elgépelt kódnál a szabály
    csendben soha nem riasztana (mint a kérdőívszabálynál)."""
    if params.questionnaire is not None:
        _template_by_code(db, params.questionnaire)
        return
    _measurement_type_by_code(db, params.measurement_type)


def create_rule(
    db: Session,
    *,
    patient_id: uuid.UUID,
    created_by: uuid.UUID,
    rule_type: RuleType,
    params: dict[str, Any],
    severity: Severity,
) -> Rule:
    """Új szabály az első verziójával."""
    rule = Rule(patient_id=patient_id, created_by=created_by)
    db.add(rule)
    db.flush()
    add_rule_version(
        db, rule, created_by=created_by, rule_type=rule_type, params=params, severity=severity
    )
    return rule


def add_rule_version(
    db: Session,
    rule: Rule,
    *,
    created_by: uuid.UUID,
    rule_type: RuleType,
    params: dict[str, Any],
    severity: Severity,
    now: datetime | None = None,
) -> RuleVersion:
    """Szabálymódosítás = új verzió (F12); a korábbiak változatlanok maradnak.

    Típuszár: a szabály típusa verziók között nem változhat, mert a riasztások
    beteg + szabály szerint vonódnak össze (egy küszöbriasztás nem folytatódhat
    például elmaradt-adat jelzésként). Más típushoz új szabály kell.

    Ha a szabálynak van nyitott riasztása, a történetébe „szabály módosult"
    esemény kerül a módosító orvossal és az új verzióval (07_mukodesi_szabalyok.md
    3. rész; Fable-átnézés F2). A riasztás megnyitáskori verziója, súlyossága és
    kiváltó adatai nem változnak: az új verzió a következő kiértékeléstől számít.

    Egyidejű mentés: a szabály sora a verziószám olvasása előtt zárolódik
    (SELECT … FOR UPDATE), így két párhuzamos módosítás egymás után fut, és a
    második már az első verzióját látja; a (rule_id, version_no) egyediség nem
    sérülhet. Zárolási sorrend: szabály, majd a nyitott riasztás; az életút-
    műveletek csak a riasztást zárolják, így körkörös várakozás nem alakulhat ki."""
    now = now or datetime.now(UTC)
    db.execute(select(Rule.id).where(Rule.id == rule.id).with_for_update())
    last = db.scalar(
        select(RuleVersion)
        .where(RuleVersion.rule_id == rule.id)
        .order_by(RuleVersion.version_no.desc())
        .limit(1)
    )
    if last is not None and last.rule_type is not rule_type:
        raise RuleError(
            "rule_type_locked",
            f"A szabály típusa nem módosítható ({last.rule_type} → {rule_type}); "
            "más típushoz új szabályt kell létrehozni",
        )
    version = RuleVersion(
        rule_id=rule.id,
        version_no=(last.version_no if last else 0) + 1,
        rule_type=rule_type,
        params=_validated_params(db, rule_type, params),
        severity=severity,
        created_by=created_by,
    )
    db.add(version)
    db.flush()
    alert = open_alert(db, rule.patient_id, rule.id, for_update=True)
    if alert is not None:
        db.add(
            AlertEvent(
                alert_id=alert.id,
                actor_id=created_by,
                event_type=AlertEventType.RULE_CHANGED,
                rule_version_id=version.id,
                trigger_data_ids=None,
                created_at=now,
            )
        )
        db.flush()
    return version


def current_version(db: Session, rule_id: uuid.UUID) -> RuleVersion:
    return db.scalars(
        select(RuleVersion)
        .where(RuleVersion.rule_id == rule_id)
        .order_by(RuleVersion.version_no.desc())
        .limit(1)
    ).one()


@dataclass
class RuleEntry:
    """Egy szabály a szabálylistához (orvosi felület): a verziói időrendben (az
    utolsó az aktuális) és a nyitott riasztásainak száma."""

    rule: Rule
    versions: list[RuleVersion]
    open_alerts: int

    @property
    def current(self) -> RuleVersion:
        return self.versions[-1]


def list_rules(db: Session, patient_id: uuid.UUID) -> list[RuleEntry]:
    """A beteg összes szabálya létrehozás szerint, a teljes verziólistával."""
    rules = db.scalars(
        select(Rule)
        .where(Rule.patient_id == patient_id)
        .options(selectinload(Rule.versions))
        .order_by(Rule.created_at, Rule.id)
        # Egy kérésen belül a módosítás után is a friss verziólista kell.
        .execution_options(populate_existing=True)
    ).all()
    open_counts = dict(
        db.execute(
            select(Alert.rule_id, func.count())
            .where(Alert.patient_id == patient_id, Alert.status != AlertStatus.CLOSED)
            .group_by(Alert.rule_id)
        ).all()
    )
    return [
        RuleEntry(rule=rule, versions=list(rule.versions), open_alerts=open_counts.get(rule.id, 0))
        for rule in rules
    ]


def threshold_violations(params: ThresholdParams, measurement: Measurement) -> list[Violation]:
    """A mérés határon kívüli értékei a megadott paraméterek szerint."""
    if measurement.type.code != params.measurement_type:
        return []
    violations: list[Violation] = []
    for value in sorted(measurement.values, key=lambda v: v.component.order_no):
        limit = params.limits.get(value.component.code)
        if limit is None:
            continue
        if limit.max is not None and value.value > limit.max:
            violations.append(Violation(value.component.code, value.value, "max", limit.max))
        elif limit.min is not None and value.value < limit.min:
            violations.append(Violation(value.component.code, value.value, "min", limit.min))
    return violations


def open_alert(
    db: Session, patient_id: uuid.UUID, rule_id: uuid.UUID, *, for_update: bool = False
) -> Alert | None:
    """A beteg + szabály páros nyitott riasztása (legfeljebb egy van).

    `for_update=True` az írási ágnak való (új esemény kerül a riasztásba): a sort
    ugyanúgy zárolja (SELECT … FOR UPDATE), mint az életút-műveletek lock_alert-je.
    Ha közben egy orvos épp lezárja, a kiértékelés megvárja a lezárás végét; a
    PostgreSQL ekkor a friss soron újra ellenőrzi a feltételt, a lezárt riasztás
    kiesik, és a hívó új riasztást nyit, nem a lezártba ír. A csak olvasó hívások
    zár nélkül futnak."""
    query = select(Alert).where(
        Alert.patient_id == patient_id,
        Alert.rule_id == rule_id,
        Alert.status != AlertStatus.CLOSED,
    )
    if for_update:
        query = query.with_for_update().execution_options(populate_existing=True)
    return db.scalar(query)


def _active_rules(
    db: Session, patient_id: uuid.UUID, rule_type: RuleType
) -> Iterator[tuple[Rule, RuleVersion]]:
    """A beteg aktív szabályai az aktuális verziójukkal, egy szabálytípusból.

    Rögzített sorrendben, hogy két egyidejű kiértékelés a riasztásokat azonos
    sorrendben zárolja (_raise_alert), és ne várjanak körkörösen egymásra."""
    rules = db.scalars(
        select(Rule)
        .where(Rule.patient_id == patient_id, Rule.is_active.is_(True))
        .order_by(Rule.created_at, Rule.id)
    ).all()
    for rule in rules:
        version = current_version(db, rule.id)
        if version.rule_type is rule_type:
            yield rule, version


def _raise_alert(
    db: Session,
    rule: Rule,
    version: RuleVersion,
    patient_id: uuid.UUID,
    trigger_ids: list[str],
    now: datetime,
) -> Alert:
    """Riasztás nyitása, vagy ha a beteg + szabály párosra már van nyitott,
    „ismételt aktiválódás" esemény hozzá (F18; a súlyosság emelkedhet). Minden
    esemény tárolja az alkalmazott szabályverziót és a kiváltó adatot (F17).

    A nyitott riasztás sorzárral olvasódik (open_alert for_update), így egy
    egyidejű lezárás után nem a lezártba kerül „ismételt aktiválódás".

    TODO M3: két egyidejű kérés ugyanarra a beteg + szabály párosra mindkettőben
    „nincs nyitott riasztást" láthat (nem létező sort a FOR UPDATE nem zárol); a
    második ekkor az uq_alerts_open_per_rule indexbe ütközik, és a mérése is
    visszagördül. Megoldás: a beteg szabályainak zárolása (SELECT … FOR UPDATE) a
    kiértékelés elején (Fable-átnézés F4)."""
    alert = open_alert(db, patient_id, rule.id, for_update=True)
    if alert is None:
        alert = Alert(
            patient_id=patient_id,
            rule_id=rule.id,
            rule_version_id=version.id,
            severity=version.severity,
            trigger_data_ids=trigger_ids,
            created_at=now,
        )
        db.add(alert)
        db.flush()
        event_type = AlertEventType.CREATED
    else:
        if SEVERITY_RANK[version.severity] > SEVERITY_RANK[alert.severity]:
            alert.severity = version.severity
        event_type = AlertEventType.RE_TRIGGERED
    db.add(
        AlertEvent(
            alert_id=alert.id,
            event_type=event_type,
            rule_version_id=version.id,
            trigger_data_ids=trigger_ids,
            created_at=now,
        )
    )
    return alert


def window_violations(
    db: Session, params: WindowParams, measurement: Measurement
) -> list[Measurement]:
    """Az időablak határsértő mérései measured_at szerint rendezve (az új mérést
    is beleértve). Az ablak [measured_at − window_days nap, measured_at],
    mindkét széle beleértve, a beteg ugyanilyen típusú méréseiből. A felülírt
    (javított) mérés nem számít, csak a javítási lánc vége (not_superseded, A7).

    Ismert korlát: a visszadátumozott mérés csak a saját measured_at-jáig látja
    az ablakot, a nála később mért értékeket nem."""
    start = measurement.measured_at - timedelta(days=params.window_days)
    in_window = db.scalars(
        select(Measurement)
        .where(
            Measurement.patient_id == measurement.patient_id,
            Measurement.type_id == measurement.type_id,
            Measurement.measured_at >= start,
            Measurement.measured_at <= measurement.measured_at,
            not_superseded(),
        )
        .options(
            selectinload(Measurement.values).selectinload(MeasurementValue.component),
            selectinload(Measurement.type),
        )
        .order_by(Measurement.measured_at, Measurement.id)
    )
    return [m for m in in_window if threshold_violations(params, m)]


def evaluate_measurement(
    db: Session, measurement: Measurement, now: datetime | None = None
) -> list[Alert]:
    """Az új mérés kiértékelése a beteg aktív küszöb- és időablakos
    szabályainak aktuális verziójával."""
    now = now or datetime.now(UTC)
    touched: list[Alert] = []
    for rule, version in _active_rules(db, measurement.patient_id, RuleType.THRESHOLD):
        if threshold_violations(ThresholdParams.model_validate(version.params), measurement):
            touched.append(
                _raise_alert(db, rule, version, measurement.patient_id, [str(measurement.id)], now)
            )
    for rule, version in _active_rules(db, measurement.patient_id, RuleType.WINDOW):
        params = WindowParams.model_validate(version.params)
        # Csak határsértő új mérés értékel: egy rendben lévő mérés nem nyithat
        # (lezárás után újra) riasztást a még ablakban lévő korábbi értékekből
        # (07_mukodesi_szabalyok.md, 1. rész: lezárás, majd megerősítő mérés).
        if not threshold_violations(params, measurement):
            continue
        violating = window_violations(db, params, measurement)
        if len(violating) >= params.count:
            trigger_ids = [str(m.id) for m in violating]
            touched.append(
                _raise_alert(db, rule, version, measurement.patient_id, trigger_ids, now)
            )
    db.flush()
    return touched


# Az események, amelyek a riasztás kiértékelését rögzítik (a kiváltó adataik a
# riasztás aktuális alapja); a „kiváltó adat javítva" nem ilyen.
EVALUATION_EVENTS = (AlertEventType.CREATED, AlertEventType.RE_TRIGGERED)


def _chain_end(db: Session, measurement: Measurement) -> Measurement:
    """A mérés javítási láncának vége (az érvényes érték): m3 → m3′ → m3″.
    Lekérdezéssel, nem a correction kapcsolatból, mert az a sessionben a
    javítás előtti (üres) állapotában maradhatott."""
    while True:
        successor = db.scalar(
            select(Measurement)
            .where(Measurement.corrected_from == measurement.id)
            .options(
                selectinload(Measurement.values).selectinload(MeasurementValue.component),
                selectinload(Measurement.type),
            )
        )
        if successor is None:
            return measurement
        measurement = successor


def correction_condition_met(db: Session, alert: Alert, version: RuleVersion) -> bool | None:
    """Teljesül-e még a riasztás feltétele a javítás után, az adott (aktuális)
    szabályverzió szerint (07_mukodesi_szabalyok.md 3. rész; A7).

    Az alap a riasztás legutóbbi kiértékelése (keletkezés vagy ismételt
    aktiválódás) a kiváltó adataival:
    - küszöbszabálynál a kiváltó mérés(ek) javítási láncának vége határsértő-e;
    - időablakos szabálynál az ablak újraszámolása ugyanarra a végpontra (a
      legutóbbi kiváltó mérés ideje; a javítás ezt nem változtatja, D1), a
      felülírt mérések nélkül: legalább count határsértő mérés van-e benne.
      A 07-es példában: m2, m3′, m4 a v3 (> 135) szerint 2 sértő < 3, tehát
      „a feltétel már nem teljesül".
    Más szabálytípusnál (kérdőív, elmaradt adat) nincs mérés-kiváltó: None."""
    if version.rule_type not in (RuleType.THRESHOLD, RuleType.WINDOW):
        return None
    basis = db.scalar(
        select(AlertEvent)
        .where(AlertEvent.alert_id == alert.id, AlertEvent.event_type.in_(EVALUATION_EVENTS))
        .order_by(AlertEvent.created_at.desc(), AlertEvent.id.desc())
        .limit(1)
    )
    ids = [uuid.UUID(i) for i in (basis.trigger_data_ids or [])] if basis else []
    triggers = list(
        db.scalars(
            select(Measurement)
            .where(Measurement.id.in_(ids))
            .options(
                selectinload(Measurement.values).selectinload(MeasurementValue.component),
                selectinload(Measurement.type),
            )
        )
    )
    if not triggers:
        return False
    if version.rule_type is RuleType.THRESHOLD:
        params = ThresholdParams.model_validate(version.params)
        return any(threshold_violations(params, _chain_end(db, m)) for m in triggers)
    w_params = WindowParams.model_validate(version.params)
    anchor = max(triggers, key=lambda m: (m.measured_at, m.id))
    return len(window_violations(db, w_params, anchor)) >= w_params.count


def flag_corrected_trigger(
    db: Session,
    original: Measurement,
    correction: Measurement,
    *,
    actor_id: uuid.UUID | None = None,
    now: datetime | None = None,
) -> list[Alert]:
    """„Kiváltó adat javítva" esemény minden riasztásba, amelynek valamelyik
    eseménye a javított mérést kiváltóként tartalmazza (A7; a hallgató döntései
    D2, D4). A javítás után hívandó (a javító sor már a sessionben van).

    Az esemény kiváltó adata [eredeti, javított], a szabályverziója az aktuális,
    és tárolja, hogy a feltétel e szerint még teljesül-e (pillanatkép,
    correction_condition_met). Láncnál (m3′ javítása) a korábbi javítás-esemény
    tartalmazza m3′-t, így ugyanaz a riasztás kapja az újabb eseményt is.

    - Nyitott riasztás: az esemény mellé needs_review jelölést kap; automatikus
      lezárás nincs, az állapot és a súlyosság nem változik (a jelölés nem
      állapot). Az írás a meglévő sorzáras úton megy (open_alert for_update); ha
      közben egy orvos lezárta, a lezártként kezeljük.
    - Lezárt riasztás (D4): az esemény bekerül a történetébe, de needs_review
      nem áll be, és az állapota sem változik (a lezárás végállapot).

    A riasztások a szabályok rögzített sorrendjében zárolódnak (mint a
    kiértékelésben), így két egyidejű művelet nem várhat körkörösen egymásra.
    Visszaadja az érintett riasztásokat."""
    now = now or datetime.now(UTC)
    with_trigger = select(AlertEvent.alert_id).where(
        AlertEvent.trigger_data_ids.contains([str(original.id)])
    )
    alerts = db.scalars(
        select(Alert)
        .join(Rule, Alert.rule_id == Rule.id)
        .where(Alert.patient_id == original.patient_id, Alert.id.in_(with_trigger))
        .order_by(Rule.created_at, Rule.id, Alert.created_at, Alert.id)
    ).all()
    touched = []
    for alert in alerts:
        is_open = False
        if alert.status is not AlertStatus.CLOSED:
            locked = open_alert(db, alert.patient_id, alert.rule_id, for_update=True)
            is_open = locked is not None and locked.id == alert.id
            if not is_open:
                db.refresh(alert)
        version = current_version(db, alert.rule_id)
        db.add(
            AlertEvent(
                alert_id=alert.id,
                actor_id=actor_id,
                event_type=AlertEventType.TRIGGER_CORRECTED,
                rule_version_id=version.id,
                trigger_data_ids=[str(original.id), str(correction.id)],
                condition_met=correction_condition_met(db, alert, version),
                created_at=now,
            )
        )
        if is_open:
            alert.needs_review = True
        touched.append(alert)
    db.flush()
    return touched


def worsening_trend(db: Session, submission: Submission, count: int) -> list[Submission]:
    """A romló trend kiváltói időrendben, vagy üres lista, ha nincs trend.

    A beteg utolsó `count` kitöltése ugyanabból a kérdőívből (beküldés szerint);
    mind a legújabbal azonos kérdőívverzión kell legyen (verzióváltás után a
    trend újraindul, 07_mukodesi_szabalyok.md 3. rész), és az összpontszám
    szigorúan nő (egyenlőség nem elég; több pont = rosszabb)."""
    latest = list(
        db.scalars(
            select(Submission)
            .join(QuestionnaireVersion, Submission.version_id == QuestionnaireVersion.id)
            .where(
                Submission.patient_id == submission.patient_id,
                QuestionnaireVersion.template_id == submission.version.template_id,
            )
            .order_by(Submission.submitted_at.desc(), Submission.id.desc())
            .limit(count)
        )
    )
    if len(latest) < count:
        return []
    chronological = latest[::-1]
    if any(s.version_id != chronological[-1].version_id for s in chronological):
        return []
    scores = [s.total_score for s in chronological]
    if all(a < b for a, b in zip(scores, scores[1:], strict=False)):
        return chronological
    return []


def evaluate_submission(
    db: Session, submission: Submission, now: datetime | None = None
) -> list[Alert]:
    """Az új kérdőív-kitöltés kiértékelése a beteg aktív kérdőívszabályaival.
    Sávszabálynál riasztás, ha az összpontszám a megadott sávok egyikébe esik
    (a sávhatárok a kitöltött kérdőívverzió részei, F13); trendszabálynál, ha
    az utolsó K azonos verziójú kitöltés pontszáma szigorúan nő."""
    now = now or datetime.now(UTC)
    touched: list[Alert] = []
    for rule, version in _active_rules(db, submission.patient_id, RuleType.QUESTIONNAIRE):
        params = QuestionnaireParams.model_validate(version.params)
        if submission.version.template.code != params.questionnaire:
            continue
        if params.bands is not None:
            if band_for(submission.version, submission.total_score) not in params.bands:
                continue
            trigger_ids = [str(submission.id)]
        else:
            assert params.trend_count is not None
            trend = worsening_trend(db, submission, params.trend_count)
            if not trend:
                continue
            trigger_ids = [str(s.id) for s in trend]
        touched.append(_raise_alert(db, rule, version, submission.patient_id, trigger_ids, now))
    db.flush()
    return touched


@dataclass(frozen=True)
class MissedTarget:
    """Egy most elmulasztottra zárt alkalom célpontja: a beteg, és vagy a
    méréstípus, vagy a kérdőívsablon azonosítója (az előírásból)."""

    patient_id: uuid.UUID
    measurement_type_id: uuid.UUID | None
    questionnaire_template_id: uuid.UUID | None


def missing_target_id(db: Session, params: MissingDataParams) -> uuid.UUID | None:
    """A szabály célpontjának azonosítója (kérdőívsablon vagy méréstípus) a
    kódja alapján; None, ha a kód közben megszűnt (létrehozáskor létezett)."""
    if params.questionnaire is not None:
        return db.scalar(
            select(QuestionnaireTemplate.id).where(
                QuestionnaireTemplate.code == params.questionnaire
            )
        )
    return db.scalar(
        select(MeasurementType.id).where(MeasurementType.code == params.measurement_type)
    )


def missing_target_column(params: MissingDataParams) -> Any:
    """Az előírás oszlopa, amely a szabály célpontjára mutat."""
    if params.questionnaire is not None:
        return Assignment.questionnaire_template_id
    return Assignment.measurement_type_id


def _hits(params: MissingDataParams, target_id: uuid.UUID, target: MissedTarget) -> bool:
    """A most lezárt alkalom célpontja a szabályé-e."""
    if params.questionnaire is not None:
        return target.questionnaire_template_id == target_id
    return target.measurement_type_id == target_id


def missed_streak(
    db: Session, patient_id: uuid.UUID, params: MissingDataParams, target_id: uuid.UUID
) -> list[AssignmentOccurrence]:
    """Az elmaradt adat kiváltói határidő szerint rendezve, vagy üres lista.

    A beteg adott célpontra szóló összes alkalma (az előírás-módosítási láncon
    átívelően, a visszavont előírásokéval együtt: csak a célpont számít), ezek
    közül a lezártak (nem esedékesek) utolsó `count` darabja; riasztás, ha mind
    elmulasztott. A késve teljesítés (pótlás) így megszakítja a sorozatot."""
    count = params.consecutive_missed
    latest = list(
        db.scalars(
            select(AssignmentOccurrence)
            .join(Assignment, AssignmentOccurrence.assignment_id == Assignment.id)
            .where(
                Assignment.patient_id == patient_id,
                missing_target_column(params) == target_id,
                AssignmentOccurrence.status != OccurrenceStatus.DUE,
            )
            .order_by(AssignmentOccurrence.due_at.desc(), AssignmentOccurrence.id.desc())
            .limit(count)
        )
    )
    if len(latest) < count or any(o.status is not OccurrenceStatus.MISSED for o in latest):
        return []
    return latest[::-1]


def evaluate_missed(
    db: Session, targets: set[MissedTarget], now: datetime | None = None
) -> list[Alert]:
    """Az elmaradt adat szabályok kiértékelése a most elmulasztottra zárt
    alkalmak célpontjaira. Az occurrences.close_missed_occurrences hívja, így
    a háttérfolyamat, az „ellenőrzés most" és minden más hívó ugyanígy értékel.

    Csak az a szabály értékelődik, amelynek a célpontján most zárult alkalom:
    az ismételt futás, amely semmit nem zár le, nem ad új eseményt
    (idempotens). Nyitott riasztás mellett egy újabb elmulasztás ismételt
    aktiválódás (_raise_alert)."""
    now = now or datetime.now(UTC)
    touched: list[Alert] = []
    for patient_id in sorted({t.patient_id for t in targets}):
        patient_targets = [t for t in targets if t.patient_id == patient_id]
        for rule, version in _active_rules(db, patient_id, RuleType.MISSING_DATA):
            params = MissingDataParams.model_validate(version.params)
            target_id = missing_target_id(db, params)
            if target_id is None or not any(_hits(params, target_id, t) for t in patient_targets):
                continue
            streak = missed_streak(db, patient_id, params, target_id)
            if streak:
                trigger_ids = [str(o.id) for o in streak]
                touched.append(_raise_alert(db, rule, version, patient_id, trigger_ids, now))
    db.flush()
    return touched
