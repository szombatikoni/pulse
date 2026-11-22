"""Az admin-végpontok (M3, A1) sémái. A válaszokban nincs betegadat (F2):
a felhasználónál csak azonosító adat, a születési dátum sem."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.models import UserRole
from app.services.admin import AssignmentRow, UserRow


class AdminUserOut(BaseModel):
    id: uuid.UUID
    email: str
    role: UserRole
    # Beteg- és orvosprofil neve; adminnál üres.
    name: str | None
    # A beteg- vagy orvosprofil azonosítója (az összerendeléshez); adminnál üres.
    profile_id: uuid.UUID | None
    is_active: bool
    created_at: datetime
    # NULL = még nem lépett be.
    last_login_at: datetime | None


class AdminUserCreate(BaseModel):
    """Új felhasználó. A név betegnél és orvosnál kötelező, a születési dátum
    csak betegnél; adminnál mindkettő figyelmen kívül marad. A formai és
    hosszellenőrzés a szolgáltatásban van, kóddal (services/admin.py)."""

    email: str = Field(max_length=320, examples=["uj.beteg@pulse.example"])
    password: str = Field(max_length=1024)
    role: UserRole
    name: str | None = Field(default=None, max_length=1000)
    birth_date: date | None = None


class AdminUserRename(BaseModel):
    name: str = Field(max_length=1000)


class AdminAssignmentOut(BaseModel):
    id: uuid.UUID
    # Profil-azonosítók (DoctorProfile.id, PatientProfile.id).
    doctor_id: uuid.UUID
    doctor_name: str
    patient_id: uuid.UUID
    patient_name: str
    valid_from: datetime
    # NULL = érvényes, nyitott végű.
    valid_to: datetime | None


class AdminAssignmentCreate(BaseModel):
    """Az orvos- és a betegprofil azonosítója; a kezdet mindig „most"."""

    doctor_id: uuid.UUID
    patient_id: uuid.UUID


class ComponentRange(BaseModel):
    code: str = Field(max_length=50)
    min_value: float = Field(allow_inf_nan=False)
    max_value: float = Field(allow_inf_nan=False)


class MeasurementRangesUpdate(BaseModel):
    """A méréstípus komponenseinek rögzíthető tartománya; csak a felsorolt
    komponensek változnak."""

    components: list[ComponentRange] = Field(min_length=1, max_length=10)


def admin_user_out(row: UserRow) -> AdminUserOut:
    return AdminUserOut(
        id=row.user.id,
        email=row.user.email,
        role=row.user.role,
        name=row.name,
        profile_id=row.profile_id,
        is_active=row.user.is_active,
        created_at=row.user.created_at,
        last_login_at=row.user.last_login_at,
    )


def admin_assignment_out(row: AssignmentRow) -> AdminAssignmentOut:
    return AdminAssignmentOut(
        id=row.link.id,
        doctor_id=row.link.doctor_id,
        doctor_name=row.doctor_name,
        patient_id=row.link.patient_id,
        patient_name=row.patient_name,
        valid_from=row.link.valid_from,
        valid_to=row.link.valid_to,
    )
