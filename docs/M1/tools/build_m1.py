"""PULSE_M1.html előállítása a docs/M1 markdown-forrásaiból.

Használat (a repo gyökeréből):
    python docs/M1/tools/build_m1.py
    powershell -File docs/M1/tools/html2docx.ps1   # Word: HTML -> DOCX + PDF

A markdown-fájlok a forrás; a HTML csak köztes formátum a Word-konverzióhoz.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
M1 = ROOT / "docs" / "M1"
IMG = ROOT / "images"
OUT = M1 / "PULSE_M1.html"
DATE = "2026. szeptember 29."

fig_no = 0


def figure(name, caption):
    global fig_no
    fig_no += 1
    src = (IMG / name).as_posix()
    return (f'<p align="center"><img src="{src}"></p>\n'
            f'<p class="caption">{fig_no}. ábra: {caption}</p>\n')


def inline(t):
    t = t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", t)
    t = re.sub(r"`([^`]+)`", r"\1", t)
    t = t.replace("&lt;br/&gt;", "<br>")
    return t


def md_to_html(text, mermaid_figures=None, skip_h1=True, chapter=None):
    """Egyszerű markdown-részhalmaz -> HTML. A mermaid-blokkok helyére a
    mermaid_figures lista soron következő eleme (kész HTML) kerül."""
    mermaid_figures = list(mermaid_figures or [])
    out, lines, i = [], text.splitlines(), 0
    para = []

    def flush():
        if para:
            txt = inline(" ".join(s.strip() for s in para))
            cls = ' class="disclaimer"' if txt.startswith("A rendszer demonstrációs célú") else ""
            out.append(f"<p{cls}>" + txt + "</p>")
            para.clear()

    while i < len(lines):
        ln = lines[i]
        if ln.startswith("```"):
            flush()
            j = i + 1
            while j < len(lines) and not lines[j].startswith("```"):
                j += 1
            if ln.startswith("```mermaid") and mermaid_figures:
                out.append(mermaid_figures.pop(0))
            i = j + 1
            continue
        if ln.startswith("> "):
            flush(); i += 1; continue
        if ln.startswith("# "):
            flush()
            if not skip_h1:
                out.append("<h2>" + inline(ln[2:]) + "</h2>")
            i += 1; continue
        if ln.startswith("## "):
            flush()
            h = ln[3:]
            if chapter is not None:
                h = re.sub(r"^(\d+)\. ", lambda m: f"{chapter}.{m.group(1)}. ", h)
            out.append("<h3>" + inline(h) + "</h3>"); i += 1; continue
        if ln.startswith("### "):
            flush(); out.append("<p><b>" + inline(ln[4:]) + "</b></p>"); i += 1; continue
        if ln.startswith("|"):
            flush()
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r"-+", c) for c in cells):
                    rows.append(cells)
                i += 1
            out.append("<table>")
            for r, cells in enumerate(rows):
                tag = "th" if r == 0 else "td"
                out.append("<tr>" + "".join(f"<{tag}>{inline(c)}</{tag}>" for c in cells) + "</tr>")
            out.append("</table>")
            continue
        if ln.startswith("- "):
            flush()
            out.append("<ul>")
            while i < len(lines) and (lines[i].startswith("- ") or lines[i].startswith("  ")):
                if lines[i].startswith("- "):
                    item = [lines[i][2:]]
                    i += 1
                    while i < len(lines) and lines[i].startswith("  ") and not lines[i].startswith("  - "):
                        item.append(lines[i].strip()); i += 1
                    sub = []
                    while i < len(lines) and lines[i].startswith("  - "):
                        s = [lines[i][4:]]; i += 1
                        while i < len(lines) and lines[i].startswith("    "):
                            s.append(lines[i].strip()); i += 1
                        sub.append("<li>" + inline(" ".join(s)) + "</li>")
                    out.append("<li>" + inline(" ".join(item)) +
                               ("<ul>" + "".join(sub) + "</ul>" if sub else "") + "</li>")
                else:
                    i += 1
            out.append("</ul>")
            continue
        if ln.strip() == "":
            flush(); i += 1; continue
        para.append(ln); i += 1
    flush()
    return "\n".join(out)


def read(name):
    return (M1 / name).read_text(encoding="utf-8-sig")


CSS = """
  body { font-family: Calibri, sans-serif; font-size: 11pt; color: #222; line-height: 1.35; }
  h1 { color: #2C4A6E; font-size: 20pt; margin-bottom: 2pt; }
  h2 { page-break-before: always; page-break-after: avoid; color: #2C4A6E; font-size: 15pt; margin-top: 22pt; border-bottom: 1pt solid #2C4A6E; padding-bottom: 2pt; }
  h3 { page-break-after: avoid; color: #2C4A6E; font-size: 12pt; margin-top: 14pt; }
  .meta { color: #555; font-size: 10.5pt; margin-bottom: 16pt; }
  table { border-collapse: collapse; width: 100%; font-size: 10.5pt; margin: 8pt 0; }
  th, td { border: 1pt solid #999; padding: 4pt 7pt; text-align: left; vertical-align: top; }
  th { background: #E8EDF3; color: #2C4A6E; }
  .disclaimer { border-left: 3pt solid #2C4A6E; background: #F0F3F7; padding: 8pt 12pt; font-size: 10.5pt; margin-top: 10pt; }
  li { margin-bottom: 3pt; }
  .caption { font-size: 9.5pt; color: #555; text-align: center; margin-top: 2pt; page-break-before: avoid; }
"""

parts = []
parts.append(f"""<!doctype html>
<html lang="hu"><head><meta charset="utf-8">
<title>PULSE — M1 leadandók</title><style>{CSS}</style></head><body>
<h1>PULSE — 1. mérföldkő leadandói</h1>
<p class="meta">
PULSE – Krónikus betegkövető telemedicina platform<br>
Szombati Konrád (IJKCKR), üzemmérnök-informatikus BProf, SZTE<br>
Témavezető: Dr. Bilicki Vilmos, SZTE Informatikai Intézet<br>
{DATE} — a témavezetői visszajelzés alapján pontosított változat · Repó: github.com/szombatikoni/pulse
</p>
""")

# 1. Feladatkiírás (a fejléc-sorok kihagyva: a meta-blokkban vannak)
fk = read("01_feladatkiiras.md")
fk = "\n".join(l for l in fk.splitlines() if not l.startswith("**"))
parts.append('<h2 style="page-break-before:auto">1. Feladatkiírás</h2>\n' + md_to_html(fk))

# 2. Követelmények
parts.append("<h2>2. Követelmények</h2>\n" + md_to_html(read("02_kovetelmenyek.md")))

# 3. Adatmodell: indoklás + ábra
am = read("03_adatmodell.md")
parts.append("<h2>3. Adatmodell</h2>\n" + md_to_html(am)
             + figure("adatmodell.png", "A PULSE adatmodellje (E-K diagram, 22 entitás)"))

# 4. Működési szabályok példákon
parts.append("<h2>4. Működési szabályok példákon</h2>\n" + md_to_html(read("07_mukodesi_szabalyok.md"), chapter=4))

# 5. Folyamat- és architektúraábrák
fa = read("06_folyamatabrak.md").replace(
    "a `07_mukodesi_szabalyok.md` mutatja be.",
    "a 4. fejezet mutatja be.")
parts.append("<h2>5. Folyamat- és architektúraábrák</h2>\n" + md_to_html(fa, mermaid_figures=[
    figure("folyamat_riasztas.png", "A riasztás életútja"),
    figure("folyamat_kirendeles.png", "Egy előírás egy alkalmának életciklusa"),
    figure("statusz_elallitas.png", "A beteg-státusz előállítása"),
    figure("architektura.png", "Rendszerarchitektúra"),
]))

# 6. Képernyővázlatok
wf = [("pulse0.png", "Bejelentkezés"),
      ("pulse1.png", "Beteg — kezdőlap (esedékes teendők, grafikonok, utolsó mérések)"),
      ("pulse2.png", "Beteg — mérésrögzítés (többértékű mérés, javítás, pótolható alkalom)"),
      ("pulse3.png", "Beteg — kérdőívkitöltés (az alkalomhoz rögzített verzió)"),
      ("pulse4.png", "Orvos — priorizált beteglista (öt státusz, indoklással)"),
      ("pulse5.png", "Orvos — beteg-részletes oldal (küszöbvonalak, riasztás-magyarázat)"),
      ("pulse6.png", "Orvos — szabály-szerkesztő (verziótörténettel)"),
      ("pulse7.png", "Orvos — kérdőív-szerkesztő (pontozás iránya, kiértékelési határok)"),
      ("pulse8.png", "Orvos — riasztáslista és eseménytörténet"),
      ("pulse9.png", "Admin — felhasználók, összerendelések, méréstípusok")]
parts.append("<h2>6. Képernyővázlatok</h2>\n"
             "<p>A vázlatok a tervezett vizuális iránnyal készültek: sötét felület, piros "
             "akcentusszín. A piros mint márkaszín az interakciós elemeké (gombok, aktív menü); "
             "a beteg-státusz (Súlyos, Figyelem, Adathiány, Kezelve, Rendben) és a "
             "riasztás-súlyosság jelentéshordozó színei ettől függetlenek, és mindig ikonnal és "
             "szöveges címkével együtt jelennek meg. Minden adat kitalált, mesterséges példa.</p>\n"
             + "".join(figure(f, c) for f, c in wf))

# 7. Ütemterv
parts.append("<h2>7. Ütemterv</h2>\n" + md_to_html(read("05_utemterv.md")))
parts.append("</body></html>\n")

OUT.write_text("\n".join(parts), encoding="utf-8")
print("written", OUT, fig_no, "figures")
