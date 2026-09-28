# Működési szabályok példákon

Ez a fejezet dátumozott példasorokon mutatja be, hogyan áll elő a beteg
státusza, hogyan kezeli a rendszer az ismétlődő teendőket és az elmaradást,
valamint mi történik szabálymódosításkor és adatjavításkor. A példák
mesterséges adatokkal készültek.

## 1. Beteg-státusz és riasztáslezárás

A beteg státusza számított érték. Több feltétel egyidejű fennállásakor a
táblázatban feljebb álló érvényes; a felület a többi okot is kiírja.

| Státusz | Mikor |
|---|---|
| Súlyos | súlyos nyitott riasztás van |
| Figyelem | közepes nyitott riasztás van |
| Adathiány | valamelyik előírás legutóbbi lejárt alkalma elmaradt, és nem pótolták |
| Kezelve | az orvos lezárta a riasztást, de a lezárás óta még nem érkezett rendben lévő adat |
| Rendben | friss, rendben lévő adat van, és a fentiek egyike sem áll fenn |

A lezárás tehát önmagában soha nem ad Rendben állapotot: ahhoz a lezárás után
beérkező, a szabály szerint rendben lévő adat kell.

**Példa: lezárás, majd megerősítő mérés**

| Időpont | Esemény | Státusz |
|---|---|---|
| szept. 16. | 7 napon belül a harmadik 140 Hgmm feletti szisztolés érték → riasztás | Súlyos |
| szept. 21. 10:02 | Az orvos lezárja: „Telefonon egyeztettem, gyógyszer módosítva." | Kezelve — „Dr. Szabó lezárta, megerősítő mérés még nem érkezett" |
| szept. 22. 07:40 | Mérés: 128/82 Hgmm, a szabály rendben lévőnek értékeli | Rendben |

**Ugyanez más kimenettel**

- *A lezárás után elmarad a mérés:* a szept. 22-i alkalom határideje mérés
  nélkül lejár → Adathiány.
- *A lezárás után újra magas a mérés* (szept. 22.: 146/92): a 7 napos
  ablakban még benne van a szept. 16-i és 18-i magas érték is, így a feltétel
  azonnal újra teljesül, és új riasztás nyílik → Súlyos. A lezárás a
  riasztást zárja le, a korábbi méréseket nem törli.

## 2. Esedékesség és elmaradás

Az orvos előírást állít be, például: *vérnyomásmérés naponta, 06:00 és 10:00
között, 10 napig.* Az előírás egyes alkalmait egy ütemezett háttérfolyamat
hozza létre menet közben, és ugyanez a folyamat 15 percenként (beállítható)
ellenőrzi a határidőket akkor is, ha semmilyen adat nem érkezik. A folyamat
ismételt futása sem hoz létre dupla alkalmat vagy riasztást.

A mérés a mérés időpontja alapján tartozik egy alkalomhoz; a beteg nem
választ alkalmat. Visszamenőleg legfeljebb két napra lehet mérést rögzíteni,
a rögzítés tényleges ideje külön tárolódik.

| Időpont | Esemény | Alkalom |
|---|---|---|
| szept. 22. 00:00 | A háttérfolyamat létrehozza a 22-i alkalmat (06:00–10:00) | #1 esedékes |
| szept. 22. 07:40 | Mérés érkezik (m1) | #1 teljesítve (m1) |
| szept. 23. 10:15 | A 23-i alkalomra határidőig nem jött mérés | #2 elmulasztva → a státusz Adathiány |
| szept. 24. 08:10 | A beteg rögzíti: „tegnap 19:00-kor mértem" (m2) | #2 késve teljesítve (m2) |
| szept. 24. 08:12 | A beteg rögzíti a mai mérést (m3, mérés ideje 07:30) | #3 teljesítve (m3) |

A mérésrögzítő felület a pótolható alkalmat felajánlja („Tegnap nem
rögzítettél vérnyomást…"), és mentés után kiírja, melyik alkalmat teljesítette
a mérés. Az első elmulasztás a státuszt azonnal Adathiányra állítja;
riasztás az „elmaradt adatküldés" szabályban beállított számú (alapértelmezés
szerint két egymást követő) elmulasztás után keletkezik.

## 3. Szabálymódosítás és adatjavítás

A riasztásokat a rendszer beteg + szabály szerint vonja össze, ezért egy
szabály módosítása után ugyanaz a nyitott riasztás folytatódik. Minden
esemény tárolja az alkalmazott szabályverziót és a kiváltó adatokat.

| Időpont | Esemény | Eseménytörténet |
|---|---|---|
| szept. 16. | Harmadik 140 feletti mérés (m1, m2, m3) | *keletkezett* · v2 (>140 Hgmm, 3× 7 napon belül, közepes) · kiváltó: m1, m2, m3 |
| szept. 19. | Az orvos szigorít: v3 (>135 Hgmm, 3× 7 napon belül, súlyos) | *szabály módosult* v2 → v3 · Dr. Szabó. A riasztás v2 szerinti jelentése nem változik. |
| szept. 20. | Új mérés: m4 = 138/88 — v2 szerint nem, v3 szerint küszöb feletti | *ismételt aktiválódás* · v3 · kiváltó: m2, m3, m4 · súlyosság: közepes → súlyos |
| szept. 21. | A beteg javítja az m3-at (151 helyett 131 volt) → m3′ | *kiváltó adat javítva* · v3 · m3 → m3′ · a feltétel már nem teljesül |
| szept. 21. | A riasztás nem záródik le magától, „kiváltó adat javítva" jelölést kap | Az orvos zárja le indoklással; a beteg ezután Kezelve státuszú. |

Az eredeti m3 megmarad (javítottként), és a szept. 16-i esemény továbbra is
rá hivatkozik. Automatikus lezárás azért nincs, mert a javítást a beteg
végzi, és a rendszer nem tudja ellenőrizni; egy riasztás nem tűnhet el egy
betegoldali módosítás miatt.

**Kérdőív-verzióváltás**

- A beteg azt a verziót tölti ki, amelyik az alkalom létrejöttekor érvényes
  volt, és az alkalomhoz rögzült. Ha az orvos a mai (v3-as) alkalom
  határidejekor kiadja a v4-et, a mai alkalom v3 marad — késve pótlásnál is —,
  a következő alkalom már v4.
- A kiértékelési határok a kérdőívverzió részei, így az új verzió a saját
  pontozásával együtt a saját határait is hozza.
- A romló trend csak azonos verziójú kitöltések között számítódik; verzióváltás
  után a trendvizsgálat újraindul. A grafikonon a verziók külön szakaszként
  jelennek meg („v3 → v4" jelöléssel), a vízszintes tengelyen az alkalom
  dátuma szerepel.

## 4. Kérdőív-pontozás

Egységes szabály: több pont = rosszabb állapot. Skálás kérdésnél a kérdőív
készítője megadja, melyik vég jelenti a jobb állapotot; a rendszer ebből
számítja a pontokat úgy, hogy a jobb vég mindig 0 pont:

- ha a kisebb érték a jobb: pont = válasz − skála minimuma;
- ha a nagyobb érték a jobb: pont = skála maximuma − válasz.

A kész válasz → pont tábla a kérdőívverzióban tárolódik; kitöltéskor a
pontszám ebből olvasódik ki.

| Kérdés | Skála | Válasz | Pont |
|---|---|---|---|
| Hogyan aludt? | 1 = nagyon rosszul … 5 = nagyon jól (a nagyobb a jobb) | 4 | 1 |
| Mennyire fáradt? | 1 = egyáltalán nem … 5 = nagyon (a kisebb a jobb) | 4 | 3 |
| Tapasztalt-e szédülést? | Nem / Ritkán / Naponta: 0 / 2 / 5 pont | Ritkán | 2 |
| | | **Összesen** | **6** → figyelmeztető sáv (6–10 pont) |
