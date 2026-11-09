"""riasztás felelőse és értesítések

A riasztás-életút (M3, A6): a riasztás aktuális felelőse (alerts.assigned_to,
az orvos felhasználója; a régi sorokban üres), és a betegnek szóló
értesítések táblája (notifications). Az értesítés most egy típusú: az orvos
visszajelzése a riasztás lezárásakor; az e-mail-kézbesítés (A9) erre épül.

Kézi javítás az autogenerate után: a felsorolás-oszlop ellenőrző megszorítása
kétszer szerepelt volna (mint a korábbi migrációkban); a névkonvenció szerinti
maradt.

Revision ID: c20bba6e2a66
Revises: 3b9d2e7a41c6
Create Date: 2026-11-09 11:59:32.492701

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c20bba6e2a66"
down_revision: str | Sequence[str] | None = "3b9d2e7a41c6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column(
            "type",
            sa.Enum("alert_feedback", name="notification_type", native_enum=False, length=20),
            nullable=False,
        ),
        sa.Column("text", sa.String(length=500), nullable=False),
        sa.Column("alert_id", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "type IN ('alert_feedback')", name=op.f("ck_notifications_notification_type")
        ),
        sa.ForeignKeyConstraint(
            ["alert_id"], ["alerts.id"], name=op.f("fk_notifications_alert_id_alerts")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_notifications_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["patient_id"],
            ["patient_profiles.id"],
            name=op.f("fk_notifications_patient_id_patient_profiles"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
    )
    op.create_index(
        op.f("ix_notifications_patient_id"), "notifications", ["patient_id"], unique=False
    )
    op.add_column("alerts", sa.Column("assigned_to", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_alerts_assigned_to_users"), "alerts", "users", ["assigned_to"], ["id"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f("fk_alerts_assigned_to_users"), "alerts", type_="foreignkey")
    op.drop_column("alerts", "assigned_to")
    op.drop_index(op.f("ix_notifications_patient_id"), table_name="notifications")
    op.drop_table("notifications")
