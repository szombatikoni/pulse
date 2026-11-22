"""Orvosi megjegyzések a beteghez (M3, A8; F16).

Csak hozzáírható: új megjegyzés és a lista, szerkesztés és törlés nincs (a
hallgató döntése, A8 D2). Hogy ki érheti el, azt a végpont dönti el
(ensure_patient_access, csak a hozzárendelt orvos); itt nincs jogosultság.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Note
from app.services.alerts import user_names


@dataclass
class NoteEntry:
    """Egy megjegyzés a szerzője megjelenítendő nevével."""

    note: Note
    author_name: str


def add_note(
    db: Session,
    *,
    patient_id: uuid.UUID,
    author_id: uuid.UUID,
    text: str,
    now: datetime | None = None,
) -> Note:
    """Új megjegyzés. A szöveget a séma már ellenőrizte (nem üres, legfeljebb
    NOTE_TEXT_MAX karakter, a szélső szóközök nélkül)."""
    note = Note(
        patient_id=patient_id,
        author_id=author_id,
        text=text,
        created_at=now or datetime.now(UTC),
    )
    db.add(note)
    db.flush()
    return note


def list_notes(db: Session, patient_id: uuid.UUID) -> list[NoteEntry]:
    """A beteg összes megjegyzése, a legújabb elöl (azonos időpontnál az
    azonosító dönt, hogy a sorrend minden lekérésnél ugyanaz legyen)."""
    notes = db.scalars(
        select(Note).where(Note.patient_id == patient_id).order_by(Note.created_at.desc(), Note.id)
    ).all()
    names = user_names(db, {n.author_id for n in notes})
    return [NoteEntry(note=n, author_name=names.get(n.author_id, "")) for n in notes]
