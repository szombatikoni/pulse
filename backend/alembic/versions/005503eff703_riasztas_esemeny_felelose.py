"""riasztás-esemény felelőse

A felelőshöz rendelés eseménye tárolja, KIHEZ rendelték (alert_events.assignee_id,
az orvos felhasználója); így újra-hozzárendelés után is kiolvasható a korábbi
felelősök sora (M3, A6). A régi sorokban és a többi eseménynél üres. Az
esemény-tábla csak hozzáírható marad (az oszlop felvétele nem módosít sort).

Revision ID: 005503eff703
Revises: c20bba6e2a66
Create Date: 2026-11-09 16:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "005503eff703"
down_revision: str | Sequence[str] | None = "c20bba6e2a66"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("alert_events", sa.Column("assignee_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_alert_events_assignee_id_users"),
        "alert_events",
        "users",
        ["assignee_id"],
        ["id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        op.f("fk_alert_events_assignee_id_users"), "alert_events", type_="foreignkey"
    )
    op.drop_column("alert_events", "assignee_id")
