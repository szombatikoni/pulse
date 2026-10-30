"""A PULSE FHIR-kiadásának letöltése a futó API-ból (M3, K1).

Belép orvosként, a beteglistájából név szerint kikeresi a beteget, és letölti a
csomagját (GET /api/patients/{id}/fhir) az adat/ mappába. Csak a szabványos
könyvtárat használja.

Futtatás az integration/ mappából, futó PULSE-példány mellett (a demóadatokkal):
    python -I kiadas/letoltes.py
    python -I kiadas/letoltes.py --beteg "Varga Béla" --api http://127.0.0.1:8000
A demófiókok jelszava a seed közös jelszava; a PULSE_JELSZO változóval felülírható.
Kilépési kód: 0 = letöltve, 1 = hiba.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

GYOKER = Path(__file__).resolve().parent.parent
KIMENET = GYOKER / "adat" / "pulse_kiadas_bundle.json"


def keres(url: str, token: str | None = None, adat: dict | None = None) -> object:
    fejlec = {"Accept": "application/json, application/fhir+json"}
    if token:
        fejlec["Authorization"] = f"Bearer {token}"
    torzs = None
    if adat is not None:
        torzs = json.dumps(adat).encode("utf-8")
        fejlec["Content-Type"] = "application/json"
    with urllib.request.urlopen(urllib.request.Request(url, torzs, fejlec), timeout=30) as valasz:
        return json.loads(valasz.read().decode("utf-8"))


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--api", default="http://127.0.0.1:8000", help="a PULSE címe")
    p.add_argument("--orvos", default="dr.kovacs@pulse.example", help="az orvos belépési e-mailje")
    p.add_argument("--beteg", default="Szabó János", help="a beteg neve az orvos listáján")
    p.add_argument("--kimenet", type=Path, default=KIMENET)
    a = p.parse_args()
    jelszo = os.environ.get("PULSE_JELSZO", "pulse-demo-2026")

    try:
        token = keres(f"{a.api}/api/auth/login", adat={"email": a.orvos, "password": jelszo})[
            "access_token"
        ]
        betegek = keres(f"{a.api}/api/doctor/patients", token)
        talalat = [b for b in betegek if b["name"] == a.beteg]
        if len(talalat) != 1:
            print(f"A beteg nincs (pontosan egyszer) {a.orvos} listáján: {a.beteg}")
            return 1
        csomag = keres(f"{a.api}/api/patients/{talalat[0]['id']}/fhir", token)
    except (urllib.error.URLError, KeyError) as hiba:
        print(f"A letöltés nem sikerült ({a.api}): {hiba}")
        return 1

    a.kimenet.parent.mkdir(parents=True, exist_ok=True)
    a.kimenet.write_text(
        json.dumps(csomag, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    tipusok: dict[str, int] = {}
    for e in csomag["entry"]:
        tipus = e["resource"]["resourceType"]
        tipusok[tipus] = tipusok.get(tipus, 0) + 1
    print(f"Letöltve: {a.beteg} ({talalat[0]['id']}) -> {a.kimenet.relative_to(GYOKER)}")
    print("   ", ", ".join(f"{t}: {n}" for t, n in tipusok.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
