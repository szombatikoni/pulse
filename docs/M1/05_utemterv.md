# Ütemterv (heti bontás)

Vállalt ráfordítás: heti 10–12 óra. A dolgozatírás nem külön fázis: minden
mérföldkő után az addigi eredmények fejezetvázlata elkészül.

| Hét | Időszak | Tartalom |
|---|---|---|
| 1. | szept. 18–27. | **M1 leadás:** javított feladatkiírás, követelmények, E-K diagram, képernyővázlatok, ütemterv; repo és AI-napló naprakész |
| 2. | szept. 29 – okt. 5. | Repo-struktúra (backend/frontend/docker-compose), FastAPI + React skeleton, adatbázis-migrációk (Alembic), auth (JWT, szerepkörök) |
| 3. | okt. 6–12. | Vertikális szelet 1: mérésrögzítés (többértékű méréssel) + egyszerű küszöbszabály + riasztás megjelenítése orvosi oldalon |
| 4. | okt. 13–18. | Vertikális szelet 2: kérdőívkitöltés + pontszám; a teljes folyamat Dockerrel demózható → **M2 (okt. 18.)** |
| 5. | okt. 20–26. | Szabálymotor: mind a 4 szabálytípus + RuleVersion (immutabilis verziózás) |
| 6. | okt. 27 – nov. 2. | Riasztás-magyarázat (kiváltó verzió + adatok); javított mérés → újrakiértékelés; riasztás-életút állapotgép + AlertEvent |
| 7. | nov. 3–9. | Kérdőívszerkesztő + QuestionnaireVersion; deduplikáció; beteg-státusz számítása |
| 8. | nov. 10–16. | Követési tervek (Assignment, életciklus, elmulasztás-szabály); értesítések + e-mail (Mailpit, retry, NotificationDelivery) |
| 9. | nov. 17–22. | Jogosultsági tesztek + a két központi modul tesztkészlete → **M3 (nov. 22.)** |
| 10. | nov. 24–30. | Szintetikus adatgenerátor + beteg-forgatókönyvek; baseline vs. szabálykiértékelés összehasonlítása |
| 11. | dec. 1–7. | Teljesítménymérések (kiértékelés + API-válaszidők, adatlépcsők); CI/CD véglegesítés + nyilvános demókörnyezet |
| 12. | dec. 8–12. | Kiértékelési fejezet, teljes tesztkészlet-ellenőrzés (70%+), dolgozat véglegesítése → **M4 (dec. 12.)** |
| 13. | dec. 13–19. | Tartalék; **hivatalos leadás: dec. 19.** |

**Scope-szelep:** csúszás esetén először a kiértékelési forgatókönyvek száma
és a szerkesztők kényelmi funkciói szűkíthetők; a két központi modul
(szabálymotor verziózással és magyarázattal; verziózott kérdőívek követési
tervekkel) lényege nem.
