"""Az admin végpontjai: „ellenőrzés most" (M3, A2), és az admin-felület (M3,
A1; F20): felhasználók, orvos–beteg összerendelések, a méréstípusok
rögzíthető tartománya.

Csak az admin éri el (a beteg és az orvos 403, token nélkül 401). A logika a
szolgáltatásban van (services/admin.py); a hibák a detail.code-ban kóddal
jönnek, mint az előírásoknál: ütközés a meglévő állapottal 409, érvénytelen
adat 422, nem létező azonosító 404. A válaszokban nincs betegadat (F2)."""

import uuid

from fastapi import APIRouter, HTTPException, status

from app.api.deps import AdminUser
from app.core.db import DbSession
from app.models import User
from app.schemas.admin import (
    AdminAssignmentCreate,
    AdminAssignmentOut,
    AdminUserCreate,
    AdminUserOut,
    AdminUserRename,
    MeasurementRangesUpdate,
    admin_assignment_out,
    admin_user_out,
)
from app.schemas.measurements import MeasurementTypeOut, measurement_type_out
from app.schemas.occurrences import OccurrenceCheckOut
from app.services import admin
from app.services.admin import AdminError
from app.services.occurrences import run_occurrence_check

router = APIRouter(prefix="/admin", tags=["admin"])

FORBIDDEN = {403: {"description": "Csak az admin"}}
NOT_FOUND = {404: {"description": "Nincs ilyen azonosító"}}
USER_ERRORS = {
    **FORBIDDEN,
    409: {"description": "Ütközés (a detail.code: email_taken, self_disable, last_admin)"},
    422: {
        "description": "Érvénytelen adat (a detail.code: email_invalid, password_length, "
        "name_required, name_too_long, birth_date_required, birth_date_invalid, no_name)"
    },
}
ASSIGNMENT_ERRORS = {
    **FORBIDDEN,
    409: {"description": "Ütközés (a detail.code: already_assigned, already_ended, not_started)"},
    422: {
        "description": "Érvénytelen adat (a detail.code: not_a_doctor, not_a_patient, "
        "inactive_user)"
    },
}
RANGE_ERRORS = {
    **FORBIDDEN,
    **NOT_FOUND,
    422: {"description": "Érvénytelen tartomány (a detail.code: unknown_component, range_invalid)"},
}


def _error(error: AdminError) -> HTTPException:
    """Az ellenőrzések minden módosítás előtt futnak, így hibánál nincs mit
    visszavonni; a kérés sessionje commit nélkül zárul."""
    code = status.HTTP_409_CONFLICT if error.conflict else status.HTTP_422_UNPROCESSABLE_CONTENT
    return HTTPException(status_code=code, detail={"code": error.code})


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


def _user_or_404(db: DbSession, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise _not_found()
    return user


@router.post("/occurrence-check", responses=FORBIDDEN)
def occurrence_check(db: DbSession, _user: AdminUser) -> OccurrenceCheckOut:
    """„Ellenőrzés most": a háttérfolyamat egy futása azonnal (alkalom-nyitás és
    az elmulasztottak lezárása). A demóban így nem kell a következő óránkénti
    futásra várni; ismételt hívás nem okoz változást (idempotens)."""
    result = run_occurrence_check(db)
    db.commit()
    return OccurrenceCheckOut(opened=result.opened, missed=result.missed)


@router.get("/users", responses=FORBIDDEN)
def users(db: DbSession, _user: AdminUser) -> list[AdminUserOut]:
    """A felhasználók listája: név, e-mail, szerepkör, állapot, létrehozás és
    utolsó belépés ideje. Betegadat (születési dátum, státusz, mérés) nincs benne."""
    return [admin_user_out(row) for row in admin.list_users(db)]


@router.post("/users", status_code=status.HTTP_201_CREATED, responses=USER_ERRORS)
def create_user(body: AdminUserCreate, db: DbSession, _user: AdminUser) -> AdminUserOut:
    """Új felhasználó (beteg, orvos vagy admin) a kezdeti jelszóval, amelyet az
    admin ad meg és juttat el (10–255 karakter)."""
    try:
        row = admin.create_account(
            db,
            email=body.email,
            password=body.password,
            role=body.role,
            name=body.name,
            birth_date=body.birth_date,
        )
    except AdminError as error:
        raise _error(error) from error
    db.commit()
    return admin_user_out(row)


@router.patch("/users/{user_id}", responses={**USER_ERRORS, **NOT_FOUND})
def rename_user(
    user_id: uuid.UUID, body: AdminUserRename, db: DbSession, _user: AdminUser
) -> AdminUserOut:
    """A név javítása (beteg és orvos). Az e-mail és a szerepkör létrehozás után
    nem változik."""
    user = _user_or_404(db, user_id)
    try:
        row = admin.rename_user(db, user, body.name)
    except AdminError as error:
        raise _error(error) from error
    db.commit()
    return admin_user_out(row)


@router.post("/users/{user_id}/disable", responses={**USER_ERRORS, **NOT_FOUND})
def disable_user(user_id: uuid.UUID, db: DbSession, actor: AdminUser) -> AdminUserOut:
    """Letiltás: a felhasználó nem léphet be, a már kiadott tokenje is azonnal
    érvénytelen. Saját fiók (self_disable) és az utolsó aktív admin (last_admin)
    nem tiltható le. Már letiltott fióknál nem változik semmi (idempotens)."""
    user = _user_or_404(db, user_id)
    try:
        row = admin.disable_user(db, actor, user)
    except AdminError as error:
        raise _error(error) from error
    db.commit()
    return admin_user_out(row)


@router.post("/users/{user_id}/enable", responses={**FORBIDDEN, **NOT_FOUND})
def enable_user(user_id: uuid.UUID, db: DbSession, _user: AdminUser) -> AdminUserOut:
    """Visszaengedélyezés. Betegnél a letiltott időszakba eső határidejű alkalom
    utólag sem számít elmulasztottnak; a letiltás előtti alkalmak változatlanul
    számítanak. Már aktív fióknál nem változik semmi (idempotens)."""
    user = _user_or_404(db, user_id)
    row = admin.enable_user(db, user)
    db.commit()
    return admin_user_out(row)


@router.get("/assignments", responses=FORBIDDEN)
def assignments(db: DbSession, _user: AdminUser) -> list[AdminAssignmentOut]:
    """Az orvos–beteg összerendelések (a lezártak is) az orvos és a beteg
    nevével, kezdettel és véggel."""
    return [admin_assignment_out(row) for row in admin.list_assignments(db)]


@router.post("/assignments", status_code=status.HTTP_201_CREATED, responses=ASSIGNMENT_ERRORS)
def create_assignment(
    body: AdminAssignmentCreate, db: DbSession, _user: AdminUser
) -> AdminAssignmentOut:
    """Új összerendelés azonnali kezdettel: az orvos a következő kérésétől
    eléri a beteget."""
    try:
        row = admin.create_assignment(db, body.doctor_id, body.patient_id)
    except AdminError as error:
        raise _error(error) from error
    db.commit()
    return admin_assignment_out(row)


@router.post("/assignments/{assignment_id}/end", responses={**ASSIGNMENT_ERRORS, **NOT_FOUND})
def end_assignment(assignment_id: uuid.UUID, db: DbSession, _user: AdminUser) -> AdminAssignmentOut:
    """Megszüntetés azonnal: az orvos hozzáférése a következő kérésétől
    megszűnik; a sor a történetben megmarad."""
    try:
        row = admin.end_assignment(db, assignment_id)
    except LookupError as error:
        raise _not_found() from error
    except AdminError as error:
        raise _error(error) from error
    db.commit()
    return admin_assignment_out(row)


@router.put("/measurement-types/{code}/ranges", responses=RANGE_ERRORS)
def update_ranges(
    code: str, body: MeasurementRangesUpdate, db: DbSession, _user: AdminUser
) -> MeasurementTypeOut:
    """A méréstípus komponenseinek rögzíthető tartománya (az elírásszűrés
    határa, nem orvosi határérték). Csak a jövőbeli rögzítést érinti; a meglévő
    mérések, szabályok és riasztások jelentése nem változik. A típusok listája a
    közös GET /measurement-types."""
    ranges = {c.code: (c.min_value, c.max_value) for c in body.components}
    try:
        measurement_type = admin.update_ranges(db, code, ranges)
    except LookupError as error:
        raise _not_found() from error
    except AdminError as error:
        raise _error(error) from error
    db.commit()
    return measurement_type_out(measurement_type)
