"""megjegyzések

Orvosi megjegyzés a beteghez (M3, A8; F16): a notes tábla. Csak hozzáírható
(nincs szerkesztés és törlés); a beteg nem látja, a beteghez éppen hozzárendelt
orvosok igen. Az M1-es adatmodell doctor_id mezője helyett author_id (users.id),
mint a notifications.created_by. Az üres szöveget ellenőrző megszorítás is
kizárja.

Revision ID: ebbfec625d58
Revises: a7c3e91d5f20
Create Date: 2026-11-21 15:16:45.833552

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ebbfec625d58"
down_revision: str | Sequence[str] | None = "a7c3e91d5f20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "notes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column("text", sa.String(length=1000), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("text ~ '[^[:space:]]'", name=op.f("ck_notes_text_not_blank")),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], name=op.f("fk_notes_author_id_users")),
        sa.ForeignKeyConstraint(
            ["patient_id"],
            ["patient_profiles.id"],
            name=op.f("fk_notes_patient_id_patient_profiles"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notes")),
    )
    op.create_index(op.f("ix_notes_patient_id"), "notes", ["patient_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_notes_patient_id"), table_name="notes")
    op.drop_table("notes")
