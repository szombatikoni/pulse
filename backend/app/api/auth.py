from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser
from app.core.config import settings
from app.core.db import DbSession
from app.core.security import create_access_token
from app.schemas.auth import CurrentUserResponse, LoginRequest, TokenResponse
from app.services.users import AccountDisabledError, authenticate, record_login

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/login",
    responses={
        401: {"description": "Hibás e-mail-cím vagy jelszó"},
        403: {
            "description": "Helyes jelszó, de a fiók le van tiltva (detail.code: account_disabled)"
        },
    },
)
def login(body: LoginRequest, db: DbSession) -> TokenResponse:
    """Bejelentkezés e-mail-címmel és jelszóval; sikeres esetben hozzáférési token.
    Minden sikertelen esetben (ismeretlen cím, rossz jelszó, letiltott fiók rossz
    jelszóval) ugyanaz a válasz, hogy ne derüljön ki, melyik volt a hiba. Egyetlen
    kivétel: helyes jelszóval a letiltott fiók 403-at kap account_disabled kóddal
    (M3, A1); ezt csak a jelszó ismerője tudhatja meg."""
    try:
        user = authenticate(db, body.email, body.password)
    except AccountDisabledError as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail={"code": "account_disabled"}
        ) from error
    if user is None:
        # Az RFC 9110 szerint a 401-es válaszban kötelező a WWW-Authenticate fejléc.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    record_login(db, user)
    return TokenResponse(
        access_token=create_access_token(user.id),
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.get("/me")
def me(user: CurrentUser) -> CurrentUserResponse:
    """A bejelentkezett felhasználó adatai (a frontend ebből tudja, kit és
    milyen szerepkörben kell kiszolgálnia)."""
    profile = user.patient_profile or user.doctor_profile
    return CurrentUserResponse(
        id=user.id,
        email=user.email,
        role=user.role,
        name=profile.name if profile else None,
        patient_id=user.patient_profile.id if user.patient_profile else None,
    )
