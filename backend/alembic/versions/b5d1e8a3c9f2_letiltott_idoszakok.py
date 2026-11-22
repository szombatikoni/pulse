"""letiltott időszakok

Az admin-felület (M3, A1) letiltása és visszaengedélyezése: a
user_disabled_periods tábla a felhasználó letiltott időszakait tárolja
([disabled_at, enabled_at), üres enabled_at = most is tart). A letiltott beteg
azon alkalma, amelynek határideje egy ilyen időszakba esik, nem számít
elmulasztottnak, utólag sem (a hallgató döntése, 2026-11-16); a letiltás előtti
és utáni alkalmak változatlanul számítanak. Több letiltás is tárolható,
felhasználónként legfeljebb egy nyitott.

A belépést továbbra is a users.is_active dönti el. Ha a migráció idején már
van letiltott felhasználó (a demóban nincs), az a migráció pillanatától nyitott
időszakot kap, így a táblával összhangban van; a korábbi alkalmai nem változnak.

Revision ID: b5d1e8a3c9f2
Revises: e14010eb61d3
Create Date: 2026-11-21 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b5d1e8a3c9f2"
down_revision: str | Sequence[str] | None = "e14010eb61d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "user_disabled_periods",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("enabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "enabled_at IS NULL OR enabled_at > disabled_at",
            name=op.f("ck_user_disabled_periods_valid_period"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_user_disabled_periods_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_disabled_periods")),
    )
    op.create_index(op.f("ix_user_disabled_periods_user_id"), "user_disabled_periods", ["user_id"])
    op.create_index(
        "uq_user_disabled_periods_open",
        "user_disabled_periods",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("enabled_at IS NULL"),
    )
    # A már letiltott felhasználók (ha vannak) nyitott időszakot kapnak.
    op.execute(
        "INSERT INTO user_disabled_periods (id, user_id, disabled_at) "
        "SELECT gen_random_uuid(), id, now() FROM users WHERE NOT is_active"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "uq_user_disabled_periods_open",
        table_name="user_disabled_periods",
        postgresql_where=sa.text("enabled_at IS NULL"),
    )
    op.drop_index(op.f("ix_user_disabled_periods_user_id"), table_name="user_disabled_periods")
    op.drop_table("user_disabled_periods")
