from enum import StrEnum

from sqlalchemy import Enum, MetaData
from sqlalchemy.orm import DeclarativeBase

# Egységes névadás a megszorításoknak (kulcsok, indexek, ellenőrzések). Így az
# Alembic minden gépen ugyanazokat a neveket generálja, és egy későbbi
# migráció név szerint hivatkozhat rájuk.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def str_enum(enum_cls: type[StrEnum], name: str, length: int = 32) -> Enum:
    """Felsorolás-oszlop szövegként, ellenőrző megszorítással (nem PostgreSQL
    enum-típusként), mint a szerepkörnél: új érték felvétele egyszerű migráció."""
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=length,
        values_callable=lambda members: [m.value for m in members],
    )
