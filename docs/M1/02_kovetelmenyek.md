# Követelmények

## Funkcionális követelmények

### Hitelesítés és szerepkörök
- **F1.** A rendszer e-mail + jelszó alapú bejelentkezést nyújt (JWT); három
  szerepkört különböztet meg: beteg, orvos, admin.
- **F2.** Minden végpont szerveroldalon szűr szerepkör és hozzárendelés
  szerint: a beteg csak a saját adatait éri el; az orvos csak a hozzá rendelt
  betegek adatait; az admin az adminisztratív erőforrásokat.
- **F3.** Az orvos–beteg összerendelés időbeli érvényességgel rendelkezik;
  megszüntetésekor a hozzáférés azonnal megszűnik, létrejöttekor kinyílik.

### Beteg
- **F4.** A beteg méréseket rögzíthet a törzsadatokban definiált
  méréstípusokhoz; a többértékű mérés támogatott (pl. vérnyomás:
  szisztolés + diasztolés érték egy mérésben).
- **F5.** A beteg megtekintheti mérési előzményeit listában és grafikonon,
  méréstípusonként, időszakszűréssel.
- **F6.** A beteg látja esedékes teendőit (előírt mérések, kitöltendő
  kérdőívek határidővel), és kitöltheti a kirendelt kérdőíveket.
- **F7.** A beteg utólag javíthatja hibásan rögzített mérését; a javítás
  újrakiértékelést vált ki, és az esemény rögzül az érintett riasztás
  történetében.
- **F8.** A beteg értesítést kap esedékes teendőiről (felületi értesítés +
  e-mail).

### Orvos
- **F9.** Az orvos priorizált beteglistát lát zöld/sárga/piros/szürke
  státusszal; a szürke jelentése: nincs elég friss adat. A státusz a nyitott
  jelzésekből számítódik.
- **F10.** Az orvos beteg-részletes oldalt lát: grafikonok küszöbvonalakkal,
  mérési és kitöltési előzmények, riasztások magyarázattal, megjegyzések.
- **F11.** Az orvos a négy szabálytípust paraméterezheti betegenként:
  (1) egyszeri küszöbátlépés (méréstípus, min/max, súlyosság);
  (2) időablakos ismétlődés (≥N eltérés M napon belül);
  (3) kérdőív-pontszám határátlépése vagy romló trend K kitöltésen át;
  (4) elmaradt adatküldés jelzése.
- **F12.** Minden szabálymódosítás új, immutabilis szabályverziót hoz létre;
  a riasztás a keletkezéskori verzióra hivatkozik.
- **F13.** Az orvos kérdőívsablonokat szerkeszthet: skálás (1–5, 1–10) és
  egy-/többválasztós kérdések, kérdésenkénti pontszám, kiértékelési határok.
  Minden sablonmódosítás új, immutabilis kérdőívverziót hoz létre; a kitöltés
  a kitöltéskori verzióra hivatkozik.
- **F14.** Az orvos követési tervet állít össze: mit, milyen gyakran, milyen
  határidőre; a kirendelés életciklusa: kirendelve → esedékes →
  teljesítve/elmulasztva.
- **F15.** Az orvos kezeli a riasztásokat: megtekintés, felelőshöz rendelés,
  lezárás kötelező indoklással; minden váltás eseményként rögzül
  (ki, mikor, mit).
- **F16.** Az orvos megjegyzéseket fűzhet a beteghez.

### Riasztási alrendszer
- **F17.** Minden riasztás tárolja a kiváltó szabályverziót és a konkrét
  adat-azonosítókat; ezekből a felületen olvasható magyarázat jelenik meg.
- **F18.** Deduplikáció: nyitott riasztás mellett ugyanarra a beteg+szabály
  párosra új kiváltó adat nem új riasztást, hanem "ismételt aktiválódás"
  eseményt hoz létre (a súlyosság emelkedhet).
- **F19.** A riasztás létrejötte adatbázis-tranzakcióban történik; az
  e-mail-küldés ettől elkülönítve, újrapróbálkozással fut, kézbesítése külön
  nyilvántartott. Sikertelen e-mail nem jelent elveszett riasztást.

### Admin
- **F20.** Az admin felhasználókat hoz létre és kezel, orvos–beteg
  összerendeléseket kezel, méréstípus-törzsadatokat karbantart.

## Nem-funkcionális követelmények

- **NF1. Biztonság:** JWT-alapú hitelesítés; jelszavak hashelve; a
  jogosultsági szabályok szerveroldalon érvényesülnek, és célzott automatizált
  tesztek igazolják (idegen beteg adatának elérése tiltott; összerendelés
  változása azonnal érvényesül).
- **NF2. Auditálhatóság és magyarázhatóság:** a riasztások és kitöltések
  jelentése utólag nem változhat (immutabilis verziók); a riasztásokhoz teljes
  eseménytörténet tartozik.
- **NF3. Tesztelés:** pytest-alapú tesztkészlet, legalább 70% lefedettség;
  kiemelt esetek: szabályhatárok, időablak-szélek, hiányos/javított adat,
  kérdőívverzió-váltás, deduplikáció, e-mail-hibaág, teljes folyamat a
  bevitel­től a riasztás lezárásáig.
- **NF4. Teljesítmény:** a kiértékelés futásideje és a kulcs API-végpontok
  válaszideje mérve, növekvő adatmennyiségnél (nagyságrendi lépcsők),
  táblázatban és grafikonon dokumentálva.
- **NF5. Telepíthetőség:** Docker + docker-compose alapú, reprodukálható
  telepítés; GitHub Actions CI/CD; nyilvános demókörnyezet.
- **NF6. Dokumentáltság:** OpenAPI/Swagger a FastAPI-ból generálva; fejlesztői
  dokumentáció a repóban.
- **NF7. Nemzetköziesítés:** a felület i18next-alapú, magyar és angol nyelven.
- **NF8. Korlátok (disclaimer):** a rendszer demonstrációs célú, kizárólag
  mesterséges adatokkal működik; nem orvostechnikai eszköz, nem helyettesít
  orvosi döntést.
