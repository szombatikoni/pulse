"""Belépési pont: `python -m seed` (a backend mappából vagy az api konténerben)."""

from app.core.db import SessionLocal
from seed.demo import DEMO_PASSWORD, seed_demo_data


def main() -> None:
    with SessionLocal() as db:
        for line in seed_demo_data(db):
            print(line)
    print(f"Kész. A demófiókok közös jelszava: {DEMO_PASSWORD}")


if __name__ == "__main__":
    main()
