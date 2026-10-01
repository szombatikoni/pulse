# PULSE_M1.html -> PULSE_M1.docx + PULSE_M1.pdf a telepített Word-del (COM).
# Futtatás a repo gyökeréből: powershell -ExecutionPolicy Bypass -File docs/M1/tools/html2docx.ps1
$root = Resolve-Path (Join-Path $PSScriptRoot "..\..\..")
$html = Join-Path $root "docs\M1\PULSE_M1.html"
$docx = Join-Path $root "docs\M1\PULSE_M1.docx"
$pdf  = Join-Path $root "docs\M1\PULSE_M1.pdf"

$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
try {
    $doc = $word.Documents.Open([string]$html, $false, $true)   # ReadOnly
    # A4, 2 cm margók
    $ps = $doc.PageSetup
    $ps.PaperSize = 7          # wdPaperA4
    $ps.TopMargin = 56.7; $ps.BottomMargin = 56.7; $ps.LeftMargin = 56.7; $ps.RightMargin = 56.7
    $maxW = $ps.PageWidth - $ps.LeftMargin - $ps.RightMargin
    $maxH = $ps.PageHeight - $ps.TopMargin - $ps.BottomMargin - 90   # hely a címnek + képaláírásnak
    # Képek beágyazása (a HTML-ből csatolt képként jönnek), szövegtükörre méretezve
    foreach ($s in @($doc.InlineShapes)) {
        if ($s.LinkFormat -ne $null) {
            $s.LinkFormat.SavePictureWithDocument = $true
            $s.LinkFormat.BreakLink()
        }
        $s.LockAspectRatio = -1
        if ($s.Width -gt $maxW) { $s.Width = $maxW }
        if ($s.Height -gt $maxH) { $s.Height = $maxH }
    }
    # Képaláírás maradjon az ábrával
    foreach ($p in $doc.Paragraphs) {
        if ($p.Range.InlineShapes.Count -gt 0) { $p.KeepWithNext = -1 }
    }
    # Az E-K diagram (1. ábra) külön, fekvő oldalra
    $er = $null
    foreach ($p in $doc.Paragraphs) {
        if ($p.Range.InlineShapes.Count -gt 0 -and $p.Next(1).Range.Text -like "1. *bra: A PULSE adatmodellje*") { $er = $p; break }
    }
    if ($er -ne $null) {
        $cap = $er.Next(1)
        $r = $cap.Range; $r.MoveEnd(1, -1) | Out-Null; $r.Collapse(0); $r.InsertBreak(2)   # szakasztörés a képaláírás végén
        $r = $er.Range; $r.Collapse(1); $r.InsertBreak(2)                                  # ... és az ábra előtt
        $sec = $doc.Sections | Where-Object { $_.Range.InlineShapes.Count -gt 0 -and $_.Range.Text -like "*1. *bra: A PULSE adatmodellje*" } | Select-Object -First 1
        if ($sec -eq $null) { throw "Az E-K diagram szakasza nem talalhato" }
        $sec.PageSetup.Orientation = 1             # wdOrientLandscape
        # a törés után maradó üres bekezdés minimális, a fejezetcím ne kérjen még egy oldaltörést
        $nx = $doc.Sections.Item($sec.Index + 1).Range.Paragraphs
        $nx.Item(1).Range.Font.Size = 1; $nx.Item(1).SpaceAfter = 0; $nx.Item(1).SpaceBefore = 0
        $nx.Item(2).PageBreakBefore = 0
        $sec.PageSetup.TopMargin = 42.5; $sec.PageSetup.BottomMargin = 42.5
        $sec.PageSetup.LeftMargin = 42.5; $sec.PageSetup.RightMargin = 42.5
        $img = $sec.Range.InlineShapes.Item(1)
        $img.LockAspectRatio = -1
        $img.Width = $sec.PageSetup.PageWidth - 85
        $lh = $sec.PageSetup.PageHeight - 85 - 40
        if ($img.Height -gt $lh) { $img.Height = $lh }
    }
    # Táblázatok: a fejléc ne szakadjon el a soroktól, a rövid bevezető sor maradjon a táblázattal
    foreach ($t in @($doc.Tables)) {
        $t.Rows.Item(1).HeadingFormat = -1
        $t.Rows.AllowBreakAcrossPages = 0
        $t.Rows.Item(1).Range.ParagraphFormat.KeepWithNext = -1
        if ($t.Rows.Count -le 8) {   # rövid táblázat: egyben marad, a bevezető sorral együtt
            for ($k = 2; $k -lt $t.Rows.Count; $k++) { $t.Rows.Item($k).Range.ParagraphFormat.KeepWithNext = -1 }
            $prev = $t.Range.Paragraphs.Item(1).Previous(1)
            if ($prev -ne $null -and $prev.Range.Text.Length -lt 120) { $prev.KeepWithNext = -1 }
        }
    }
    $doc.SaveAs2([string]$docx, 16)   # wdFormatXMLDocument
    $doc.SaveAs2([string]$pdf, 17)    # wdFormatPDF
    $doc.Close(0)
    Write-Output "OK: $docx ; $pdf"
} finally {
    $word.Quit()
    [void][Runtime.InteropServices.Marshal]::ReleaseComObject($word)
}
