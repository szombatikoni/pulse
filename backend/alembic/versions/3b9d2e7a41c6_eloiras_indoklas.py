"""előírás indoklása

Visszavonásnál és módosításnál az orvos rövid, nem kötelező indoklása
(assignments.revoke_note; M3, A3; a hallgató döntése, 2026-11-01). A beteg is
látja; a régi sorokban üres.

Revision ID: 3b9d2e7a41c6
Revises: 825da954a008
Create Date: 2026-11-01 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3b9d2e7a41c6"
down_revision: str | Sequence[str] | None = "825da954a008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("assignments", sa.Column("revoke_note", sa.String(length=500), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("assignments", "revoke_note")
