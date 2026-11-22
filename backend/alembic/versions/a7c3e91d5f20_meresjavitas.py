"""mérésjavítás

A mérésjavítás (M3, A7) két kiegészítése:
- measurements.corrected_from egyedi: egy mérésnek legfeljebb egy javítása lehet,
  így a javítási lánc nem ágazhat el (m3 → m3′ → m3″, mindig a vége érvényes);
  két egyidejű javításnál a szolgáltatás sorzára mellett az adatbázis is őrzi.
  A NULL (nem javítás) bármennyiszer előfordulhat;
- alert_events.condition_met: a „kiváltó adat javítva" esemény pillanatképe,
  hogy a riasztás feltétele a javítás után az akkor aktuális szabályverzió
  szerint még teljesül-e. A régi sorokban és a többi eseménynél üres; az
  esemény-tábla csak hozzáírható marad (az oszlop felvétele nem módosít sort).

Revision ID: a7c3e91d5f20
Revises: 005503eff703
Create Date: 2026-11-09 20:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c3e91d5f20"
down_revision: str | Sequence[str] | None = "005503eff703"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_unique_constraint(
        op.f("uq_measurements_corrected_from"), "measurements", ["corrected_from"]
    )
    op.add_column("alert_events", sa.Column("condition_met", sa.Boolean(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("alert_events", "condition_met")
    op.drop_constraint(op.f("uq_measurements_corrected_from"), "measurements", type_="unique")
