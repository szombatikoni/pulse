"""Független kézi számítás a CQL-motor eredményének ellenőrzésére.

A szkript NEM használja a CQL-t és a motort: a kutatás 3.5-ös kézi példájának
táblázatából (lent, beírva) pontos törtekkel (fractions) számol, majd
összeveti:
  1. a táblázatot a FHIR-csomaggal (adat/beteg_hbpm_bundle.json),
  2. a saját eredményét a motor kimenetével (eredmeny/eredmeny.json).

Futtatás az integration/ mappából:
    python -I ellenorzes/kezi_szamitas.py
vagy Dockerrel:
    docker compose run --rm ellenorzes
Kilépési kód: 0 = minden egyezik, 1 = eltérés.
"""

from __future__ import annotations

import json
import math
import sys
from datetime import date, datetime, timedelta
from fractions import Fraction
from pathlib import Path

GYOKER = Path(__file__).resolve().parent.parent
CSOMAG = GYOKER / "adat" / "beteg_hbpm_bundle.json"
EREDMENY = GYOKER / "eredmeny" / "eredmeny.json"

# A 3.5-ös kézi példa (helyi nap -> leolvasások: szisztolés, diasztolés).
TABLAZAT: dict[date, list[tuple[int, int]]] = {
    date(2026, 10, 5): [(150, 95), (148, 94), (146, 92), (144, 92)],
    date(2026, 10, 6): [(138, 86), (136, 85), (134, 84), (136, 86)],
    date(2026, 10, 7): [(140, 88), (138, 86), (132, 82), (134, 84)],
    date(2026, 10, 8): [(136, 86), (134, 84), (130, 80), (132, 82)],
}
SZULETESI_DATUM = date(1958, 3, 14)

# A sorozat: [tól, ig) helyi idő szerint.
SOROZAT = (datetime.fromisoformat("2026-10-05T00:00:00+02:00"),
           datetime.fromisoformat("2026-10-09T00:00:00+02:00"))

ALAP = {
    "exclude_first_day": True,
    "first_day": "FirstReadingDay",
    "min_days": 3,
    "age_threshold": 80,
    "target_under": (Fraction(135), Fraction(85)),
    "target_over": (Fraction(145), Fraction(85)),
    "both_below": True,
    "rounding": None,
    "birth_date": SZULETESI_DATUM,
    "series": SOROZAT,
}

FORGATOKONYVEK = {
    "A-alap": {},
    "B-elso-nap-nelkul": {"exclude_first_day": False},
    "C-eleg-az-egyik": {"both_below": False},
    "D-kerekites-egeszre": {"rounding": 0},
    "E-min-4-nap": {"min_days": 4},
    "F-80-ev-feletti": {"birth_date": date(1944, 3, 14)},
    "G-kirendeles-kezdonapja": {
        "first_day": "PeriodStartDay",
        "series": (datetime.fromisoformat("2026-10-04T00:00:00+02:00"), SOROZAT[1]),
    },
}


def eletkor(szuletes: date, nap: date) -> int:
    return nap.year - szuletes.year - ((nap.month, nap.day) < (szuletes.month, szuletes.day))


def kerekit(x: Fraction, tizedes: int) -> Fraction:
    # Felfelé kerekítés a félértéknél (pozitív számoknál ugyanaz, mint a JS Math.round).
    szorzo = 10 ** tizedes
    return Fraction(math.floor(x * szorzo + Fraction(1, 2)), szorzo)


def szamol(p: dict) -> dict:
    tol, ig = p["series"]
    napok = sorted(TABLAZAT)
    # A táblázat minden napja a sorozatba esik (okt. 5-8.), ezt ellenőrizzük is.
    assert all(tol.date() <= n < ig.date() for n in napok)

    if not p["exclude_first_day"]:
        elso_nap = None
    elif p["first_day"] == "PeriodStartDay":
        elso_nap = tol.date()
    else:
        elso_nap = napok[0]

    bent = [n for n in napok if elso_nap is None or n > elso_nap]
    kint = [n for n in napok if elso_nap is not None and n <= elso_nap]
    meresek = [m for n in bent for m in TABLAZAT[n]]
    sys_atlag = Fraction(sum(s for s, _ in meresek), len(meresek))
    dia_atlag = Fraction(sum(d for _, d in meresek), len(meresek))

    # Életkor a sorozat utolsó napján (a felülről nyitott időszak vége előtti nap).
    ref_nap = (ig - timedelta(milliseconds=1)).date()
    kor = eletkor(p["birth_date"], ref_nap)
    cel_sys, cel_dia = p["target_over"] if kor >= p["age_threshold"] else p["target_under"]

    if p["rounding"] is None:
        cmp_sys, cmp_dia = sys_atlag, dia_atlag
    else:
        cmp_sys, cmp_dia = kerekit(sys_atlag, p["rounding"]), kerekit(dia_atlag, p["rounding"])

    sys_alatta, dia_alatta = cmp_sys < cel_sys, cmp_dia < cel_dia
    eleg = len(bent) >= p["min_days"]
    if not eleg:
        cel = None
    elif p["both_below"]:
        cel = sys_alatta and dia_alatta
    else:
        cel = sys_alatta or dia_alatta

    return {
        "excludedFirstDay": elso_nap.isoformat() if elso_nap else None,
        "excludedReadingCount": sum(len(TABLAZAT[n]) for n in kint),
        "includedReadingCount": len(meresek),
        "includedDays": [n.isoformat() for n in bent],
        "includedDayCount": len(bent),
        "enoughData": eleg,
        "meanSystolic": sys_atlag,
        "meanDiastolic": dia_atlag,
        "comparedSystolic": cmp_sys,
        "comparedDiastolic": cmp_dia,
        "ageInYears": kor,
        "targetSystolic": cel_sys,
        "targetDiastolic": cel_dia,
        "systolicBelowTarget": sys_alatta,
        "diastolicBelowTarget": dia_alatta,
        "targetMet": cel,
    }


def egyezik(vart, kapott) -> bool:
    if isinstance(vart, Fraction):
        # A motor JS-számot (64 bites lebegőpontos) ad; ennél pontosabb egyezés nem várható.
        return isinstance(kapott, (int, float)) and abs(Fraction(kapott) - vart) < Fraction(1, 10**9)
    return vart == kapott


def kiir(x) -> str:
    if isinstance(x, Fraction):
        return f"{x.numerator}/{x.denominator} = {float(x):.6f}" if x.denominator != 1 else str(x.numerator)
    return json.dumps(x, ensure_ascii=False)


def csomag_ellenorzes() -> tuple[list[str], dict[str, date]]:
    """A FHIR-csomag mérései egyeznek-e a táblázattal (helyi nap, érték, egység).

    Visszaadja a mérésazonosító -> helyi nap megfeleltetést is (a csomag sorrendjében).
    """
    hibak = []
    csomag = json.loads(CSOMAG.read_text(encoding="utf-8"))
    napi: dict[date, list[tuple[int, int]]] = {}
    id_nap: dict[str, date] = {}
    for b in csomag["entry"]:
        r = b["resource"]
        if r["resourceType"] != "Observation":
            continue
        ido = datetime.fromisoformat(r["effectiveDateTime"])
        if ido.utcoffset() is None:
            hibak.append(f"{r['id']}: időzóna nélküli időpont")
        ertek = {}
        for c in r["component"]:
            kod = c["code"]["coding"][0]["code"]
            q = c["valueQuantity"]
            if q.get("system") != "http://unitsofmeasure.org" or q.get("code") != "mm[Hg]":
                hibak.append(f"{r['id']}: nem mm[Hg] egység")
            ertek[kod] = q["value"]
        napi.setdefault(ido.date(), []).append((ertek["8480-6"], ertek["8462-4"]))
        id_nap[r["id"]] = ido.date()  # a tárolt eltolás szerinti (helyi) nap
    if {k: sorted(v) for k, v in napi.items()} != {k: sorted(v) for k, v in TABLAZAT.items()}:
        hibak.append("a csomag mérései nem egyeznek a 3.5-ös táblázattal")
    return hibak, id_nap


def main() -> int:
    # Windows-konzolon (cp1250) is olvasható legyen a kimenet.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    hibak, id_nap = csomag_ellenorzes()
    print("A FHIR-csomag és a 3.5-ös táblázat:", "egyezik" if not hibak else "ELTÉR")
    for h in hibak:
        print("   ", h)

    motor = {f["id"]: f for f in json.loads(EREDMENY.read_text(encoding="utf-8"))["forgatokonyvek"]}
    if set(motor) != set(FORGATOKONYVEK):
        hibak.append(f"a forgatókönyvek listája eltér: {sorted(set(motor) ^ set(FORGATOKONYVEK))}")

    for fid, valtozas in FORGATOKONYVEK.items():
        vart = szamol({**ALAP, **valtozas})
        kapott = motor[fid]["eredmeny"]
        kapott = {**kapott, "excludedReadingCount": len(kapott["excludedReadingIds"])}
        # A magyarázat azonosítói: a csomagból, a helyi nap szerint, a csomag sorrendjében.
        vart["includedReadingIds"] = [i for i, n in id_nap.items() if n.isoformat() in vart["includedDays"]]
        vart["excludedReadingIds"] = [i for i, n in id_nap.items() if n.isoformat() not in vart["includedDays"]]
        elteres = [k for k in vart if not egyezik(vart[k], kapott.get(k))]
        print(f"\n{fid}: {'EGYEZIK' if not elteres else 'ELTÉR'}")
        print(f"    átlag (kézi, pontos tört): {kiir(vart['meanSystolic'])} / {kiir(vart['meanDiastolic'])}")
        print(f"    átlag (motor):             {kapott['meanSystolic']} / {kapott['meanDiastolic']}")
        print(f"    azonosítók: {len(vart['includedReadingIds'])} figyelembe vett, "
              f"{len(vart['excludedReadingIds'])} kizárt — egyezik a motoréval: "
              f"{'igen' if 'includedReadingIds' not in elteres and 'excludedReadingIds' not in elteres else 'NEM'}")
        print(f"    n={vart['includedReadingCount']}, napok={vart['includedDayCount']}, "
              f"cél={kiir(vart['targetSystolic'])}/{kiir(vart['targetDiastolic'])}, "
              f"targetMet: kézi={kiir(vart['targetMet'])}, motor={kiir(kapott['targetMet'])}")
        for k in elteres:
            hibak.append(f"{fid}.{k}: kézi={kiir(vart[k])}, motor={kiir(kapott.get(k))}")
            print(f"    ELTÉRÉS {k}: kézi={kiir(vart[k])}, motor={kiir(kapott.get(k))}")

    print("\nÖsszesen:", "minden egyezik" if not hibak else f"{len(hibak)} eltérés")
    return 0 if not hibak else 1


if __name__ == "__main__":
    sys.exit(main())
