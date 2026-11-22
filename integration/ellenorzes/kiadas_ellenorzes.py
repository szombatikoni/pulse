"""A FHIR-kiadás független ellenőrzése az ADATBÁZIS soraiból (M3, K1).

A szkript nem használja sem a PULSE kiadó kódját, sem a kiadott csomagot: a
beteg sorait nyers SQL-lel olvassa ki, és ezekből számolja a várt értékeket.
Ezt veti össze azzal, amit a motor a csomagból beolvasott és kiszámolt
(eredmeny/kiadas_feldolgozas.json, a kiadas_feldolgozas.mjs kimenete):

  1. Observation: mérésenként a LOINC-kód, az értékek, a UCUM-egységkódok, a
     mérés és a rögzítés ideje (helyi eltolással, ezredmásodpercig) és a helyi
     nap; nincs hiányzó és nincs fölös mérés. A felülírt (javított) mérés nem
     várt: a kiadás csak a javítási lánc végét adja ki (M3, A7, D6a);
  2. QuestionnaireResponse: a kitöltéskori verzióra hivatkozik-e, a kitöltés
     ideje és a válaszok; Questionnaire: a hivatkozott verziók kérdései és
     válaszlehetőségei;
  3. a NICE-szabály (M2) eredménye a kiadott csomagon: a kizárt első nap, a
     figyelembe vett mérések azonosítói, az átlagok (pontos törtekkel), az
     életkor és a célérték.

A helyi időt és a helyi napot a PostgreSQL számolja a saját időzóna-adatbázisával
(SET TIME ZONE, to_char, AT TIME ZONE), nem a Python zoneinfo, amellyel a kiadó
dolgozik; így a két oldal nem ugyanazzal a kóddal hibázhat. Az időpontot a
pillanat (epoch) szerint is összeveti.

Futtatás az integration/ mappából (psycopg kell, ezért a backend környezetével):
    uv run --project ../backend python -I ellenorzes/kiadas_ellenorzes.py
Más beteg: --beteg varga.bela@pulse.example (alapból Szabó János).
Az adatbázis címe: PULSE_DB_URL (alapból a pulse-e2e példány, 127.0.0.1:5432/pulse).
Kilépési kód: 0 = minden egyezik, 1 = eltérés.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime
from fractions import Fraction
from pathlib import Path

import psycopg

GYOKER = Path(__file__).resolve().parent.parent
EREDMENY = GYOKER / "eredmeny" / "kiadas_feldolgozas.json"
IDOZONA = "Europe/Budapest"
UCUM = "http://unitsofmeasure.org"
KERDOIV_URL = "https://example.org/pulse/fhir/Questionnaire/"

# A NICE-szabály alapértékei (integration/cql/PulseHbpmAverage.cql).
MIN_NAP = 3
KORHATAR = 80
CEL_ALATTA = (Fraction(135), Fraction(85))
CEL_FELETTE = (Fraction(145), Fraction(85))

# A helyi idő a PostgreSQL-ből: másodpercig, mikroszekundum, eltolás, helyi nap, pillanat.
IDO_SQL = """
    to_char({o}, 'YYYY-MM-DD"T"HH24:MI:SS'), to_char({o}, 'US')::int,
    to_char({o}, 'TZH:TZM'), ({o} AT TIME ZONE '{tz}')::date, extract(epoch FROM {o})
"""


def ido(sor: tuple) -> dict:
    """A várt motoroldali alak: tört másodperc csak akkor, ha van, és legfeljebb
    ezredmásodpercig (a kiadás és a CQL DateTime pontossága)."""
    masodpercig, us, eltolas, nap, epoch = sor
    tort = f".{us // 1000:03d}" if us else ""
    ora, perc = eltolas.split(":")
    return {
        "ertek": f"{masodpercig}{tort}{eltolas}",
        "eltolasOra": int(ora) + (1 if ora.startswith("+") else -1) * int(perc) / 60,
        "helyiNap": nap.isoformat(),
        "epoch": Fraction(str(epoch)),
    }


def ido_sql(oszlop: str) -> str:
    return IDO_SQL.format(o=oszlop, tz=IDOZONA)


def adatbazis(conn: psycopg.Connection, email: str) -> dict:
    """A beteg sorai az adatbázisból, a kiadótól függetlenül."""
    with conn.cursor() as cur:
        cur.execute(f"SET TIME ZONE '{IDOZONA}'")
        cur.execute(
            "SELECT p.id::text, p.birth_date FROM patient_profiles p"
            " JOIN users u ON u.id = p.user_id WHERE u.email = %s",
            (email,),
        )
        talalat = cur.fetchone()
        if talalat is None:
            raise SystemExit(f"Nincs ilyen beteg az adatbázisban: {email}")
        beteg_id, szuletes = talalat

        cur.execute(
            f"""SELECT m.id::text, t.loinc_code,
                       (SELECT count(*) FROM measurement_components k WHERE k.type_id = t.id),
                       c.loinc_code, c.unit, c.code, v.value,
                       {ido_sql("m.measured_at")}, {ido_sql("m.recorded_at")}
                FROM measurements m
                JOIN measurement_types t ON t.id = m.type_id
                JOIN measurement_values v ON v.measurement_id = m.id
                JOIN measurement_components c ON c.id = v.component_id
                WHERE m.patient_id = %s
                  -- A felülírt (javított) mérés nem kerül a kiadásba (A7, D6a):
                  -- csak a javítási lánc vége.
                  AND NOT EXISTS (SELECT 1 FROM measurements j WHERE j.corrected_from = m.id)
                ORDER BY m.measured_at, m.id, c.order_no""",
            (beteg_id,),
        )
        meresek: dict[str, dict] = {}
        for sor in cur.fetchall():
            mid, tipus_loinc, komp_db, komp_loinc, egyseg, komp_kod, ertek = sor[:7]
            m = meresek.setdefault(
                mid,
                {
                    "kod": tipus_loinc,
                    "effective": ido(sor[7:12]),
                    "issued": ido(sor[12:17]),
                    "ertekek": [],
                    "komponens": {},
                },
            )
            # Egyértékű mérésnél az érték az Observationé, a kódja a méréstípusé.
            kod = komp_loinc if komp_db > 1 else tipus_loinc
            m["ertekek"].append({"kod": kod, "ertek": ertek, "egysegKod": egyseg})
            m["komponens"][komp_kod] = (ertek, egyseg)

        cur.execute(
            f"""SELECT s.id::text, t.code, v.version_no, v.id::text, {ido_sql("s.submitted_at")}
                FROM submissions s
                JOIN questionnaire_versions v ON v.id = s.version_id
                JOIN questionnaire_templates t ON t.id = v.template_id
                WHERE s.patient_id = %s ORDER BY s.submitted_at, s.id""",
            (beteg_id,),
        )
        kitoltesek = {
            sid: {"kerdoiv": f"{KERDOIV_URL}{kod}|{szam}", "verzio_id": vid, "authored": ido(sor)}
            for sid, kod, szam, vid, *sor in cur.fetchall()
        }
        cur.execute(
            """SELECT a.submission_id::text, a.question_id::text, a.value
               FROM answers a JOIN questions q ON q.id = a.question_id
               WHERE a.submission_id = ANY(%s::uuid[]) ORDER BY q.order_no""",
            (list(kitoltesek),),
        )
        for sid, kerdes, valasz in cur.fetchall():
            ertekek = valasz if isinstance(valasz, list) else [valasz]
            kitoltesek[sid].setdefault("valaszok", []).append(
                {"linkId": kerdes, "kodok": [str(x) for x in ertekek]}
            )

        verziok = sorted({k["verzio_id"] for k in kitoltesek.values()})
        cur.execute(
            """SELECT q.version_id::text, q.id::text, q.options_scores FROM questions q
               WHERE q.version_id = ANY(%s::uuid[]) ORDER BY q.version_id, q.order_no""",
            (verziok,),
        )
        kerdoivek: dict[str, list] = {v: [] for v in verziok}
        for vid, qid, lehetosegek in cur.fetchall():
            kerdoivek[vid].append(
                {"linkId": qid, "valaszlehetosegek": [o["value"] for o in lehetosegek]}
            )

    return {
        "beteg": {"id": beteg_id, "szuletesiDatum": szuletes.isoformat()},
        "meresek": meresek,
        "kitoltesek": kitoltesek,
        "kerdoivek": kerdoivek,
    }


def ido_egyezik(vart: dict, kapott: dict | None) -> list[str]:
    if kapott is None:
        return ["hiányzik"]
    hibak = []
    for kulcs in ("ertek", "helyiNap"):
        if vart[kulcs] != kapott[kulcs]:
            hibak.append(f"{kulcs}: adatbázis={vart[kulcs]}, motor={kapott[kulcs]}")
    if vart["eltolasOra"] != kapott["eltolasOra"]:
        hibak.append(f"eltolás: adatbázis={vart['eltolasOra']}, motor={kapott['eltolasOra']}")
    # Ugyanaz a pillanat (ezredmásodpercig, a kiadás pontossága).
    pillanat = Fraction(str(datetime.fromisoformat(kapott["ertek"]).timestamp()))
    if abs(pillanat - vart["epoch"]) >= Fraction(1, 1000):
        hibak.append(f"pillanat: adatbázis={float(vart['epoch'])}, motor={float(pillanat)}")
    return hibak


def observation_ellenorzes(db: dict, motor: dict) -> tuple[list[str], dict]:
    hibak = []
    kapott = {o["id"]: o for o in motor["observation"]}
    if set(kapott) != set(db["meresek"]):
        csak_db = sorted(set(db["meresek"]) - set(kapott))
        csak_motor = sorted(set(kapott) - set(db["meresek"]))
        hibak.append(f"a mérések halmaza eltér: adatbázis {csak_db}, motor {csak_motor}")
    statisztika = {"mérés": 0, "érték": 0, "eltolás": set()}
    for mid, vart in db["meresek"].items():
        o = kapott.get(mid)
        if o is None:
            continue
        statisztika["mérés"] += 1
        if o["statusz"] != "final":
            hibak.append(f"{mid}: státusz {o['statusz']}")
        if o["kod"] != vart["kod"]:
            hibak.append(f"{mid}: kód adatbázis={vart['kod']}, motor={o['kod']}")
        motor_ertekek = [{k: e[k] for k in ("kod", "ertek", "egysegKod")} for e in o["ertekek"]]
        if motor_ertekek != vart["ertekek"]:
            hibak.append(f"{mid}: értékek adatbázis={vart['ertekek']}, motor={motor_ertekek}")
        if any(e["rendszer"] != UCUM for e in o["ertekek"]):
            hibak.append(f"{mid}: nem UCUM-egységrendszer")
        statisztika["érték"] += len(o["ertekek"])
        for mezo in ("effective", "issued"):
            hibak += [f"{mid}.{mezo}: {h}" for h in ido_egyezik(vart[mezo], o[mezo])]
        statisztika["eltolás"].add(vart["effective"]["ertek"][-6:])
    return hibak, statisztika


def kerdoiv_ellenorzes(db: dict, motor: dict) -> list[str]:
    hibak = []
    kapott = {r["id"]: r for r in motor["questionnaireResponse"]}
    if set(kapott) != set(db["kitoltesek"]):
        hibak.append("a kitöltések halmaza eltér")
    for sid, vart in db["kitoltesek"].items():
        r = kapott.get(sid)
        if r is None:
            continue
        if r["kerdoiv"] != vart["kerdoiv"]:
            hibak.append(f"{sid}: verzió adatbázis={vart['kerdoiv']}, motor={r['kerdoiv']}")
        if r["statusz"] != "completed":
            hibak.append(f"{sid}: státusz {r['statusz']}")
        hibak += [f"{sid}.authored: {h}" for h in ido_egyezik(vart["authored"], r["authored"])]
        if r["valaszok"] != vart.get("valaszok", []):
            hibak.append(f"{sid}: válaszok adatbázis={vart.get('valaszok')}, motor={r['valaszok']}")

    kerdoivek = {q["id"]: q for q in motor["questionnaire"]}
    if set(kerdoivek) != set(db["kerdoivek"]):
        hibak.append("a kérdőívverziók halmaza eltér (csak a kitöltések által hivatkozottak)")
    for vid, kerdesek in db["kerdoivek"].items():
        if vid in kerdoivek and kerdoivek[vid]["kerdesek"] != kerdesek:
            hibak.append(f"Questionnaire/{vid}: a kérdések vagy a válaszlehetőségek eltérnek")
    # A hivatkozott verziószám a motor által beolvasott Questionnaire-é is.
    for r in kapott.values():
        url, verzio = r["kerdoiv"].rsplit("|", 1)
        if not any(q["url"] == url and q["verzio"] == verzio for q in kerdoivek.values()):
            hibak.append(f"{r['id']}: a hivatkozott verzió ({r['kerdoiv']}) nincs a csomagban")
    return hibak


def eletkor(szuletes: date, nap: date) -> int:
    return nap.year - szuletes.year - ((nap.month, nap.day) < (szuletes.month, szuletes.day))


def nice_ellenorzes(db: dict, motor_kimenet: dict) -> tuple[list[str], dict | None]:
    """Az M2-es kézi számítás logikája (első nap kiesik, a többi leolvasás
    egyszerű átlaga) az adatbázis vérnyomás-soraiból, a helyi nap szerint.
    Ha legfeljebb egy napról van vérnyomás, None (a rész kimarad)."""
    vernyomas = [
        (mid, m["effective"]["helyiNap"], m["komponens"])
        for mid, m in db["meresek"].items()
        if m["kod"] == "85354-9"
    ]
    if not vernyomas:
        return [], None
    elso = min(nap for _, nap, _ in vernyomas)
    bent = [(mid, nap, k) for mid, nap, k in vernyomas if nap > elso]
    if not bent:
        # Csak az első napról van mérés: nincs mit átlagolni, a rész kimarad.
        return [], None
    sys_atlag = sum(Fraction(k["systolic"][0]) for _, _, k in bent) / len(bent)
    dia_atlag = sum(Fraction(k["diastolic"][0]) for _, _, k in bent) / len(bent)
    napok = sorted({nap for _, nap, _ in bent})
    # A szabály a kiértékelés napján számolja az életkort (nincs Series Period).
    kiert_nap = date.fromisoformat(motor_kimenet["futtatas"]["kiertekelesIdopontja"][:10])
    kor = eletkor(date.fromisoformat(db["beteg"]["szuletesiDatum"]), kiert_nap)
    cel_sys, cel_dia = CEL_FELETTE if kor >= KORHATAR else CEL_ALATTA
    eleg = len(napok) >= MIN_NAP
    vart = {
        "excludedFirstDay": elso,
        "excludedReadingIds": sorted(mid for mid, nap, _ in vernyomas if nap <= elso),
        "includedReadingIds": sorted(mid for mid, _, _ in bent),
        "includedDays": napok,
        "meanSystolic": sys_atlag,
        "meanDiastolic": dia_atlag,
        "ageInYears": kor,
        "targetSystolic": cel_sys,
        "targetDiastolic": cel_dia,
        "targetMet": (sys_atlag < cel_sys and dia_atlag < cel_dia) if eleg else None,
    }
    e = motor_kimenet["nice"]["eredmeny"]
    kapott = {**e, "excludedReadingIds": sorted(e["excludedReadingIds"])}
    kapott["includedReadingIds"] = sorted(e["includedReadingIds"])
    hibak = []
    for k, v in vart.items():
        if isinstance(v, Fraction):
            ok = abs(Fraction(kapott[k]) - v) < Fraction(1, 10**9)
        else:
            ok = kapott.get(k) == v
        if not ok:
            hibak.append(f"NICE.{k}: adatbázis={v}, motor={kapott.get(k)}")
    return hibak, vart


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--beteg", default="szabo.janos@pulse.example", help="a beteg e-mail-címe")
    a = p.parse_args()
    url = os.environ.get("PULSE_DB_URL", "postgresql://pulse:pulse@127.0.0.1:5432/pulse")

    with psycopg.connect(url) as conn:
        db = adatbazis(conn, a.beteg)
    motor = json.loads(EREDMENY.read_text(encoding="utf-8"))
    beolvasas = motor["beolvasas"]

    hibak = []
    if beolvasas["beteg"] != db["beteg"]:
        hibak.append(f"beteg: adatbázis={db['beteg']}, motor={beolvasas['beteg']}")
    print(f"Beteg: {a.beteg} (Patient/{db['beteg']['id']}):", "egyezik" if not hibak else "ELTÉR")

    obs_hibak, stat = observation_ellenorzes(db, beolvasas)
    print(
        f"\n1. Observation: {stat['mérés']} mérés, {stat['érték']} érték "
        f"(eltolások: {', '.join(sorted(stat['eltolás']))}):",
        "EGYEZIK" if not obs_hibak else "ELTÉR",
    )
    kerdoiv_hibak = kerdoiv_ellenorzes(db, beolvasas)
    print(
        f"2. Kérdőív: {len(db['kitoltesek'])} kitöltés, {len(db['kerdoivek'])} hivatkozott verzió:",
        "EGYEZIK" if not kerdoiv_hibak else "ELTÉR",
    )
    nice_hibak, nice = nice_ellenorzes(db, motor)
    m = motor["nice"]["eredmeny"]
    if nice is None:
        print("3. NICE-szabály: kimarad (legfeljebb egy napról van vérnyomásmérés)")
    else:
        nice_kiiras(nice, nice_hibak, m)

    hibak += obs_hibak + kerdoiv_hibak + nice_hibak
    for h in hibak:
        print("    ELTÉRÉS", h)
    print("\nÖsszesen:", "minden egyezik" if not hibak else f"{len(hibak)} eltérés")
    return 0 if not hibak else 1


def nice_kiiras(nice: dict, nice_hibak: list[str], m: dict) -> None:
    print(f"3. NICE-szabály a kiadott csomagon: {'EGYEZIK' if not nice_hibak else 'ELTÉR'}")
    print(
        f"    kézi (adatbázisból): átlag {nice['meanSystolic']} / {nice['meanDiastolic']}"
        f" = {float(nice['meanSystolic']):.6f} / {float(nice['meanDiastolic']):.6f},"
        f" n={len(nice['includedReadingIds'])}, kizárt nap {nice['excludedFirstDay']}"
    )
    print(
        f"    motor:               átlag {m['meanSystolic']} / {m['meanDiastolic']},"
        f" n={m['includedReadingCount']},"
        f" targetMet: kézi={nice['targetMet']}, motor={m['targetMet']}"
    )


if __name__ == "__main__":
    sys.exit(main())
