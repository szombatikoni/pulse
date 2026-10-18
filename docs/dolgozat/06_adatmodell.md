# Adatmodell

A @abra:adatmodell a teljes tervezett adatmodellt mutatja, 22 entitással. A
mezők a második mérföldkő migrációi szerintiek; a még el nem készült entitások
szaggatott kerettel szerepelnek. Az alábbiakban a fontosabb tervezési döntéseket
írom le. A második mérföldkőig a
felhasználók, profilok és összerendelések, a mérések, a szabályok és
riasztások, valamint a kérdőívek és kirendeléseik táblái készültek el. Az
alkalmak, a megjegyzések és az értesítések a következő mérföldkőben kerülnek
be.

![A PULSE adatmodellje](images/dolgozat_adatmodell.png){#abra:adatmodell}

## Felhasználók, profilok és összerendelés

Minden felhasználó egy `User` sor (e-mail-cím, jelszóhash, szerepkör), a
szerepkörhöz tartozó adatok külön profilban vannak (`PatientProfile`,
`DoctorProfile`). Az orvos és a beteg kapcsolata (`DoctorPatient`) időbeli
érvényességgel rendelkezik: kezdete és vége van. A hozzáférés mindig az
éppen érvényes összerendelésen alapul, így ha az összerendelés megszűnik, az
orvos a következő kérésnél már nem éri el a beteg adatait. Az adatbázis egy
kizáró megszorítással azt is tiltja, hogy ugyanannak az orvos–beteg párnak két
egymást átfedő időszaka legyen.

A betegprofil szándékosan szűk (név, születési dátum). Egy éles rendszerben
további adatok is kellenének (TAJ-szám, elérhetőség), de mivel a rendszer
kizárólag mesterséges adatokkal működik, ezek nem kerültek be. Utólag egy-egy
oszloppal felvehetők.

## Többértékű mérés

A vérnyomás két értékből áll (szisztolés és diasztolés), ezért a méréstípus
komponensekre bomlik (`MeasurementComponent`). Egy mérés (`Measurement`)
komponensenként egy-egy értéksort (`MeasurementValue`) kap. Egyértékű
méréseknél, például a pulzusnál, egyetlen komponens van. A komponens tárolja
a mértékegységet (UCUM-kóddal) és a rögzíthető tartományt. Ez utóbbi csak a
nyilvánvaló elírást szűri ki (például 1400 Hgmm); az orvosi határokat a
szabályok adják. Ezt a mezőt az első tervben még referenciatartománynak
neveztem, de az orvosi nyelvben ez az egészséges értékek szokásos sávját
jelenti, ezért a megvalósításban „rögzíthető tartomány" lett a neve. A
méréstípus és a komponensek LOINC-kódot is kapnak, így egy
későbbi FHIR-exportnál a mérés jelentése egyértelmű.

A mérés két időpontot tárol: mikor mérte a beteg (`measured_at`), és mikor
rögzítette (`recorded_at`). Mérést legfeljebb két napra visszamenőleg lehet
rögzíteni. A mérés ideje dönti el, melyik alkalomhoz tartozik, a rögzítés
ideje pedig azt, hogy a határidőn belül vagy késve érkezett (lásd a Működés
fejezetet). A javítás nem írja felül az eredeti mérést: az
új mérés a `corrected_from` mezővel hivatkozik rá.

### Relációs tárolás vagy dokumentum-adatbázis

A többértékű mérés kézenfekvő példa arra, hol lehetne dokumentum-alapú
tárolást választani: a mérés értékei egyetlen JSON-objektumban
(`{"systolic": 152, "diastolic": 95}`) is elférnének, akár egy
dokumentum-adatbázisban, akár a PostgreSQL JSONB-oszlopában. A normalizált
táblát három okból választottam:

- a szabálykiértékelés komponensenként vizsgál küszöböt, és ehhez a komponens
  külön sor, saját azonosítóval és egységgel;
- új többértékű méréstípus sémamódosítás nélkül felvehető, csak törzsadat kell
  hozzá;
- az adatbázis maga ellenőrzi, hogy egy mérésben minden komponens legfeljebb
  egyszer szerepeljen.

Az adatok többi része is erősen kapcsolódik (orvos, beteg, mérés, szabály,
verzió, riasztás), és több helyen tranzakció kell: a mérés és a riasztás
együtt íródik. Ezek relációs adatbázisban természetesek. Ahol viszont a
szerkezet típusonként eltér, és a tartalom egyben értelmes, JSONB-t
használok: ilyen a szabályverzió paraméterlistája, a kérdőív kiértékelési
sávjai és a válasz → pont tábla.

## Verziózott szabályok és kérdőívek

A szabály (`Rule`) és a kérdőívsablon (`QuestionnaireTemplate`) csak az
identitást hordozza: melyik betegre vonatkozik, ki hozta létre. A tényleges
tartalom verziókban él (`RuleVersion`, illetve `QuestionnaireVersion` a
kérdéseivel). Egy verzió létrejötte után nem módosul; minden változtatás új
verziót hoz létre. Ezt nemcsak az alkalmazás tartja be: az adatbázisban egy
trigger minden módosító és törlő műveletet elutasít ezeken a táblákon.

Erre azért van szükség, mert a riasztás és a kitöltés jelentése a
keletkezéskori verziótól függ. Egy riasztás azt mondja: „a 2. verzió szerint
140 Hgmm felett riaszt, és ez a mérés átlépte"; egy kitöltés azt, hogy „az 1.
verzió pontozása szerint 6 pont, figyelmeztető sáv". Ha a verziót utólag át
lehetne írni, a régi riasztások és kitöltések jelentése is megváltozna.

A kérdőív pontozási táblája is a verzióban tárolódik. A pontszámot kitöltéskor
a rendszer a tárolt táblából olvassa ki, nem kódból számolja, így egy későbbi
kódmódosítás sem írja át a régi kitöltések pontjait. A pontszámok egész
számok, így a sávhatárok vizsgálatánál nem lépnek fel lebegőpontos
kerekítési hibák.

## Riasztás és eseménytörténet

A riasztás (`Alert`) tárolja, melyik szabály melyik verziója nyitotta meg, és
mely adatok váltották ki. Minden további történés egy eseménysor
(`AlertEvent`): ismételt aktiválódás, megtekintés, felelőshöz rendelés,
lezárás, szabálymódosítás, kiváltó adat javítása. Minden esemény a saját
alkalmazott verzióját és kiváltó adatait tárolja, így az eseménytörténetből
minden lépésnél kiolvasható, melyik verzió milyen adat alapján mit
állapított meg. Az eseménytábla csak bővíthető, ezt szintén trigger
biztosítja.

A riasztásokat a rendszer beteg és szabály szerint vonja össze: nyitott
riasztás mellett ugyanarra a párosra új riasztás nem jön létre, hanem
„ismételt aktiválódás" esemény. Ezt egy részleges egyedi index az
adatbázisban is garantálja: egy beteg–szabály párra legfeljebb egy nem lezárt
riasztás lehet.

## Előírás és alkalom

A követési terv eleme az előírás (`Assignment`): mit (mérés vagy kérdőív),
milyen gyakran, milyen határidővel, mettől meddig. Az előírás egyes alkalmai
külön sorok (`AssignmentOccurrence`), saját határidővel, státusszal
(esedékes, teljesítve, késve teljesítve, elmulasztva) és a teljesítő méréssel
vagy kitöltéssel. Az alkalmakat a háttérfolyamat menet közben hozza létre, nem
előre, a teljes időszakra. Így az előírás módosítása vagy visszavonása nem
igényli előre legyártott sorok törlését. Egy egyedi megszorítás (előírás +
határidő) garantálja, hogy a háttérfolyamat ismételt futása sem hoz létre
dupla alkalmat.

Az alkalom a kérdőívverziót is rögzíti: a beteg azt a verziót tölti ki,
amelyik az alkalom létrejöttekor érvényes volt, akkor is, ha közben új verzió
jelent meg.

## Azonosítók

Minden tábla elsődleges kulcsa UUID, nem sorszám. Az elsődleges védelem a
szerveroldali jogosultság-ellenőrzés; az UUID ehhez egy további réteg. A
véletlen azonosítók nem találhatók ki végigpróbálgatással, és nem árulják el,
hány rekord van a rendszerben. Ára a nagyobb tárigény és a kevésbé tömör
index, ami a vállalt adatmennyiségnél nem érdemi hátrány.

## Ami későbbre maradt

Az adminisztratív műveletek általános naplója (`AuditLog`) nem része a
modellnek: a két központi modul elsőbbséget kapott. A riasztások
eseménytörténete a klinikailag fontos lépéseket enélkül is rögzíti.
