# A rendszer működése

Ez a fejezet dátumozott példákon mutatja be a működési szabályokat: hogyan
áll elő a beteg státusza, hogyan kezeli a rendszer az ismétlődő teendőket és
az elmaradást, mi történik szabálymódosításkor és adatjavításkor, és hogyan
pontoz a kérdőív. A példák mesterséges adatokkal készültek. A státusz, a
küszöbszabály, a deduplikáció és a kérdőív-pontozás a második mérföldkő óta
működik, és tesztek ellenőrzik. A harmadik mérföldkőben elkészült a többi
szabálytípus, az alkalmak tárolása, a riasztás lezárása és a mérésjavítás is;
a beteg teendőlistája (mi esedékes, mi kész, mi maradt el, és meddig
pótolható) a tárolt alkalmakból számolódik. A fejezet végén egy integrációs
próba szerepel: egy klinikai irányelven alapuló szabály, szabványos adatokon,
meglévő motorral kiértékelve. A fejezetet egy leképezési terv zárja: hogyan
illeszkedne a követési terv egy szabványos protokoll-leíráshoz.

## A beteg státusza

A beteg státusza számított érték, nem tárolt mező. Ha tárolnám, az idő
múlásával elavulna: egy beteg, akitől egy hete nem jött adat, magától nem
váltana Adathiányra, mert az idő múlása nem esemény, ami frissítené. Ezért a
rendszer minden lekérdezéskor a nyitott riasztásokból, az alkalmak
teljesítéséből, a legutóbbi adat frissességéből és a lezárás utáni megerősítő
adatból számolja ki. Több feltétel egyidejű fennállásakor a táblázatban
feljebb álló érvényes, a felület a többi okot is kiírja.

| Státusz | Mikor |
|-------|-----------------------------------------------------|
| Súlyos | súlyos nyitott riasztás van |
| Figyelem | közepes nyitott riasztás van |
| Adathiány | egy előírás legutóbbi lejárt alkalma elmaradt, és nem pótolták; vagy nincs friss adat |
| Kezelve | az orvos lezárta a riasztást, de azóta nem érkezett rendben lévő adat |
| Rendben | friss, rendben lévő adat van, és a fentiek egyike sem áll fenn |

![A beteg státuszának előállítása](images/statusz_elallitas.png){#abra:statusz}

A legfontosabb elv, hogy sem a lezárás, sem az adat hiánya nem ad kedvező
státuszt. Egy frissen felvett beteg, akinek még nincs mérése, Adathiány
státuszú, nem Rendben. Előírás nélkül akkor friss az adat, ha a legutóbbi
mérés vagy kitöltés legfeljebb 7 napos. Ugyanez érvényes addig, amíg az
előírás első alkalma le nem zárult.

**Példa: lezárás, majd megerősítő mérés**

| Időpont | Esemény | Státusz |
|----------|---------------------------------------------|-------|
| szept. 16. | 7 napon belül a harmadik 140 Hgmm feletti szisztolés érték → közepes riasztás | Figyelem |
| szept. 21. 10:02 | Az orvos lezárja: „Telefonon egyeztettem, gyógyszer módosítva." | Kezelve |
| szept. 22. 07:40 | Mérés: 128/82 Hgmm, a szabály szerint rendben | Rendben |

Ha a lezárás után elmarad a mérés, a következő alkalom határideje után a
státusz Adathiány lesz. Ha a lezárás után újra magas érték jön, és a 7 napos
ablakban még ott vannak a korábbi magas mérések, a feltétel azonnal újra
teljesül, és új riasztás nyílik. A lezárás a riasztást zárja le, a korábbi
méréseket nem törli.

## Esedékesség és elmaradás

Az orvos előírást állít be, például: *vérnyomásmérés naponta, 10:00-ig,
10 napig.* Minden alkalomhoz egy időszak tartozik: napi előírásnál a naptári
nap, heti vagy N napos előírásnál a teljes időköz. A határidő az időszak
utolsó napján, a beállított időpontban van.

- **Melyik alkalomé a mérés?** Amelyiknek az időszakába a mérés időpontja
  esik; a beteg nem választ alkalmat.
- **Időben vagy késve?** A határidő előtti rögzítés teljesíti az alkalmat, a
  későbbi késve teljesíti. A döntés a rögzítés tárolt időpontjának és a
  határidőnek az összevetéséből születik, így nem függ attól, hogy a
  háttérfolyamat mikor futott utoljára. A háttérfolyamatra csak akkor van
  szükség, ha semmi nem érkezik: ő jelöli elmulasztottnak az alkalmat, és ő
  indítja az elmaradt adatra vonatkozó szabályt.
- **Meddig pótolható?** Mérést legfeljebb két napra visszamenőleg lehet
  rögzíteni, a mérés időpontjától számítva. Egy elmulasztott alkalom így
  addig pótolható, amíg az időszakába eső mérés még rögzíthető; utána
  végleges. A kétnapos határ csak az új mérés visszadátumozására vonatkozik:
  a már rögzített mérés értéke időkorlát nélkül javítható, a javítás a mérés
  időpontját nem változtatja meg.

![Egy alkalom életciklusa](images/dolgozat_folyamat_kirendeles.png){#abra:alkalom}

| Időpont | Esemény | Alkalom |
|---------|-----------------------------------|---------------|
| szept. 22. 00:00 | A háttérfolyamat létrehozza a 22-i alkalmat (határidő 10:00) | #1 esedékes |
| szept. 22. 07:40 | Mérés érkezik (m1) | #1 teljesítve |
| szept. 23. 10:15 | A 23-i alkalomra határidőig nem jött mérés | #2 elmulasztva → Adathiány |
| szept. 24. 08:10 | A beteg rögzíti: „tegnap 19:00-kor mértem" (m2) | #2 késve teljesítve |
| szept. 24. 08:12 | A beteg rögzíti a mai mérést (m3, 07:30) | #3 teljesítve |

Az első elmulasztás a státuszt azonnal Adathiányra állítja. Riasztás csak
az „elmaradt adatküldés" szabályban beállított számú (alapértelmezés szerint
két egymást követő) elmulasztás után keletkezik. Mérésnél az alkalom a
pótlási idő végéig, az időszak vége után 48 óráig még teljesíthető, ezért a
szabály csak ezután számolja elmulasztottnak. A riasztás így később
keletkezik, mint ahogy a határidő lejár, a státusz viszont ettől függetlenül
már a határidőnél Adathiány.

**Kérdőívnél nincs pótlás.** A kérdőív a kitöltés pillanatának állapotáról
szól, ezért nem dátumozható vissza: a kitöltés mindig az aktuális alkalomhoz
számít, az elmaradt korábbi alkalom pedig elmulasztva marad. Ugyanezért a
kérdések időszaka igazodik a kirendelés gyakoriságához: heti kérdőív az elmúlt
hétre kérdez, napi az aznapra. A demókérdőív első verziója ennek még nem
felelt meg (heti kirendelés mellett az előző éjszakára és az aznapra is
kérdezett). A második verzióban a kérdések az elmúlt hétre szólnak, a
pontozás és a sávok nem változtak; ez egyben a verzióváltást is bemutatja.

## Riasztás, deduplikáció és szabálymódosítás

A riasztás életútja egy egyszerű állapotgép: keletkezett → megtekintett →
felelőshöz rendelt → lezárt. Lépés kihagyható, visszaút nincs. Lezárni
bármelyik nyitott állapotból, de csak indoklással lehet, és minden váltás
eseményként rögzül (ki, mikor, mit).

![A riasztás életútja](images/folyamat_riasztas.png){#abra:riasztas}

A riasztásokat a rendszer beteg és szabály szerint vonja össze. Nyitott
riasztás mellett ugyanarra a szabályra érkező újabb kiváltó adat nem nyit új
riasztást, hanem „ismételt aktiválódás" eseményt ad; a súlyosság ilyenkor
emelkedhet, de nem csökkenhet. A demóadatokban Szabó Jánosnál ez látszik: a
harmadik 140/90 Hgmm feletti mérés megnyitja az időablakos szabály riasztását,
a negyedik ugyanahhoz kapcsolódik, így egy riasztás tartozik hozzá, két
eseménnyel.

Szabálymódosításkor ugyanaz a nyitott riasztás folytatódik, az új adatot
viszont már az új verzió értékeli. Minden esemény tárolja az alkalmazott
verziót és a kiváltó adatokat.

| Időpont | Esemény | Eseménytörténet |
|-------|--------------------------|------------------------------|
| szept. 16. | Harmadik 140 feletti mérés (m1, m2, m3) | *keletkezett* · 2. verzió (>140, 3× 7 napon belül, közepes) · m1, m2, m3 |
| szept. 19. | Az orvos szigorít: 3. verzió (>135, 3× 7 napon belül, súlyos) | *szabály módosult* · a riasztás 2. verzió szerinti jelentése nem változik |
| szept. 20. | m4 = 138/88: a 2. verzió szerint rendben, a 3. szerint nem | *ismételt aktiválódás* · 3. verzió · m2, m3, m4 · közepes → súlyos |
| szept. 21. | A beteg javítja az m3-at (151 helyett 131) | *kiváltó adat javítva* · a feltétel már nem teljesül |
| szept. 21. | A riasztás nem záródik le magától | Az orvos zárja le indoklással → Kezelve |

A javított mérés nem írja felül az eredetit, és a szept. 16-i esemény
továbbra is az eredetire hivatkozik. Automatikus lezárás azért nincs, mert a
javítást a beteg végzi, és a rendszer nem tudja ellenőrizni: egy riasztás nem
tűnhet el egy betegoldali módosítás miatt.

**Kérdőív-verzióváltás.** A beteg azt a verziót tölti ki, amelyik az alkalom
létrejöttekor érvényes volt. A kiértékelési sávok a
verzió részei, így az új verzió a saját pontozásával együtt a saját sávjait
hozza. A romló trendet a rendszer csak azonos verziójú kitöltések között
vizsgálja, verzióváltás után a vizsgálat újraindul.

## Kérdőív-pontozás

A pontozás egységes: több pont rosszabb állapotot jelent. Skálás kérdésnél a
kérdőív készítője megadja, melyik vég a jobb állapot, és a rendszer ebből
úgy számolja a pontokat, hogy a jobb vég mindig 0 pont:

- ha a kisebb érték a jobb: pont = válasz − a skála minimuma;
- ha a nagyobb érték a jobb: pont = a skála maximuma − válasz.

A kész válasz → pont tábla a kérdőívverzióban tárolódik. A kiértékelési
sávoknak hézag és átfedés nélkül le kell fedniük a 0-tól a legnagyobb
elérhető pontszámig tartó tartományt, így minden kitöltés pontosan egy sávba
esik. Ezt a rendszer a verzió létrehozásakor ellenőrzi.

| Kérdés | Skála | Válasz | Pont |
|-----------|---------------------------|-------|----------------|
| Hogyan aludt? | 1 = nagyon rosszul … 5 = nagyon jól (a nagyobb a jobb) | 4 | 1 |
| Mennyire fáradt? | 1 = egyáltalán nem … 5 = nagyon (a kisebb a jobb) | 4 | 3 |
| Tapasztalt-e szédülést? | Nem / Ritkán / Naponta: 0 / 2 / 5 pont | Ritkán | 2 |
| | | **Összesen** | **6** → figyelmeztető sáv (6–10) |

A demókérdőív sávjai: 0–5 rendben, 6–10 figyelmeztető, 11–13 kritikus. A
fenti számpélda a tesztek között is szerepel. A kérdőívszabály a sávra
riaszt: a demóadatokban a figyelmeztető vagy kritikus sáv közepes, a
kritikus sáv súlyos riasztást ad. A vérnyomásnál a demó 7 napon belül három
140/90 Hgmm feletti mérés után közepes, 180 Hgmm szisztolés felett azonnal
súlyos riasztást ad. Ezek bemutató
értékek, nem klinikai ajánlások: a valódi határokat az orvos betegenként
állítja be.

**Mit lát a beteg?** A kitöltés után csak nyugtát kap, a pontszámot, a sávot és
a riasztást nem. Ennek három oka van: egy orvosi értelmezés nélküli „Súlyos"
vagy „kritikus" felirat megijesztheti a beteget, vagy épp hamis megnyugvást
adhat; a riasztás az orvosnak szól, aki eldönti, mit jelent és mi a teendő; és
ha a beteg látná, melyik válasz mennyi pontot ér, a válaszait is
befolyásolhatná. Az értelmezést az orvos közli: a riasztás lezárásakor
rövid visszajelzést küldhet a betegnek, amelyet a beteg a teendői között lát.

## Integrációs próba: ajánláson alapuló szabály szabványos adatokon

A témavezetőm javaslatára a szabálykiértékelést egy publikált klinikai
irányelvhez kötöm: a vérnyomásátlag számításának módja az irányelvből jön, az
adat a FHIR R4 szabvány szerinti formában kerül a kiértékeléshez, a számítást
pedig egy nyílt forráskódú CQL-motor végzi. Mielőtt ezt a harmadik
mérföldkőben beépíteném, egy önálló próbával ellenőriztem, hogy a lánc a
gyakorlatban működik. A próba a repó `integration/` mappájában
van, és a PULSE-tól függetlenül, Dockerrel futtatható.

### Az átvett ajánlás

Az alap a brit NICE NG136 irányelve a felnőttkori magas vérnyomásról
[@nice-ng136]. Az ajánlások szövegét nem idézem; az alábbi táblázat saját
összefoglalóm arról, mit mondanak, és mit kezdek velük.

| Ajánlás | Saját összefoglaló | A PULSE-ban |
|-------|-----------------------------|-----------------------------|
| 1.2.7 | Otthoni méréssel a diagnózis megerősítésekor alkalmanként két mérés kell, legalább egy perc különbséggel, ülve; naponta kétszer, lehetőleg reggel és este; legalább 4, ideálisan 7 napig. Az első nap méréseit el kell hagyni, a többi átlaga számít. | Az első nap kizárása és az átlagolás megvalósítva (az előbbi paraméter). A legalább 4 nap egy paraméter (alapértéke: 3 értékelhető nap az első nap után). A napi két alkalom, a két leolvasás, az egy perc és az ülő helyzet nincs ellenőrizve. |
| 1.2.8 | A diagnózishoz a rendelői mérés is kell, az otthoni átlag mellett. | A PULSE-ban nincs rendelői mérés, ezért a rendszer **nem diagnosztizál**. |
| 1.4.22 | A kezelés követésénél a szokásos ébrenléti időszakban mért otthoni átlagot kell a célhoz mérni; a számításra az 1.2.6 és az 1.2.7 ajánlásra utal. A cél 80 év alatt 135/85 Hgmm alatt, 80 éves kortól 145/85 Hgmm alatt. Törékeny vagy több betegséggel élő betegnél orvosi mérlegelés kell. | Ez a próba szabálya: a kezelés követéséhez számol átlagot, életkor szerinti céllal. |
| 1.4.15 | A kezelésre adott választ rendelői méréssel kell követni; az otthoni mérés használatát az 1.4.22 írja le. | Korlát: a PULSE az otthoni adatot az orvos elé teszi, a rendelői mérést nem váltja ki. |

### A próba felépítése

1. **Adat.** Egy mesterséges, 68 éves beteg négy napnyi otthoni mérése FHIR
   R4 formában: naponta két alkalom, alkalmanként két leolvasás, összesen 16
   vérnyomás-Observation [@fhir-r4-observation]. A mérés LOINC-kódot kap
   (panel: 85354-9; szisztolés: 8480-6, diasztolés: 8462-4) [@loinc-85354-9],
   az egység UCUM-kódot (`mm[Hg]`), az időpont helyi időeltolást (`+02:00`).
2. **Szabály.** A fenti logika CQL-ben (Clinical Quality Language)
   [@cql-spec]. A kétértelmű pontok paraméterek, így ugyanaz a szabály több
   beállítással is futtatható.
3. **Fordítás és futtatás.** A CQL-t egy fordítószolgáltatás ELM-re (a CQL
   gépi formájára, itt JSON-ban) fordítja [@cql-translation-service], a meglévő
   cql-execution motor futtatja [@cql-execution] a cql-exec-fhir adapterrel,
   amely a FHIR-adatot a motor elé teszi [@cql-exec-fhir]. Minden verzió
   rögzített: fordító 4.2.0, cql-execution 3.3.2, cql-exec-fhir 2.2.0, FHIR
   4.0.1, Node 24; a Docker-image-ek lenyomattal.
4. **Eredmény.** A motor nemcsak igen/nem választ ad, hanem minden adatot, ami
   a magyarázathoz kell: melyik nap esett ki, mely mérések (azonosítóval)
   számítottak, mennyi az átlag, az életkor és a cél.

### Eredmény és ellenőrzés

Az alapbeállítással az első nap (okt. 5.) négy mérése kiesik, marad 12 mérés
három napról. Az átlag 135 / 84,4 Hgmm, a cél 135/85 alatt. A szisztolés
átlag nincs a határ *alatt*, ezért a cél nem teljesül. A próba ebből egy
mondatos magyarázatot is ad:

> Átlag 135,0/84,4 Hgmm, 12 mérésből (2026-10-06 – 2026-10-08, 3 nap); a
> 2026-10-05-i 4 mérés első napként kiesett; célérték: 135/85 Hgmm alatt
> (68 éves; mindkét átlagnak a határ alatt kell lennie): a cél NEM teljesül.

Az eredményt egy külön Python-szkript ellenőrzi, amely sem a CQL-t, sem a
motort nem használja, és pontos törtekkel számol. Ugyanazt az adatot hét
beállítással futtattam le: az alapbeállítás mellett a többi egy-egy
kétértelmű pont vagy eset hatását mutatja:

| Beállítás | Mérésszám | Átlag | Cél | Teljesül? |
|-----------------------------|-------|---------|-------|-----------|
| alap | 12 | 135 / 84,42 | 135/85 | nem |
| az első nap nem esik ki | 16 | 138 / 86,625 | 135/85 | nem |
| elég, ha az egyik érték a cél alatt van | 12 | 135 / 84,42 | 135/85 | **igen** |
| kerekítés egészre az összevetés előtt | 12 | 135 / 84,42 | 135/85 | nem |
| legalább 4 értékelhető nap kell | 12 | 135 / 84,42 | 135/85 | nincs elég adat |
| a beteg 80 év feletti | 12 | 135 / 84,42 | 145/85 | **igen** |
| az első nap a kirendelés kezdőnapja | 16 | 138 / 86,625 | 135/85 | nem |

Mind a hét esetben egyezik az átlag, a mérésszám, a kiesett és a figyelembe
vett mérések azonosítója, az életkor, a cél és az eredmény. Az egyetlen
eltérés a számábrázolásé: a motor lebegőpontosan számol (84,41666…), a pontos
érték 1013/12.

### Amit a próba feltárt

- **Ismétlődő értékek.** A CQL-ben egy lekérdezés eredménye alapértelmezésben
  ismétlődés nélküli. Egy korábbi szabályvázlatban ezért két azonos mérés
  (például kétszer 136) egynek számított volna, és hibás lett volna az átlag.
  A próba során derült ki; a javítás egy kulcsszó (`return all`), és a
  független számítással való egyezés igazolja.
- **Motorhiba.** A használt motorverzióban egy alapérték nélküli, meg nem
  adott paraméter nem üres értéket ad, ezért egy összehasonlítás hamisan
  „nem teljesül"-t adott. A kerülőút: minden paraméternek van alapértéke.
- **Időzóna.** A „nap" a mérés tárolt időeltolása szerint számít. Ha a PULSE
  UTC-ben adná ki a méréseket, egy éjfél utáni mérés az előző napra csúszna,
  és tévesen első napként eshetne ki. Az exportnak ezért helyi eltolással
  kell írnia; ez is indokolja a rendszerszintű időzónát.

### Nyitott döntések

A próbában a kétértelmű pontok alapértékei a háttérkutatás javaslatai, nem
végleges döntések.

A kétértelmű pontok és a próbában használt alapértékek:

1. Az első mérési nap a kezelés követésénél is kiesik, bár az ajánlás 1.2.7
   pontja a diagnózisról szól.
2. Az „első nap" az első mérés napja, nem a kirendelés kezdőnapja.
3. Mindkét átlagnak a cél alatt kell lennie, nem elég az egyiknek.
4. Legalább 3 értékelhető nap kell (az első nappal együtt 4).
5. Az összevetés előtt nincs kerekítés.
6. Az életkor a sorozat utolsó napján számít.
7. Az átlag minden leolvasás egyszerű átlaga, nem az alkalmankénti két
   leolvasás átlagainak átlaga (teljes pároknál a kettő ugyanaz, hiányos
   párnál eltér).
8. A hiányos (például csak szisztolés) mérés kimarad, és külön listán
   látszik. Javított mérésből a PULSE csak az utolsó változatot adja ki, a
   felülírt mérés nem kerül a motorhoz.

Ha nincs elég adat, az eredmény „nincs elég adat", a PULSE paneljén „Nem
értékelhető". A kiértékelés eredménye nem tárolódik, és nem hat a státuszra,
így kedvező státuszt sem adhat.

### Korlátok

A FHIR-csomagot hivatalos validátorral még nem ellenőriztem. A próba egyetlen
fordító- és motorverzióval futott. A próba óta a PULSE a saját adataiból is
kiad FHIR-csomagot, és a backend egy végpontja a külön konténerben futó
motorral értékelteti ki a beteg méréseit (lásd az Architektúra fejezetet). Az
eredményt az orvos az adatlap Áttekintés fülén, tájékoztató panelen látja; a
státuszra és a riasztásokra nem hat. A saját adatbázis marad az elsődleges.

## A követési terv illesztése szabványos protokoll-leíráshoz

A próba egyetlen szabályt kötött az irányelvhez. Ez a szakasz azt vizsgálja,
hogyan illeszkedne a PULSE követési terve és a szabályai egy szabványos
protokoll-leíráshoz, a FHIR R4 PlanDefinition [@fhir-r4-plandefinition],
Library [@fhir-r4-library] és CarePlan [@fhir-r4-careplan] erőforrásához. Ez
terv és leképezési táblázat, nem megvalósítás: a rendszer ezeket az
erőforrásokat nem adja ki és nem fogadja be, a FHIR-kiadás ma a beteg
adataiból, a mérésekből és a kérdőívekből áll. A példa ugyanaz a protokoll,
mint a próbában: a NICE NG136 szerinti otthoni vérnyomás-ellenőrzés.

### Három szint, öt kérdés

A leképezést három szinten végeztem. A protokollszint a betegtől független
leírás: mit kell mérni, milyen gyakran, és milyen logika értékeli ki
(PlanDefinition, a logika Library-ként). A betegszint az, amit ebből egy
betegre előírnak (CarePlan, előírásonként ServiceRequest
[@fhir-r4-servicerequest]). Az eredményszint a beérkező adat és a belőle
született jelzés (Observation [@fhir-r4-observation], QuestionnaireResponse
[@fhir-r4-questionnaireresponse]). Egy megfeleltetés teljes, ha mezőről
mezőre, azonos jelentéssel átvihető; részleges, ha van megfelelője, de
információ vész el, vagy saját konvenció kell hozzá; és nincs, ha a másik
oldalon nincs megfelelője.

A legfontosabb megállapítás, hogy a PULSE-ban nincs protokollszintű követési
sablon. A szabály és az előírás is egy beteghez tartozik, a kérdőívsablon egy
kérdőívé, nem egy követési tervé, a CQL-könyvtár pedig fájlként él a
CQL-szolgáltatás mellett, az adatbázis nem tud róla. Ezért a protokollszint
jórészt hiányzik, a beteg- és az eredményszinten viszont szinte mindennek
van megfelelője, többnyire részleges: az előírás, az alkalom, a mérés és a
kitöltés mind megvan, csak más szerkezetben.

A beilleszthetőséghez öt kérdésre kerestem választ: honnan származik a
protokoll, melyik változata érvényes, milyen adatot igényel, mit lehet benne
betegenként beállítani, és mit ad vissza. Hogy ezeknek hol a helyük a
FHIR-ben, és hol tart ma a PULSE, azt az alábbi táblázat mutatja.

| Kérdés | Helye a FHIR-ben | A PULSE-ban ma |
|------------|------------------------------|------------------------------|
| eredet | PlanDefinition.relatedArtifact (hivatkozás) | csak szövegben: a CQL-fájl fejléce és a dolgozat |
| változat | PlanDefinition.version, Library.version | a CQL-könyvtár verziója, amelyet a CQL-szolgáltatás minden eredménnyel visszaad, és a szabályverzió sorszáma; a kettő nincs összekötve |
| bemenő adat | Library.dataRequirement | a méréstípus LOINC-kódja és a CQL lekérése |
| betegenkénti beállítás | a definíciója Library.parameter; az értéke az `$apply` hívásban a specifikáció szövege szerint név szerint átadható, bár a művelet R4-es paraméterlistája ilyet külön nem nevesít [@fhir-r4-using-expressions]; a célérték a beteg Goal erőforrásában is [@fhir-r4-goal] | saját szabálynál a szabályverzió paraméterei; a CQL-paramétereket a backend minden betegnél azonos alapértékkel adja át, csak az időszak változik |
| kimenet | az `$apply` kimenete egy CarePlan, benne a feltételek szerint alkalmazandó tevékenységekkel [@fhir-r4-plandefinition-apply] | saját szabálynál a riasztás, a szabályverzióval és a kiváltó adatokkal; a CQL-eredmény a panelen látszik, nem tárolódik |

A legfontosabb megfeleltetéseket a következő táblázat foglalja össze; a
teljes, 38 soros táblázat és egy példa az elektronikus mellékletben, a repó
`integration/FHIR_lekepezes.md` fájljában van.

| Szint | FHIR R4 elem | PULSE-megfelelő | Illeszkedés |
|------------|----------------------------|----------------------------|--------------|
| protokoll | PlanDefinition azonosítása, forrása és logikája (url, version, relatedArtifact, library) | nincs tárolva; a szabályverziók és a CQL-könyvtár között nincs hivatkozás | nincs |
| protokoll | Library.parameter | a CQL-könyvtár 11 paramétere | részleges: az alapérték elvész |
| protokoll | Library.dataRequirement | a CQL lekérése és a méréstípus LOINC-kódja | teljes |
| beteg | CarePlan.instantiatesCanonical (melyik protokollból jön a terv) | nincs | nincs |
| beteg | CarePlan tevékenységének időzítése (Timing) | az előírás gyakorisága, kezdete, vége és javasolt időpontja | részleges: a határidő és a pótlási idő nem írható le |
| beteg | ServiceRequest előírásonként | előírás | részleges |
| beteg | Task alkalmanként | alkalom | részleges, saját konvenció |
| eredmény | Observation, QuestionnaireResponse | mérés, kitöltés (a kiadás ma is megvan) | teljes |
| eredmény | Observation.basedOn, QuestionnaireResponse.basedOn | az alkalmat teljesítő mérés vagy kitöltés | részleges |
| eredmény | DetectedIssue, Task, Provenance, Flag | riasztás és a beteg státusza | részleges, nincs egyetlen megfelelő |

### Ahol a két modell eltér

A PULSE több olyat tud, aminek a FHIR-ben nincs természetes helye. A
riasztás a keletkezéskori szabályverzióra hivatkozik. Verzióra hivatkozni a
FHIR-ben is lehet (canonical url és verzió), de betegre szabott szabálynak
nincs saját erőforrása, és a verzió módosíthatatlanságát a szabvány nem
biztosítja, az a rendszer dolga. A riasztásnak életútja, deduplikációja és eseménytörténete van.
Az alkalom késve is teljesíthető, pótlási idővel. A javított mérés új sor, az
eredeti megmarad, míg a FHIR a javítást a mérés amended vagy corrected
státuszával jelöli [@fhir-r4-observation-status]. Az adathiány önálló, sosem
kedvező állapot. Fordítva, a FHIR tud olyat, amit a PULSE nem: feltételes és
egymásra épülő tevékenységeket (condition, trigger, relatedAction, egymásba
ágyazott action), gazdagabb időzítést (napi több alkalom, napszak, a hét
napjai, ismétlésszám) [@fhir-r4-datatypes], protokollból példányosított
tervet, és tágabb tervkörnyezetet (cél, kezelt betegség, ellátócsoport).

**Az alkalom.** Az alkalomnak a FHIR-ben nincs saját eleme. Saját
konvencióként alkalmanként egy Task erőforrást rendelnék hozzá
[@fhir-r4-task]: ennek tárgya (focus) az előírásnak megfelelő ServiceRequest,
az időszaka (restriction.period) az alkalom időszaka, a kimenete (output) a
teljesítő mérés vagy kitöltés. Ezt a szabvány nem írja elő, ez az én
választásom. A Task állapotai [@fhir-r4-task-status] az esedékes, a
teljesítve és az elmulasztva állapotot nagyjából lefedik (ready, completed,
cancelled), a késve teljesítve viszont elvész: completed lesz belőle, a
késés legfeljebb egy szabadon kódolt üzleti állapotban (businessStatus)
maradhatna meg. A pótlási határ (mérésnél az időszak vége után 48 óra) sem
fér el, mert a restriction.period egyetlen időszak. A kapcsolat is csak egy
irányban írható le: a mérés nem hivatkozhat a Task erőforrásra, mert az
Observation basedOn és partOf eleme ezt nem engedi.

**A riasztás.** A riasztásnak nincs egyetlen pontos FHIR-megfelelője, ezért
három részre bontottam. A tartalma (beteg, súlyosság, kiváltó adatok) a
DetectedIssue erőforráshoz áll a legközelebb [@fhir-r4-detectedissue], de a
szabvány ezt szűkebb célra szánja: egy tervezett vagy folyamatban lévő
klinikai tevékenység problémájára, például gyógyszer-kölcsönhatásra. Egy
mérési eltérés ennek tág olvasata. Az elmaradt adatküldés sem illik bele
egyértelműen: a szabvány a technikai jellegű problémákat (például a hiányos
adatot) az OperationOutcome erőforráshoz utalja, és értelmezés kérdése, hogy
egy elmaradt otthoni mérés ide vagy a klinikai tevékenység problémái közé
tartozik. Az életút (felelős, állapot,
események) Task erőforrással és eseményenként egy Provenance erőforrással
[@fhir-r4-provenance] írható le; a DetectedIssue saját státusza
eredményállapot, nem munkafolyamat. A beteg összesített státuszához a Flag
erőforrás illik [@fhir-r4-flag], amely a beteg rekordjának tömör, figyelmeztető
kiemelése; egy-egy riasztásra viszont nem, mert a Flag nem egy adott
személynek szóló jelzés. Mivel a riasztás jelentését csak több erőforrás
együtt, saját kiegészítésekkel adná vissza, a riasztás belső entitás maradt.

**Napi több alkalom.** A NICE napi kétszeri mérése FHIR-ben egy Timing-értékkel
leírható (naponta kétszer, hét napig), a PULSE-ban viszont ma nem írható elő:
egy időszakhoz egy alkalom tartozik, és ugyanarra a célra egyszerre egy
érvényes előírás lehet. Ez a rendszer korlátja, a továbbfejlesztési
lehetőségek között szerepel.

### Mit jelentene a megvalósítás

A tervből három irányban lehetne továbblépni; egyik sem vállalás, csak
lehetséges továbbfejlesztés. A legkisebb a csak kiadás: a
meglévő FHIR-csomag mellé CarePlan, előírásonként ServiceRequest,
alkalmanként Task, a riasztásokból DetectedIssue, az orvosi visszajelzésből
Communication kerülne, az adatmodell változtatása nélkül. A második egy
statikus protokoll: a PlanDefinition és a Library leírása a repóban, egy új
protokolltábla (url, verzió, forrás), amelyre az előírás és a szabályverzió
hivatkozik, és egy szolgáltatás, amely a protokollból betegre előírást és
szabályt hoz létre; ehhez már adatbázis-migráció kell. A harmadik a
szabványos `$apply` művelet, amely a PlanDefinition-ből CarePlan-t állít elő.
Ehhez egy FHIR-szerver és a művelet megvalósítása kellene, ezért a dolgozat
keretén kívül esik.
