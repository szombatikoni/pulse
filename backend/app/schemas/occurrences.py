from pydantic import BaseModel


class OccurrenceCheckOut(BaseModel):
    """Egy alkalom-ellenőrzés eredménye (ugyanaz, amit a háttérfolyamat naplóz)."""

    # Az újonnan megnyitott alkalmak száma (a visszamenőleg pótoltakkal együtt).
    opened: int
    # A most elmulasztottra zárt alkalmak száma.
    missed: int
