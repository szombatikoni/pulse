# A rendszer működése

Ez a fejezet dátumozott példákon mutatja be a működési szabályokat: hogyan
áll elő a beteg státusza, hogyan kezeli a rendszer az ismétlődő teendőket és
az elmaradást, mi történik szabálymódosításkor és adatjavításkor, és hogyan
pontoz a kérdőív. A példák mesterséges adatokkal készültek. A státusz, a
küszöbszabály, a deduplikáció és a kérdőív-pontozás a második mérföldkőben
már működik, és tesztek ellenőrzik. A beteg teendőlistája (mi esedékes, mi
kész, mi maradt el, és meddig pótolható) is már az alább leírt szabályokkal
számolódik, az előírásokból. Az alkalmak tárolása, a riasztáslezárás és a
javítás a harmadik mérföldkőben készül el. A fejezet végén egy integrációs
próba szerepel: egy klinikai irányelven alapuló szabály, szabványos adatokon,
meglévő motorral kiértékelve.

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
mérés vagy kitöltés legfeljebb 7 napos.

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
  végleges.

![Egy alkalom életciklusa](images/folyamat_kirendeles.png){#abra:alkalom}

| Időpont | Esemény | Alkalom |
|---------|-----------------------------------|---------------|
| szept. 22. 00:00 | A háttérfolyamat létrehozza a 22-i alkalmat (határidő 10:00) | #1 esedékes |
| szept. 22. 07:40 | Mérés érkezik (m1) | #1 teljesítve |
| szept. 23. 10:15 | A 23-i alkalomra határidőig nem jött mérés | #2 elmulasztva → Adathiány |
| szept. 24. 08:10 | A beteg rögzíti: „tegnap 19:00-kor mértem" (m2) | #2 késve teljesítve |
| szept. 24. 08:12 | A beteg rögzíti a mai mérést (m3, 07:30) | #3 teljesítve |

Az első elmulasztás a státuszt azonnal Adathiányra állítja. Riasztás csak
az „elmaradt adatküldés" szabályban beállított számú (alapértelmezés szerint
két egymást követő) elmulasztás után keletkezik.

**Kérdőívnél nincs pótlás.** A kérdőív a kitöltés pillanatának állapotáról
szól, ezért nem dátumozható vissza: a kitöltés mindig az aktuális alkalomhoz
számít, az elmaradt korábbi alkalom pedig elmulasztva marad. Ugyanezért a
kérdések időszaka igazodik a kirendelés gyakoriságához: heti kérdőív az elmúlt
hétre kérdez, napi az aznapra. A mostani demókérdőív ennek még nem felel meg
(heti kirendelés mellett az előző éjszakára és az aznapra is kérdez); a
harmadik mérföldkőben új verziót kap, ami egyben a verzióváltást is bemutatja.

## Riasztás, deduplikáció és szabálymódosítás

A riasztás életútja egy egyszerű állapotgép: keletkezett → megtekintett →
felelőshöz rendelt → lezárt. Lezárni csak indoklással lehet, és minden váltás
eseményként rögzül (ki, mikor, mit).

![A riasztás életútja](images/folyamat_riasztas.png){#abra:riasztas}

A riasztásokat a rendszer beteg és szabály szerint vonja össze. Nyitott
riasztás mellett ugyanarra a szabályra érkező újabb kiváltó adat nem nyit új
riasztást, hanem „ismételt aktiválódás" eseményt ad; a súlyosság ilyenkor
emelkedhet, de nem csökkenhet. A demóadatokban Szabó Jánosnál ez látszik: két
140 Hgmm feletti mérés után a vérnyomás-küszöbszabályhoz egy riasztás tartozik,
két eseménnyel.

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
kritikus sáv súlyos riasztást ad. A vérnyomásnál a demó 140/90 Hgmm felett
közepes, 180 Hgmm szisztolés felett súlyos riasztást ad. Ezek bemutató
értékek, nem klinikai ajánlások: a valódi határokat az orvos betegenként
állítja be.

**Mit lát a beteg?** A kitöltés után csak nyugtát kap, a pontszámot, a sávot és
a riasztást nem. Ennek három oka van: egy orvosi értelmezés nélküli „Súlyos"
vagy „kritikus" felirat megijesztheti a beteget, vagy épp hamis megnyugvást
adhat; a riasztás az orvosnak szól, aki eldönti, mit jelent és mi a teendő; és
ha a beteg látná, melyik válasz mennyi pontot ér, a válaszait is
befolyásolhatná. Az értelmezést az orvos közli: a tervben a riasztás lezárásakor
rövid visszajelzést küldhet a betegnek.

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

> **Jóváhagyandó (a te döntéseid, a beépítés előtt):**
> 1. Kiessen-e az első nap a kezelés követésénél is (az 1.2.7 a diagnózisról
>    szól)? A próbában: igen.
> 2. Mi az „első nap": az első mérés napja, vagy a kirendelés kezdőnapja? A
>    próbában: az első mérés napja.
> 3. Mindkét átlagnak a cél alatt kell lennie, vagy elég az egyiknek? A
>    próbában: mindkettőnek.
> 4. Hány értékelhető nap kell legalább? A próbában: 3 (az első nappal 4).
> 5. Kerekítsen-e a rendszer az összevetés előtt? A próbában: nem.
> 6. Melyik napon számít az életkor? A próbában: a sorozat utolsó napján.
> 7. A leolvasások egyszerű átlaga, vagy előbb alkalmanként a két leolvasás
>    átlaga? A próbában: minden leolvasás egyszerű átlaga (teljes pároknál a
>    kettő ugyanaz, hiányos párnál eltér).
> 8. Mi legyen a hiányos (például csak szisztolés) és a javított méréssel? A
>    próbában: a hiányos kimarad, és külön listán látszik; a javított mérés
>    kezelése a harmadik mérföldkő része.

Ha nincs elég adat, az eredmény „nincs elég adat", ami a PULSE-ban Adathiány,
nem kedvező státusz; ez a meglévő elvből következik.

### Korlátok

A FHIR-csomagot hivatalos validátorral még nem ellenőriztem. A próba egyetlen
fordító- és motorverzióval futott. A PULSE-ba még nincs beépítve: a saját
adatbázis marad az elsődleges, a FHIR-kiadás és a CQL-kiértékelés bekötése a
harmadik mérföldkő feladata.
