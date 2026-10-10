import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, Date, DateTime, Enum, ForeignKey, String, func, text
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class UserRole(StrEnum):
    PATIENT = "patient"
    DOCTOR = "doctor"
    ADMIN = "admin"


class User(Base):
    """Bejelentkezésre jogosult felhasználó. A szerepkör dönti el, melyik
    profil tartozik hozzá: betegnél PatientProfile, orvosnál DoctorProfile,
    adminnál egyik sem."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # Mindig kisbetűsítve tároljuk (services/users.py), és az adatbázis is csak
    # kisbetűs címet fogad el (lásd lent), így kis- és nagybetűtől függetlenül egyedi.
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    # Az adatbázisban szövegként, ellenőrző megszorítással (nem PostgreSQL
    # enum-típusként), így új szerepkör felvétele egyszerű migráció.
    role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            name="user_role",
            native_enum=False,
            create_constraint=True,
            length=16,
            values_callable=lambda roles: [r.value for r in roles],
        )
    )
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Az utolsó sikeres belépés ideje (az admin-felületen hasznos); NULL = még nem lépett be.
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    patient_profile: Mapped["PatientProfile | None"] = relationship(back_populates="user")
    doctor_profile: Mapped["DoctorProfile | None"] = relationship(back_populates="user")

    __table_args__ = (
        # Védelem mélységben: ha egy kódút elfelejtené a kisbetűsítést, az
        # adatbázis akkor is elutasítja a vegyes betűs címet (független teszt lelete).
        CheckConstraint("email = lower(email)", name="email_lowercase"),
    )


class PatientProfile(Base):
    """A beteg szűk, demonstrációs adattartalma (03_adatmodell.md)."""

    __tablename__ = "patient_profiles"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    birth_date: Mapped[date] = mapped_column(Date)

    user: Mapped[User] = relationship(back_populates="patient_profile")


class DoctorProfile(Base):
    __tablename__ = "doctor_profiles"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), unique=True)
    name: Mapped[str] = mapped_column(String(200))

    user: Mapped[User] = relationship(back_populates="doctor_profile")


class DoctorPatient(Base):
    """Orvos–beteg összerendelés időbeli érvényességgel. A hozzáférés mindig
    az éppen érvényes összerendelésen alapul (F3): valid_to = NULL → aktív."""

    __tablename__ = "doctor_patients"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    doctor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("doctor_profiles.id"))
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patient_profiles.id"))
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="valid_period"),
        # Ugyanarra az orvos–beteg párra az érvényességi időszakok nem fedhetik
        # át egymást (egyszerre legfeljebb egy érvényes összerendelés, F3). Az
        # időszak [valid_from, valid_to), üres valid_to = nyitott vég. A lezárt
        # sorok a történetet őrzik. A gist-index az uuid-ok egyenlőségéhez a
        # btree_gist bővítményt igényli (lásd a migrációt).
        ExcludeConstraint(
            ("doctor_id", "="),
            ("patient_id", "="),
            (func.tstzrange(text("valid_from"), text("valid_to"), "[)"), "&&"),
            name="ex_doctor_patients_no_overlap",
            using="gist",
        ),
    )
