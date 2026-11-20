# Kiértékelés

Ez a fejezet azt írja le, hogyan vizsgálom a kész rendszert méréssel. A
mérések a negyedik mérföldkőben készülnek, ezért itt még csak a módszer
szerepel, az eredmények helyét jelölés mutatja.

## Mit és miért vizsgálok

A Tesztelés fejezet tesztjei azt igazolják, hogy egy-egy szabály a leírt módon
működik. Azt viszont nem mutatják meg, hogy a szabályok együtt, egy beteg
hetekig tartó adatain milyen jelzéseket adnak az orvosnak, és ez miben más,
mint amit a legegyszerűbb megoldás adna. A kiértékelés ezért két kérdésre
keres választ: miben tér el a szabálykiértékelés az egyszerű
küszöbfigyeléstől ugyanazokon az adatokon, és hogyan viselkedik a rendszer
futásideje, ha nő az adatmennyiség.

## Mesterséges beteg-forgatókönyvek

Az összevetés előre megírt, mesterséges betegeken fut. Az első mérföldkő
pontosításakor hat forgatókönyvet rögzítettem, mindegyik egy-egy jellegzetes
helyzetet képvisel:

| Forgatókönyv | Mit mutat meg |
|----------------------------|---------------------------------------------|
| stabil beteg | kell-e jelzés, ha minden rendben van |
| egyszeri kiugrás | egyetlen magas érték, utána rendben |
| tartós, ismétlődő átlépés | több eltérés rövid időn belül |
| adathiányos időszak | elmaradó mérések és kitöltések |
| romló kérdőív a határ alatt | a pontszám nő, de nem lépi át a határt |
| javított adat | egy kiváltó mérést a beteg utólag javít |

A forgatókönyvek adatait egy szintetikus adatgenerátor állítja majd elő; ez
még nem készült el. A mostani demóadat öt kézzel összeállított betegből áll,
ezek a felület bemutatására szolgálnak, nem a kiértékelésre.

A forgatókönyvek végleges listáját és azt, hogy a generátor milyen úton tölti
be az adatokat, a mérés előtt rögzítem.

## Az összevetés módja

Az egyszerű küszöbfigyelés (alapvonal) minden határátlépésre külön riasztást
ad; a kérdőívnél is csak egy pontszámhatárt néz. Ezzel szemben a
szabálykiértékelés a négy szabálytípussal dolgozik, és nyitott riasztás
mellett az újabb kiváltó adatot ismételt aktiválódásként kezeli. Mindkét
módszer ugyanazokat az adatokat kapja, és forgatókönyvenként ezeket
számolom:

- a riasztások száma;
- az első jelzés napja, vagyis melyik módszer jelez előbb;
- az értesítések száma;
- felismeri-e a módszer az adathiányt.

Az eredmény erősen függ attól, milyen határokkal fut a két módszer. Ha a
szabálykiértékelés egyszeri küszöbszabálya ugyanazon a határon futna, mint
az alapvonal, egy egyszeri kiugrásra mindkettő jelezne. A mostani demóadat
egy olyan beállítást használ, amelyben az egyszeri küszöbszabály csak a
kritikus határon (180 Hgmm szisztolés felett) riaszt, a tartós eltérést az
időablakos szabály figyeli, a kérdőívet a sáv- és a trendszabály, az
elmaradást az elmaradt adat szabálya. Ez az első mérföldkő kiinduló
javaslata volt.

Az összevetés végleges beállítását és a mérőszámokat szintén a mérés előtt
rögzítem.

Az eltéréseket nemcsak megszámolom, hanem forgatókönyvenként meg is
magyarázom: melyik szabály, melyik adat miatt jelzett az egyik módszer, és a
másik miért nem. Az is része a kiértékelésnek, ahol a szabálykiértékelés
rosszabbul teljesít, például ha egy ismétlődő eltérésre várhatóan később
jelez, mint az alapvonal.

[KÉSŐBB: M4, táblázat és grafikon]

## Teljesítménymérés

A második mérés azt vizsgálja, hogyan nő a futásidő az adatmennyiséggel.
Két dolgot mérek: egy új mérés vagy kitöltés kiértékelésének idejét, és a
kulcsvégpontok válaszidejét. Az adatmennyiséget nagyságrendi lépcsőkben
növelem, és az eredményt lépcsőnként táblázatban és grafikonon mutatom be. Ez
a mérés ellenőrzi azt is, hogy a szinkron adatbázis-hozzáférés (lásd az
Architektúra fejezetet) ekkora rendszerhez elegendő-e.

A mért végpontokat, a lépcsőket, az ismétlések számát és a mérőkörnyezetet a
mérés előtt rögzítem, és az eredményekkel együtt közlöm.

[KÉSŐBB: M4, táblázat és grafikon]

## Korlátok

A PULSE demonstrációs rendszer, kizárólag mesterséges adatokkal működik, nem
orvostechnikai eszköz, és az orvosi döntést nem pótolja. A kiértékelés
ezért a szoftver viselkedéséről szól: arról, hogy a rendszer a tervezett
módon jelez-e. Arról, hogy a jelzések klinikailag hasznosak-e, nem mond
semmit; ehhez valódi betegadatokon végzett klinikai vizsgálat kellene. A
forgatókönyveket én írom, így azt is én döntöm el, mely helyzetek kerülnek
bele. A mérésekre vonatkozó szabályok a küszöb alatt maradó, lassú romlásra
nem jeleznek, és az összevetés eredménye a választott határoktól függ. A
teljesítménymérés az adatmennyiség hatását mutatja, valódi, sok egyidejű
felhasználós terhelést nem modellez.
