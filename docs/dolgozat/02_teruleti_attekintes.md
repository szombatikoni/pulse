# Területi áttekintés

Ebben a fejezetben négy meglévő rendszert vizsgálok, három kategóriából: két
fogyasztói naplóalkalmazást (SmartBP, mySugr), egy webes adatplatformot
(Tidepool) és egy intézményi távfelügyeleti platformot (Huma). A rendszerekről
szóló állítások a gyártók hivatalos oldalain, az alkalmazásáruházak leírásain és a súgóoldalakon
alapulnak; a mySugr-t és a Tidepoolt személyesen is kipróbáltam. Fontos korlát: nyilvános
anyagokból csak az látszik, amit a gyártó leír. Ha egy funkcióról nem esik
szó, abból nem következik, hogy nincs.

## Háttér

A magas vérnyomás az egyik leggyakoribb krónikus betegség: a WHO becslése
szerint 2024-ben világszerte 1,4 milliárd 30–79 éves felnőttet érintett, ez a
korosztály 33%-a [@who-hypertension]. Egy friss metaanalízis szerint az
otthoni vérnyomásmérés csökkenti a vérnyomást, különösen akkor, ha
távfelügyelettel vagy további orvosi támogatással párosul [@satoh2025-hbpm].
Az otthon mért adat tehát akkor ér a legtöbbet, ha valaki rendszeresen
ránéz, és szükség esetén reagál. Ehhez szolgál az orvosi oldal.

## Fogyasztói naplóalkalmazások

### SmartBP

A SmartBP vérnyomásnapló iOS-re és Androidra. A beteg kézzel rögzíti a
méréseit, az alkalmazás kiszámolja a pulzusnyomást, az artériás
középnyomást (MAP) és a testtömegindexet. A méréseket színkódolva
kategóriákba sorolja, a határok módosíthatók. PDF- és CSV-riportot készít,
amelyet e-mailben is el lehet küldeni [@smartbp-appstore]. Betegeknek szóló
webes felületet sem a gyártó oldalán, sem az áruházakban nem találtam.

2026 szeptemberében megjelent egy ingyenes, webes klinikusi felület (SmartBP
Clinic Care). A beteg egy klinikai kóddal csatlakozik, az orvos pedig hétnapos
átlagokat, trendeket, mérési aktivitást, gyógyszereket és riportokat lát
[@smartbp-clinic]. A nyilvános leírás szabályokról, riasztásról vagy
kérdőívekről nem szól.

### mySugr

A Roche mySugr alkalmazása cukorbetegeknek szóló napló: kézi rögzítés,
vércukormérők csatlakoztatása, PDF- és Excel-riport
az orvos számára. Az EU-ban orvostechnikai eszköz (a napló IIa, a
bóluskalkulátor IIb osztályú), és csak kiválasztott országokban érhető el
[@mysugr-site]. A magyar App Store-ban elérhető és telepíthető; 2026. október
15-én telepítettem és kipróbáltam. A céltartományt itt is a beteg állítja be a
saját beállításai között (alapértelmezés: 70–180 mg/dl), és testsúlycélt is
megadhat, amely a naplóban a testsúlyértékek színezését adja. A PDF-riport a
fizetős (PRO) változat része. Az eszközcsatlakozásoknál az alkalmazás maga
jelzi, hogy a lista országonként eltérhet, és a helyi engedélyezéstől függ.

> **Jóváhagyandó:** 1–2 képernyőkép ide is kerülhet (például a céltartomány
> beállítása és a riport-képernyő a PRO jelöléssel).

A termék változik: a pumpavezérlő funkció 2026 júniusában megszűnt, a napló
és a bóluskalkulátor megmaradt [@mysugr-pumpcontrol]. A Roche CGM-szenzorához
tartozó alkalmazások pedig a mySugr-be olvadnak [@accuchek-mysugr-switch].

## Webes adatplatform: Tidepool

A Tidepool nonprofit szervezet, a szoftvere nyílt forráskódú
[@tidepool-about]. Kizárólag diabéteszadattal foglalkozik: inzulinpumpák,
folyamatos glükózmonitorok és vércukormérők adatait gyűjti. Az adat egy
telepítendő feltöltőprogrammal, az eszközgyártók felhőjével való
összekapcsolással vagy mobilalkalmazással érkezik [@tidepool-devices]. A webes
felületre vonatkozó dokumentáció csak szöveges jegyzet rögzítését írja le
[@tidepool-daily-view]; a saját tesztem is ezt mutatta. Az adatot a beteg egy klinikai megosztókóddal vagy
e-mailben oszthatja meg [@tidepool-sharing], és Excel- vagy JSON-fájlba
exportálhatja [@tidepool-export].

A céltartományt alapesetben a beteg állítja be a saját fiókjában
[@tidepool-target-range]. A klinikai csomagban (Tidepool+) a klinikus is
rendelhet célt a beteghez, előre beállított célok közül
[@tidepool-glycemic-targets]. A TIDE-felület pedig glikémiás kategóriák
szerint automatikusan rangsorolja a betegeket; az egyik kategória az alacsony
szenzorviselési idő, vagyis az adathiány [@tidepool-tide]. A csomagok közül
az alap 250 betegig ingyenes, a bővebb betegszám szerint fizetős
[@tidepool-plus-plans].

**Saját kipróbálás.** A webes felületet saját fiókkal kipróbáltam (utoljára
2026. október 15-én); a feltöltőprogramot és a mobilalkalmazást nem. A webes
felületen a dokumentációval egyezően nincs kézi mérésrögzítés: az „Upload
Data" a feltöltőprogram letöltését kéri (Mac vagy Windows). A céltartomány a
beteg saját profilbeállítása (alsó és felső határ, visszaállítható az
alapértékre).

A @abra:tidepool a profiloldal céltartomány-beállítását mutatja: az alsó és a
felső határt a beteg adja meg, a mintagrafikon pedig szemlélteti, hogyan
jelenik meg a sáv.

![A Tidepool céltartomány-beállítása a beteg profiljában (saját kipróbálás, 2026. október 15.)](docs/files/kepek/tidepool/tidepool_celtartomany_abra.png){#abra:tidepool}

## Intézményi távfelügyelet: Huma

A Huma platformja betegalkalmazásból és webes klinikusi portálból áll. A
beteg vitális jeleket és validált kérdőíveket küld; a portál a klinikus által
megadott küszöbök alapján jelöli meg a figyelmet igénylő betegeket, és
betegcsoportok szerinti priorizálást ad [@huma-hospital-at-home]. A platform
2023-ban betegségtől független szoftverként EU MDR IIb osztályú tanúsítást
kapott [@huma-mdr]. 2024-ben Huma Cloud Platform néven programozás nélkül
konfigurálható formában indult, intézményi partnerekkel (gyógyszergyárak,
egészségügyi szolgáltatók) [@huma-cloud-platform]. Nyilvános árazást és
önkiszolgáló regisztrációt nem találtam, a hozzáférést kérni kell
[@huma-workspace].

## Összehasonlítás

A @abra:osszehasonlitas a négy vizsgált rendszert és a PULSE-t veti össze. A
jelölések a fejezetben hivatkozott forrásokon [@smartbp-appstore;
@smartbp-clinic; @mysugr-site; @mysugr-appstore; @tidepool-devices;
@tidepool-glycemic-targets; @tidepool-tide; @tidepool-plus-plans;
@huma-hospital-at-home; @huma-workspace] és a mySugr, illetve a Tidepool saját
kipróbálásán (2026. október 15.) alapulnak. Pipa és kereszt csak ott áll, ahol
ezt forrás vagy saját megfigyelés alátámasztja; ha egy funkcióról a nyilvános
leírás nem szól, azt külön jel mutatja, mert ebből nem következik, hogy nincs.

![A vizsgált rendszerek és a PULSE összevetése](images/dolgozat_osszehasonlitas.png){#abra:osszehasonlitas}

## A PULSE helye

Az első tervezéskor abból indultam ki, hogy a fogyasztói alkalmazásoknak
nincs orvosi oldaluk. Ez mára nem igaz: a SmartBP 2026 szeptemberében
klinikusi felületet indított, a Tidepool pedig automatikusan priorizálja a
betegeket. Ez megerősíti, hogy az otthoni adat orvosi feldolgozása valós
igény. A PULSE ezért nem azzal tér el, hogy van orvosi oldala, hanem a
következőkkel:

1. **Egy helyen a mérés, a kérdőív és a jelzés.** A vizsgált fogyasztói
   alkalmazások egy-egy betegség köré épülnek: a SmartBP a vércukrot nem
   kezeli, a mySugr a vérnyomást is rögzíti [@mysugr-manual], de a vércukorra
   épül, és állapotkérdőívről egyik leírása sem szól. A PULSE a betegnek és
   az orvosnak egy felületen adja a több mérést, a kérdőíveket és a belőlük
   számított közös státuszt. A vizsgált rendszerek közül a mérést és a
   kérdőívet együtt csak a Huma kezeli, az is csak intézményeknek.
2. **Az orvos által beállított, többféle szabály.** A rendszer nemcsak
   egyszeri küszöböt figyel, hanem időablakos ismétlődést, kérdőív-trendet és
   elmaradt adatot is, betegenként paraméterezve.
3. **Magyarázható, verziózott riasztás.** Minden riasztásnál látszik, melyik
   szabály melyik verziója, mely adatok alapján jelzett. A vizsgált rendszerek
   nyilvános anyagai ilyet nem írnak le.
4. **Az adathiány önálló jelzés.** Ha nincs friss adat, a státusz Adathiány,
   nem Rendben. A Tidepool szenzorviselési kategóriája hasonló gondolat, ami
   igazolja az irányt.

A PULSE demonstrációs rendszer, nem termék. Az összevetés célja nem az, hogy
jobbnak mutassam a meglévőknél, hanem hogy megmutassam, melyik tervezési
kérdésre ad saját választ.
