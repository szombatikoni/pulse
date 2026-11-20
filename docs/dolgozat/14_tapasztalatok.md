# Tapasztalatok, továbbfejlesztési lehetőségek

## A tervezés és az ütemezés tapasztalatai

A munkát négy mérföldkőre bontottam, mindegyikhez határidővel és a
témavezetővel egyeztetett tartalommal. Az első mérföldkő anyaga szeptember
27-én, a technikai próba október 18-án készült el, a harmadik mérföldkő
kódja október 30-án indult. A kód nagyobb egységekben került a repóba, ezért
a commitok jó része három-négy napra esik.

Nem rögzített napi beosztás szerint dolgoztam. Amikor az időm engedte,
leültem, és addig haladtam, ameddig tudtam. Amikor munkahelyi vagy tanulmányi
teendőim akadtak, kevesebbet tudtam a dolgozattal foglalkozni, mint
szerettem volna.

A harmadik mérföldkő előtt a feladatokat tételekre bontottam, a saját
óráimra becsülve. A becslés 82,5 órát adott, miközben az eredeti heti
keretből öt hét alatt 50 és 60 óra között jött ki. Akkor a szűkítés helyett
a heti időm megemelése mellett döntöttem. Az első hét így is kódmunka
nélkül telt el, ezért október 28-án újraütemeztem a tételeket, és a
tartalék ezzel elfogyott. Egy tervjavaslat például tényként állította, hogy
nem kell új adatbázis-migráció, a megvalósításkor mégis kellett.

Ha újrakezdeném, több időt hagynék a feladatokra. Jobb, ha a becslés bővebb,
és a feladat előbb készül el, mint fordítva. A becslés különösen nehéz, amikor
addig nem használt technológiát kell alkalmazni. Az utólagos ellenőrzésekre
is több időt kellett volna szánnom.

A témavezető első visszajelzése után a működési szabályokat (a beteg
státusza, az esedékesség és az elmaradás, a verzióváltás, az adatjavítás)
még a kód előtt, dátumozott példákon rögzítettem; ezek a Működés fejezet
példái. A harmadik mérföldkőben a példákat egyenként összevetettem a
tesztekkel, és ahol hiányzott, új teszt készült. A tesztek három eltérést
mutattak ki, egy közös okkal: a kódban a beteg státusza csak a pótlási idő
lejárta után váltott Adathiányra, a leírt szabály szerint viszont már a
határidő után. Úgy döntöttem, hogy a kód igazodik a dolgozathoz. A három
közül egy, a szóhasználati eltérés (az „elmulasztva" kifejezés a még
pótolható alkalomra) még nyitott.

Azért a kódot igazítottam, mert a dolgozat szabályait a témavezetőmmel
folytatott egyeztetések alapján építettem fel, és amit ő elfogadott, azt nem
akartam felborítani.

A kód és a dolgozat közben többször elvált egymástól. Az első
fejezettervezeteket egy független átnézés vetette össze a kóddal, és
például elavult mezőneveket talált az adatmodell-ábrán. Novemberben négy
fejezetben kellett az elavult részeket a kód állapotához igazítani.

A független kódátnézések kritikus hibát nem találtak. Leleteik többnyire
szélső esetek voltak: határidő az óraátállítás körül, február 29-én
született beteg életkora, egyidejű műveletek versenyhelyzete, elavuló
gyorsítótár, túl nagy kérés a CQL-szolgáltatás felé. Ezeket a meglévő
tesztek addig nem fedték le.

## Továbbfejlesztési lehetőségek

A rendszer több irányban bővíthető a leadás után:

- **A klinikai irányelv mélyebb beépítése.** A NICE-ajánláson alapuló
  kiértékelés most tájékoztató panel az orvosnál: az eredménye nem
  tárolódik, és nem hat a riasztásra és a státuszra. Önálló szabálytípusként
  a saját szabályok mellett is kiváltó oka lehetne egy jelzésnek.
- **Valódi FHIR-kapcsolat.** A rendszer most FHIR R4 szerinti csomagot ad ki
  (hivatalos validátorral még nem ellenőrizve), de
  más egészségügyi rendszerrel nem cserél adatot. A következő lépés egy
  külső FHIR-szerverrel való kétirányú kapcsolat, és az irányelvek
  protokoll-leírásainak (PlanDefinition, CarePlan) közvetlen átvétele lenne.
- **Eszközintegráció.** A mérések most kézi rögzítéssel kerülnek be. A
  vérnyomásmérők és vércukormérők adatainak automatikus átvétele csökkentené
  a beteg terhét és az elgépelés esélyét.
- **Erősebb belépés.** Kétlépcsős azonosítás megbízható eszközzel, vagy
  jelszó nélküli belépés.
- **A vállalás határán kívül eső funkciók.** A gyógyszerelés kezelése, az
  időpontfoglalás és a kétirányú üzenetküldés tudatosan maradt ki; most
  csak egyirányú orvosi visszajelzés van a riasztás lezárásakor.

## Összegzés

[KÉSŐBB: összegzés a kiértékelés eredményei után]
