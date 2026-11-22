"""A beteg státusza (F9; 07_mukodesi_szabalyok.md, 1. rész).

Számított érték, nem tárolt mező. Több feltétel egyidejű fennállásakor a
sorrendben előbb álló érvényes, a felület a többi okot is kiírja:
Súlyos > Figyelem > Adathiány > Kezelve > Rendben.

Az Adathiány okai (M3, A4 2. lépés, a hallgató döntése):
- elmulasztott alkalom ("missed_occurrence"): a beteg valamelyik érvényes
  előírásának legutóbbi lezárt alkalma elmulasztott, vagy a határideje lejárt,
  és még nem teljesült (K4, a hallgató döntése, 2026-11-16; a dolgozat 7.
  fejezete szerint a státusz a határidő után azonnal Adathiány). Lezárt az
  alkalom, ha teljesült (akár a határideje előtt), elmulasztott, vagy a
  határideje lejárt. A határidő lejárta után az esedékes (DUE) alkalom még
  pótolható (mérésnél 48 óráig, lásd occurrences.missed_from); a pótlással
  (késve teljesítés) az ok megszűnik. Elmulasztottra (MISSED) továbbra is a
  háttérfolyamat zárja. A késve teljesített (pótolt) alkalom nem elmulasztott.
  A visszavont, lejárt és még el nem kezdett előírás nem számít: az
  előírás-módosítás (visszavonás + új előírás) után a régi elmulasztása nem
  ragad a betegen. A letiltott időszakba eső határidejű, nem teljesített
  alkalom sem számít (M3, A1; services/disabled.py), sor nélkül sem: ilyenkor az
  előtte lévő, nem kimentett alkalom a legutóbbi lezárt;
- még nem érkezett adat: se mérés, se kitöltés ("no_data_yet");
- nincs friss adat ("stale_data"): csak ha a betegnek nincs lezárt alkalma
  érvényes előíráson (nincs előírása, vagy az első határidő még nem járt le).
  Ilyenkor a legutóbbi mérés vagy kitöltés legfeljebb 7 napos lehet
  (rendszerszintű beállítás, data_freshness_days); a letiltott időszak ebbe
  nem számít bele (M3, A1; a hallgató döntése, 2026-11-21: az adat kora a
  letiltott időszakok átfedésével csökken). Ahol már van lezárt
  alkalom, a frissességet az alkalmak teljesítése adja: a havi előírását
  rendben teljesítő beteg 20 napos méréssel is Rendben.

A Kezelve oka (M3, A6; a 07-es dokumentum szerint, a hallgató döntése D4a+D5):
- a beteg szabályonként LEGUTÓBB lezárt riasztása (a lezárás ideje a closed
  esemény ideje), ha a lezárás óta nem érkezett a szabály célpontjára „rendben
  lévő adat" ("closed_awaiting_data"). Rendben lévő adat az AKTUÁLIS
  szabályverzió szerint: küszöb- és időablakos szabálynál a méréstípus olyan
  mérése, amelynek mérési ideje a lezárás utáni, és nem határsértő;
  kérdőívsávnál a lezárás utáni kitöltés, amelynek sávja nincs a szabály sávjai
  közt; trendnél a lezárás utáni legújabb kitöltés nem indít trendet; elmaradt
  adatnál a célpont alkalma a lezárás után teljesült (akár késve, pótlással);
- ha a szabálynak közben új, nyitott riasztása van (a lezárás után riasztó adat
  jött), a Kezelve ok elmarad: a nyitott riasztás az erősebb, és a „megerősítő
  adatra vár" ugyanarra a szabályra félrevezető volna.
A lezárás tehát önmagában soha nem ad Rendben státuszt.

A felülírt (javított) mérés sehol nem számít (A7, közös not_superseded()
feltétel): a frissességben és a megerősítő adatnál csak a javítási lánc vége.
A javított kiváltójú nyitott riasztás needs_review jelölése a státuszt nem
változtatja (csak jelölés).

A tárolt alkalmakat olvassa, és a határidő lejártát a lekérdezés idejéből
(now) dönti el; semmit nem ír: alkalmat nem nyit és nem zár (az elmulasztottra
zárás a háttérfolyamaté). Ha a legutóbbi lejárt határidejű időszaknak még
nincs alkalomsora (a háttérfolyamat, a mentés vagy a teendőlista még nem
nyitotta meg), azt az előírás időszakaiból számolja (lapsed_without_row;
review K2, 2026-11-16): a határidő utáni Adathiány így bármely hívónál,
hívási sorrendtől függetlenül él. Ilyenkor az ok alkalom nélkül megy ki; az
orvosi végpontok (api/patients.py) ezért a státusz előtt a teendőlistát
kérik le, ami a sort megnyitja, így ott az ok az alkalom adataival jelenik meg.
Adat nélkül sosem Rendben a státusz: az adathiány nem ad kedvező jelzést.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models import (
    Alert,
    AlertEvent,
    AlertEventType,
    AlertStatus,
    Assignment,
    AssignmentOccurrence,
    AssignmentTarget,
    Measurement,
    MeasurementType,
    MeasurementValue,
    OccurrenceStatus,
    PatientProfile,
    QuestionnaireTemplate,
    QuestionnaireVersion,
    RuleType,
    RuleVersion,
    Severity,
    Submission,
    not_superseded,
)
from app.services.access import assigned_patients_query
from app.services.alerts import list_patient_alerts
from app.services.disabled import (
    disabled_overlap,
    disabled_periods,
    excused_due,
    is_excused,
)
from app.services.occurrences import latest_lapsed_period, previous_period, valid_on
from app.services.questionnaires import band_for
from app.services.rules import (
    MissingDataParams,
    QuestionnaireParams,
    ThresholdParams,
    current_version,
    missing_target_column,
    missing_target_id,
    threshold_violations,
    worsening_trend,
)


class PatientStatus(StrEnum):
    SEVERE = "severe"  # Súlyos: súlyos nyitott riasztás
    ATTENTION = "attention"  # Figyelem: közepes nyitott riasztás
    NO_DATA = "no_data"  # Adathiány: elmulasztott alkalom, vagy nincs friss adat
    HANDLED = "handled"  # Kezelve: lezárva, megerősítő adatra vár (M3)
    OK = "ok"  # Rendben: friss adat, a fentiek egyike sem


PRIORITY = list(PatientStatus)


@dataclass
class StatusReason:
    status: PatientStatus
    # "open_alert" | "missed_occurrence" | "no_data_yet" | "stale_data"
    # | "closed_awaiting_data" | "fresh_data"
    code: str
    alert: Alert | None = None
    at: datetime | None = None
    # Elmulasztott alkalomnál az alkalom (a felület „Ok" oszlopához); a még sor
    # nélküli lejárt határidőnél üres (lásd lapsed_without_row).
    occurrence: AssignmentOccurrence | None = None
    # Kezelve oknál a lezáró orvos (felhasználó) azonosítója.
    actor_id: uuid.UUID | None = None

    @property
    def occurrence_id(self) -> uuid.UUID | None:
        return self.occurrence.id if self.occurrence else None


@dataclass
class PatientStatusResult:
    status: PatientStatus
    reasons: list[StatusReason]
    last_data_at: datetime | None


def last_data_at(db: Session, patient_id: uuid.UUID) -> datetime | None:
    """A legutóbbi adat ideje: mérés (a mérés ideje) vagy kérdőív-kitöltés. A
    felülírt mérés nem számít (A7); mivel a javítás a mérés idejét megtartja
    (D1), ez az értéket nem változtatja, csak a közös szabályt követi."""
    measured = db.scalar(
        select(func.max(Measurement.measured_at)).where(
            Measurement.patient_id == patient_id, not_superseded()
        )
    )
    submitted = db.scalar(
        select(func.max(Submission.submitted_at)).where(Submission.patient_id == patient_id)
    )
    return max((t for t in (measured, submitted) if t is not None), default=None)


def latest_closed_occurrences(
    db: Session, patient_id: uuid.UUID, now: datetime
) -> list[AssignmentOccurrence]:
    """A beteg ma érvényes előírásainak legutóbbi lezárt alkalma, előírásonként
    egy, határidő szerint. Lezárt: teljesített vagy elmulasztott (akár a
    határidő előtt teljesült), vagy még esedékes, de a határideje lejárt
    (now > due_at, mint a teendőlista „késésben" állapotánál és a késve
    teljesítésnél). Inaktív kérdőívre szóló előírás nem számít: arra a
    háttérfolyamat nem nyit alkalmat, így a beteg sem teljesíthetné (mint az
    open_due_occurrences-ben)."""
    today = now.astimezone(settings.tz).date()
    latest = db.scalars(
        select(AssignmentOccurrence)
        .join(Assignment, AssignmentOccurrence.assignment_id == Assignment.id)
        .outerjoin(Assignment.template)
        .where(
            Assignment.patient_id == patient_id,
            *valid_on(today),
            or_(
                Assignment.target_kind == AssignmentTarget.MEASUREMENT,
                QuestionnaireTemplate.is_active.is_(True),
            ),
            or_(
                AssignmentOccurrence.status != OccurrenceStatus.DUE,
                AssignmentOccurrence.due_at < now,
            ),
            # A letiltott időszakba eső határidejű, esedékes alkalom nem lezárt (A1).
            ~excused_due(
                AssignmentOccurrence.status == OccurrenceStatus.DUE,
                Assignment.patient_id,
                AssignmentOccurrence.due_at,
            ),
        )
        # PostgreSQL DISTINCT ON: előírásonként a legkésőbbi határidejű sor.
        .ext(distinct_on(AssignmentOccurrence.assignment_id))
        .order_by(AssignmentOccurrence.assignment_id, AssignmentOccurrence.due_at.desc())
    ).all()
    return sorted(latest, key=lambda o: (o.due_at, o.id))


def lapsed_without_row(
    db: Session,
    patient_id: uuid.UUID,
    now: datetime,
    stored: list[AssignmentOccurrence],
) -> dict[uuid.UUID, datetime]:
    """A tárolt sor nélküli lejárt határidők (review K2, 2026-11-16): a beteg
    ma érvényes előírásainál (ugyanaz a szűrés, mint latest_closed_occurrences)
    a legutóbbi lejárt határidejű időszak, ha annak még nincs alkalomsora, és
    nincs nála későbbi lezárt (tárolt) alkalom sem. Ilyenkor az alkalom nem
    teljesülhetett (a teljesítés mindig sort hoz létre), tehát lejárt és
    teljesítetlen: a státusz ugyanúgy Adathiány, mintha a sor meglenne. Így a
    garancia a hívási sorrendtől (teendőlista, háttérfolyamat) független, és a
    státusz továbbra sem ír semmit. Előírás szerint a határidő; az előírás
    régebbi tárolt alkalma helyett ez számít (mint ha a sor meglenne)."""
    today = now.astimezone(settings.tz).date()
    assignments = db.scalars(
        select(Assignment)
        .outerjoin(Assignment.template)
        .where(
            Assignment.patient_id == patient_id,
            *valid_on(today),
            or_(
                Assignment.target_kind == AssignmentTarget.MEASUREMENT,
                QuestionnaireTemplate.is_active.is_(True),
            ),
        )
    ).all()
    latest_stored = {o.assignment_id: o.due_at for o in stored}
    excused_periods = disabled_periods(db, patient_id)
    lapsed = {}
    for assignment in assignments:
        period = latest_lapsed_period(assignment, now)
        # A letiltott időszakba eső határidő kimarad: az előtte lévő időszak számít (A1).
        while period is not None and is_excused(excused_periods, period.due_at):
            period = previous_period(assignment, period)
        if period is None:
            continue
        known = latest_stored.get(assignment.id)
        if known is not None and known >= period.due_at:
            continue
        lapsed[assignment.id] = period.due_at
    return lapsed


def latest_closed_alerts(db: Session, patient_id: uuid.UUID) -> list[tuple[Alert, AlertEvent]]:
    """A beteg szabályonként legutóbb lezárt riasztása a lezárás eseményével
    (egy lekérdezés). Lezárás-esemény nélküli lezárt riasztás nem számít."""
    rows = db.execute(
        select(Alert, AlertEvent)
        .join(
            AlertEvent,
            and_(
                AlertEvent.alert_id == Alert.id,
                AlertEvent.event_type == AlertEventType.CLOSED,
            ),
        )
        .where(Alert.patient_id == patient_id, Alert.status == AlertStatus.CLOSED)
        # PostgreSQL DISTINCT ON: szabályonként a legkésőbbi lezárás.
        .ext(distinct_on(Alert.rule_id))
        .order_by(Alert.rule_id, AlertEvent.created_at.desc(), AlertEvent.id)
    ).all()
    return [(alert, event) for alert, event in rows]


_DONE = (OccurrenceStatus.FULFILLED, OccurrenceStatus.FULFILLED_LATE)


def _measurements_since(
    db: Session, patient_id: uuid.UUID, type_code: str, since: datetime
) -> list[Measurement]:
    """A méréstípus érvényes mérései a megadott idő után. A felülírt (javított)
    mérés kimarad (A7): a régi érték nem lehet „megerősítő adat", csak a javítási
    lánc vége."""
    return list(
        db.scalars(
            select(Measurement)
            .join(MeasurementType, Measurement.type_id == MeasurementType.id)
            .where(
                Measurement.patient_id == patient_id,
                MeasurementType.code == type_code,
                Measurement.measured_at > since,
                not_superseded(),
            )
            .options(
                selectinload(Measurement.values).selectinload(MeasurementValue.component),
                selectinload(Measurement.type),
            )
            .order_by(Measurement.measured_at, Measurement.id)
        )
    )


def _submissions_since(
    db: Session, patient_id: uuid.UUID, questionnaire: str, since: datetime
) -> list[Submission]:
    return list(
        db.scalars(
            select(Submission)
            .join(QuestionnaireVersion, Submission.version_id == QuestionnaireVersion.id)
            .join(
                QuestionnaireTemplate, QuestionnaireVersion.template_id == QuestionnaireTemplate.id
            )
            .where(
                Submission.patient_id == patient_id,
                QuestionnaireTemplate.code == questionnaire,
                Submission.submitted_at > since,
            )
            .options(selectinload(Submission.version))
            .order_by(Submission.submitted_at, Submission.id)
        )
    )


def ok_data_since(
    db: Session, patient_id: uuid.UUID, version: RuleVersion, since: datetime
) -> bool:
    """Érkezett-e a lezárás óta „rendben lévő adat" a szabály célpontjára, az
    adott (aktuális) szabályverzió szerint (A6 D5; a modul leírása szerint)."""
    if version.rule_type in (RuleType.THRESHOLD, RuleType.WINDOW):
        # Az időablakos szabály határai ugyanott vannak (WindowParams ⊂ ThresholdParams).
        params = ThresholdParams.model_validate(version.params)
        return any(
            not threshold_violations(params, m)
            for m in _measurements_since(db, patient_id, params.measurement_type, since)
        )
    if version.rule_type is RuleType.QUESTIONNAIRE:
        q_params = QuestionnaireParams.model_validate(version.params)
        submissions = _submissions_since(db, patient_id, q_params.questionnaire, since)
        if q_params.bands is not None:
            return any(
                band_for(s.version, s.total_score) not in q_params.bands for s in submissions
            )
        # Trend: a worsening_trend mindig a kérdőív utolsó K kitöltését nézi, így
        # csak a legújabb kitöltésre értelmes; ha az trendet indítana, úgyis
        # nyitott riasztás van a szabályon.
        assert q_params.trend_count is not None
        return bool(submissions) and not worsening_trend(db, submissions[-1], q_params.trend_count)
    m_params = MissingDataParams.model_validate(version.params)
    target = missing_target_id(db, m_params)
    if target is None:
        return False
    fulfilled = db.scalar(
        select(AssignmentOccurrence.id)
        .join(Assignment, AssignmentOccurrence.assignment_id == Assignment.id)
        .where(
            Assignment.patient_id == patient_id,
            missing_target_column(m_params) == target,
            AssignmentOccurrence.status.in_(_DONE),
            AssignmentOccurrence.fulfilled_at > since,
        )
        .limit(1)
    )
    return fulfilled is not None


def handled_reasons(
    db: Session, patient_id: uuid.UUID, open_rule_ids: set[uuid.UUID]
) -> list[StatusReason]:
    """A Kezelve okai: szabályonként a legutóbb lezárt riasztás, ha a lezárás
    óta nem jött rendben lévő adat, és a szabálynak nincs nyitott riasztása.
    A legutóbbi lezárás elöl."""
    reasons = []
    for alert, closed in latest_closed_alerts(db, patient_id):
        if alert.rule_id in open_rule_ids:
            continue
        version = current_version(db, alert.rule_id)
        if ok_data_since(db, patient_id, version, closed.created_at):
            continue
        reasons.append(
            StatusReason(
                PatientStatus.HANDLED,
                "closed_awaiting_data",
                alert=alert,
                at=closed.created_at,
                actor_id=closed.actor_id,
            )
        )
    reasons.sort(key=lambda r: r.at, reverse=True)
    return reasons


def data_age(db: Session, patient_id: uuid.UUID, last: datetime, now: datetime) -> timedelta:
    """A legutóbbi adat kora a frissességi szabályhoz: now - last, a letiltott
    időszakok [last, now]-ba eső része nélkül (a nyitott időszak mostanáig tart).
    Így letiltva az adat nem öregszik, visszaengedélyezés után pedig ott folytatódik,
    ahol a letiltáskor tartott (M3, A1). Sosem letiltott betegnél now - last."""
    return now - last - disabled_overlap(disabled_periods(db, patient_id), last, now)


def compute_status(
    db: Session, patient_id: uuid.UUID, now: datetime | None = None
) -> PatientStatusResult:
    now = now or datetime.now(UTC)
    reasons: list[StatusReason] = []

    open_alerts = list_patient_alerts(db, patient_id, open_only=True)
    for alert in open_alerts:
        status = (
            PatientStatus.SEVERE if alert.severity is Severity.SEVERE else PatientStatus.ATTENTION
        )
        reasons.append(StatusReason(status, "open_alert", alert=alert, at=alert.created_at))

    stored = latest_closed_occurrences(db, patient_id, now)
    # Előírásonként a legutóbbi lezárt alkalom: a tárolt, vagy ha a későbbi
    # lejárt határidejű időszaknak még nincs sora, az (lásd lapsed_without_row;
    # ilyenkor az okban nincs alkalom). Határidő szerint.
    rowless = lapsed_without_row(db, patient_id, now, stored)
    closed: list[tuple[datetime, AssignmentOccurrence | None]] = [
        (o.due_at, o) for o in stored if o.assignment_id not in rowless
    ]
    closed += [(due_at, None) for due_at in rowless.values()]
    closed.sort(key=lambda c: c[0])
    for due_at, occurrence in closed:
        # Elmulasztott, vagy lejárt határidejű és még nem teljesített (pótolható).
        if occurrence is None or occurrence.status in (
            OccurrenceStatus.MISSED,
            OccurrenceStatus.DUE,
        ):
            reasons.append(
                StatusReason(
                    PatientStatus.NO_DATA,
                    "missed_occurrence",
                    at=due_at,
                    occurrence=occurrence,
                )
            )

    last = last_data_at(db, patient_id)
    if last is None:
        reasons.append(StatusReason(PatientStatus.NO_DATA, "no_data_yet"))
    elif not closed and data_age(db, patient_id, last, now) > timedelta(
        days=settings.data_freshness_days
    ):
        # A 7 napos szabály csak lezárt alkalom nélkül él (lásd a modul leírását).
        reasons.append(StatusReason(PatientStatus.NO_DATA, "stale_data", at=last))

    reasons.extend(handled_reasons(db, patient_id, {a.rule_id for a in open_alerts}))

    if not reasons:
        reasons.append(StatusReason(PatientStatus.OK, "fresh_data", at=last))

    reasons.sort(key=lambda r: PRIORITY.index(r.status))  # stabil: a sorrend azonos szinten marad
    return PatientStatusResult(reasons[0].status, reasons, last)


def doctor_patient_list(
    db: Session,
    doctor_id: uuid.UUID,
    now: datetime | None = None,
    patients: list[PatientProfile] | None = None,
) -> list[tuple[PatientProfile, PatientStatusResult]]:
    """Az orvos éppen hozzá rendelt betegei státusszal, priorizálva (F9):
    elöl a Súlyos, a végén a Rendben; azonos státuszon belül név szerint.
    A patients a hívó által már lekérdezett betegkör (assigned_patients_query
    ugyanerre az időpontra), hogy egy kérésen belül egyszer fusson (review k3)."""
    now = now or datetime.now(UTC)
    if patients is None:
        patients = list(db.scalars(assigned_patients_query(doctor_id, now)).all())
    rows = [(p, compute_status(db, p.id, now)) for p in patients]
    rows.sort(key=lambda row: (PRIORITY.index(row[1].status), row[0].name))
    return rows
