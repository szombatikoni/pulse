"""Követési terv: az orvos előírásai a betegnek (F14; M3, A2 3. lépés).

- Új előírás: mérés vagy kérdőív, gyakorisággal, határidő-időponttal, opcionális
  ajánlott időponttal, kezdettel és opcionális véggel. A kezdet nem lehet a
  múltban: visszamenőleges előírásnál a worker azonnal elmulasztott alkalmakat
  nyitna olyan időszakokra, amelyekről a beteg nem is tudhatott.
- Módosítás = lezárás + új előírás (a hallgató döntése, 2026-10-30; a2_terv
  6/1. pont): nincs helyben szerkesztés, így minden alkalom arra az előírásra
  hivatkozik, ami a keletkezésekor érvényes volt. Az új kezdete nem
  választható: ma, vagy a még el nem kezdett régi kezdete (lásd replace()).
- Visszavonás: revoked_at, a nyitott alkalmak kezelését lásd: revoke().
  Visszavonásnál és módosításnál az orvos rövid indoklást adhat (revoke_note,
  nem kötelező; a hallgató döntése, 2026-11-01), amit a beteg is lát.
- Új előírásnál az aktuális időszak alkalmát a már meglévő adat azonnal
  teljesíti (occurrences.fulfil_from_existing).
- A beteg a teendői közt rövid jelzést kap a közelmúltbeli visszavonásról és
  módosításról (plan_notices); ez is az előírás-adatokból számolódik.

A véglegesítést (commit) a hívó végzi.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models import (
    Assignment,
    AssignmentOccurrence,
    AssignmentTarget,
    Frequency,
    MeasurementType,
    OccurrenceStatus,
    QuestionnaireTemplate,
    User,
)
from app.services.measurements import get_type_by_code
from app.services.occurrences import fulfil_from_existing

# A beteg ennyi napig látja a visszavonás / módosítás jelzését.
NOTICE_DAYS = 7


class PlanError(ValueError):
    """Érvénytelen előírás vagy művelet; a `code` alapján a felület a saját
    nyelvén írja ki. A `conflict` az előírás állapotával ütköző műveletet jelzi
    (HTTP 409), a többi érvénytelen adat (HTTP 422)."""

    def __init__(self, code: str, conflict: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.conflict = conflict


@dataclass(frozen=True)
class PlanParams:
    """Az előírás paraméterei a céltól függetlenül (új előírásnál és módosításnál)."""

    frequency: Frequency
    interval_days: int | None
    due_time: time
    suggested_time: time | None
    start_date: date | None  # üresen: új előírásnál ma, módosításnál lásd replace()
    end_date: date | None


@dataclass
class PlanEntry:
    """Egy előírás a listában, a felülethez kiegészítve: a cél neve, ki írta
    elő, az állapota és (módosításnál) melyik előírás lépett a helyébe."""

    assignment: Assignment
    code: str
    name: str
    assigned_by: str
    status: str  # active | upcoming | ended | revoked
    replaced_by: uuid.UUID | None


def local_today(now: datetime | None = None) -> date:
    return (now or datetime.now(UTC)).astimezone(settings.tz).date()


def _status(assignment: Assignment, today: date) -> str:
    if assignment.revoked_at is not None:
        return "revoked"
    if assignment.end_date is not None and assignment.end_date < today:
        return "ended"
    if assignment.start_date > today:
        return "upcoming"
    return "active"


def _end_meets(assignment: Assignment) -> date | None:
    """Az a nap, amelyen az előírás után következő előírás kezdete „összeér" vele:
    visszavontnál a visszavonás napja (de nem a kezdete előtt, mert a még el sem
    kezdett előírás helyére a saját kezdetétől lép az új), lejártnál a vége
    utáni nap."""
    if assignment.revoked_at is not None:
        revoked_day = assignment.revoked_at.astimezone(settings.tz).date()
        return max(revoked_day, assignment.start_date)
    if assignment.end_date is not None:
        return assignment.end_date + timedelta(days=1)
    return None


def _same_target(a: Assignment, b: Assignment) -> bool:
    return (
        a.target_kind is b.target_kind
        and a.measurement_type_id == b.measurement_type_id
        and a.questionnaire_template_id == b.questionnaire_template_id
    )


def _successor(assignment: Assignment, others: list[Assignment]) -> Assignment | None:
    """A váltás az adatból kiolvasva (a2_terv 6/1. pont): ugyanarra a célra az az
    előírás, amelynek kezdete pontosan ott van, ahol ez véget ért. Ha egy napon
    többször módosult, a láncban a következő az, amelyiket ennél később vontak
    vissza (vagy még érvényes)."""
    meets = _end_meets(assignment)
    if meets is None:
        return None
    far = datetime.max.replace(tzinfo=UTC)
    candidates = [
        other
        for other in others
        if other.id != assignment.id
        and _same_target(other, assignment)
        and other.start_date == meets
        and (
            assignment.revoked_at is None
            or other.revoked_at is None
            or other.revoked_at > assignment.revoked_at
        )
    ]
    return min(candidates, key=lambda a: a.revoked_at or far, default=None)


def list_plan(db: Session, patient_id: uuid.UUID, now: datetime | None = None) -> list[PlanEntry]:
    """A beteg összes előírása (érvényesek és korábbiak), kezdet szerint."""
    today = local_today(now)
    assignments = list(
        db.scalars(
            select(Assignment)
            .where(Assignment.patient_id == patient_id)
            .options(selectinload(Assignment.template))
            .order_by(
                Assignment.start_date, Assignment.revoked_at.asc().nulls_last(), Assignment.id
            )
        )
    )
    types = {t.id: t for t in db.scalars(select(MeasurementType))}
    authors = {
        u.id: u
        for u in db.scalars(
            select(User)
            .where(User.id.in_({a.assigned_by for a in assignments}))
            .options(selectinload(User.doctor_profile))
        )
    }
    entries = []
    for a in assignments:
        if a.target_kind is AssignmentTarget.MEASUREMENT:
            target = types[a.measurement_type_id]
        else:
            target = a.template
        author = authors[a.assigned_by]
        successor = _successor(a, assignments)
        entries.append(
            PlanEntry(
                assignment=a,
                code=target.code,
                name=target.name,
                assigned_by=author.doctor_profile.name if author.doctor_profile else author.email,
                status=_status(a, today),
                replaced_by=successor.id if successor else None,
            )
        )
    return entries


type Target = MeasurementType | QuestionnaireTemplate


def _target(db: Session, kind: AssignmentTarget, code: str) -> Target:
    if kind is AssignmentTarget.MEASUREMENT:
        mtype = get_type_by_code(db, code)
        if mtype is None:
            raise PlanError("unknown_target")
        return mtype
    template = db.scalar(select(QuestionnaireTemplate).where(QuestionnaireTemplate.code == code))
    if template is None or not template.is_active:
        raise PlanError("unknown_target")
    return template


def _check_dates(start: date, end: date | None, today: date) -> None:
    if start < today:
        raise PlanError("start_in_past")
    if end is not None and end < start:
        raise PlanError("end_before_start")


def _check_overlap(
    db: Session,
    patient_id: uuid.UUID,
    probe: Assignment,
    start: date,
    end: date | None,
    ignore: uuid.UUID | None = None,
) -> None:
    """Ugyanarra a célra egyszerre egy érvényes előírás lehet: a változtatás
    útja a módosítás, nem egy második, párhuzamos előírás."""
    query = select(Assignment.id).where(
        Assignment.patient_id == patient_id,
        Assignment.target_kind == probe.target_kind,
        Assignment.revoked_at.is_(None),
        or_(Assignment.end_date.is_(None), Assignment.end_date >= start),
    )
    if probe.measurement_type_id is not None:
        query = query.where(Assignment.measurement_type_id == probe.measurement_type_id)
    else:
        query = query.where(Assignment.questionnaire_template_id == probe.questionnaire_template_id)
    if end is not None:
        query = query.where(Assignment.start_date <= end)
    if ignore is not None:
        query = query.where(Assignment.id != ignore)
    if db.scalar(query.limit(1)) is not None:
        raise PlanError("overlap", conflict=True)


def _build(
    patient_id: uuid.UUID,
    assigned_by: uuid.UUID,
    kind: AssignmentTarget,
    target: Target,
    params: PlanParams,
    start: date,
) -> Assignment:
    return Assignment(
        patient_id=patient_id,
        assigned_by=assigned_by,
        target_kind=kind,
        measurement_type_id=target.id if kind is AssignmentTarget.MEASUREMENT else None,
        questionnaire_template_id=target.id if kind is AssignmentTarget.QUESTIONNAIRE else None,
        frequency=params.frequency,
        # Napi és heti előírásnál az időköz nem értelmezett, ezért üres.
        interval_days=params.interval_days if params.frequency is Frequency.EVERY_N_DAYS else None,
        due_time=params.due_time,
        suggested_time=params.suggested_time,
        start_date=start,
        end_date=params.end_date,
    )


def create(
    db: Session,
    *,
    patient_id: uuid.UUID,
    assigned_by: uuid.UUID,
    kind: AssignmentTarget,
    code: str,
    params: PlanParams,
    now: datetime | None = None,
) -> Assignment:
    """Új előírás. Minden ellenőrzés a beszúrás előtt fut."""
    today = local_today(now)
    target = _target(db, kind, code)
    start = params.start_date or today
    _check_dates(start, params.end_date, today)
    assignment = _build(patient_id, assigned_by, kind, target, params, start)
    _check_overlap(db, patient_id, assignment, start, params.end_date)
    db.add(assignment)
    db.flush()
    fulfil_from_existing(db, assignment, now or datetime.now(UTC))
    return assignment


def get_for_patient(db: Session, patient_id: uuid.UUID, assignment_id: uuid.UUID) -> Assignment:
    """A beteg előírása; más beteg előírására (az útvonal betegétől eltérőre)
    LookupError, így a hozzáférés-ellenőrzés nem kerülhető meg az azonosítóval."""
    assignment = db.get(Assignment, assignment_id)
    if assignment is None or assignment.patient_id != patient_id:
        raise LookupError(str(assignment_id))
    return assignment


def _ensure_changeable(assignment: Assignment, today: date) -> None:
    status = _status(assignment, today)
    if status == "revoked":
        raise PlanError("already_revoked", conflict=True)
    if status == "ended":
        raise PlanError("already_ended", conflict=True)


def _clean_note(note: str | None) -> str | None:
    """Az indoklás szóközök nélkül; üresen nincs indoklás."""
    note = (note or "").strip()
    return note or None


def _close(db: Session, assignment: Assignment, now: datetime, note: str | None = None) -> int:
    """Lezárás: revoked_at, és a még nyitott (esedékes) alkalmak törlése.

    A hallgató döntése, 2026-11-01: a visszavonással a kötelezettség megszűnik,
    ezért a nyitott, nem teljesített alkalom törlődik; így nem válhat belőle
    elmulasztott alkalom, és nem fut be az elmaradt adat szabályhoz. A
    teljesített, késve teljesített és elmulasztott alkalmak változatlanul
    megmaradnak (ezek a történet). Esedékes alkalomra kitöltés nem
    hivatkozik (a kitöltés mindig teljesíti az alkalmát), így a törlés nem
    hagy lógó hivatkozást. Az indoklás (ha van) a lezárt előíráshoz kerül.
    Visszaadja a törölt alkalmak számát."""
    assignment.revoked_at = now
    assignment.revoke_note = _clean_note(note)
    result = db.execute(
        delete(AssignmentOccurrence).where(
            AssignmentOccurrence.assignment_id == assignment.id,
            AssignmentOccurrence.status == OccurrenceStatus.DUE,
        )
    )
    db.flush()
    return result.rowcount


def revoke(
    db: Session, assignment: Assignment, now: datetime | None = None, note: str | None = None
) -> Assignment:
    """Visszavonás opcionális indoklással (lásd _close)."""
    now = now or datetime.now(UTC)
    _ensure_changeable(assignment, local_today(now))
    _close(db, assignment, now, note)
    return assignment


def replace(
    db: Session,
    old: Assignment,
    *,
    assigned_by: uuid.UUID,
    params: PlanParams,
    now: datetime | None = None,
    note: str | None = None,
) -> Assignment:
    """Módosítás egy lépésben: az új előírás ugyanarra a célra, a régi lezárva
    (visszavonás a nyitott alkalmak törlésével, _close).

    A kezdet nem választható, és nem jöhet a jövőből (review K3, a hallgató
    döntése, 2026-11-01): az érvényes (már elkezdett) előírásnál az új kezdete
    a mai nap, a még el nem kezdettnél a régi kezdete. Így a régi lezárása és
    az új kezdete mindig összeér: nincs lefedetlen köztes nap, és a váltás a
    láncból felismerhető (_end_meets). Üres start_date-nél ez az érték
    öröklődik; ettől eltérő start_date: start_fixed hiba.

    A sorrend szándékos: előbb minden ellenőrzés és az új beszúrása, csak utána
    a régi lezárása; ha az új bármin elbukik, a régihez nem nyúltunk. A hívó
    hibánál visszagörget (rollback), így a teljes művelet atomi. Az indoklás
    a régi előíráshoz kerül."""
    now = now or datetime.now(UTC)
    today = local_today(now)
    _ensure_changeable(old, today)
    target: Target | None
    if old.target_kind is AssignmentTarget.MEASUREMENT:
        target = db.get(MeasurementType, old.measurement_type_id)
    else:
        target = old.template
        # Inaktív kérdőívre új előírás nem adható (mint az új előírásnál).
        if target is None or not target.is_active:
            raise PlanError("unknown_target")
    assert target is not None
    start = max(today, old.start_date)
    if params.start_date is not None and params.start_date != start:
        raise PlanError("start_fixed")
    _check_dates(start, params.end_date, today)
    new = _build(old.patient_id, assigned_by, old.target_kind, target, params, start)
    _check_overlap(db, old.patient_id, new, start, params.end_date, ignore=old.id)
    db.add(new)
    db.flush()
    _close(db, old, now, note)
    fulfil_from_existing(db, new, now)
    return new


@dataclass
class PlanNotice:
    """Jelzés a betegnek egy előírása közelmúltbeli változásáról. Egy
    módosítási láncból (A → B → C, a replaced_by szerint) egy jelzés lesz, a
    lánc végének állapotával: ha a vége visszavont, „visszavonta", különben
    „módosult", az érvényes (utolsó) előírás paramétereivel. Az idő és az
    indoklás a lánc utolsó változásáé."""

    kind: Literal["revoked", "modified"]
    changed_at: datetime
    note: str | None
    entry: PlanEntry  # a lánc első, a jelzési időszakban lezárt előírása
    current: PlanEntry | None  # módosításnál az érvényes (új) előírás


def plan_notices(
    db: Session, patient_id: uuid.UUID, now: datetime | None = None
) -> list[PlanNotice]:
    """A beteg előírásainak az utóbbi NOTICE_DAYS napban történt visszavonásai
    és módosításai, a legújabb elöl."""
    now = now or datetime.now(UTC)
    since = now - timedelta(days=NOTICE_DAYS)
    entries = list_plan(db, patient_id, now)
    by_id = {e.assignment.id: e for e in entries}
    recent = [
        e
        for e in entries
        if e.assignment.revoked_at is not None and e.assignment.revoked_at >= since
    ]
    # A lánc közbülső tagja (egy friss módosítás utódja) nem kap külön jelzést.
    successors = {e.replaced_by for e in recent if e.replaced_by}
    notices = []
    for head in recent:
        if head.assignment.id in successors:
            continue
        last_closed, link = head, head
        # Kör nem lehet, a bejárás véget ér: a _successor szerint az utód
        # kezdete sosem korábbi (visszavont tagnál a visszavonás napja, de nem a
        # tag kezdete előtt; lejártnál a vége utáni nap), azonos kezdetnél pedig
        # a lánc mentén a lezárás ideje (revoked_at) szigorúan nő. A bejárt
        # halmaz csak olcsó biztosíték.
        seen = {link.assignment.id}
        while link.replaced_by is not None and link.replaced_by not in seen:
            link = by_id[link.replaced_by]
            seen.add(link.assignment.id)
            if link.assignment.revoked_at is not None:
                last_closed = link
        revoked = link.assignment.revoked_at is not None
        # A lánc feje visszavont (recent), így a legutóbb lezárt tag is az.
        assert last_closed.assignment.revoked_at is not None
        notices.append(
            PlanNotice(
                kind="revoked" if revoked else "modified",
                changed_at=last_closed.assignment.revoked_at,
                note=last_closed.assignment.revoke_note,
                entry=head,
                current=None if revoked else link,
            )
        )
    notices.sort(key=lambda n: n.changed_at, reverse=True)
    return notices
