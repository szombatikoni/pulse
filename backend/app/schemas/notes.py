"""Az orvosi megjegyzések végpontjainak sémái (M3, A8)."""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from app.models.note import NOTE_TEXT_MAX
from app.schemas.patients import UserRefOut
from app.services.notes import NoteEntry

NoteText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=NOTE_TEXT_MAX)
]


class NoteCreate(BaseModel):
    text: NoteText = Field(
        description="A megjegyzés szövege (1–1000 karakter, a szélső szóközök nélkül). "
        "A beteg nem látja; utólag nem módosítható.",
        examples=["Telefonon egyeztetve, a gyógyszerelés marad."],
    )


class NoteOut(BaseModel):
    id: uuid.UUID
    text: str
    author: UserRefOut = Field(description="A szerző (orvos) felhasználója és neve.")
    created_at: datetime


def note_out(entry: NoteEntry) -> NoteOut:
    n = entry.note
    return NoteOut(
        id=n.id,
        text=n.text,
        author=UserRefOut(id=n.author_id, name=entry.author_name),
        created_at=n.created_at,
    )
