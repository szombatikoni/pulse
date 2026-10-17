"""A szakdolgozat Word- és PDF-változatának előállítása a docs/dolgozat
markdown-fejezeteiből.

Használat (a repo gyökeréből):
    python docs/dolgozat/tools/build_dolgozat.py --vazlat   # átnézésre: minden fejezet
    powershell -ExecutionPolicy Bypass -File docs/dolgozat/tools/docx2pdf.ps1

    python docs/dolgozat/tools/build_dolgozat.py            # leadásra: csak a kész fejezetek
    powershell -ExecutionPolicy Bypass -File docs/dolgozat/tools/docx2pdf.ps1 -Pdf

A forrás a markdown; a docx-ben tett javítások (változáskövetés, megjegyzések)
a markdownba átvezetve maradnak meg, a következő generálás a docx-et felülírja.

Jelölések a fejezetekben:
    # Cím {-}                     számozatlan fejezet (előlapok, Motiváció stb.)
    ![Aláírás](kep.png){#abra:kulcs}  ábra; hivatkozás rá a szövegben: @abra:kulcs
    [@kulcs]                      forráshivatkozás (forrasok.md); sorszáma az
                                  első előfordulás sorrendjében alakul
    {{include utvonal}}           másik markdown-fájl törzse (pl. a feladatkiírás)
    {{oldaltores}}  {{tartalomjegyzek}}  {{irodalomjegyzek}}
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
D = ROOT / "docs" / "dolgozat"
BUILD = D / "build"

# (fájl, kész-e) — a kész fejezetek kerülnek a leadott változatba
# (2026-10-17: az M2-höz elkészült fejezetek; a többi még csak címsor)
FEJEZETEK = [
    ("00_elolapok.md", True),
    ("01_motivacio.md", True),
    ("02_teruleti_attekintes.md", True),
    ("03_funkcionalis_specifikacio.md", True),
    ("04_technologiak.md", False),
    ("05_architektura.md", True),
    ("06_adatmodell.md", True),
    ("07_mukodes.md", True),
    ("08_biztonsag.md", False),
    ("09_kodreszletek.md", False),
    ("10_teszteles.md", False),
    ("11_kiertekeles.md", False),
    ("12_devops.md", False),
    ("13_ai_hasznalat.md", True),
    ("14_tapasztalatok.md", False),
    ("99_zarolapok.md", True),
]

OLDALTORES = '```{=openxml}\n<w:p><w:r><w:br w:type="page"/></w:r></w:p>\n```'
TOC_JEL = "PULSE_TARTALOMJEGYZEK_HELYE"


def include(m):
    t = (ROOT / m.group(1).strip()).read_text(encoding="utf-8-sig")
    # a forrásfájl főcíme és **Kulcs:** fejlécsorai nem kellenek
    sorok = [s for s in t.splitlines() if not s.startswith("# ") and not s.startswith("**")]
    return "\n".join(sorok).strip()


def forrasok():
    """forrasok.md: '- kulcs: hivatkozás szövege' sorok."""
    f = {}
    for s in (D / "forrasok.md").read_text(encoding="utf-8-sig").splitlines():
        m = re.match(r"^- ([\w:-]+): (.+)$", s)
        if m:
            f[m.group(1)] = m.group(2).strip()
    return f


def main(vazlat):
    szoveg = []
    for nev, kesz in FEJEZETEK:
        if kesz or vazlat:
            szoveg.append((D / nev).read_text(encoding="utf-8-sig"))
    t = "\n\n".join(szoveg)
    t = re.sub(r"\{\{include ([^}]+)\}\}", include, t)
    if not vazlat:
        # A „> **Jóváhagyandó…**" blokkok belső jegyzetek, a leadott változatba nem kellenek.
        t = re.sub(r"(?m)^> \*\*Jóváhagyandó.*\n(?:>.*\n)*\n?", "", t)

    # Fejezet- és ábraszámozás; a kódblokkok érintetlenek
    out, h1, h2, h3, abra = [], 0, 0, 0, 0
    abrak = {}
    kodban = False
    for s in t.splitlines():
        if s.startswith("```"):
            kodban = not kodban
        if kodban:
            out.append(s); continue
        m = re.match(r"^(#{1,3}) (.+?)\s*(\{-\})?\s*$", s)
        if m:
            szint, cim, szamozatlan = len(m.group(1)), m.group(2), m.group(3)
            if szamozatlan:
                out.append(f"{m.group(1)} {cim} {{-}}"); continue
            if szint == 1:
                h1 += 1; h2 = h3 = abra = 0; szam = f"{h1}."
            elif szint == 2:
                h2 += 1; h3 = 0; szam = f"{h1}.{h2}."
            else:
                h3 += 1; szam = f"{h1}.{h2}.{h3}."
            out.append(f"{m.group(1)} {szam} {cim} {{-}}"); continue
        m = re.match(r"^!\[(.*)\]\((.+?)\)(\{#(abra:[\w-]+)\})?\s*$", s)
        if m:
            abra += 1
            szam = f"{h1}.{abra}." if h1 else f"{abra}."
            if m.group(4):
                abrak[m.group(4)] = szam
            out.append(f"![{szam} ábra – {m.group(1)}]({m.group(2)})"); continue
        out.append(s)
    t = "\n".join(out)
    # Ábrahivatkozás: „A @abra:x mutatja" -> „Az 1.1. ábra mutatja"; a névelő a
    # számtól függ (az 1., az 5., de a 2., a 10.), ezért a generálás állítja be.
    def abra_hiv(m):
        szam = abrak.get(m.group(2), f"[??{m.group(2)}]")
        nevelo = m.group(1)
        if nevelo:
            elso = int(re.match(r"\d+", szam).group()) if szam[0].isdigit() else 0
            uj = "az" if elso in (1, 5) else "a"
            nevelo = (uj.capitalize() if nevelo[0].isupper() else uj) + " "
        return f"{nevelo or ''}{szam} ábra"
    t = re.sub(r"(\b[Aa]z? )?@(abra:[\w-]+)", abra_hiv, t)

    # Forráshivatkozások: [@a] vagy [@a; @b] -> [1] / [1, 2]
    f, sorrend = forrasok(), []

    def hiv(m):
        szamok = []
        for k in re.findall(r"@([\w:-]+)", m.group(1)):
            if k not in f:
                sys.exit(f"Ismeretlen forrás: {k} (forrasok.md)")
            if k not in sorrend:
                sorrend.append(k)
            szamok.append(str(sorrend.index(k) + 1))
        return "[" + ", ".join(szamok) + "]"
    t = re.sub(r"\[(@[\w:-]+(?:;\s*@[\w:-]+)*)\]", hiv, t)
    irodalom = "\n".join(f"{i}. {f[k]}" for i, k in enumerate(sorrend, 1)) or "*(Még nincs hivatkozott forrás.)*"
    t = t.replace("{{irodalomjegyzek}}", irodalom)
    t = t.replace("{{oldaltores}}", OLDALTORES)
    t = t.replace("{{tartalomjegyzek}}", TOC_JEL)

    BUILD.mkdir(exist_ok=True)
    md = BUILD / "PULSE_szakdolgozat.md"
    md.write_text(t, encoding="utf-8")
    docx = BUILD / "PULSE_szakdolgozat.docx"
    subprocess.run(["pandoc", str(md), "-f", "markdown-auto_identifiers", "-o", str(docx),
                    "--reference-doc", str(D / "sablon" / "reference.docx"),
                    "--resource-path", str(ROOT)], check=True)
    print("written", docx, f"({len(sorrend)} forrás, {sum(1 for _ in abrak)} hivatkozott ábra)")


if __name__ == "__main__":
    main("--vazlat" in sys.argv)
