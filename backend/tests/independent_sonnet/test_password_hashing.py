"""Jelszó-hash tárolás — a 8. jóváhagyott pont."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User
from tests.independent_sonnet.helpers import make_patient


def test_password_stored_as_argon2_hash(db: Session) -> None:
    make_patient(db, email="hash-teszt@example.com", password="EgyNagyonJoJelszo!1")

    stored = db.scalar(select(User).where(User.email == "hash-teszt@example.com"))

    assert stored is not None
    assert stored.password_hash.startswith("$argon2id$")
    assert "EgyNagyonJoJelszo" not in stored.password_hash
