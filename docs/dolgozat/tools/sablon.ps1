# A dolgozat Word-sablonjának (reference.docx) előállítása.
# A formázás a Nyugtafelosztó mintadolgozatot követi: Times New Roman 12 pt,
# másfeles sorköz, sorkizárt szöveg első soros behúzással, középre zárt címsorok.
# A kiinduló fájl egy pandoc által generált minta (a pandoc saját alapsablonját
# a Word COM-on át nem nyitja meg), amely minden használt stílust tartalmaz.
# Futtatás a repo gyökeréből (Word szükséges):
#   pandoc docs/dolgozat/tools/sablon_minta.md -o docs/dolgozat/sablon/alap.docx --resource-path=docs/dolgozat/tools
#   powershell -ExecutionPolicy Bypass -File docs/dolgozat/tools/sablon.ps1
$dir = Resolve-Path (Join-Path $PSScriptRoot "..\sablon")
$src = Join-Path $dir "alap.docx"
$dst = Join-Path $dir "reference.docx"

$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
try {
    # egyedi nevű ideiglenes másolatot nyitunk meg: egy korábban megszakított futás
    # után a Word ugyanazt az útvonalat rejtett figyelmeztetéssel nyitná meg
    $tmp = Join-Path $env:TEMP ("pulse_sablon_" + [guid]::NewGuid().ToString("N") + ".docx")
    Copy-Item $src $tmp
    $doc = $word.Documents.Open([string]$tmp, $false, $false, $false)

    function St($key) { try { return $doc.Styles.Item($key) } catch { return $null } }
    function Font($s, $size, $bold) {
        $s.Font.Name = "Times New Roman"; $s.Font.Size = [single]$size; $s.Font.Bold = [int]$bold
        $s.Font.Italic = 0; $s.Font.Color = 0          # wdColorAutomatic = fekete
    }
    function Custom($name, $base) {
        $s = St $name
        if ($s -eq $null) { $s = $doc.Styles.Add($name, 1) }   # wdStyleTypeParagraph
        if ($base) { $s.BaseStyle = $base }
        return $s
    }

    # Alap és folyószöveg
    $normal = St(-1)
    Font $normal 12 0
    $normal.ParagraphFormat.SpaceBefore = 0; $normal.ParagraphFormat.SpaceAfter = 0
    $normal.ParagraphFormat.LineSpacingRule = 1   # wdLineSpace1pt5
    $body = St(-67)                                # Body Text
    Font $body 12 0
    $body.ParagraphFormat.Alignment = 3            # sorkizárt
    $body.ParagraphFormat.FirstLineIndent = 35.4   # 1,25 cm
    $body.ParagraphFormat.SpaceBefore = 0; $body.ParagraphFormat.SpaceAfter = 0
    $body.ParagraphFormat.LineSpacingRule = 1
    $first = Custom "First Paragraph" $body.NameLocal
    $first.ParagraphFormat.FirstLineIndent = 0
    $nb = Custom "Behuzas nelkul" $body.NameLocal   # pl. a tartalmi összefoglaló mezői
    $nb.ParagraphFormat.FirstLineIndent = 0; $nb.ParagraphFormat.SpaceAfter = 6
    $mn = Custom "Mezonev" $body.NameLocal         # a tartalmi összefoglaló mezőnevei
    $mn.ParagraphFormat.FirstLineIndent = 0; $mn.ParagraphFormat.SpaceBefore = 6
    $mn.ParagraphFormat.KeepWithNext = -1; $mn.Font.Bold = -1
    $compact = Custom "Compact" $body.NameLocal
    $compact.ParagraphFormat.FirstLineIndent = 0; $compact.ParagraphFormat.Alignment = 0

    # Címsorok: középre zárt, félkövér; az 1. szint mindig új oldalon kezdődik
    $sizes = @{ -2 = 16; -3 = 13; -4 = 12 }
    foreach ($k in @(-2, -3, -4)) {
        $h = St($k)
        Font $h ($sizes[$k]) (-1)
        $h.ParagraphFormat.Alignment = 1
        $h.ParagraphFormat.SpaceBefore = 18; $h.ParagraphFormat.SpaceAfter = 12
        $h.ParagraphFormat.KeepWithNext = -1
        $h.ParagraphFormat.FirstLineIndent = 0
    }
    (St(-2)).ParagraphFormat.PageBreakBefore = -1
    (St(-2)).ParagraphFormat.SpaceBefore = 0

    # Ábrák és képaláírások
    foreach ($n in @("Figure", "Captioned Figure")) {
        $f = Custom $n $null
        $f.ParagraphFormat.Alignment = 1; $f.ParagraphFormat.FirstLineIndent = 0
        $f.ParagraphFormat.KeepWithNext = -1; $f.ParagraphFormat.SpaceBefore = 6
    }
    foreach ($n in @("Image Caption", "Table Caption")) {
        $c = Custom $n $null
        Font $c 11 0
        $c.ParagraphFormat.Alignment = 1; $c.ParagraphFormat.FirstLineIndent = 0
        $c.ParagraphFormat.SpaceAfter = 12
    }
    (Custom "Table Caption" $null).ParagraphFormat.KeepWithNext = -1

    # Címlap stílusai
    $cl = Custom "Cimlap" $normal.NameLocal
    Font $cl 14 (-1)
    $cl.ParagraphFormat.Alignment = 1; $cl.ParagraphFormat.FirstLineIndent = 0
    $cc = Custom "Cimlap cim" $cl.NameLocal
    Font $cc 18 (-1)
    $cc.ParagraphFormat.SpaceBefore = 96; $cc.ParagraphFormat.SpaceAfter = 48
    $cs = Custom "Cimlap kozep" $cl.NameLocal
    Font $cs 14 0
    $cv = Custom "Cimlap lab" $cs.NameLocal
    $cv.ParagraphFormat.SpaceBefore = 110

    # Tartalomjegyzék: az 1. szint nagybetűs, félkövér
    $t1 = St(-20); Font $t1 12 (-1); $t1.Font.AllCaps = -1
    foreach ($k in @(-21, -22)) { $t = St($k); Font $t 11 0 }

    # A4, 2,5 cm margók
    $ps = $doc.PageSetup
    $ps.PaperSize = 7
    $ps.TopMargin = 70.9; $ps.BottomMargin = 70.9; $ps.LeftMargin = 70.9; $ps.RightMargin = 70.9

    $doc.Content.Delete() | Out-Null   # a mintatartalom nem kell, csak a stílusok
    $doc.SaveAs2([string]$dst, 16)
    $doc.Close([ref]0); $doc = $null
    Write-Output "OK: $dst"
} finally {
    if ($doc -ne $null) { try { $doc.Close([ref]0) } catch {} }
    $word.Quit()
    [void][Runtime.InteropServices.Marshal]::ReleaseComObject($word)
}
