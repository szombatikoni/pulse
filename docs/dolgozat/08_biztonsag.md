# Biztonság és jogosultságkezelés

A PULSE egészségügyi jellegű adatok kezelésére készült (a demóban kizárólag
mesterséges adatokkal), ezért a jogosultságot végig a szerveren ellenőrzöm. A felület elrejthet gombokat, de ez csak kényelmi
funkció: minden döntés a backendben születik, az adatbázis aktuális
állapotából. A portokat és a titkok kezelését az Architektúra fejezet írja le.

## Hitelesítés

A felhasználó e-mail-címmel és jelszóval lép be, saját JSON-formátumú
kéréssel (`POST /api/auth/login`). Az e-mail-címet a rendszer kisbetűsítve
tárolja és keresi, így a kis- és nagybetűs írásmód ugyanazt a fiókot jelenti.
A jelszó nem kerül az adatbázisba, csak az Argon2-hash-e (argon2id, a pwdlib
könyvtár ajánlott beállításával). A hash magában hordozza a véletlen sót és a
paramétereket, ezért ezeket külön nem kell tárolni. A hashelés és az
ellenőrzés a `backend/app/core/security.py` fájlban van.

Sikertelen belépésnél mindig ugyanaz a 401-es válasz jön, akár ismeretlen az
e-mail-cím, akár rossz a jelszó, akár le van tiltva a fiók. Ismeretlen címnél
is lefut egy jelszó-ellenőrzés egy próbahash-sel, így a válaszidőből sem
derül ki, létezik-e a fiók. Új fiók legalább 10 karakteres jelszóval hozható
létre; belépéskor viszont csak a felső határt (255 karakter) vizsgálom, hogy a
belépés ne árulja el a szabályt, és egy későbbi szabályváltozás ne zárja ki a
régi fiókokat.

Sikeres belépés után a szerver egy HS256-tal aláírt JWT-t ad. A token csak a
felhasználó azonosítóját, a kiállítás idejét és a lejáratot tartalmazza,
jelszót, szerepkört vagy betegadatot nem. A tartalma bárki számára
olvasható, mert csak kódolt, nem titkosított; a hamisítás ellen az aláírás
véd. Az érvényesség 60 perc, és környezeti változóval állítható. Megújító
token nincs, lejárat után újra be kell lépni. Eredetileg terveztem megújító
tokent, de végül elhagytam: ekkora rendszerhez a 60 perces token és az
újrabelépés elég, a megújító token pedig új, külön védendő felületet nyitott
volna. Továbbfejlesztési lehetőségként tartom számon.

A felület a tokent a böngésző munkamenet-tárolójában (`sessionStorage`)
tartja, és minden kérésnél az `Authorization: Bearer` fejlécben küldi.
Oldalfrissítés után megmarad, a lap bezárásakor törlődik. Ha egy tokennel
küldött kérésre 401 jön, a felület törli a tokent, és a belépőoldalra visz,
ahonnan belépés után visszatér a korábbi oldalra. Ezt azért választottam,
mert ez az egyszerűbb megoldás, és nem kell hozzá CSRF-védelem. Az ára, hogy
egy esetleges XSS-hiba esetén egy támadó szkript kiolvashatná a tokent; a
`httpOnly` süti ez ellen véd, cserébe CSRF-védelmet igényel. Demonstrációs
rendszernél, mesterséges adatokkal ezt a kockázatot vállalhatónak tartottam,
éles rendszerben `httpOnly` sütit használnék CSRF-védelemmel.

A szerepkört szándékosan nem teszem a tokenbe. A szerver minden kérésnél az
adatbázisból tölti be a felhasználót, és ha a fiók nem aktív, 401-et ad. Így
a letiltás nem a token lejártakor, hanem azonnal hat, ami ellensúlyozza, hogy
a JWT lejárat előtt nem vonható vissza. A letiltott fiók belépni sem tud. A
letiltásra ma még nincs felület, az az admin felülettel készül el.

## Szerepkörök és az ellenőrzés helye

Három szerepkör van: beteg, orvos és admin. Az ellenőrzés két szinten
történik, mindkettő a backendben.

Az első szint a FastAPI függőségrendszere (`backend/app/api/deps.py`). A
`get_current_user` függőség ellenőrzi a token aláírását és lejáratát,
betölti a felhasználót, és megnézi, hogy aktív-e; ha bármelyik nem teljesül,
401 a válasz. A `require_roles` függőség-gyár erre épül: a végpont
paraméterében megadott szerepkörön kívül mindenkinek 403-at ad. Ebből három
rövid típus készül (`PatientUser`, `DoctorUser`, `AdminUser`), így a végpont
paramétereiből látszik, ki hívhatja. Bejelentkezés nélkül csak a belépés, az
állapot-ellenőrzés (`/api/health`) és az API-leírás érhető el.

A második szint a betegadat. Erre egyetlen közös függvény van
(`can_access_patient`, `backend/app/services/access.py`), amelyet a végpontok
az `ensure_patient_access` segédfüggvényen keresztül hívnak. A beteg csak a
saját betegprofiljához fér hozzá. Az orvos csak olyan beteghez, akivel a
kérés pillanatában érvényes összerendelése van. Az admin betegadatot
egyáltalán nem ér el. Ma az admin egyetlen végpontja a háttérfolyamat
ellenőrzésének kézi indítása; a felhasználókat és az összerendeléseket a
demóadat-betöltő hozza létre, az admin felület még nem készült el.

## Szerveroldali szűrés

A @abra:biztonsag egy kérés útját mutatja a böngészőtől a tokenellenőrzésen és
a szerepkör-ellenőrzésen át a beteghez szűrt lekérdezésig, valamint azt, hogy
mely szolgáltatások érhetők el a gépről, és melyek csak a belső hálózaton.
Az ábra a teljes láncot mutatja: a szerepkör-ellenőrzés kimarad azoknál a
végpontoknál, amelyeket bármely bejelentkezett szerepkör hívhat.

![A biztonsági architektúra: a kérés útja és a hálózati határok](images/dolgozat_biztonsag.png){#abra:biztonsag}

Az orvos és a beteg összerendelése (`DoctorPatient`) időbeli érvényességgel
rendelkezik: van kezdete, és a vége lehet üres (nyitott) vagy egy időpont. A
hozzáférés mindig az éppen érvényes összerendelésen múlik. Mivel minden kérés
újra lekérdezi, az összerendelés lezárása után a szerver már a következő
kérést elutasítja, egy új összerendelés pedig azonnal megnyitja az adatokat.
A jövőre időzített összerendelés még nem ad hozzáférést. Az adatbázis két
megszorítással védi a táblát: a záró időpont nem lehet a kezdő előtt, és
ugyanarra a párra az érvényességi időszakok nem fedhetik át egymást. A
lezárt sorok megmaradnak, így a korábbi összerendelések visszakereshetők.

A listák ugyanezen az elven szűrnek. Az orvos beteglistája és a Riasztások
oldal is csak az éppen hozzá rendelt betegeket, illetve azok riasztásait
kérdezi le, tehát az idegen beteg nem csak tiltott, hanem meg sem jelenik.

Ha valaki idegen erőforrást kér, a szerver a következőképpen válaszol:

| Helyzet | Válasz |
|----------------------------------------------|-------|
| nincs token, lejárt vagy hibás token, letiltott fiók | 401 |
| rossz szerepkör (pl. beteg egy orvosi végponton) | 403 |
| idegen beteg, vagy nem létező betegazonosító | 403 |
| nem létező vagy idegen riasztás, szabály, illetve mérés javítása | 403 |
| a jogosult beteghez nem tartozó előírás | 404 |
| nem létező kérdőívsablon (a szerkesztőben) | 404 |

A betegadatot érintő erőforrásoknál a nem létező azonosítóra is 403 jön, így
a válaszból nem derül ki, hogy az azonosító létezik-e. Két helyen azonban 404
van: az előírásnál a beteghez való jogosultság ellenőrzése után, ha az
előírás nem ehhez a beteghez tartozik, és a kérdőívsablonoknál, amelyek nem
betegadatok, és bármely orvos szerkesztheti őket.

## A bemenet ellenőrzése

Minden kérés törzsét Pydantic-séma ellenőrzi, mielőtt a szolgáltatáshoz érne;
a hibás bemenetre 422 a válasz. A séma korlátozza a mezők hosszát és a
listák méretét, a mérés idejét csak időzónával fogadja el. A mért értéket a
szolgáltatás a méréstípus tárolt tartományához méri, és a tartományon kívüli
értéket okkóddal utasítja el.

A kérdőívszerkesztő szövegmezőinél (név, kérdés, válaszfelirat, a skála
végfeliratai) szigorúbb a szabály. A szöveg nem tartalmazhat vezérlőkaraktert
(például NUL-t, sortörést vagy tabulátort), és nem állhat csak láthatatlan
karakterből, mert a beteg üres kérdést látna. A pontszámokat és a skála
határait szigorú egészként fogadja el, a `true`, az `"5"` vagy az `5.5`
érték is 422-t kap. A szerkesztőben csak az 1-től 5-ig és az 1-től 10-ig
tartó skála választható.

## A belső CQL-szolgáltatás

A CQL-szolgáltatás és a háttérfolyamat nem nyit portot a gép felé (a
`docker-compose.yml` egyikhez sem rendel `ports` bejegyzést). A backend a
compose belső hálózatán, a `http://cql:8080` címen éri el a motort, így
kiértékelést csak a backenden át lehet kérni, és a NICE-végpont csak a beteg
hozzárendelt orvosának szól.

## A jogosultság tesztjei

A jogosultsági teszteket három csoportba soroltam. A számok
tesztfüggvényeket jelentenek; a paraméterezett tesztek futáskor ennél több
esetet adnak.

| Csoport | Fájlok | Tesztfüggvény | Mit bizonyít |
|------------------|-------------------|------|--------------------------|
| alapok | `test_security.py`, `test_auth_api.py`, `test_access.py` | 7 + 11 + 13 | a hash sózott és ellenőrizhető, a token lejár és nem hamisítható, a belépés minden hibára ugyanazt adja, a letiltott fiók kizárt; a beteg csak a sajátját, az orvos csak a hozzárendeltjét éri el, az admin semmit; az összerendelés lezárása és létrejötte azonnal hat, az átfedő összerendelést az adatbázis elutasítja |
| végpontok | 12 API-tesztfájl (pl. `test_patient_api.py`, `test_alerts_api.py`, `test_rules_api.py`, `test_plans_api.py`) | 42 | idegen orvos, idegen beteg és admin 403-at kap az adott végponton, a nem létező azonosító is 403, az összerendelés lezárása a végpontokon is azonnal hat |
| független | két külön mappa (`tests/independent_*/`) | 145 + 74 | a hitelesítés és a hozzáférés követelményeiből, a meglévő tesztek ismerete nélkül írt tesztek |

A végpontoknál számolt 42 tesztfüggvény mindegyike 403-as választ ellenőriz.
A független teszteket két külön agent írta; a módszert a Tesztelés
fejezet írja le. A böngészős folyamattesztben is van egy eset, amelyben egy
orvos egy idegen beteg adatlapjának címét nyitja meg, és a szerver 403-at ad.

## Ismert korlátok

Néhány hiányosságról tudok, ezeket a negyedik mérföldkőben javítom. A 403 és
a 404 használata még nem egységes. A 422-es válasz a FastAPI alapviselkedése
szerint visszaírja a hibás mező értékét, a belépésnél a jelszót is. A
szerkesztőn kívüli szabad szöveges mezők még nem szűrik a NUL karaktert. Az
alkalmazásszerver (uvicorn) naplójában a kérés címével együtt a beteg
azonosítója is megjelenik.

A PULSE demonstrációs rendszer. Kizárólag mesterséges adatokkal dolgozik, nem
orvostechnikai eszköz, és az orvosi döntést nem pótolja.
