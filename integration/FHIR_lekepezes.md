# A követési terv leképezése FHIR R4 erőforrásokra

Ez a dokumentum a szakdolgozat Működés fejezetének „A követési terv illesztése
szabványos protokoll-leíráshoz" szakaszát egészíti ki: a teljes leképezési
táblázatot és egy példát tartalmaz. Terv, nem megvalósítás: a PULSE az itt
felsorolt erőforrások közül ma csak az Observation és a QuestionnaireResponse
erőforrást adja ki (a hivatkozott Questionnaire erőforrással együtt).

A PULSE-oldal a jelenlegi adatmodell tábla- és mezőneveit használja, a
FHIR-oldal az R4 (4.0.1) specifikációt követi; a felhasznált oldalak a
dokumentum végén vannak. Az illeszkedés fokai: teljes (mezőről mezőre, azonos
jelentéssel), részleges (információ vész el, vagy konvenció kell), nincs
(a másik oldalon nincs megfelelője). A CarePlan egy tevékenységénél a detail
és a reference közül csak az egyik adható meg; a 18–20. sor a beágyazott, a
22. sor a hivatkozott változatot írja le.

## Leképezési táblázat

Protokollszint (PlanDefinition, ActivityDefinition, Library):

| # | FHIR R4 elem | PULSE-megfelelő | Illeszkedés | Megjegyzés |
|------|----------------------|--------------------|------------|----------------------|
| 1 | `PlanDefinition` azonosítása: `url`, `version`, `name`, `type` (pl. clinical-protocol), `status` (draft, active, retired, unknown) | nincs | nincs | Nincs protokolltábla; minden előírás és szabály betegre készül. |
| 2 | `PlanDefinition.relatedArtifact` (`type` = citation, `citation`, `url`) | nincs adatként; a CQL-fájl fejléce és a dolgozat forrásjegyzéke | nincs | A forrás (NICE NG136, 1.2.7 és 1.4.22) szövegben azonosítható, adatban nem. |
| 3 | `PlanDefinition.library` | nincs | nincs | A `rule_versions` sorai és a CQL-könyvtár között nincs hivatkozás. |
| 4 | `PlanDefinition.action.definition[x]` (ActivityDefinition, PlanDefinition vagy Questionnaire canonical url-je) | `assignments.target_kind`, és `measurement_type_id` vagy `questionnaire_template_id` | részleges | A cél megvan, de betegszinten; kérdőívnél a canonical url ma is előáll a sablon kódjából. |
| 5 | `PlanDefinition.action.timing[x]` (köztük Timing) | `assignments.frequency` (daily, weekly, every_n_days), `interval_days`, `suggested_time`, `due_time` | részleges | Csak betegszinten van; a Timing jóval gazdagabb (lásd a 19. sort). |
| 6 | `PlanDefinition.action.condition` (`kind`: applicability, start, stop; `expression`) | `rule_versions.rule_type` és `params` | részleges | Jelentéseltérés: a FHIR-feltétel egy tevékenység alkalmazhatóságát dönti el, a PULSE-szabály riasztást nyit. |
| 7 | `PlanDefinition.goal.target` (`measure`, `detail[x]`, `due`) | a szabályverzió küszöbei és időablaka; a CQL célérték-paraméterei | részleges | Egy célérték leírható; az életkortól függő cél két célként vagy feltétellel írható le. |
| 8 | `ActivityDefinition.code` | `measurement_types.loinc_code` (pl. 85354-9) | részleges | A LOINC-kód a mérés eredményét kódolja, nem a mérés elvégzését; konvencióval használható. |
| 9 | `ActivityDefinition.observationResultRequirement`, ObservationDefinition-re (`code`, `quantitativeDetails.unit`, `qualifiedInterval` absolute kategóriával) | `measurement_components` (`loinc_code`, `unit`, `min_value`, `max_value`) | részleges | Az absolute kategória a lehetséges értékek tartománya, ez felel meg a rögzíthető tartománynak. A reference és a critical kategóriának nincs megfelelője a törzsadatban: az orvosi határokat a PULSE a szabályokban tárolja. |
| 10 | `Library` azonosítása: `url`, `version`, `name`, `type` (logic-library), `status` | a CQL-fájl könyvtárdeklarációja: `library PulseHbpmAverage version '0.1.0'` | részleges | Fájlban van, adatbázisban nem. A `type` R4-ben kötelező. A CQL-szolgáltatás minden kiértékelésnél visszaadja a könyvtár azonosítóját, verzióját és lenyomatát. |
| 11 | `Library.content` (Attachment; `contentType`, pl. text/cql) | `integration/cql/PulseHbpmAverage.cql`; a lefordított ELM (`integration/elm/`) a CQL-szolgáltatás image-ében | részleges | A CQL-forrás text/cql tartalomként leírható; az ELM JSON formájának tartalomtípusát az R4 Library-oldala nem nevezi meg. |
| 12 | `Library.parameter` (ParameterDefinition: `name`, `use` = in, `type`, `min`, `max`) | a CQL 11 `parameter` deklarációja (pl. `"Exclude First Day" Boolean default true`) | részleges | A név, a típus és az irány egy az egyben leírható; az alapérték elvész, mert a ParameterDefinition-ben nincs eleme. |
| 13 | `Library.dataRequirement` (`type` = Observation, `codeFilter.code`) | a CQL lekérése (`[Observation: "Blood pressure panel"]`); `measurement_types.loinc_code` | teljes | A specifikáció szerint a `$data-requirements` művelet a CQL lekéréseiből is előállíthatja ([Using Expressions](https://hl7.org/fhir/R4/clinicalreasoning-topics-using-expressions.html)); nem próbáltam ki. |
| 14 | `Library` (logic-library) a négy saját szabálytípusra | `rule_versions.rule_type` és a szabálykiértékelő szolgáltatás (Python-kód) | nincs | A négy szabálytípus logikája kódban van, nem cserélhető artefaktum; csak a paraméterek szerkezete írható le ParameterDefinition-nel. |

Betegszint (CarePlan, ServiceRequest, Task):

| # | FHIR R4 elem | PULSE-megfelelő | Illeszkedés | Megjegyzés |
|------|----------------------|--------------------|------------|----------------------|
| 15 | `CarePlan` (`subject`, `status`, `intent` = plan, `period`) | nincs tárolt terv; a beteg `assignments` sorainak összessége | részleges | A CarePlan kiadáskor összeállítható lenne; a `status` és a `period` számított érték. |
| 16 | `CarePlan.instantiatesCanonical` (PlanDefinition, Questionnaire, Measure, ActivityDefinition, OperationDefinition) | nincs | nincs | Az előírás nem rögzíti, melyik protokollból készült; ehhez a PULSE-ban sincs mező, és protokolltábla sincs, amelyre mutathatna. |
| 17 | `CarePlan.author` | `assignments.assigned_by` | részleges | A PULSE-ban előírásonként van, a CarePlan-ben tervenként; előírásonként a `ServiceRequest.requester` illik hozzá. |
| 18 | `CarePlan.activity.detail.code` vagy `.instantiatesCanonical` | `measurement_types.loinc_code`; kérdőívnél a canonical url | részleges | Mindkét cél kódja, illetve url-je ma is előáll, de a LOINC-kód a mérés eredményét kódolja, nem a mérés elvégzését (mint a 8. sorban). |
| 19 | `CarePlan.activity.detail.scheduled[x]`, Timing-ként (`repeat`: `frequency`, `period`, `periodUnit`, `bounds[x]`, `timeOfDay`) | `frequency`, `interval_days`, `start_date`, `end_date`, `suggested_time` | részleges | A gyakoriság és az időszak leírható; a határidő (`due_time`, az időszak utolsó napján) és a pótlási idő (mérésnél az időszak vége után 48 óra) nem. |
| 20 | `CarePlan.activity.detail.status` (not-started, scheduled, in-progress, on-hold, completed, cancelled, stopped, unknown, entered-in-error) és `statusReason` | számított állapot (érvényes, később kezdődő, lejárt, visszavont) a `start_date`, `end_date` és `revoked_at` alapján; indoklás: `revoke_note` | részleges | A PULSE nem tárolja, hanem számolja. A visszavonás a stopped vagy a cancelled állapotnak felel meg (konvenció); az indoklás a `statusReason` szövegébe férne. |
| 21 | `CarePlan.replaces`, `ServiceRequest.replaces` | módosításkor a régi előírás visszavonva, az új azonos célú előírás ott kezdődik, ahol a régi véget ért; a láncot a rendszer az adatból olvassa ki | részleges | A FHIR tárolt hivatkozást vár. |
| 22 | `ServiceRequest` előírásonként (`instantiatesCanonical`, `basedOn` CarePlan-re, `status`, `intent` = order, `code`, `occurrenceTiming`, `requester`, `authoredOn`) | egy `assignments` sor | részleges | A legközelebbi megfelelő; a revoked állapot a `revoked_at`-nak felel meg. A szabvány szerint a beavatkozást a beteg maga is végezheti. Az `instantiatesCanonical` csak ActivityDefinition-re vagy PlanDefinition-re mutathat, kérdőívre nem; az előírás létrehozási ideje (`authoredOn`) nincs tárolva. |
| 23 | `Task` alkalmanként (`focus` a ServiceRequest-re, `for` a betegre, `restriction.period`, `executionPeriod`) | egy `assignment_occurrences` sor (`period_start`, `due_at`, `fulfilled_at`) | részleges | Saját konvenció, nem a szabvány előírása. A PULSE-ban négy időpont van (az időszak kezdete, a nem tárolt, hanem számolt vége, a határidő és a pótlási idő vége), a `restriction.period` egyetlen időszak. A letiltott időszakba eső határidejű alkalom nem jön létre, így Task sem tartozna hozzá. |
| 24 | `Task.status` (draft, requested, received, accepted, rejected, ready, cancelled, in-progress, on-hold, failed, completed, entered-in-error) | `assignment_occurrences.status` (due, fulfilled, fulfilled_late, missed) | részleges | due ≈ ready; fulfilled ≈ completed; fulfilled_late ≈ completed, a késés elvész (legfeljebb a `businessStatus`-ban maradhat meg); a missed nagyjából a cancelled állapotnak felel meg (a failed hibát jelent, nem mulasztást). |
| 25 | `Task.output.value[x]` (hivatkozás Observation-re vagy QuestionnaireResponse-ra) | `assignment_occurrences.measurement_id`; kérdőívnél `submissions.occurrence_id` | teljes | Az alkalom és a teljesítő adat kapcsolata megvan. |
| 26 | `Task.input` (pl. a kérdőív canonical url-je a verzióval) | `assignment_occurrences.questionnaire_version_id` | részleges | Az alkalom létrehozásakor érvényes kérdőívverzió rögzítése PULSE-sajátosság; FHIR-ben csak konvencióval írható le. |

Eredményszint (Observation, QuestionnaireResponse, riasztás):

| # | FHIR R4 elem | PULSE-megfelelő | Illeszkedés | Megjegyzés |
|------|----------------------|--------------------|------------|----------------------|
| 27 | `Observation` (`code` LOINC-kóddal, `component`, `valueQuantity` UCUM-kóddal, `effectiveDateTime`, `issued`, `subject`) | `measurements`, `measurement_values`, `measurement_components` | teljes | A rendszer ma is kiadja: `measured_at` → `effectiveDateTime`, `recorded_at` → `issued`. |
| 28 | `Observation.basedOn` (CarePlan, ServiceRequest és más kérések; Task nem) | fordított irányban: `assignment_occurrences.measurement_id` | részleges | A modellben megvan, a kiadás ma nem írja ki. Az alkalom szintje (Task) sem a `basedOn`, sem a `partOf` elembe nem fér. |
| 29 | `Observation.status` (amended, corrected) | `measurements.corrected_from` (új sor, az eredeti megmarad) | részleges | A FHIR a javítást a mérés amended vagy corrected státuszával jelöli; a PULSE új sort hoz létre, láncban. A kiadásban ma csak a lánc utolsó eleme szerepel, final státusszal. |
| 30 | `QuestionnaireResponse` (`questionnaire` canonical url-je a verzióval, `status`, `subject`, `authored`, `item.answer`) | `submissions`, `answers` | teljes | A rendszer ma is kiadja, a kitöltéskori verzióra hivatkozva. |
| 31 | `QuestionnaireResponse.basedOn` (CarePlan, ServiceRequest) | `submissions.occurrence_id` | részleges | Mint a 28. sor. |
| 32 | `Observation.derivedFrom` QuestionnaireResponse-ra (a pontszám külön Observation-ként) | `submissions.total_score`, `answers.score`; a sávok: `questionnaire_versions.scoring_thresholds` | részleges | A pontszám külön Observation lehetne; ma szándékosan nem kerül ki, mert a beteg sem látja. |
| 33 | `DetectedIssue` (`patient`, `identified[x]`, `severity`: high, moderate, low; `implicated`, `evidence.detail`, `detail`) | `alerts` (`patient_id`, `created_at`, `severity`: moderate, severe; `trigger_data_ids`, `rule_version_id`) | részleges | A mezők illeszkednek (közepes ≈ moderate, súlyos ≈ high; `trigger_data_ids` → `evidence.detail`), de a DetectedIssue egy tervezett vagy folyamatban lévő klinikai tevékenység problémájára való; a technikai jellegű problémákat (például a hiányos adatot) a szabvány az OperationOutcome erőforráshoz utalja. |
| 34 | `DetectedIssue.mitigation` (`action`, `date`, `author`) | lezárás: `alert_events` (closed, `reason`, `actor_id`, `created_at`) | részleges | A lezárás leírható; a `mitigation.action` kötelező; a PULSE szabad szöveges indoklása a szöveges (text) elemébe férne. |
| 35 | `Flag` (`status`: active, inactive, entered-in-error; `code`, `subject`, `period`) | a beteg számított státusza (Súlyos, Figyelem, Adathiány, Kezelve, Rendben) | részleges | A beteg összesített állapotjelzőjére illik; egyes riasztásra nem, mert a Flag nem egy adott személynek szóló jelzés. |
| 36 | `Task` mint munkafolyamat (`owner`, `status`) | `alerts.assigned_to`, `alerts.status` (new, seen, assigned, closed) | részleges | A felelős és az állapot Task erőforrással jobban leírható, mint a DetectedIssue `status` elemével (registered, preliminary, final, amended stb.). |
| 37 | `Provenance` (`target`, `recorded`, `agent.who`, `activity`, `entity.role`, pl. revision) | `alert_events` (`event_type`, `actor_id`, `created_at`, `rule_version_id`, `trigger_data_ids`) | részleges | Eseményenként egy Provenance; az ismételt aktiválódás, a szabálymódosítás, a kiváltó adat javítása és a feltétel teljesülésének pillanatképe (`condition_met`) csak saját kódolással írható le. |
| 38 | `Communication` (`subject`, `recipient`, `sender`, `sent`, `payload.contentString`, `about`, `status` = completed) | `notifications` (az orvos visszajelzése: `patient_id`, `created_by`, `created_at`, `text`, `alert_id`) | teljes | Az orvos egyirányú visszajelzése a betegnek; az `about` a riasztásnak megfelelő erőforrásra mutatna. |

Összesen 38 sor: 5 teljes, 28 részleges, 5 nincs.

## Példa: a protokoll PlanDefinition és Library erőforrásként

Az alábbi két erőforrás szemléltetés: validátorral nem ellenőriztem, és a
PULSE nem állítja elő. Az example.org cím csak azonosító, mint a PULSE
FHIR-kiadásában. A Library a CQL 11 paraméteréből kettőt mutat. A feltétel
egy CQL-kifejezés, amely a hivatkozott könyvtár „Target Met" definíciójára
épül; ha a PlanDefinition egyetlen könyvtárat hivatkozik, a kifejezés annak a
definícióit látja ([Using Expressions](https://hl7.org/fhir/R4/clinicalreasoning-topics-using-expressions.html)). Ha nincs elég adat, a
„Target Met" értéke null, és a feltétel nem teljesül; az adathiányt a példa
nem jelzi, arra külön tevékenység kellene.

```json
{
  "resourceType": "PlanDefinition",
  "url": "https://example.org/pulse/fhir/PlanDefinition/ng136-hbpm-kovetes",
  "version": "0.1.0",
  "name": "Ng136HbpmKovetes",
  "type": { "coding": [{
    "system": "http://terminology.hl7.org/CodeSystem/plan-definition-type",
    "code": "clinical-protocol" }] },
  "status": "draft",
  "relatedArtifact": [{ "type": "citation",
    "citation": "NICE NG136, 1.2.7 és 1.4.22",
    "url": "https://www.nice.org.uk/guidance/ng136" }],
  "library": ["https://example.org/pulse/fhir/Library/PulseHbpmAverage|0.1.0"],
  "action": [
    { "title": "Otthoni vérnyomásmérés",
      "code": [{ "coding": [{ "system": "http://loinc.org", "code": "85354-9" }] }],
      "timingTiming": { "repeat": {
        "boundsDuration": { "value": 7, "unit": "nap",
                            "system": "http://unitsofmeasure.org", "code": "d" },
        "frequency": 2, "period": 1, "periodUnit": "d" } } },
    { "title": "Orvosi felülvizsgálat: az otthoni átlag nem éri el a célt",
      "condition": [{ "kind": "applicability",
        "expression": { "language": "text/cql",
                        "expression": "\"Target Met\" is false" } }] }
  ]
}
```

```json
{
  "resourceType": "Library",
  "url": "https://example.org/pulse/fhir/Library/PulseHbpmAverage",
  "version": "0.1.0",
  "name": "PulseHbpmAverage",
  "status": "draft",
  "type": { "coding": [{
    "system": "http://terminology.hl7.org/CodeSystem/library-type",
    "code": "logic-library" }] },
  "parameter": [
    { "name": "Exclude First Day", "use": "in", "min": 0, "max": "1", "type": "boolean" },
    { "name": "Min Included Days", "use": "in", "min": 0, "max": "1", "type": "integer" }
  ],
  "dataRequirement": [{ "type": "Observation",
    "codeFilter": [{ "path": "code",
      "code": [{ "system": "http://loinc.org", "code": "85354-9" }] }] }],
  "content": [{ "contentType": "text/cql",
    "url": "https://example.org/pulse/cql/PulseHbpmAverage.cql" }]
}
```

## Források

HL7 International: FHIR R4 (v4.0.1). Utolsó megtekintés: 2026. 11. 22.

- [Observation](https://hl7.org/fhir/R4/observation.html)
- [PlanDefinition](https://hl7.org/fhir/R4/plandefinition.html)
- [Operation $apply on PlanDefinition](https://hl7.org/fhir/R4/plandefinition-operation-apply.html)
- [Library](https://hl7.org/fhir/R4/library.html)
- [CarePlan](https://hl7.org/fhir/R4/careplan.html)
- [ServiceRequest](https://hl7.org/fhir/R4/servicerequest.html)
- [QuestionnaireResponse](https://hl7.org/fhir/R4/questionnaireresponse.html)
- [Using Expressions](https://hl7.org/fhir/R4/clinicalreasoning-topics-using-expressions.html)
- [Goal](https://hl7.org/fhir/R4/goal.html)
- [ObservationStatus (értékkészlet)](https://hl7.org/fhir/R4/valueset-observation-status.html)
- [Data Types (Timing)](https://hl7.org/fhir/R4/datatypes.html)
- [Task](https://hl7.org/fhir/R4/task.html)
- [TaskStatus (értékkészlet)](https://hl7.org/fhir/R4/valueset-task-status.html)
- [DetectedIssue](https://hl7.org/fhir/R4/detectedissue.html)
- [Provenance](https://hl7.org/fhir/R4/provenance.html)
- [Flag](https://hl7.org/fhir/R4/flag.html)
- [ActivityDefinition](https://hl7.org/fhir/R4/activitydefinition.html)
- [ObservationDefinition](https://hl7.org/fhir/R4/observationdefinition.html)
- [Communication](https://hl7.org/fhir/R4/communication.html)
- [MetaData Types (ParameterDefinition, RelatedArtifact, DataRequirement, Expression)](https://hl7.org/fhir/R4/metadatatypes.html)
