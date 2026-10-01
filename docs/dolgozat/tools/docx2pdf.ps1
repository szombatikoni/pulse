# A pandoc által előállított docx utófeldolgozása a telepített Word-del (COM):
# tartalomjegyzék, táblázatkeretek, oldalszám, majd mentés DOCX formában.
# PDF csak a -Pdf kapcsolóval készül (a leadott, kész változathoz).
# Futtatás a repo gyökeréből a build_dolgozat.py után:
#   powershell -ExecutionPolicy Bypass -File docs/dolgozat/tools/docx2pdf.ps1 [-Pdf]
param([switch]$Pdf)
$d = Resolve-Path (Join-Path $PSScriptRoot "..")
$src = Join-Path $d "build\PULSE_szakdolgozat.docx"
$docx = Join-Path $d "PULSE_szakdolgozat.docx"
$pdfFajl = Join-Path $d "PULSE_szakdolgozat.pdf"
$jel = "PULSE_TARTALOMJEGYZEK_HELYE"
$ujj = Join-Path $d "build\docx.sha256"   # a legutóbb generált docx ujjlenyomata

# Ha a docx-et a legutóbbi generálás óta kézzel módosították (változáskövetés,
# megjegyzések), nem írjuk felül: előbb a markdownba kell átvezetni.
if ((Test-Path $docx) -and (Test-Path $ujj)) {
    if ((Get-FileHash $docx -Algorithm SHA256).Hash -ne (Get-Content $ujj -Raw).Trim()) {
        Write-Output "MEGALLT: a $docx a legutóbbi generálás óta módosult. Előbb vezesd át a javításokat a markdownba, vagy töröld a docx-et."
        exit 2
    }
}

$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
$doc = $null
try {
    # egyedi nevű másolat: egy megszakított futás után a Word ugyanazt az
    # útvonalat rejtett figyelmeztetéssel nyitná meg
    $tmp = Join-Path $env:TEMP ("pulse_dolgozat_" + [guid]::NewGuid().ToString("N") + ".docx")
    Copy-Item $src $tmp
    $doc = $word.Documents.Open([string]$tmp, $false, $false, $false)

    # Táblázatok: vékony keret, a fejléc ismétlődik és nem szakad el; a címlap
    # kéthasábos (Készítette / Témavezető) táblázata keret nélkül marad
    foreach ($t in @($doc.Tables)) {
        if ($t.Range.Text -like "*Készítette*") {
            $t.Borders.Enable = 0
            $t.PreferredWidthType = 2; $t.PreferredWidth = 100   # teljes szélesség
            $t.Range.ParagraphFormat.SpaceAfter = 2
            continue
        }
        $t.Borders.Enable = 1
        $t.Rows.Item(1).HeadingFormat = -1
        $t.Rows.Item(1).Range.Font.Bold = -1
        $t.Rows.AllowBreakAcrossPages = 0
        $t.Rows.Item(1).Range.ParagraphFormat.KeepWithNext = -1
    }

    # Tartalomjegyzék a jelölő bekezdés helyére (1–3. szint)
    $r = $doc.Content
    if ($r.Find.Execute($jel)) {
        $p = $r.Paragraphs.Item(1).Range
        $p.Text = ""
        $doc.TablesOfContents.Add($p, $true, 1, 3) | Out-Null
    }

    # Oldalszám jobbra lent, a címlapon nincs
    $sec = $doc.Sections.Item(1)
    $sec.PageSetup.DifferentFirstPageHeaderFooter = -1
    $sec.Footers.Item(1).PageNumbers.Add(2, $false) | Out-Null   # wdAlignPageNumberRight

    $doc.Fields.Update() | Out-Null
    foreach ($toc in @($doc.TablesOfContents)) { $toc.Update() }

    $doc.SaveAs2([string]$docx, 16)
    if ($Pdf) { $doc.SaveAs2([string]$pdfFajl, 17) }
    $doc.Close([ref]0); $doc = $null
    (Get-FileHash $docx -Algorithm SHA256).Hash | Set-Content $ujj
    if ($Pdf) { Write-Output "OK: $docx ; $pdfFajl" } else { Write-Output "OK: $docx" }
} finally {
    if ($doc -ne $null) { try { $doc.Close([ref]0) } catch {} }
    $word.Quit()
    [void][Runtime.InteropServices.Marshal]::ReleaseComObject($word)
}
