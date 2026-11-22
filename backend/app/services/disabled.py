"""A letiltott időszak és az elmaradt adat (M3, A1; a hallgató döntése, 2026-11-16).

A letiltott beteg az orvos listáján marad, és amíg le van tiltva, az alkalmai
nem számítanak elmulasztottnak; a letiltás ideje utólag sem számít. Minden más
(előírások, szabályok, mérések, riasztások, a letiltás előtti és utáni alkalmak)
változatlan.

A szabály (egy helyen, ezt használja a háttérfolyamat, a státusz és a
teendőlista):

- letiltott időszak: [disabled_at, enabled_at) a user_disabled_periods táblából;
  üres enabled_at = most is tart (UserDisabledPeriod);
- egy alkalom (vagy a még sor nélküli időszaka) akkor „kimentett", ha a
  HATÁRIDEJE (due_at) egy letiltott időszakba esik: disabled_at <= due_at <
  enabled_at. A határ: a letiltás pillanatára eső határidő már kimentett, a
  visszaengedélyezés pillanatára eső már számít;
- a kimentett alkalom nem lehet elmulasztott: a háttérfolyamat nem nyitja meg,
  a már nyitott esedékes sorát pedig a pótlási ablak végén elmulasztottra zárás
  helyett törli (mint az előírás visszavonásakor, plans.py); a státusz nem ad
  belőle Adathiányt, a teendőlista nem mutatja (késésben, pótlás sincs);
- ami nem kimentett, az pontosan úgy számít, mint eddig. Ha az időszak a
  letiltás alatt kezdődött, de a határideje a visszaengedélyezés utáni, akkor
  számít (a számolás a visszaengedélyezés utáni első határidőtől indul). A
  letiltás előtti teljesített és elmulasztott alkalmak megmaradnak és
  számítanak; az elmaradt adat sorozata a letiltás két oldalán folytatódik,
  mintha a kimentett időszak ott sem lenne;
- a teljesített alkalom mindig számít (adat, nem hiány), akkor is, ha a
  határideje kimentett;
- a letiltás előtti határidejű, nem teljesített alkalom a szokásos időben (a
  pótlási ablak végén) elmulasztottra zárul, letiltva is; elmaradt adat riasztás
  (és e-mail) viszont nem keletkezik belőle, sem letiltva, sem utólag a
  visszaengedélyezéskor: a lezárás nem értékel, ha a beteg valamelyik
  letiltott időszaka átfedi a [pótlási idő vége, a lezárás ideje] szakaszt
  (occurrences.py). Egy
  visszaengedélyezés utáni új elmulasztás sorozatában ezek is számítanak;
- a frissességi szabály (7 nap, status.py) az adat korából a letiltott időszakot
  levonja: letiltva az adat nem öregszik (a hallgató döntése, 2026-11-21).

Soha le nem tiltott betegnél nincs sora a táblának, így minden lekérdezés
eredménye ugyanaz, mint e szabály nélkül. Letiltott (is_active = false), de
időszak nélküli felhasználó a szolgáltatáson át nem jöhet létre (a letiltás és
az időszak egy tranzakcióban születik; a migráció a régieknek nyitott időszakot
ad); ha mégis előfordulna, a számolásban nem letiltottként szerepel.
"""

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import ColumnElement, and_, exists, or_, select
from sqlalchemy.orm import Session, aliased

from app.models import PatientProfile, User
from app.models.user import UserDisabledPeriod


@dataclass(frozen=True)
class DisabledPeriod:
    """[start, end); end = None: most is tart."""

    start: datetime
    end: datetime | None

    def contains(self, at: datetime) -> bool:
        return self.start <= at and (self.end is None or at < self.end)


def is_excused(periods: Sequence[DisabledPeriod], due_at: datetime) -> bool:
    """A határidő egy letiltott időszakba esik-e (lásd a modul leírását)."""
    return any(p.contains(due_at) for p in periods)


def overlaps(periods: Sequence[DisabledPeriod], start: datetime, end: datetime) -> bool:
    """Átfedi-e valamelyik letiltott időszak a [start, end] szakaszt (a nyitott
    időszak mostanáig tart, így a most letiltott beteg mindig átfed)."""
    return any(p.start <= end and (p.end is None or p.end > start) for p in periods)


def disabled_overlap(
    periods: Sequence[DisabledPeriod], start: datetime, end: datetime
) -> timedelta:
    """A letiltott időszakok [start, end]-be eső teljes hossza (a nyitott időszak
    end-ig tart). Az időszakok nem fedik egymást (egyszerre legfeljebb egy nyitott,
    a lezártak egymás után következnek)."""
    total = timedelta(0)
    for period in periods:
        lo = max(period.start, start)
        hi = min(period.end or end, end)
        if hi > lo:
            total += hi - lo
    return total


def disabled_periods_by_patient(
    db: Session, patient_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, list[DisabledPeriod]]:
    """A betegek (PatientProfile.id) letiltott időszakai egy lekérdezéssel; akinek
    nincs, az kimarad a szótárból."""
    ids = list(set(patient_ids))
    result: dict[uuid.UUID, list[DisabledPeriod]] = {}
    if not ids:
        return result
    rows = db.execute(
        select(PatientProfile.id, UserDisabledPeriod.disabled_at, UserDisabledPeriod.enabled_at)
        .join(UserDisabledPeriod, UserDisabledPeriod.user_id == PatientProfile.user_id)
        .where(PatientProfile.id.in_(ids))
        .order_by(UserDisabledPeriod.disabled_at)
    )
    for patient_id, start, end in rows:
        result.setdefault(patient_id, []).append(DisabledPeriod(start, end))
    return result


def disabled_periods(db: Session, patient_id: uuid.UUID) -> list[DisabledPeriod]:
    """Egy beteg letiltott időszakai (üres lista, ha sosem volt letiltva)."""
    return disabled_periods_by_patient(db, [patient_id]).get(patient_id, [])


def inactive_patients(db: Session, patient_ids: Iterable[uuid.UUID]) -> set[uuid.UUID]:
    """A most letiltott betegek (User.is_active = false) a megadottak közül."""
    ids = list(set(patient_ids))
    if not ids:
        return set()
    return set(
        db.scalars(
            select(PatientProfile.id)
            .join(User, User.id == PatientProfile.user_id)
            .where(PatientProfile.id.in_(ids), User.is_active.is_(False))
        )
    )


def excused_deadline(
    patient_id: ColumnElement[uuid.UUID], due_at: ColumnElement[datetime]
) -> ColumnElement[bool]:
    """Ugyanez SQL-ben: a betegnek (patient_id oszlop) van-e olyan letiltott
    időszaka, amelybe a határidő (due_at oszlop) esik. Önálló, korrelált EXISTS
    saját profil-álnévvel, így a hívó lekérdezésében semmit nem kell előre
    csatolni (nem keletkezhet Descartes-szorzat)."""
    profile = aliased(PatientProfile)
    return (
        exists()
        .where(
            profile.id == patient_id,
            UserDisabledPeriod.user_id == profile.user_id,
            UserDisabledPeriod.disabled_at <= due_at,
            or_(UserDisabledPeriod.enabled_at.is_(None), due_at < UserDisabledPeriod.enabled_at),
        )
        .correlate_except(profile, UserDisabledPeriod)
    )


def excused_due(
    status_is_due: ColumnElement[bool],
    patient_id: ColumnElement[uuid.UUID],
    due_at: ColumnElement[datetime],
) -> ColumnElement[bool]:
    """Kimentett, még esedékes alkalom (ez nem lehet „lezárt" és elmulasztott)."""
    return and_(status_is_due, excused_deadline(patient_id, due_at))
