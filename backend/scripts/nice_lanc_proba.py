"""A NICE-kiértékelés teljes lánca a valódi rendszeren (M3, K2, T1).

A pytest-ek a CQL-szolgáltatást hamis klienssel helyettesítik; ez a szkript a
futó compose-stacken próbálja ki az egész utat: adatbázis → FHIR-csomag →
valódi CQL-motor (külön konténer) → összevetés a saját számítással. Egy
seedelt orvossal belép, a hozzárendelt demóbetegére (Molnár Katalin, a seed
szerint minden nap mér) meghívja a végpontot, és elvárja: 200, `matches: true`,
üres `mismatched_fields`, elég adat, és mindkét átlag egyezik egy harmadik,
itt kézzel számolt értékkel. A kézi számítás nem használja a backend
számítását: a beteg méréslistáját az API-ból kéri le, és maga választja ki az
ablakot (7 lezárt budapesti nap), az első napot és az átlagot.

Csak olvas (a kiértékelés semmit nem tárol). A seed relatív időpontú: a
mérések a futtatás napjához képest készülnek, ezért frissen seedelt adatbázis
kell (régi adatbázison „nincs elég adat" lesz, és a szkript ezt hibaként jelzi).

Futtatás (a CI Docker-jobja is így hívja, a seed után):
    docker compose exec -T api python -m scripts.nice_lanc_proba
Kilépési kód: 0 siker, 1 bármilyen eltérés vagy hiba.
"""

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from fractions import Fraction
from zoneinfo import ZoneInfo

API = os.environ.get("PULSE_API", "http://127.0.0.1:8000/api")
DOCTOR = "dr.kovacs@pulse.example"
PASSWORD = os.environ.get("PULSE_DEMO_PASSWORD", "pulse-demo-2026")  # seed/demo.py
PATIENT = "Molnár Katalin"
TZ = ZoneInfo("Europe/Budapest")
TOLERANCE = Fraction(1, 10**9)


class Failure(Exception):
    pass


def call(method: str, path: str, token: str | None = None, body: dict | None = None):
    request = urllib.request.Request(
        f"{API}{path}",
        data=None if body is None else json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}
        | ({"Authorization": f"Bearer {token}"} if token else {}),
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode(errors="replace")


def check(condition: bool, message: str) -> None:
    if not condition:
        raise Failure(message)


def manual_expectation(readings: list[dict], today: date) -> dict:
    """A várt eredmény kézzel: a 7 lezárt nap [ma-7, ma), az első mérési nap
    kizárva, a többi mérés átlaga pontos törtekkel."""
    start, end = today - timedelta(days=7), today
    rows = []
    for m in readings:
        if m.get("corrected_by"):  # felülírt (javított) mérés: nem számít
            continue
        day = datetime.fromisoformat(m["measured_at"]).astimezone(TZ).date()
        if start <= day < end:
            values = {v["component"]: Fraction(str(v["value"])) for v in m["values"]}
            rows.append((day, m["id"], values["systolic"], values["diastolic"]))
    check(bool(rows), f"{PATIENT}: nincs vérnyomásmérés [{start}, {end}) ablakban")
    first = min(day for day, *_ in rows)
    included = [r for r in rows if r[0] > first]
    days = sorted({r[0] for r in included})
    check(
        len(days) >= 3,
        f"{PATIENT}: csak {len(days)} figyelembe vett nap (legalább 3 kell); friss seed kell",
    )
    return {
        "period": (start, end),
        "excluded_first_day": first,
        "included_ids": sorted(r[1] for r in included),
        "included_days": days,
        "mean_systolic": sum(r[2] for r in included) / len(included),
        "mean_diastolic": sum(r[3] for r in included) / len(included),
    }


def main() -> None:
    today = datetime.now(TZ).date()
    status, body = call("POST", "/auth/login", body={"email": DOCTOR, "password": PASSWORD})
    check(status == 200, f"belépés: {status} {body}")
    token = body["access_token"]

    status, patients = call("GET", "/doctor/patients", token)
    check(status == 200, f"betegek listája: {status} {patients}")
    matching = [p for p in patients if p["name"] == PATIENT]
    check(len(matching) == 1, f"{PATIENT} nincs (pontosan egyszer) {DOCTOR} betegei között")
    patient_id = matching[0]["id"]

    status, readings = call(
        "GET", f"/patients/{patient_id}/measurements?type=blood_pressure&limit=500", token
    )
    check(status == 200, f"méréslista: {status} {readings}")
    expected = manual_expectation(readings, today)

    status, result = call("POST", f"/patients/{patient_id}/nice-evaluation", token)
    check(status == 200, f"nice-evaluation: {status} {result}")
    check(result["matches"] is True, f"matches: {result['matches']}")
    check(result["mismatched_fields"] == [], f"mismatched_fields: {result['mismatched_fields']}")

    start, end = (datetime.fromisoformat(result["period"][k]) for k in ("start", "end"))
    check(
        (start.date(), end.date()) == expected["period"],
        f"időszak: [{start}, {end}), kézzel: {expected['period']}",
    )
    for side in ("cql", "own"):
        r = result[side]
        check(r["enough_data"] is True, f"{side}.enough_data: {r['enough_data']}")
        check(
            r["excluded_first_day"] == expected["excluded_first_day"].isoformat(),
            f"{side}.excluded_first_day: {r['excluded_first_day']}",
        )
        check(
            sorted(r["included_reading_ids"]) == expected["included_ids"],
            f"{side}.included_reading_ids eltér a kézi kiválasztástól",
        )
        check(
            r["included_days"] == [d.isoformat() for d in expected["included_days"]],
            f"{side}.included_days: {r['included_days']}",
        )
        for name in ("mean_systolic", "mean_diastolic"):
            check(
                abs(Fraction(r[name]) - expected[name]) < TOLERANCE,
                f"{side}.{name}: {r[name]}, kézzel: {float(expected[name])}",
            )

    print(
        f"OK: {PATIENT}, időszak [{start.isoformat()}, {end.isoformat()}), "
        f"kizárt első nap {expected['excluded_first_day']}, "
        f"{len(expected['included_ids'])} mérés {len(expected['included_days'])} napról; "
        f"átlag kézzel {float(expected['mean_systolic']):.4f} / "
        f"{float(expected['mean_diastolic']):.4f}, CQL {result['cql']['mean_systolic']} / "
        f"{result['cql']['mean_diastolic']}, saját {result['own']['mean_systolic']} / "
        f"{result['own']['mean_diastolic']}; target_met {result['cql']['target_met']}; "
        f"motor {result['engine'].get('cql-execution')}, {result['duration_ms']} ms"
    )


if __name__ == "__main__":
    try:
        main()
    except Failure as failure:
        print(f"HIBA: {failure}", file=sys.stderr)
        sys.exit(1)
