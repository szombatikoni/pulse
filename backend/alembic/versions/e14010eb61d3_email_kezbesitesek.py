"""e-mail-kézbesítések

Az orvosnak szóló e-mail-értesítés (M3, A9) kézbesítési sorai
(notification_deliveries): új riasztásnál címzettenként egy sor, a riasztással
egy tranzakcióban; a háttérfolyamat kézbesítő köre küldi el, újrapróbálkozással.
Index a (status, next_attempt_at) párra: a kör a lejárt, várakozó sorokat keresi.
Ellenőrző megszorítás: az új riasztásról szóló sornak mindig van riasztása.

Kézi javítás az autogenerate után: a felsorolás-oszlopok ellenőrző megszorítása
kétszer szerepelt volna (mint a korábbi migrációkban); a névkonvenció szerinti
maradt.

Revision ID: e14010eb61d3
Revises: ebbfec625d58
Create Date: 2026-11-21 15:29:26.316841

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e14010eb61d3"
down_revision: str | Sequence[str] | None = "ebbfec625d58"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum("alert_created", name="delivery_kind", native_enum=False, length=20),
            nullable=False,
        ),
        sa.Column("alert_id", sa.Uuid(), nullable=True),
        sa.Column("recipient_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending", "sent", "failed", name="delivery_status", native_enum=False, length=10
            ),
            nullable=False,
        ),
        sa.Column("attempts", sa.SmallInteger(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=300), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('alert_created')", name=op.f("ck_notification_deliveries_delivery_kind")
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'sent', 'failed')",
            name=op.f("ck_notification_deliveries_delivery_status"),
        ),
        sa.CheckConstraint(
            "kind <> 'alert_created' OR alert_id IS NOT NULL",
            name=op.f("ck_notification_deliveries_alert_created_has_alert"),
        ),
        sa.ForeignKeyConstraint(
            ["alert_id"], ["alerts.id"], name=op.f("fk_notification_deliveries_alert_id_alerts")
        ),
        sa.ForeignKeyConstraint(
            ["recipient_user_id"],
            ["users.id"],
            name=op.f("fk_notification_deliveries_recipient_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification_deliveries")),
    )
    op.create_index(
        "ix_notification_deliveries_status_next_attempt_at",
        "notification_deliveries",
        ["status", "next_attempt_at"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_notification_deliveries_status_next_attempt_at", table_name="notification_deliveries"
    )
    op.drop_table("notification_deliveries")
