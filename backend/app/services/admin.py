"""Az admin-felület műveletei (M3, A1; F20): felhasználók, orvos–beteg
összerendelések és a méréstípusok rögzíthető tartománya.

Az admin betegadatot nem kap (F2): a felhasználólistában csak azonosító adat
van (név, e-mail, szerepkör, állapot, létrehozás és utolsó belépés ideje), a
születési dátum csak a létrehozáskor adható meg, a listában nem jelenik meg.

A hallgató döntései (2026-11-16):
- a kezdeti jelszót az admin adja meg, a meglévő hosszszabállyal (10–255);
- létrehozás után csak a név és az aktív állapot változik, az e-mail és a
  szerepkör nem;
- a letiltott beteg az orvos listáján marad; az az alkalma, amelynek határideje
  a letiltott időszakba esik, nem számít elmulasztottnak, utólag sem
  (UserDisabledPeriod, services/disabled.py);
- az összerendelés azonnal kezdődik és azonnal szűnik meg (valid_from, valid_to
  = most), jövőbeli dátum nincs;
- a méréstípusoknál csak a komponensek rögzíthető tartománya (min_value,
  max_value) szerkeszthető; ez a jövőbeli rögzítés elírásszűrése, a meglévő
  mérések, szabályok és riasztások jelentését nem érinti.

A hibák kóddal jönnek (AdminError.code), a felület a saját nyelvén írja ki
őket, mint az előírásoknál (plans.PlanError). Minden ellenőrzés a módosítás
előtt fut; a véglegesítést (commit) a hívó végzi.
"""

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.security import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH
from app.models import (
    DoctorPatient,
    DoctorProfile,
    MeasurementComponent,
    MeasurementType,
    PatientProfile,
    User,
    UserRole,
)
from app.models.user import UserDisabledPeriod
from app.services.measurements import get_type_by_code
from app.services.users import create_user, get_user_by_email, normalize_email

# Egyszerű formai ellenőrzés új függőség nélkül: van „@", előtte és utána
# szóköz nélküli szöveg, a domainben pont (a terv 3. része szerint).
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
EMAIL_MAX_LENGTH = 255
NAME_MAX_LENGTH = 200
EARLIEST_BIRTH_DATE = date(1900, 1, 1)
# A rögzíthető tartomány józan határai: a négy méréstípus mind nemnegatív, és a
# legnagyobb meglévő felső határ 350 (testsúly, kg).
RANGE_FLOOR = 0.0
RANGE_CEILING = 1000.0

ROLE_ORDER = [UserRole.ADMIN, UserRole.DOCTOR, UserRole.PATIENT]


class AdminError(ValueError):
    """Érvénytelen művelet; a `code` alapján a felület a saját nyelvén írja ki.
    conflict=True: ütközés a meglévő állapottal (409), különben érvénytelen
    adat (422)."""

    def __init__(self, code: str, conflict: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.conflict = conflict


@dataclass
class UserRow:
    """Egy felhasználó az admin-listában. A profile_id a beteg- vagy
    orvosprofil azonosítója (az összerendeléshez); adminnál üres."""

    user: User
    name: str | None
    profile_id: uuid.UUID | None


def _row(user: User) -> UserRow:
    profile = user.patient_profile or user.doctor_profile
    return UserRow(
        user=user,
        name=profile.name if profile else None,
        profile_id=profile.id if profile else None,
    )


def list_users(db: Session) -> list[UserRow]:
    """Minden felhasználó: előbb az adminok, aztán az orvosok, végül a betegek,
    azon belül név (adminnál e-mail) szerint."""
    users = db.scalars(
        select(User).options(selectinload(User.patient_profile), selectinload(User.doctor_profile))
    ).all()
    rows = [_row(u) for u in users]
    rows.sort(
        key=lambda r: (
            ROLE_ORDER.index(r.user.role),
            (r.name or r.user.email).casefold(),
            r.user.email,
        )
    )
    return rows


def _clean_name(name: str | None) -> str:
    cleaned = (name or "").strip()
    if not cleaned:
        raise AdminError("name_required")
    if len(cleaned) > NAME_MAX_LENGTH:
        raise AdminError("name_too_long")
    return cleaned


def create_account(
    db: Session,
    *,
    email: str,
    password: str,
    role: UserRole,
    name: str | None = None,
    birth_date: date | None = None,
    today: date | None = None,
) -> UserRow:
    """Új felhasználó a szerepkör profiljával (users.create_user). Adminnál a
    név és a születési dátum nem tárolódik (az adminnak nincs profilja)."""
    # A mai nap a rendszer időzónájában (Europe/Budapest), mint máshol is.
    today = today or datetime.now(settings.tz).date()
    email = normalize_email(email)
    if len(email) > EMAIL_MAX_LENGTH or not EMAIL_PATTERN.match(email):
        raise AdminError("email_invalid")
    if not PASSWORD_MIN_LENGTH <= len(password) <= PASSWORD_MAX_LENGTH:
        raise AdminError("password_length")
    if role is UserRole.ADMIN:
        name = birth_date = None
    else:
        name = _clean_name(name)
    if role is UserRole.PATIENT:
        if birth_date is None:
            raise AdminError("birth_date_required")
        if not EARLIEST_BIRTH_DATE <= birth_date <= today:
            raise AdminError("birth_date_invalid")
    else:
        birth_date = None
    if get_user_by_email(db, email) is not None:
        raise AdminError("email_taken", conflict=True)
    try:
        # Két egyidejű létrehozásnál az egyedi index dönt; a mentési pont miatt
        # a kérés sessionje az ütközés után is használható marad.
        with db.begin_nested():
            user = create_user(
                db, email=email, password=password, role=role, name=name, birth_date=birth_date
            )
    except IntegrityError as error:
        raise AdminError("email_taken", conflict=True) from error
    return _row(user)


def rename_user(db: Session, user: User, name: str | None) -> UserRow:
    """A név javítása (beteg és orvos); az adminnak nincs neve."""
    profile = user.patient_profile or user.doctor_profile
    if profile is None:
        raise AdminError("no_name")
    profile.name = _clean_name(name)
    db.flush()
    return _row(user)


def disable_user(db: Session, actor: User, user: User, now: datetime | None = None) -> UserRow:
    """Letiltás: a fiók nem léphet be, és a már kiadott tokenje is azonnal
    érvénytelen (deps.get_current_user minden kérésnél az adatbázisból
    olvas). Az összerendeléseket nem zárja le, így a visszaengedélyezés
    újra-összerendelés nélkül állítja vissza a hozzáférést. Ugyanebben a
    tranzakcióban nyílik a letiltott időszak (UserDisabledPeriod), amelyből a
    beteg elmaradt adatának számolása dolgozik (services/disabled.py).

    Saját fiókot nem lehet letiltani (self_disable), és az utolsó aktív admint
    sem (last_admin). Az aktív adminok sorát zárolva számol: két admin
    egyidejű kölcsönös letiltásánál a második már a friss állapotot látja, így
    nem maradhat admin nélkül a rendszer. Már letiltott fióknál nem ír semmit
    (idempotens)."""
    now = now or datetime.now(UTC)
    if user.id == actor.id:
        raise AdminError("self_disable", conflict=True)
    if user.role is UserRole.ADMIN:
        active_admins = db.scalars(
            select(User.id)
            .where(User.role == UserRole.ADMIN, User.is_active.is_(True))
            # Mindig azonos sorrendben zárol: két admin egymást letiltva sem
            # kerülhet holtpontba (deadlock).
            .order_by(User.id)
            .with_for_update()
        ).all()
        if not [admin_id for admin_id in active_admins if admin_id != user.id]:
            raise AdminError("last_admin", conflict=True)
    # A felhasználó sora zárolva: két egyidejű letiltás vagy visszaengedélyezés
    # egymás után fut, és a második a friss állapotot látja.
    db.refresh(user, with_for_update=True)
    if user.is_active:
        user.is_active = False
        db.add(UserDisabledPeriod(user_id=user.id, disabled_at=now))
        db.flush()
    return _row(user)


def enable_user(db: Session, user: User, now: datetime | None = None) -> UserRow:
    """Visszaengedélyezés: a fiók újra beléphet, és a nyitott letiltott időszak
    most lezárul. Betegnél az az alkalom, amelynek határideje a letiltott
    időszakba esett, utólag sem számít elmulasztottnak; a letiltás előtti
    alkalmak változatlanul számítanak (services/disabled.py). Már aktív fióknál
    nem ír semmit (idempotens)."""
    now = now or datetime.now(UTC)
    db.refresh(user, with_for_update=True)
    if not user.is_active:
        user.is_active = True
        period = db.scalar(
            select(UserDisabledPeriod).where(
                UserDisabledPeriod.user_id == user.id, UserDisabledPeriod.enabled_at.is_(None)
            )
        )
        if period is not None:
            # Az időszak vége mindig a kezdete után van (ellenőrző megszorítás).
            period.enabled_at = max(now, period.disabled_at + timedelta(microseconds=1))
        db.flush()
    return _row(user)


@dataclass
class AssignmentRow:
    link: DoctorPatient
    doctor_name: str
    patient_name: str


def list_assignments(db: Session) -> list[AssignmentRow]:
    """Minden összerendelés (a lezártak is, a történethez), orvos és beteg
    neve szerint, azon belül a kezdet szerint."""
    rows = db.execute(
        select(DoctorPatient, DoctorProfile.name, PatientProfile.name)
        .join(DoctorProfile, DoctorPatient.doctor_id == DoctorProfile.id)
        .join(PatientProfile, DoctorPatient.patient_id == PatientProfile.id)
        .order_by(DoctorProfile.name, PatientProfile.name, DoctorPatient.valid_from)
    )
    return [AssignmentRow(link, doctor, patient) for link, doctor, patient in rows]


def _assignment_row(db: Session, link: DoctorPatient) -> AssignmentRow:
    doctor = db.get(DoctorProfile, link.doctor_id)
    patient = db.get(PatientProfile, link.patient_id)
    assert doctor is not None and patient is not None
    return AssignmentRow(link, doctor.name, patient.name)


def create_assignment(
    db: Session, doctor_id: uuid.UUID, patient_id: uuid.UUID, now: datetime | None = None
) -> AssignmentRow:
    """Új összerendelés azonnali kezdettel (valid_from = most): az orvos a
    következő kérésétől eléri a beteget (access.can_access_patient). A két
    azonosító profil-azonosító. Aktív orvos és aktív beteg kell; ha az orvosnak
    már érvényes összerendelése van a beteggel, 409 (already_assigned). Az
    egyidejű kéréseket az adatbázis átfedést tiltó megszorítása fogja meg."""
    now = now or datetime.now(UTC)
    doctor = db.get(DoctorProfile, doctor_id)
    if doctor is None:
        raise AdminError("not_a_doctor")
    patient = db.get(PatientProfile, patient_id)
    if patient is None:
        raise AdminError("not_a_patient")
    if not doctor.user.is_active or not patient.user.is_active:
        raise AdminError("inactive_user")
    link = DoctorPatient(doctor_id=doctor.id, patient_id=patient.id, valid_from=now)
    try:
        with db.begin_nested():
            db.add(link)
            db.flush()
    except IntegrityError as error:
        raise AdminError("already_assigned", conflict=True) from error
    return _assignment_row(db, link)


def end_assignment(
    db: Session, assignment_id: uuid.UUID, now: datetime | None = None
) -> AssignmentRow:
    """Az összerendelés megszüntetése azonnal (valid_to = most); a sor a
    történetben megmarad, az orvos hozzáférése a következő kérésétől megszűnik.
    A már lezárt sorra 409 (already_ended). A még el nem kezdődött sort (a
    felületről ilyen nem jön létre) nem zárja le, mert a vége a kezdete elé
    esne: 409 (not_started)."""
    now = now or datetime.now(UTC)
    link = db.get(DoctorPatient, assignment_id, with_for_update=True)
    if link is None:
        raise LookupError(assignment_id)
    if link.valid_to is not None and link.valid_to <= now:
        raise AdminError("already_ended", conflict=True)
    if link.valid_from >= now:
        raise AdminError("not_started", conflict=True)
    link.valid_to = now
    db.flush()
    return _assignment_row(db, link)


def update_ranges(
    db: Session, type_code: str, ranges: dict[str, tuple[float, float]]
) -> MeasurementType:
    """A méréstípus komponenseinek rögzíthető tartománya (component kód →
    (min, max)). Csak a megadott komponensek változnak; a kód, a LOINC, az
    egység és a név nem szerkeszthető. Ellenőrzés: ismert komponens, véges
    szám, RANGE_FLOOR <= min < max <= RANGE_CEILING.

    A tartomány csak a jövőbeli rögzítést (és a mérés javítását) szűri
    (measurements._checked_values); a meglévő mérések, a szabályok és a
    riasztások nem hivatkoznak rá, így a jelentésük nem változik."""
    measurement_type = get_type_by_code(db, type_code)
    if measurement_type is None:
        raise LookupError(type_code)
    components = {c.code: c for c in measurement_type.components}
    for code, (low, high) in ranges.items():
        if code not in components:
            raise AdminError("unknown_component")
        if not RANGE_FLOOR <= low < high <= RANGE_CEILING:
            raise AdminError("range_invalid")
    for code, (low, high) in ranges.items():
        component: MeasurementComponent = components[code]
        component.min_value = low
        component.max_value = high
    db.flush()
    return measurement_type
