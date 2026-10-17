# AI-eszközhasználat

A szakdolgozat készítése során AI-eszközt használtam, és ezt kezdettől
vállaltam a témavezetőm felé. Ebben a fejezetben leírom, mire használtam,
hogyan osztottuk meg a felelősséget, és hogyan ellenőriztem az eredményt. A
munkamenetenkénti részletek a repóban lévő AI-használati naplóban
találhatók.

## Eszközök

- **Claude (csevegőfelület):** a kezdeti szakaszban a koncepció-kérdőív, a
  feladatkiírás és a módosított terv szövegtervezeteihez.
- **Claude Code (VS Code-bővítmény):** a fejlesztés fő eszköze. Kódot,
  dokumentációt és szövegtervezetet készít, parancsokat futtat (tesztek,
  Docker, migrációk), és megmagyarázza a kódot.
- **További, független agentek:** egy-egy jól körülhatárolt feladatra külön
  agentet indítottam, a tesztírásnál két, egymástól eltérő modellel: független
  kódátnézésre, követelményekből írt független tesztekre, valamint források
  és technológiák felkutatására.

## A felelősség megosztása

A munkamódszer alapja, hogy az AI tervezetet és kódot készít, a döntés, az
átnézés és a felelősség pedig az enyém. Ebből három
szabály következik:

1. **Tervezési döntést az AI nem hoz.** Ha hézagot vagy kérdést talál,
   javaslatot tesz alternatívákkal, és én választok. Ha a munka közben egy
   részletet az AI választott (például egy alapértelmezett értéket), azt
   külön listán jelöljük, és jóváhagyásig nyitott pontként kezeljük.
2. **Csak azt fogadom el, amit értek.** A kódhoz egy saját, fejlesztői
   jegyzet készül, amely minden lépés után bővül: fájlonként és
   döntésenként leírja, mi mit csinál és miért. Ebből készülök a védésre is.
3. **Minden tényállítást ellenőrzök.** Az AI magabiztosan állíthat valótlant,
   ezért a forrásokat elsődleges helyről nézzük meg, a kód működését pedig
   tesztek és kipróbálás igazolja.

A második mérföldkőnél a határidő miatt eltértem a kis lépésenkénti
átnézéstől: az AI a két folyamat kódját előre elkészítette, én utólag nézem
át. A nem jóváhagyott részleteket ilyenkor is külön lista tartalmazza.

## Ellenőrzési módszerek

**Független tesztírás.** A kódot író agent tesztjei mellett két másik, eltérő
modellű agent is írt teszteket, kizárólag a követelményekből. A meglévő
teszteket nem látták, és az alkalmazáskódot nem javíthatták, csak jelentettek.
Az eltéréseket közösen néztük át: kódhiba, hibás tesztelvárás vagy
kétértelmű követelmény volt-e. Az első körben az egyik független tesztkészlet
négy specifikációs hézagot tárt fel. Az e-mail-cím kisbetűsségét és az
összerendelések átfedésmentességét addig csak a kód biztosította, a
jelszóhossz pedig a létrehozásnál és a belépésnél eltért. Ezeket
adatbázis- és szolgáltatásszintű szabállyal javítottuk.

**Független kódátnézés.** Minden nagyobb lépés után egy külön agent nézte át
a kódot a követelmények és a működési szabályok alapján. A leletekről én
döntöttem: javítás, a következő mérföldkőre halasztás vagy elutasítás.

**Elsődleges források.** A biztonsági döntéseknél (jelszóhash, a bejelentkezés
módja, második tényező) a szabványokat és a telepített csomag forrását
néztük meg, nem másodlagos összefoglalókat. Az integrációs iránynál a
klinikai ajánlást magam olvastam el.

**Független számítás.** A CQL-próbában a motor eredményét egy tőle független,
pontos törtekkel számoló szkript ellenőrzi, hét paraméterváltozatban.

**Kipróbálás és CI.** A folyamatokat böngészőben is végigpróbáltuk, és a
GitHub Actions minden változtatásnál lefuttatja a teszteket és az
ellenőrzéseket.

## Példák a hibák kiszűrésére

- **Nem létező funkció:** a piackutatás egyik tervezete betegeknek szóló webes
  felületet tulajdonított egy versenytársnak, amely betegoldalon csak
  mobilalkalmazásként létezik. A gyártói oldal ellenőrzésekor kiszűrtem.
- **Elavult adat:** egy versenytársról régi termékmodell szerepelt; az
  újraellenőrzés után frissült.
- **Hibás generált migráció:** az automatikusan generált migrációban egy
  adatbázis-megszorítás többször, két azonos névvel szerepelt. Kézzel
  javítottuk, majd a migrációkat oda-vissza lefuttatva ellenőriztük.
- **Rejtett számítási hiba:** a CQL-szabály korábbi vázlata hibás átlagot
  adott volna, mert a lekérdezés alapértelmezésben kiszűri az ismétlődő
  értékeket (két azonos mérés egynek számított volna). A próba során derült ki,
  a javítást a független számítással való egyezés igazolja.
- **Nem létező verziójelölés:** a CI-konfiguráció egy olyan verziójelölésre
  hivatkozott, amelyet a használt GitHub-művelet nem ad ki. Az első futás
  elbukott; a hibaüzenet alapján a pontos verzióra rögzítettük.

## Az AI-napló

A repó gyökerében lévő AI-használati napló minden munkamenetről rögzíti:

- a használt eszközt;
- az AI szerepét;
- a saját döntéseimet és felvetéseimet;
- azokat a visszakérdezéseimet, amelyekből döntés vagy változás lett;
- az ellenőrzés módját, konkrét javításokkal.

A bejegyzések fordított időrendben követik egymást.

## Tanulságok

> **Jóváhagyandó:** ezt a részt neked kell megírnod, a saját tapasztalataid
> alapján. Pár kérdés, ami segíthet: Mi működött jól a munkamódszerben? Hol
> kellett a legtöbbet ellenőrizni? Mit csinálnál másképp? Mit tanultál meg
> közben, amit AI nélkül nem, vagy lassabban tanultál volna meg?
