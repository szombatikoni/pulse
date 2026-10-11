import os

# A tesztek külön adatbázison futnak (pulse_test), hogy ne írják felül a
# fejlesztői adatokat. A beállítást az alkalmazás importálása előtt kell megadni.
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://pulse:pulse@127.0.0.1:5432/pulse_test"
)

from collections.abc import Iterator  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.db import engine, get_db  # noqa: E402
from app.main import app  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> None:
    """A teszt-adatbázist egyszer, a valódi migrációkkal hozzuk naprakész
    állapotba; így maguk a migrációk is tesztelve vannak."""
    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")


@pytest.fixture
def db() -> Iterator[Session]:
    """Minden teszt egy külső tranzakcióban fut, amit a végén visszagörgetünk:
    a tesztek nem hagynak nyomot, és nem zavarják egymást. A kódbeli commit
    ilyenkor csak egy mentési pontot (savepoint) zár le."""
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(
        bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
    )
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    """API-kliens, amely ugyanazt a (visszagörgetett) sessiont használja, mint a teszt."""
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
