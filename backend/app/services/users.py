from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import (
    DUMMY_HASH,
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
    hash_password,
    verify_password,
)
from app.models import DoctorProfile, PatientProfile, User, UserRole


def normalize_email(email: str) -> str:
    """Kiss.Anna@… és kiss.anna@… ugyanaz a fiók."""
    return email.strip().lower()


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == normalize_email(email)))


def create_user(
    db: Session,
    *,
    email: str,
    password: str,
    role: UserRole,
    name: str | None = None,
    birth_date: date | None = None,
) -> User:
    """Felhasználó létrehozása a szerepkörhöz tartozó profillal együtt.
    Csak flush-t végez; a commitról a hívó dönt."""
    if not PASSWORD_MIN_LENGTH <= len(password) <= PASSWORD_MAX_LENGTH:
        raise ValueError(
            f"A jelszó hossza {PASSWORD_MIN_LENGTH}–{PASSWORD_MAX_LENGTH} karakter lehet."
        )
    user = User(email=normalize_email(email), password_hash=hash_password(password), role=role)
    if role is UserRole.PATIENT:
        if name is None or birth_date is None:
            raise ValueError("A beteghez név és születési dátum kell.")
        user.patient_profile = PatientProfile(name=name, birth_date=birth_date)
    elif role is UserRole.DOCTOR:
        if name is None:
            raise ValueError("Az orvoshoz név kell.")
        user.doctor_profile = DoctorProfile(name=name)
    db.add(user)
    db.flush()
    return user


def record_login(db: Session, user: User) -> None:
    """A sikeres belépés idejének rögzítése (commit is)."""
    user.last_login_at = datetime.now(UTC)
    db.commit()


def authenticate(db: Session, email: str, password: str) -> User | None:
    """A felhasználó, ha az e-mail és a jelszó helyes és a fiók aktív; különben None.

    Ismeretlen e-mailnél is lefut egy jelszó-ellenőrzés (DUMMY_HASH), így a
    sikertelen belépés ideje nem árulja el, létezik-e a fiók. A hívó minden
    sikertelen esetben ugyanazt a hibaüzenetet adja.
    """
    user = get_user_by_email(db, email)
    if user is None:
        verify_password(password, DUMMY_HASH)
        return None
    if not verify_password(password, user.password_hash):
        return None
    if not user.is_active:
        return None
    return user
