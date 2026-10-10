"""Spec 8–9, NF1: felhasználó létrehozása, profilok, e-mail-egyediség, jelszóhash."""

from datetime import date

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH, verify_password
from app.models import DoctorProfile, PatientProfile, User, UserRole
from app.services.users import create_user
from tests.independent_fable.helpers import (
    DEFAULT_PASSWORD,
    make_admin,
    make_doctor,
    make_patient,
    unique_email,
)

# --- 9. létrehozás és profilok --------------------------------------------------


def test_create_patient_has_patient_profile_only(db: Session):
    user = create_user(
        db,
        email=unique_email(),
        password=DEFAULT_PASSWORD,
        role=UserRole.PATIENT,
        name="Beteg Béla",
        birth_date=date(1960, 2, 29),
    )
    assert user.id is not None
    assert user.role is UserRole.PATIENT
    assert user.is_active is True
    assert user.last_login_at is None
    assert user.patient_profile is not None
    assert user.patient_profile.name == "Beteg Béla"
    assert user.patient_profile.birth_date == date(1960, 2, 29)
    assert user.patient_profile.user_id == user.id
    assert user.doctor_profile is None


def test_create_doctor_has_doctor_profile_only(db: Session):
    user = create_user(
        db, email=unique_email(), password=DEFAULT_PASSWORD, role=UserRole.DOCTOR, name="Dr. X"
    )
    assert user.role is UserRole.DOCTOR
    assert user.doctor_profile is not None
    assert user.doctor_profile.name == "Dr. X"
    assert user.doctor_profile.user_id == user.id
    assert user.patient_profile is None


def test_create_admin_has_no_profile(db: Session):
    user = create_user(db, email=unique_email(), password=DEFAULT_PASSWORD, role=UserRole.ADMIN)
    assert user.role is UserRole.ADMIN
    assert user.patient_profile is None
    assert user.doctor_profile is None


def test_create_admin_ignores_name_and_birth_date_without_creating_profile(db: Session):
    user = create_user(
        db,
        email=unique_email(),
        password=DEFAULT_PASSWORD,
        role=UserRole.ADMIN,
        name="Admin Anna",
        birth_date=date(1990, 1, 1),
    )
    assert user.patient_profile is None
    assert user.doctor_profile is None
    assert (
        db.scalar(
            select(func.count())
            .select_from(PatientProfile)
            .where(PatientProfile.user_id == user.id)
        )
        == 0
    )
    assert (
        db.scalar(
            select(func.count()).select_from(DoctorProfile).where(DoctorProfile.user_id == user.id)
        )
        == 0
    )


def test_create_doctor_with_birth_date_does_not_create_patient_profile(db: Session):
    user = create_user(
        db,
        email=unique_email(),
        password=DEFAULT_PASSWORD,
        role=UserRole.DOCTOR,
        name="Dr. Y",
        birth_date=date(1980, 1, 1),
    )
    assert user.doctor_profile is not None
    assert user.patient_profile is None


def test_create_patient_without_birth_date_fails(db: Session):
    with pytest.raises(ValueError):
        create_user(
            db, email=unique_email(), password=DEFAULT_PASSWORD, role=UserRole.PATIENT, name="B"
        )


def test_create_patient_without_name_fails(db: Session):
    with pytest.raises(ValueError):
        create_user(
            db,
            email=unique_email(),
            password=DEFAULT_PASSWORD,
            role=UserRole.PATIENT,
            birth_date=date(1970, 1, 1),
        )


def test_create_doctor_without_name_fails(db: Session):
    with pytest.raises(ValueError):
        create_user(db, email=unique_email(), password=DEFAULT_PASSWORD, role=UserRole.DOCTOR)


def test_failed_patient_creation_leaves_no_user_row(db: Session):
    email = unique_email()
    with pytest.raises(ValueError):
        create_user(db, email=email, password=DEFAULT_PASSWORD, role=UserRole.PATIENT, name="B")
    assert db.scalar(select(User).where(User.email == email)) is None


def test_persisted_role_is_the_plain_string_value(db: Session):
    """A role oszlop szöveges ('patient'), nem az enum neve ('PATIENT')."""
    user = make_patient(db).user
    raw = db.execute(text("select role from users where id = :id"), {"id": user.id}).scalar()
    assert raw == "patient"


# --- 9. e-mail: kisbetűs tárolás és egyediség ------------------------------------


def test_email_is_stored_lowercased_and_stripped(db: Session):
    user = create_user(
        db,
        email="  Nagy.Péter@Pulse-Teszt.HU  ",
        password=DEFAULT_PASSWORD,
        role=UserRole.ADMIN,
    )
    assert user.email == "nagy.péter@pulse-teszt.hu"
    raw = db.execute(text("select email from users where id = :id"), {"id": user.id}).scalar()
    assert raw == "nagy.péter@pulse-teszt.hu"


def test_duplicate_email_exact_rejected(db: Session):
    email = unique_email()
    create_user(db, email=email, password=DEFAULT_PASSWORD, role=UserRole.ADMIN)
    with pytest.raises(IntegrityError):
        create_user(db, email=email, password=DEFAULT_PASSWORD, role=UserRole.ADMIN)
    db.rollback()


def test_duplicate_email_different_case_rejected(db: Session):
    create_user(db, email="dupla@pulse-teszt.hu", password=DEFAULT_PASSWORD, role=UserRole.ADMIN)
    with pytest.raises(IntegrityError):
        create_user(
            db,
            email="DUPLA@Pulse-Teszt.hu",
            password=DEFAULT_PASSWORD,
            role=UserRole.DOCTOR,
            name="Dr. Dupla",
        )
    db.rollback()


def test_duplicate_email_with_whitespace_rejected(db: Session):
    create_user(db, email="szokoz@pulse-teszt.hu", password=DEFAULT_PASSWORD, role=UserRole.ADMIN)
    with pytest.raises(IntegrityError):
        create_user(
            db,
            email="  szokoz@pulse-teszt.hu ",
            password=DEFAULT_PASSWORD,
            role=UserRole.PATIENT,
            name="B",
            birth_date=date(1970, 1, 1),
        )
    db.rollback()


def test_duplicate_email_across_roles_rejected(db: Session):
    """Ugyanaz az e-mail nem lehet egyszerre beteg és orvos fiók."""
    make_patient(db, email="ketszerep@pulse-teszt.hu")
    with pytest.raises(IntegrityError):
        make_doctor(db, email="ketszerep@pulse-teszt.hu")
    db.rollback()


def test_database_itself_enforces_case_insensitive_email_uniqueness(db: Session):
    """[SPEC-VÁLTOZÁS 2026-10-10] Védelem mélységben: a szolgáltatásréteget
    megkerülő vegyes betűs beszúrást az adatbázis utasítja el
    (ck_users_email_lowercase). Korábban lelet volt."""
    create_user(db, email="szint@pulse-teszt.hu", password=DEFAULT_PASSWORD, role=UserRole.ADMIN)
    db.add(User(email="Szint@pulse-teszt.hu", password_hash="x", role=UserRole.ADMIN))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_database_rejects_mixed_case_email_even_without_duplicate(db: Session):
    """[ÚJ 2026-10-10] A CHECK nem a duplikátumot, hanem magát a nem kisbetűs
    címet tiltja: egyedülálló vegyes betűs sor sem szúrható be."""
    db.add(User(email="Egyedul@pulse-teszt.hu", password_hash="x", role=UserRole.ADMIN))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_database_rejects_email_with_surrounding_whitespace_or_not(db: Session):
    """[ÚJ 2026-10-10] A CHECK csak a kisbetűsséget fogja; a szélén szóközös, de
    kisbetűs cím átmegy rajta. Dokumentálja a kényszer hatókörét (nem lelet, a
    spec csak lower()-t kér)."""
    db.add(User(email=" szokozos@pulse-teszt.hu ", password_hash="x", role=UserRole.ADMIN))
    db.flush()  # nem dob


# --- 9. jelszóhossz létrehozáskor (spec-változás 2026-10-10) ----------------------


@pytest.mark.parametrize("length", [0, 1, PASSWORD_MIN_LENGTH - 1, PASSWORD_MAX_LENGTH + 1])
def test_create_user_rejects_password_outside_rule(db: Session, length):
    with pytest.raises(ValueError):
        create_user(db, email=unique_email(), password="x" * length, role=UserRole.ADMIN)


@pytest.mark.parametrize("length", [PASSWORD_MIN_LENGTH, PASSWORD_MAX_LENGTH])
def test_create_user_accepts_password_at_rule_boundaries(db: Session, length):
    user = create_user(db, email=unique_email(), password="y" * length, role=UserRole.ADMIN)
    assert verify_password("y" * length, user.password_hash)


def test_create_user_password_rule_applies_to_all_roles(db: Session):
    short = "x" * (PASSWORD_MIN_LENGTH - 1)
    with pytest.raises(ValueError):
        create_user(db, email=unique_email(), password=short, role=UserRole.ADMIN)
    with pytest.raises(ValueError):
        create_user(db, email=unique_email(), password=short, role=UserRole.DOCTOR, name="Dr.")
    with pytest.raises(ValueError):
        create_user(
            db,
            email=unique_email(),
            password=short,
            role=UserRole.PATIENT,
            name="B",
            birth_date=date(1970, 1, 1),
        )


def test_rejected_password_leaves_no_user_row(db: Session):
    email = unique_email()
    with pytest.raises(ValueError):
        create_user(db, email=email, password="rovid", role=UserRole.ADMIN)
    assert db.scalar(select(User).where(User.email == email)) is None


def test_password_rule_counts_characters_not_bytes(db: Session):
    """10 ékezetes karakter (több bájt) elfogadott; a szabály karakterben mérjük."""
    password = "áéíóöőúüűá"
    assert len(password) == PASSWORD_MIN_LENGTH
    user = create_user(db, email=unique_email(), password=password, role=UserRole.ADMIN)
    assert verify_password(password, user.password_hash)


# --- 8. jelszóhash ---------------------------------------------------------------


def test_password_stored_as_argon2id_hash(db: Session):
    user = make_patient(db, password="Teszt-Jelszo-99").user
    raw = db.execute(
        text("select password_hash from users where id = :id"), {"id": user.id}
    ).scalar()
    assert raw.startswith("$argon2id$")
    assert raw != "Teszt-Jelszo-99"
    assert "Teszt-Jelszo-99" not in raw


def test_hash_verifies_only_the_right_password(db: Session):
    user = make_patient(db, password="Teszt-Jelszo-99").user
    assert verify_password("Teszt-Jelszo-99", user.password_hash)
    assert not verify_password("teszt-jelszo-99", user.password_hash)
    assert not verify_password("Teszt-Jelszo-99 ", user.password_hash)
    assert not verify_password("", user.password_hash)


def test_same_password_gives_different_hashes(db: Session):
    """Sózott hash: két fiók azonos jelszóval sem azonosítható a hash alapján."""
    a = make_patient(db, password="Kozos-Jelszo-1").user
    b = make_doctor(db, password="Kozos-Jelszo-1").user
    assert a.password_hash != b.password_hash


def test_raw_password_not_anywhere_in_user_row(db: Session):
    password = "Egyedi-Nyers-Jelszo-7731"
    user = make_admin(db, password=password).user
    row = db.execute(
        text("select row_to_json(u)::text from users u where id = :id"), {"id": user.id}
    ).scalar()
    assert password not in row
    assert password.lower() not in row.lower()


def test_raw_password_not_anywhere_in_any_table(db: Session):
    """Minden táblát végignézünk szövegként (profilok, összerendelések is)."""
    password = "Nyers-Jelszo-Mindenhol-5519"
    make_patient(db, password=password)
    make_doctor(db, password=password)
    tables = (
        db.execute(
            text(
                "select table_name from information_schema.tables "
                "where table_schema = 'public' and table_type = 'BASE TABLE'"
            )
        )
        .scalars()
        .all()
    )
    assert tables, "nincs tábla a teszt-adatbázisban"
    for table in tables:
        rows = db.execute(text(f'select row_to_json(t)::text from "{table}" t')).scalars().all()
        for row in rows:
            assert password not in row, f"nyers jelszó a(z) {table} táblában"


def test_hash_length_fits_column(db: Session):
    """A hash elfér a 255 karakteres oszlopban (különben csonkolás/hiba lenne)."""
    user = make_patient(db).user
    assert len(user.password_hash) <= 255
