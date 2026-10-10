import uuid

from pydantic import BaseModel, Field

from app.core.security import PASSWORD_MAX_LENGTH
from app.models import UserRole


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255, examples=["dr.kovacs@pulse.example"])
    password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="A token érvényessége másodpercben.")


class CurrentUserResponse(BaseModel):
    id: uuid.UUID
    email: str
    role: UserRole
    name: str | None = Field(description="A profil szerinti név; adminnál nincs.")
