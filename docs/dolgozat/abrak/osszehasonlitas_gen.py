"""Az összehasonlító ábra (osszehasonlitas.drawio) előállítása.
A cellák bizonyítéka: docs/files/kutatas/osszehasonlitas_bizonyitek.md.
Futtatás: python docs/dolgozat/abrak/osszehasonlitas_gen.py, majd draw.io-export."""
from pathlib import Path
from xml.sax.saxutils import escape

Y = '<span style="color:#2E7D32;font-size:15px;">&#10004;</span>'
P = '<span style="color:#C77700;font-size:15px;">&#9680;</span>'
N = '<span style="color:#C62828;font-size:15px;">&#10008;</span>'
D = '<span style="color:#9AA0A6;font-size:15px;">&ndash;</span>'


def c(sym, note=""):
    n = f'<br><span style="font-size:10px;color:#555;">{note}</span>' if note else ""
    return sym + n


def t(text):
    return f'<span style="font-size:11px;">{text}</span>'


COLS = ["SmartBP", "mySugr", "Tidepool", "Huma", "PULSE*"]
ROWS = [
    ("Betegoldali webes felület", [c(D, "alkalmazásboltban"), c(D), c(P, "web, de adat csak<br>eszközről"), c(D, "betegalkalmazás"), c(Y)]),
    ("Kézi mérésrögzítés", [c(Y), c(Y), c(N, "a weben nincs"), c(D), c(Y)]),
    ("Több paraméter", [c(P, "vérnyomás-központú"), c(P, "vércukor-központú;<br>vérnyomás is rögzíthető"), c(N, "csak diabétesz"), c(Y, "vitális jelek"), c(Y, "vérnyomás, vércukor,<br>pulzus, testsúly")]),
    ("Állapotkérdőív", [c(D), c(D), c(D), c(Y), c(Y, "verziózott")]),
    ("Orvosi felület", [c(Y, "web, 2026-tól"), c(P, "riport (PDF: előfizetés)"), c(Y), c(Y), c(Y)]),
    ("Orvos által beállított szabály", [c(D), c(D), c(P, "előre beállított célok"), c(Y, "küszöb"), c(Y, "négy szabálytípus")]),
    ("Priorizált beteglista", [c(D), c(D), c(Y, "Tidepool+"), c(Y), c(Y)]),
    ("Adathiány jelzése", [c(D), c(D), c(P, "alacsony viselési idő"), c(D), c(Y, "önálló státusz")]),
    ("Magyarázott, verziózott riasztás", [c(D), c(D), c(D), c(D), c(Y)]),
    ("Hozzáférés", [t("ingyenes,<br>előfizetéssel"), t("ingyenes, előfizetéssel;<br>országonként"), t("250 betegig<br>ingyenes"), t("intézményi,<br>kérésre"), t("demonstrációs")]),
]

H = "#2C4A6E"
TD = 'style="border:1px solid #C9D1DC;padding:5px 8px;text-align:center;vertical-align:middle;'
TH = f'style="border:1px solid {H};padding:6px 8px;background:{H};color:#fff;font-weight:bold;text-align:center;'

h = '<table style="border-collapse:collapse;font-family:Times New Roman;font-size:13px;">'
h += f"<tr><th {TH}\"></th>" + "".join(
    f'<th {TH}{"background:#1F3550;" if x.startswith("PULSE") else ""}">{x}</th>' for x in COLS) + "</tr>"
for i, (name, cells) in enumerate(ROWS):
    bg = "#FFFFFF" if i % 2 == 0 else "#F6F8FB"
    h += f'<tr><td {TD}text-align:left;background:#E8EDF3;font-weight:bold;width:150px;">{name}</td>' + "".join(
        f'<td {TD}background:{"#EEF3EA" if j == 4 else bg};width:118px;">{v}</td>' for j, v in enumerate(cells)) + "</tr>"
h += "</table>"
leg = (f'<div style="font-family:Times New Roman;font-size:12px;text-align:left;">{Y} megvan &nbsp;&nbsp; {P} részben &nbsp;&nbsp; '
       f'{N} nincs (dokumentáció vagy saját kipróbálás szerint) &nbsp;&nbsp; {D} a nyilvános leírásban nem szerepel'
       '<br><span style="font-size:11px;color:#555;">* A PULSE oszlop a tervezett rendszert mutatja; a megvalósítás állapotát '
       'a Funkcionális specifikáció táblázata adja meg.</span></div>')


def q(v):
    return escape(v, {'"': "&quot;"})


cells = [
    f'<mxCell id="t" value="{q(h)}" style="text;html=1;whiteSpace=nowrap;overflow=visible;align=left;verticalAlign=top;" vertex="1" parent="1"><mxGeometry x="0" y="0" width="690" height="500" as="geometry"/></mxCell>',
    f'<mxCell id="l" value="{q(leg)}" style="text;html=1;whiteSpace=wrap;align=left;verticalAlign=top;" vertex="1" parent="1"><mxGeometry x="0" y="505" width="690" height="50" as="geometry"/></mxCell>',
]
xml = ('<mxfile host="app.diagrams.net"><diagram name="Összehasonlítás" id="cmp"><mxGraphModel grid="0" page="0"><root>'
       '<mxCell id="0"/><mxCell id="1" parent="0"/>' + "".join(cells) + "</root></mxGraphModel></diagram></mxfile>")
Path(__file__).with_name("osszehasonlitas.drawio").write_text(xml, encoding="utf-8")
