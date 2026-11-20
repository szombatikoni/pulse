# Tesztelés

A tesztelés célja kettős: igazolni, hogy a működési szabályok (a Működés
fejezet példái) a kódban is úgy teljesülnek, ahogy leírtam őket, és megakadályozni,
hogy egy későbbi módosítás csendben elrontson egy már működő részt. Ezért a
tesztek nagy része nem egy-egy függvényt vizsgál elszigetelten, hanem egy
szabályt vagy egy folyamatot, valódi adatbázison.

## Tesztszintek és eszközök

**Backend (pytest).** A backend tesztjei valódi PostgreSQL-adatbázison
(`pulse_test`) futnak, nem memóriabeli helyettesítőn, mert több védelem az
adatbázisban van (lásd az Architektúra fejezetet). A futás elején a tesztek
a valódi Alembic-migrációkkal hozzák naprakész állapotba az adatbázist, így
maguk a migrációk is tesztelve vannak. Minden teszt egy külső tranzakcióban
fut, amelyet a végén visszagörgetek: a tesztek nem hagynak nyomot, és nem
zavarják egymást. A tesztek két szinten hívják a kódot: a szolgáltatásréteget
közvetlenül, vagy a FastAPI tesztkliensén keresztül a végpontokat, a
hitelesítéssel és a jogosultság-ellenőrzéssel együtt. Az idő a tesztekben
paraméter: a határidő-ellenőrzést végző függvény ugyanaz, mint a
háttérfolyamatban, csak szimulált időponttal hívom meg.

**CQL-szolgáltatás (`node --test`).** A külön konténerben futó CQL-motor
HTTP-felületét a Node beépített tesztfuttatója ellenőrzi, új függőség nélkül.
A tesztek a Működés fejezet integrációs próbájának hét beállítását futtatják le a
szolgáltatáson, és a korábban rögzített kimenettel vetik össze; emellett a
hibás bemenetekre adott válaszokat és a február 29-i születésnap kezelését
vizsgálják.

**Böngészős folyamattesztek (Playwright).** Az `e2e/` mappa tesztjei egy
elindított, frissen feltöltött demórendszeren, Chromiumban járják végig a
felhasználói folyamatokat, magyar nyelvi és budapesti időzóna-beállítással.
A lépések egymásra épülnek (a beteg rögzít, utána az orvos látja), ezért
egyszerre csak egy teszt fut.

**Láncpróba.** A pytest a CQL-szolgáltatást hamis klienssel helyettesíti,
hogy a backend tesztjei a motor nélkül is fussanak. A teljes láncot
(adatbázis, FHIR-csomag, valódi CQL-motor, összevetés a saját számítással)
egy külön szkript próbálja ki a futó rendszeren, egy demóbetegen, egy
harmadik, kézzel számolt elvárással. Ez egyetlen ellenőrzés, nem tesztkészlet.

## A tesztek száma

A táblázat a tesztfüggvényeket számolja területenként, a fájlok alapján. A
paraméterezett tesztek (például egy határeset több értékkel) futáskor több
esetként jelennek meg, ezért a lefuttatott esetek száma ennél nagyobb.

| Szint | Terület | Tesztfüggvény |
|------------|------------------------------------------|------:|
| pytest | hitelesítés, jogosultság, felhasználók | 41 |
| pytest | ugyanez, két független tesztkészlet (lásd lent) | 219 |
| pytest | mérés és mérésjavítás | 29 |
| pytest | szabálymotor (négy típus, verziók, szabály-API) | 61 |
| pytest | riasztás-életút | 45 |
| pytest | kérdőív, pontozás, szerkesztő | 54 |
| pytest | követési terv, alkalmak, státusz, teendők, háttérfolyamat | 142 |
| pytest | beteg- és orvosi lekérdezések | 21 |
| pytest | FHIR-kiadás, NICE-kiértékelés, CQL-kliens | 78 |
| pytest | demóadat, a Működés fejezet dátumozott példái | 22 |
| pytest | **összesen** | **712** |
| node --test | CQL-szolgáltatás | 38 |
| Playwright | böngészős folyamatok | 26 |

A pytest futáskor 985 esetet hajt végre: a legutóbbi teljes futáson
(2026. november 20.) ebből 984 sikeres volt, 1 pedig várt bukás (lásd lent).
A Playwright mind a 26 tesztje ugyanekkor sikeres volt.
A végleges változatban a számokat a leadott kódváltozaton újra lefuttatva
közlöm.

## Lefedettség

A backend utasítás-lefedettsége a CI legutóbbi futásán (2026. november 20.)
99% volt: a 3406 utasításból 32 nem futott le. A CI az `app` csomagot a
demóadat-betöltővel együtt méri, és 70% alatt elbukik. A lefedettséget
alsó korlátnak tekintem, nem célnak: azt mutatja meg, melyik kódrészhez nem
nyúl egyetlen teszt sem, azt viszont nem, hogy a tesztek a helyes
viselkedést várják-e el. Erre szolgálnak a kiemelt esetek és a független
tesztkészletek.

## Kiemelt esetek

**Jogosultság.** A hozzáférés-ellenőrzést szolgáltatás- és végpontszinten is
tesztelem. A beteg csak a saját adatát éri el, és más beteg nevében nem
rögzíthet; az orvos csak a hozzárendelt betegét. Idegen beteg adatlapja,
mérései, kérdőívei és FHIR-csomagja 403-at ad, a riasztásán más nem hajthat
végre műveletet, és egy nem létező beteg azonosítója is 403-at ad, nem
404-et, hogy a válaszból ne lehessen kikövetkeztetni, létezik-e a beteg. Az összerendelés megszüntetése után a
hozzáférés azonnal megszűnik, létrejöttekor azonnal megnyílik, a jövőbeli
kezdetű összerendelés pedig még nem ad hozzáférést. Ehhez nem kell új token,
mert a felhasználót minden kérésnél az adatbázisból töltöm be. Az admin nem
látja a betegadatokat.

**Szabályhatárok és időablak-szélek.** A küszöbszabálynál a 140 Hgmm-es
határ maga még nem eltérés, a 141 már igen. A vérnyomás két értéke külön is
kiválthatja a riasztást, de ha mindkettő átlépi a határt, akkor is csak egy
riasztás keletkezik. Az időablakos szabály pontosan az N-edik eltérésnél
jelez. A pontosan 7 nappal korábbi mérés még beleszámít az ablakba, az egy
másodperccel korábbi már nem, és csak a szabály saját méréstípusa számít.

**Deduplikáció.** Nyitott riasztás mellett a második kiváltó adat ismételt
aktiválódást ad, nem új riasztást, és a súlyosság nem csökkenhet. A demóban
Szabó Jánosnál egy riasztás tartozik az időablakos szabályhoz, két eseménnyel.

**Javított mérés.** A Működés fejezet szabálymódosítási példáját (szigorítás,
ismételt aktiválódás, a kiváltó mérés javítása) egy teszt lépésről lépésre
végigjárja. Ellenőrzi, hogy az eredeti mérés megmarad, a korábbi esemény rá
hivatkozik, a riasztás nem záródik le magától, és a régi verzió szerinti
jelentése nem változik.

**Kérdőívverzió-váltás.** A kitöltés az alkalomhoz rögzített verzióval és
annak pontozásával értékelődik, egy új verzió a régi kitöltések jelentését
nem írja át, és a romló trend vizsgálata verzióváltás után újraindul.

**Időzítés.** A határidő-ellenőrzés kétszeri futtatása ugyanazt az állapotot
adja: nem keletkezik dupla alkalom vagy riasztás. Külön tesztek vizsgálják a
helyi éjfél szerinti napfordulót, a késve teljesítést és a pótlási idő
végét.

**Hiányzó teszt.** Az e-mail-értesítés még nem készült el, ezért a
kézbesítés hibaágának tesztje is hiányzik.

## A dátumozott példák tesztjei

A Működés fejezet dátumozott példáit és állításait tételenként vetettem
össze a tesztekkel. A 43 tételből 24-et már meglévő teszt ellenőrzött,
13-hoz új teszt készült vagy a meglévő egészült ki, 3 tételnél a kód eltért
a leírttól (ebből kettőt a kód javításával megszüntettem, egy maradt), 3
pedig akkor nem volt tesztelhető. Ez utóbbiak közül a demókérdőív új
verziója azóta elkészült, és a demóadat tesztje ellenőrzi; teszt nélkül egy
elvi állítás és a nyitott döntések listája maradt. A megmaradt eltérést
`xfail(strict=True)` jelöli: a teszt a dolgozat szerinti elvárást rögzíti, és
ha a kód vagy a szöveg változik, a teszt jelez.

A három eltérésnek közös oka volt. A két javított tételnél a határidő és a
pótlási idő vége között a státusz a dolgozat szerint Adathiány, a kódban
viszont Rendben vagy Kezelve volt. Itt a kódot igazítottam a dolgozathoz. A
megmaradt eltérés szóhasználati: az alkalom-táblázat 3. sora a határidő után
„elmulasztva" állapotot ír, a kódban viszont ez az alkalom a pótlási idő
végéig esedékes, és csak utána lesz végleg elmulasztott. A státusz ilyenkor
már a dolgozat szerint Adathiány. A Működés fejezet szövegét ezen a ponton
pontosítani fogom.

## A tesztek futtatása

A backend tesztjei a `backend/` mappából futnak (`uv run pytest`), egy
elérhető PostgreSQL-adatbázissal. A CQL-szolgáltatás tesztjei az
`integration/` mappából (`npm ci`, majd `npm run teszt`). A böngészős
tesztekhez előbb el kell indítani a rendszert és betölteni a demóadatot
(`docker compose up --build -d`, majd `docker compose exec api python -m
seed`), utána az `e2e/` mappából: `npm ci`, `npx playwright install
chromium`, majd `npx playwright test`.

A GitHub Actions minden, a `develop` vagy a `main` ágra kerülő változtatásnál
mindhármat lefuttatja (az Architektúra fejezetben leírt négy ellenőrzés
részeként), a böngészős tesztek előtt a láncpróbával. Hiba esetén a
képernyőképek letölthetők, a konténerek naplója a futás kimenetében
olvasható.

## Független tesztek és átnézések

A tesztek egy részét nem a kódot író agent írta. A hitelesítés és a
jogosultság területén két, eltérő modellű agent kizárólag a követelményekből
írt teszteket (két külön mappában, `tests/independent_*/`), a meglévő
tesztek ismerete nélkül; a kódból csak a hívási felületet nézték meg, és az
alkalmazáskódot nem javíthatták. Ezek a táblázatban külön sorban
szerepelnek. Emellett minden nagyobb lépés után független kódátnézés
készült, és a leletekről én döntöttem. A módszert és a feltárt hibákat az
AI-eszközhasználat fejezet írja le.

## Ismert hibák és korlátok

A tesztek és az átnézések nem szüntettek meg minden eltérést. Az alábbiak a
mai állapotban is fennállnak. A javításuk a véglegesítés része, vagy ismert
korlátként maradnak.

| Terület | Jelenség |
|--------------|-----------------------------------------------------------|
| Követési terv | Ha az orvos egy ma véget érő előírást a mai határidő után vesz fel, a beteg azonnal Adathiányt kap, mert az előírás egyetlen alkalma már lejárt. |
| Követési terv | Ha az orvos módosításkor korábbra hozza a határidőt, és az új határidő aznap már elmúlt, a beteg azonnal Adathiányt kap, akkor is, ha a régi határidőhöz képest nem késett. |
| Státusz | Egy lejárt előírás el nem végzett utolsó alkalma éjfélkor kikerül a státuszból: a beteg adat nélkül Rendbenre vált, pedig az alkalom még pótolható. |
| Felület | A még pótolható alkalmat a felület „Elmulasztott alkalom" felirattal mutatja, holott a rendszerben az elmulasztott a végleges állapot. |
| Kérdőívszerkesztő | Nem figyelmeztet nem mentett módosításra: más oldalra lépve vagy a lapot bezárva a módosítás elvész. A mentés visszajelzése a további szerkesztés közben is látszik. Az azonos feliratú válaszok tiltása másképp kódolt vagy láthatatlan karakterekkel megkerülhető. |
| API | A nem létező erőforrásra adott válasz nem egységes: a betegnél, a riasztásnál és a szabálynál 403, az előírásnál és a kérdőívnél 404. Idegen adatot ez nem fed fel, mert az előírást a rendszer csak a beteghez való hozzáférés ellenőrzése után keresi meg. |
| API | A hibás formátumú kérésre adott válasz visszaírja a beküldött mezőértéket, a belépésnél egyes esetekben a jelszót is. |
| Teljesítmény | Az orvosi beteglista betegenként külön lekérdezéseket futtat (négy betegnél kb. 80-at), így a lekérdezések száma a betegszámmal együtt nő. |
| Demóadat | Legkésőbb a betöltés utáni napon 10:01-től a demóbetegek aznapi mérése hiányzik, ezért a Rendben beteg is Adathiányra vált. Bemutató előtt az adatokat újra kell tölteni. |

## Felhasználói kipróbálás

A fenti tesztek fejlesztői tesztek: azt igazolják, hogy a rendszer a leírt
szabályok szerint működik, azt nem, hogy egy orvos vagy egy beteg el tud-e
igazodni rajta. Ezért a harmadik mérföldkő után a környezetemből 4–6 fővel
felhasználói kipróbálást tervezek a demórendszeren, kizárólag mesterséges
adatokkal.

A résztvevők feladatait és a tapasztalatok rögzítésének módját a kipróbálás
előtt, külön tervben rögzítem.

[KÉSŐBB: UAT eredményei]
