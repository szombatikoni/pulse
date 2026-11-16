// A lefordított CQL-szabály (ELM) futtatása a mesterséges beteg FHIR-csomagján.
//
// Futtatás: docker compose run --rm motor
// (helyben is: npm ci && node futtatas.mjs)
//
// Motor: cql-execution 3.3.2, FHIR-adapter: cql-exec-fhir 2.2.0 (FHIR 4.0.1).
// A fordítóra nincs szükség: az ELM az elm/ mappában van.
//
// A kimenet: a forgatókönyvek eredménye olvasható JSON-ként a képernyőn és az
// eredmeny/eredmeny.json fájlban. A forgatókönyvek ugyanazt az adatot futtatják
// más paraméterekkel, hogy látszódjon, melyik kétértelmű pont mit változtat.

import { mkdir, writeFile } from 'node:fs/promises';
import {
  ELM_FHIRHELPERS, ELM_FO, cql, csomagVerzio, elmBetoltes, hash, json, kiertekeles, konyvtar, olvas,
} from './motor.mjs';
const CSOMAG = 'adat/beteg_hbpm_bundle.json';
const KIMENET = 'eredmeny/eredmeny.json';

// Rögzített kiértékelési időpont, hogy az eredmény megismételhető legyen.
const KIERTEKELES_IDOPONTJA = '2026-10-09T08:00:00.000+02:00';

// A mérési sorozat időszaka: [okt. 5. 0:00, okt. 9. 0:00), helyi idő szerint.
const SOROZAT = ['2026-10-05T00:00:00.000+02:00', '2026-10-09T00:00:00.000+02:00'];

const FORGATOKONYVEK = [
  {
    id: 'A-alap',
    leiras: 'Alapértékek (a kutatás javaslatai)',
    parameterek: {},
  },
  {
    id: 'B-elso-nap-nelkul',
    leiras: 'Az első nap NEM esik ki',
    parameterek: { 'Exclude First Day': false },
  },
  {
    id: 'C-eleg-az-egyik',
    leiras: 'A cél teljesül, ha legalább az egyik átlag a határ alatt van',
    parameterek: { 'Both Components Must Be Below Target': false },
  },
  {
    id: 'D-kerekites-egeszre',
    leiras: 'Az átlagok egészre kerekítve az összevetés előtt',
    parameterek: { 'Comparison Rounding Precision': 0 },
  },
  {
    id: 'E-min-4-nap',
    leiras: 'Legalább 4 értékelhető nap kell (az első nap nélkül)',
    parameterek: { 'Min Included Days': 4 },
  },
  {
    id: 'F-80-ev-feletti',
    leiras: 'Ugyanezek a mérések egy 80 év feletti betegnél (születési dátum a memóriában átírva: 1944-03-14)',
    parameterek: {},
    szuletesiDatum: '1944-03-14',
  },
  {
    id: 'G-kirendeles-kezdonapja',
    leiras: 'Első nap = a sorozat kezdőnapja; a sorozat okt. 4-én indul, de az első mérés okt. 5-i',
    parameterek: { 'First Day Definition': 'PeriodStartDay' },
    sorozat: ['2026-10-04T00:00:00.000+02:00', '2026-10-09T00:00:00.000+02:00'],
  },
];

// Rövid magyar magyarázat a motor eredményéből (bemutató; a végleges szöveg a PULSE dolga).
function magyarazat(e) {
  const sz = (x) => (x == null ? '–' : x.toFixed(1).replace('.', ','));
  const napok = e.includedDays;
  const idoszak = napok.length ? `${napok[0]} – ${napok[napok.length - 1]}` : 'nincs';
  const kiesett = !e.excludedFirstDay
    ? 'első nap nem esett ki'
    : e.excludedReadingIds.length
      ? `a ${e.excludedFirstDay}-i ${e.excludedReadingIds.length} mérés első napként kiesett`
      : `az első napnak tekintett ${e.excludedFirstDay}-n nem volt mérés`;
  const cel = `célérték: ${e.targetSystolic}/${e.targetDiastolic} Hgmm alatt (${e.ageInYears} éves; ` +
    (e.bothComponentsMustBeBelowTarget ? 'mindkét átlagnak' : 'legalább az egyik átlagnak') +
    ' a határ alatt kell lennie)';
  const eredmeny = e.targetMet == null
    ? `nincs elég adat (${e.includedDayCount} értékelhető nap, legalább ${e.minIncludedDays} kell)`
    : e.targetMet ? 'a cél teljesül' : 'a cél NEM teljesül';
  return `Átlag ${sz(e.meanSystolic)}/${sz(e.meanDiastolic)} Hgmm, ${e.includedReadingCount} mérésből ` +
    `(${idoszak}, ${e.includedDayCount} nap); ${kiesett}; ${cel}: ${eredmeny}.`;
}

async function futtat(forgatokonyv, elm, fhirHelpersElm, csomag) {
  const lib = konyvtar(elm, fhirHelpersElm);
  const [tol, ig] = forgatokonyv.sorozat ?? SOROZAT;
  const parameterek = {
    'Series Period': new cql.Interval(cql.DateTime.parse(tol), cql.DateTime.parse(ig), true, false),
    ...forgatokonyv.parameterek,
  };

  let betegCsomag = csomag;
  if (forgatokonyv.szuletesiDatum) {
    betegCsomag = structuredClone(csomag);
    betegCsomag.entry.find((b) => b.resource.resourceType === 'Patient').resource.birthDate =
      forgatokonyv.szuletesiDatum;
  }

  const { betegId, eredmeny: e } = await kiertekeles(
    lib, betegCsomag, parameterek, cql.DateTime.parse(KIERTEKELES_IDOPONTJA),
  );
  return {
    id: forgatokonyv.id,
    leiras: forgatokonyv.leiras,
    parameterek: json(parameterek),
    beteg: `Patient/${betegId}`,
    eredmeny: e,
    magyarazat: magyarazat(e),
  };
}

const { elm, fhirHelpersElm, sha256 } = await elmBetoltes();
const csomag = await olvas(CSOMAG);

const kimenet = {
  futtatas: {
    motor: `cql-execution ${await csomagVerzio('cql-execution')}`,
    fhirAdapter: `cql-exec-fhir ${await csomagVerzio('cql-exec-fhir')}, PatientSource.FHIRv401()`,
    node: process.version,
    kiertekelesIdopontja: KIERTEKELES_IDOPONTJA,
    elm: {
      [ELM_FO]: { konyvtar: `${elm.library.identifier.id} ${elm.library.identifier.version}`, sha256: sha256[ELM_FO] },
      [ELM_FHIRHELPERS]: { konyvtar: `${fhirHelpersElm.library.identifier.id} ${fhirHelpersElm.library.identifier.version}`, sha256: sha256[ELM_FHIRHELPERS] },
    },
    csomag: { utvonal: CSOMAG, sha256: await hash(CSOMAG) },
  },
  forgatokonyvek: [],
};

for (const f of FORGATOKONYVEK) {
  kimenet.forgatokonyvek.push(await futtat(f, elm, fhirHelpersElm, csomag));
}

await mkdir('eredmeny', { recursive: true });
await writeFile(KIMENET, JSON.stringify(kimenet, null, 2) + '\n', 'utf8');

// Képernyő: az alapeset teljes eredménye, utána az összes forgatókönyv röviden.
const alap = kimenet.forgatokonyvek[0];
console.log(JSON.stringify({ futtatas: kimenet.futtatas, alapeset: alap }, null, 2));
console.log('\nForgatókönyvek (ugyanaz az adat, más paraméter):');
for (const f of kimenet.forgatokonyvek) {
  const e = f.eredmeny;
  console.log(
    `  ${f.id.padEnd(24)} n=${String(e.includedReadingCount).padStart(2)}  ` +
    `átlag=${e.meanSystolic}/${e.meanDiastolic}  cél=${e.targetSystolic}/${e.targetDiastolic}  ` +
    `targetMet=${e.targetMet}`,
  );
}
console.log(`\nMentve: ${KIMENET}`);
