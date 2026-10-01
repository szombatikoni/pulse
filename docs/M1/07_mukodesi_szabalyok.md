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
| Adathiány | valamelyik előírás legutóbbi lejárt alkalma elmaradt, és nem pótolták; vagy nincs friss adat |
| Kezelve | az orvos lezárta a riasztást, de a lezárás óta még nem érkezett rendben lévő adat |
| Rendben | friss, rendben lévő adat van, és a fentiek egyike sem áll fenn |

A lezárás tehát önmagában soha nem ad Rendben állapotot: ahhoz a lezárás után
beérkező, a szabály szerint rendben lévő adat kell. Adat nélkül sincs Rendben:
egy frissen felvett beteg, akinek még nincs mérése vagy kitöltése, Adathiány
státuszú („még nem érkezett adat”). Ahol már lejárt alkalom van, a frissességet
az alkalmak teljesítése adja. Előírás nélkül, illetve az első határidő előtt
akkor friss az adat, ha a legutóbbi mérés vagy kitöltés legfeljebb 7 napos; ez
rendszerszintű beállítás, nem betegenként tárolt érték.

**Példa: lezárás, majd megerősítő mérés**

| Időpont | Esemény | Státusz |
|---|---|---|
| szept. 16. | 7 napon belül a harmadik 140 Hgmm feletti szisztolés érték → közepes riasztás | Figyelem |
| szept. 21. 10:02 | Az orvos lezárja: „Telefonon egyeztettem, gyógyszer módosítva.” | Kezelve — „Dr. Szabó lezárta, megerősítő mérés még nem érkezett” |
| szept. 22. 07:40 | Mérés: 128/82 Hgmm, a szabály rendben lévőnek értékeli | Rendben |

**Ugyanez más kimenettel**

- *A lezárás után elmarad a mérés:* a szept. 22-i alkalom határideje mérés
  nélkül lejár → Adathiány.
- *A lezárás után újra magas a mérés* (szept. 22.: 146/92): a 7 napos
  ablakban még benne van a szept. 16-i és 18-i magas érték is, így a feltétel
  azonnal újra teljesül, és új riasztás nyílik → Figyelem. A lezárás a
  riasztást zárja le, a korábbi méréseket nem törli.

## 2. Esedékesség és elmaradás

Az orvos előírást állít be, például: *vérnyomásmérés naponta, 10:00-ig
(ajánlott kezdés 06:00), 10 napig.* Az előírás egyes alkalmait egy ütemezett háttérfolyamat
hozza létre menet közben, és ugyanez a folyamat 15 percenként (beállítható)
ellenőrzi a határidőket akkor is, ha semmilyen adat nem érkezik. A folyamat
ismételt futása sem hoz létre dupla alkalmat vagy riasztást.

Minden alkalomhoz egy időszak tartozik: napi előírásnál a naptári nap, heti
vagy N napos előírásnál a teljes időköz. A határidő az időszak utolsó napján,
a beállított időpontban van (napi előírásnál tehát aznap 10:00-kor).

- *Melyik alkalomé a mérés?* Amelyiknek az időszakába a mérés időpontja esik;
  a beteg nem választ alkalmat. A 23-án 19:00-kor mért érték a 23-i alkalomé.
- *Időben vagy késve?* Ha a mérést a határidő előtt rögzítik, az alkalom
  teljesítve; ha utána, késve teljesítve. A napon belüli kezdőidő (06:00) csak
  a betegnek szóló ajánlás. Rögzítéskor a rendszer előbb lefuttatja a
  határidő-ellenőrzést, így a határidő után rögzített mérés akkor is késve
  teljesít, ha a háttérfolyamat még nem futott le.
- *Meddig pótolható?* Mérést legfeljebb két napra visszamenőleg lehet
  rögzíteni, így az elmulasztott alkalom az időszaka vége után két napig
  pótolható, utána végleges. A rögzítés tényleges ideje külön tárolódik.
- *Kérdőív:* kitöltést nem lehet visszadátumozni; a kitöltés a legrégebbi,
  még pótolható alkalomhoz rendelődik, a felület ezt pótlásként ajánlja fel.

| Időpont | Esemény | Alkalom |
|---|---|---|
| szept. 22. 00:00 | A háttérfolyamat létrehozza a 22-i alkalmat (időszak: szept. 22., határidő 10:00) | #1 esedékes |
| szept. 22. 07:40 | Mérés érkezik (m1) | #1 teljesítve (m1) |
| szept. 23. 10:15 | A 23-i alkalomra határidőig nem jött mérés | #2 elmulasztva → a státusz Adathiány |
| szept. 24. 08:10 | A beteg rögzíti: „tegnap 19:00-kor mértem” (m2) | #2 késve teljesítve (m2) |
| szept. 24. 08:12 | A beteg rögzíti a mai mérést (m3, mérés ideje 07:30) | #3 teljesítve (m3) |

A mérésrögzítő felület a pótolható alkalmat felajánlja („Tegnap nem
rögzítettél vérnyomást…”), és mentés után kiírja, melyik alkalmat teljesítette
a mérés. Az első elmulasztás a státuszt azonnal Adathiányra állítja;
riasztás az „elmaradt adatküldés” szabályban beállított számú (alapértelmezés
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
| szept. 21. | A riasztás nem záródik le magától, „kiváltó adat javítva” jelölést kap | Az orvos zárja le indoklással; a beteg ezután Kezelve státuszú. |

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
  jelennek meg („v3 → v4” jelöléssel), a vízszintes tengelyen az alkalom
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

## 5. A kiértékelés összehasonlításának beállítása

Ha a szabálymotor 1. típusa (egyszeri küszöbátlépés) ugyanazon a határon fut,
mint az egyszerű küszöbfigyelés, a két módszer csak a riasztások
összevonásában tér el: egy egyszeri kiugrásra mindkettő jelez. Az
összehasonlítás ezért rögzített szabálykonfigurációval fut, amely a
kiértékelési forgatókönyvek minden betegére azonos:

| | Alapvonal (egyszerű küszöbfigyelés) | Szabálykiértékelés |
|---|---|---|
| Mérések | minden 140 Hgmm feletti szisztolés érték külön riasztás | 1. típus csak a kritikus határon (>180 Hgmm, súlyos); 2. típus: ≥3 érték 140 felett 7 napon belül (közepes) |
| Kérdőív | minden határ feletti pontszám külön riasztás | 3. típus: határátlépés vagy romló trend 3 kitöltésen át |
| Adathiány | nincs | 4. típus: 2 egymást követő elmulasztott alkalom |
| Ismétlődés | minden átlépés új riasztás | nyitott riasztás mellett ismételt aktiválódás, nem új riasztás |

Így az „egyszeri kiugrás” forgatókönyvben (egyetlen 152 Hgmm-es érték) az
alapvonal riaszt, a szabálykiértékelés nem, mert az érték a kritikus határ
alatt marad, és az ismétlődési feltétel sem teljesül. A táblázat számai a
kiinduló beállítást adják; a végleges határok a forgatókönyvekkel együtt a
kiértékelési fejezetben rögzülnek.

Az eredmény ettől a választott konfigurációtól függ: ha az 1. típus is a
140-es határon futna, egyszeri kiugrásra a szabálykiértékelés is riasztana.
Ezt a kiértékelési fejezet a korlátok között rögzíti.
