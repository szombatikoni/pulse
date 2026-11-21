import uuid

from fastapi import APIRouter, status

from app.api.deps import DoctorUser, ensure_patient_access
from app.core.db import DbSession
from app.schemas.notes import NoteCreate, NoteOut, note_out
from app.services import notes
from app.services.notes import NoteEntry

router = APIRouter(tags=["notes"])

FORBIDDEN = {403: {"description": "Csak a beteg hozzárendelt orvosa"}}


@router.get("/patients/{patient_id}/notes", responses=FORBIDDEN)
def patient_notes(patient_id: uuid.UUID, db: DbSession, user: DoctorUser) -> list[NoteOut]:
    """Az orvosok megjegyzései a betegről (F16), a legújabb elöl, a szerző
    nevével. A beteghez éppen hozzárendelt minden orvos látja, a beteg és az
    admin nem."""
    ensure_patient_access(db, user, patient_id)
    return [note_out(e) for e in notes.list_notes(db, patient_id)]


@router.post(
    "/patients/{patient_id}/notes",
    status_code=status.HTTP_201_CREATED,
    responses={**FORBIDDEN, 422: {"description": "Üres vagy túl hosszú szöveg"}},
)
def create_note(
    patient_id: uuid.UUID, body: NoteCreate, db: DbSession, user: DoctorUser
) -> NoteOut:
    """Új megjegyzés a beteghez. Csak hozzáírható: utólag nem szerkeszthető és
    nem törölhető, a tévedést új megjegyzés javítja."""
    ensure_patient_access(db, user, patient_id)
    note = notes.add_note(db, patient_id=patient_id, author_id=user.id, text=body.text)
    db.commit()
    name = user.doctor_profile.name if user.doctor_profile else user.email
    return note_out(NoteEntry(note=note, author_name=name))
