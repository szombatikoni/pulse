"""Jelszóhash (Argon2) és hozzáférési token (JWT) kezelése."""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash

from app.core.config import settings

JWT_ALGORITHM = "HS256"

# Jelszóhossz. Létrehozáskor legalább PASSWORD_MIN_LENGTH kell; belépéskor
# szándékosan csak a felső határ számít (1..MAX), hogy a belépés ne árulja el a
# szabályt, és egy esetleges szabályváltozás ne zárja ki a régi fiókokat.
PASSWORD_MIN_LENGTH = 10
PASSWORD_MAX_LENGTH = 255

# A pwdlib ajánlott beállítása: Argon2. A hash tartalmazza a sót és a
# paramétereket is, ezért külön tárolni nem kell őket.
password_hash = PasswordHash.recommended()

# Nem létező e-mail-címnél is ehhez hasonlítjuk a jelszót, hogy a válaszidő
# ne áruljon el semmit a fiók létezéséről (időzítéses támadás ellen).
DUMMY_HASH = password_hash.hash("dummy-password-for-constant-time-check")


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return password_hash.verify(password, hashed)


def create_access_token(user_id: uuid.UUID, expires_delta: timedelta | None = None) -> str:
    """Aláírt token a felhasználó azonosítójával és lejárati idővel.

    A szerepkört szándékosan NEM tesszük a tokenbe: minden kérésnél az
    adatbázisból olvassuk, így a szerepkör-változás vagy letiltás azonnal hat.
    """
    now = datetime.now(UTC)
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": str(user_id), "iat": now, "exp": now + expires_delta}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> uuid.UUID | None:
    """A token felhasználó-azonosítója, vagy None, ha a token érvénytelen
    (rossz aláírás, lejárt, sérült vagy hiányzó azonosító)."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["sub", "exp"]},
        )
        return uuid.UUID(payload["sub"])
    except (jwt.InvalidTokenError, ValueError):
        return None
