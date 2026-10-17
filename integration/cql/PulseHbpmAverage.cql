/*
PULSE M2 integrációs próba — otthoni vérnyomásmérés-sorozat átlaga az első nap
kizárásával, és a célérték teljesülése.

Szakmai forrás (csak hivatkozás, a szöveg nem kerül a repóba):
  NICE guideline NG136, recommendations 1.2.7 (az átlagolás módja) és
  1.4.22 (célérték a kezelés követésénél, életkor szerint)
  https://www.nice.org.uk/guidance/ng136/chapter/Recommendations

A könyvtár NEM diagnosztizál: a kezelés követéséhez számol átlagot.
Demonstrációs kód, kizárólag mesterséges adatra.

A kétértelmű pontok paraméterek; az alapértékek a kutatás javaslatai, nem
végleges döntések (lásd integration/README.md, „A próba feltételezései”).

Fordítás: cql-translation-service v2.8.0 (cql-to-elm 4.2.0); futtatás:
cql-execution 3.3.2 + cql-exec-fhir 2.2.0. CQL 1.5 szintű nyelvi elemek.
*/
library PulseHbpmAverage version '0.1.0'

using FHIR version '4.0.1'

include FHIRHelpers version '4.0.1' called FHIRHelpers

codesystem "LOINC": 'http://loinc.org'

code "Blood pressure panel": '85354-9' from "LOINC" display 'Blood pressure panel with all children optional'
code "Systolic blood pressure": '8480-6' from "LOINC" display 'Systolic blood pressure'
code "Diastolic blood pressure": '8462-4' from "LOINC" display 'Diastolic blood pressure'

// ---------------------------------------------------------------------------
// Paraméterek
// ---------------------------------------------------------------------------

// MOTOR-KERÜLŐÚT: a cql-execution 3.3.2-ben az alapérték NÉLKÜLI, meg nem adott
// paraméter nem null-t ad vissza (hanem a paraméter-definíciót), ezért az
// `is null` hamis lesz, a Round NaN-t ad. A `default null` ezt elkerüli.

// A mérési sorozat időszaka (később: a követési terv kirendelésének időszaka).
// Ha nincs megadva, a csomag minden vérnyomásmérése a sorozat része.
parameter "Series Period" Interval<DateTime> default null

// Kiessenek-e az első nap mérései (NG136 1.2.7).
parameter "Exclude First Day" Boolean default true

// Mi az „első nap”:
//   'FirstReadingDay' = az első érvényes mérést tartalmazó naptári nap,
//   'PeriodStartDay'  = a "Series Period" kezdőnapja (kirendelés kezdete).
// A nap a mérés effectiveDateTime-jában tárolt helyi időeltolás szerinti dátum.
parameter "First Day Definition" String default 'FirstReadingDay'

// Legalább ennyi értékelhető (nem kizárt) napnak kell lennie; különben a
// "Target Met" értéke null (nincs elég adat — sosem kedvező eredmény).
parameter "Min Included Days" Integer default 3

// Célérték (NG136 1.4.22): az életkorhatár alatt / felett.
parameter "Age Threshold Years" Integer default 80
parameter "Target Systolic Below Age Threshold" Decimal default 135.0
parameter "Target Diastolic Below Age Threshold" Decimal default 85.0
parameter "Target Systolic At Or Above Age Threshold" Decimal default 145.0
parameter "Target Diastolic At Or Above Age Threshold" Decimal default 85.0

// true  = a cél akkor teljesül, ha MINDKÉT átlag a határ alatt van;
// false = elég, ha legalább az egyik a határ alatt van.
parameter "Both Components Must Be Below Target" Boolean default true

// Kerekítés az összevetés előtt: null = nincs kerekítés; különben ennyi
// tizedesjegyre kerekít (0 = egészre).
parameter "Comparison Rounding Precision" Integer default null

context Patient

// ---------------------------------------------------------------------------
// Segédfüggvények
// ---------------------------------------------------------------------------

// A mérés időpontja (csak effectiveDateTime; effectivePeriod esetén null).
define function "Effective DateTime"(O FHIR.Observation):
  (O.effective as FHIR.dateTime).value

// A mérés naptári napja a tárolt időeltolás szerint (helyi nap).
define function "Local Day"(O FHIR.Observation):
  date from "Effective DateTime"(O)

// Érték Hgmm-ben; más egységnél vagy hiányzó értéknél null.
define function "Mmhg Value"(Q FHIR.Quantity):
  if Q.system.value = 'http://unitsofmeasure.org' and Q.code.value = 'mm[Hg]'
    then FHIRHelpers.ToQuantity(Q).value
  else null

define function "Systolic Value"(O FHIR.Observation):
  singleton from (
    O.component C
      where C.code ~ "Systolic blood pressure"
      return all "Mmhg Value"(C.value as FHIR.Quantity)
  )

define function "Diastolic Value"(O FHIR.Observation):
  singleton from (
    O.component C
      where C.code ~ "Diastolic blood pressure"
      return all "Mmhg Value"(C.value as FHIR.Quantity)
  )

// ---------------------------------------------------------------------------
// A sorozat mérései
// ---------------------------------------------------------------------------

define "Series Readings":
  [Observation: "Blood pressure panel"] O
    where O.status.value in { 'final', 'amended', 'corrected' }
      and "Effective DateTime"(O) is not null
      and ("Series Period" is null or "Effective DateTime"(O) during "Series Period")

// Csak a teljes (szisztolés ÉS diasztolés, Hgmm) mérések számítanak.
define "Valid Readings":
  "Series Readings" O
    where "Systolic Value"(O) is not null
      and "Diastolic Value"(O) is not null

define "Incomplete Readings":
  "Series Readings" O
    where "Systolic Value"(O) is null
      or "Diastolic Value"(O) is null

define "First Reading Day":
  Min("Valid Readings" O return all "Local Day"(O))

define "Excluded First Day":
  case
    when not "Exclude First Day" then null as Date
    when "First Day Definition" = 'PeriodStartDay' then date from start of "Series Period"
    when "First Day Definition" = 'FirstReadingDay' then "First Reading Day"
    else Message(null as Date, true, 'PULSE.UnknownFirstDayDefinition', 'Error',
      'Unknown "First Day Definition": ' & "First Day Definition")
  end

define "First Day Readings":
  "Valid Readings" O
    where "Local Day"(O) <= "Excluded First Day"

define "Included Readings":
  "Valid Readings" O
    where "Excluded First Day" is null
      or "Local Day"(O) > "Excluded First Day"

// FIGYELEM: a CQL-ben a query `return` záradéka alapból distinct, ezért kell
// a `return all` — különben az ismétlődő értékek (pl. kétszer 136) csak
// egyszer számítanának bele az átlagba.
define "Systolic Values":
  "Included Readings" O return all "Systolic Value"(O)

define "Diastolic Values":
  "Included Readings" O return all "Diastolic Value"(O)

define "Mean Systolic": Avg("Systolic Values")
define "Mean Diastolic": Avg("Diastolic Values")

define "Included Reading Count": Count("Included Readings")

define "Included Days":
  "Included Readings" O return "Local Day"(O) sort asc

define "Included Day Count": Count("Included Days")

define "Enough Data": "Included Day Count" >= "Min Included Days"

// ---------------------------------------------------------------------------
// Célérték (életkor szerint) és összevetés
// ---------------------------------------------------------------------------

// Az életkor a sorozat végén (ha nincs időszak: a kiértékelés napján).
define "Age Reference Date":
  Coalesce(date from end of "Series Period", Today())

define "Age In Years": AgeInYearsAt("Age Reference Date")

define "Target Systolic":
  if "Age In Years" >= "Age Threshold Years"
    then "Target Systolic At Or Above Age Threshold"
  else "Target Systolic Below Age Threshold"

define "Target Diastolic":
  if "Age In Years" >= "Age Threshold Years"
    then "Target Diastolic At Or Above Age Threshold"
  else "Target Diastolic Below Age Threshold"

define "Compared Systolic":
  if "Comparison Rounding Precision" is null then "Mean Systolic"
  else Round("Mean Systolic", "Comparison Rounding Precision")

define "Compared Diastolic":
  if "Comparison Rounding Precision" is null then "Mean Diastolic"
  else Round("Mean Diastolic", "Comparison Rounding Precision")

define "Systolic Below Target": "Compared Systolic" < "Target Systolic"
define "Diastolic Below Target": "Compared Diastolic" < "Target Diastolic"

// null = nincs elég adat (a PULSE-ban ez szürke státusz, nem kedvező).
define "Target Met":
  if not "Enough Data" then null as Boolean
  else if "Both Components Must Be Below Target"
    then "Systolic Below Target" and "Diastolic Below Target"
  else "Systolic Below Target" or "Diastolic Below Target"

// ---------------------------------------------------------------------------
// A magyarázathoz szükséges adatok egy helyen
// ---------------------------------------------------------------------------

define "Evaluation Result":
  Tuple {
    library: 'PulseHbpmAverage',
    libraryVersion: '0.1.0',
    seriesPeriod: "Series Period",
    excludedFirstDay: "Excluded First Day",
    excludedReadingIds: "First Day Readings" O return all O.id.value,
    incompleteReadingIds: "Incomplete Readings" O return all O.id.value,
    includedReadingIds: "Included Readings" O return all O.id.value,
    includedReadingCount: "Included Reading Count",
    includedDays: "Included Days",
    includedDayCount: "Included Day Count",
    minIncludedDays: "Min Included Days",
    enoughData: "Enough Data",
    meanSystolic: "Mean Systolic",
    meanDiastolic: "Mean Diastolic",
    comparedSystolic: "Compared Systolic",
    comparedDiastolic: "Compared Diastolic",
    ageInYears: "Age In Years",
    targetSystolic: "Target Systolic",
    targetDiastolic: "Target Diastolic",
    bothComponentsMustBeBelowTarget: "Both Components Must Be Below Target",
    systolicBelowTarget: "Systolic Below Target",
    diastolicBelowTarget: "Diastolic Below Target",
    targetMet: "Target Met"
  }
