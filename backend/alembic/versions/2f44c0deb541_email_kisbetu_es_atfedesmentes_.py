"""email kisbetu es atfedesmentes osszerendeles

A független tesztírók (Fable) leleteire hozott döntések (2026-10-10):
- users: az adatbázis csak kisbetűs e-mail-címet fogad el (CHECK), így a
  meglévő egyedi kényszerrel együtt kis- és nagybetűtől függetlenül egyedi;
- doctor_patients: az érvényességi időszak vége a kezdete után van (CHECK), és
  ugyanarra az orvos–beteg párra az időszakok nem fedhetik át egymást
  (EXCLUDE ... USING gist). Ez lefedi a korábbi részleges egyedi indexet is
  (két nyitott időszak is átfed), ezért az indexet eltávolítjuk.

Kézzel írt migráció: az autogenerate csak az index eltávolítását ismerte fel,
a CHECK- és EXCLUDE-kényszerek összevetését nem támogatja.

Revision ID: 2f44c0deb541
Revises: 4e17342ce819
Create Date: 2026-10-10

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2f44c0deb541"
down_revision: str | Sequence[str] | None = "4e17342ce819"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_check_constraint(op.f("ck_users_email_lowercase"), "users", "email = lower(email)")

    op.create_check_constraint(
        op.f("ck_doctor_patients_valid_period"),
        "doctor_patients",
        "valid_to IS NULL OR valid_to > valid_from",
    )
    # A gist-indexben az uuid-oszlopok egyenlőség-vizsgálatához kell (a hivatalos
    # PostgreSQL-image tartalmazza; a bővítmény adatbázisonként egyszer jön létre).
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute(
        "ALTER TABLE doctor_patients ADD CONSTRAINT ex_doctor_patients_no_overlap "
        "EXCLUDE USING gist (doctor_id WITH =, patient_id WITH =, "
        "tstzrange(valid_from, valid_to, '[)') WITH &&)"
    )
    op.drop_index(
        op.f("uq_doctor_patients_active_pair"),
        table_name="doctor_patients",
        postgresql_where=sa.text("valid_to IS NULL"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.create_index(
        op.f("uq_doctor_patients_active_pair"),
        "doctor_patients",
        ["doctor_id", "patient_id"],
        unique=True,
        postgresql_where=sa.text("valid_to IS NULL"),
    )
    op.drop_constraint("ex_doctor_patients_no_overlap", "doctor_patients")
    op.drop_constraint(op.f("ck_doctor_patients_valid_period"), "doctor_patients", type_="check")
    op.drop_constraint(op.f("ck_users_email_lowercase"), "users", type_="check")
    # A btree_gist bővítményt szándékosan nem töröljük: más objektum is használhatja.
