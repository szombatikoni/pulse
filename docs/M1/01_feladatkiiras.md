# Feladatkiírás

**Cím:** PULSE – Krónikus betegkövető telemedicina platform
**Hallgató:** Szombati Konrád (IJKCKR), üzemmérnök-informatikus BProf
**Témavezető:** Dr. Bilicki Vilmos, SZTE Informatikai Intézet

A szakdolgozat célja egy webes telemedicina-platform megtervezése és
megvalósítása, amely krónikus betegek (vérnyomás, vércukor, pulzus, testsúly)
otthoni mérésrögzítését és orvos által kirendelt állapotkérdőívek kitöltését
támogatja, a beérkező adatokat pedig konfigurálható, magyarázható
szabálykiértékeléssel dolgozza fel.

A rendszer három szerepkört valósít meg. A **beteg** méréseket rögzít,
előzményeit grafikonokon követi, és a követési tervében előírt kérdőíveket
tölti ki. 

Az **orvos** priorizált, státuszjelzéses beteglistát kap, betegenként
részletes nézetet grafikonokkal és küszöbvonalakkal; szabályokat és küszöböket
állít be, kérdőíveket rendel ki, és kezeli a riasztásokat (megtekintés,
felelőshöz rendelés, lezárás indoklással). 

Az **admin** a felhasználókat, az orvos–beteg összerendeléseket és a méréstípus-törzsadatokat kezeli.

A kiértékelés négy paraméterezhető szabálytípusra épül: egyszeri
küszöbátlépés; időablakos ismétlődés (≥N eltérés M napon belül);
kérdőív-pontszám határátlépése vagy romló trendje; valamint az elmaradt
adatküldés önálló jelzése (adathiány sosem eredményez kedvező státuszt).
A szabályok és a kérdőívsablonok verziózottak: minden módosítás új,
megváltoztathatatlan verziót hoz létre, a riasztások és kitöltések a
keletkezéskori verzióra hivatkoznak, így a korábbi események jelentése utólag
nem változik. Minden riasztás rögzíti a kiváltó szabályverziót és adatokat,
ebből a felületen olvasható magyarázat készül. A riasztások életútja
állapotgéppel követett (keletkezett → megtekintett → felelőshöz rendelt →
indoklással lezárt), eseménytörténettel és deduplikációval. A jogosultságkezelés
szerveroldali szűréssel minden végponton érvényesül, és célzott tesztek
igazolják.

A dolgozat a kész rendszert mérésekkel is értékeli: előre definiált
szintetikus beteg-forgatókönyveken hasonlítja össze, hogy az egyszerű
küszöbfigyelés és a szabálykiértékelés mikor és miért ad eltérő jelzést,
valamint méri a kiértékelés futásidejét és a kulcs API-végpontok válaszidejét
növekvő adatmennyiségnél. A kiértékelés célja annak vizsgálata, hogy a szoftver
a tervezett módon működik-e — a rendszer klinikai hasznosságáról nem tesz és
nem is tehet megállapítást.

A megvalósítás technológiái: React + TypeScript frontend, Python + FastAPI
backend, PostgreSQL adatbázis, Docker-alapú futtatókörnyezet. A fejlesztést
teljes CI/CD-folyamat (GitHub Actions) kíséri, automatizált tesztekkel és
nyilvános demókörnyezettel.

A rendszer demonstrációs célú, kizárólag mesterséges adatokkal működik; nem
orvostechnikai eszköz, és nem helyettesít orvosi döntést vagy sürgősségi
ellátást.
