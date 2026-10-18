"""Közös végpont-függőségek: ki a bejelentkezett felhasználó, és mi a szerepköre."""

import uuid
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.db import DbSession
from app.core.security import decode_access_token
from app.models import User, UserRole
from app.services.access import can_access_patient

# A Swaggerben ettől jelenik meg az „Authorize" gomb (Bearer token mezővel).
# auto_error=False: a hiányzó tokenre mi magunk adunk 401-et, egységesen.
bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    """A tokenből azonosított, aktív felhasználó; különben 401.
    A felhasználót minden kérésnél az adatbázisból töltjük be, így a letiltás
    azonnal hat, nem csak a token lejártakor."""
    if credentials is None:
        raise _unauthorized()
    user_id = decode_access_token(credentials.credentials)
    if user_id is None:
        raise _unauthorized()
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise _unauthorized()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: UserRole) -> Callable[[User], User]:
    """Függőség-gyár: csak a megadott szerepkörök érhetik el a végpontot (különben 403).
    Használat: `user: Annotated[User, Depends(require_roles(UserRole.DOCTOR))]`."""

    def checker(user: CurrentUser) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        return user

    return checker


DoctorUser = Annotated[User, Depends(require_roles(UserRole.DOCTOR))]
PatientUser = Annotated[User, Depends(require_roles(UserRole.PATIENT))]


def ensure_patient_access(db: Session, user: User, patient_id: uuid.UUID) -> None:
    """403, ha a felhasználó nem érheti el a beteg adatait (F2, F3). Nem létező
    betegre is 403 jön, így a válaszból nem derül ki, létezik-e az azonosító."""
    if not can_access_patient(db, user, patient_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
