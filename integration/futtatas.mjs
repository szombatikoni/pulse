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

import { createHash } from 'node:crypto';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import cql from 'cql-execution';
import cqlfhir from 'cql-exec-fhir';

const ELM_FO = 'elm/PulseHbpmAverage-0.1.0.json';
const ELM_FHIRHELPERS = 'elm/FHIRHelpers-4.0.1.json';
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

const olvas = async (utvonal) => JSON.parse(await readFile(utvonal, 'utf8'));
const hash = async (utvonal) =>
  createHash('sha256').update(await readFile(utvonal)).digest('hex');

// A telepített csomag verziója (a konténerben a node_modules egy szinttel feljebb van).
async function csomagVerzio(nev) {
  for (const hely of [`node_modules/${nev}/package.json`, `../node_modules/${nev}/package.json`]) {
    try {
      return (await olvas(hely)).version;
    } catch {
      // következő hely
    }
  }
  return 'ismeretlen';
}

// A motor értékeinek olvasható JSON-alakja.
function json(ertek) {
  if (ertek == null) return null;
  if (Array.isArray(ertek)) return ertek.map(json);
  if (typeof ertek !== 'object') return ertek;
  if (ertek.isDate || ertek.isDateTime) return ertek.toString();
  if (ertek.isInterval) {
    return {
      low: json(ertek.low),
      high: json(ertek.high),
      lowClosed: ertek.lowClosed,
      highClosed: ertek.highClosed,
    };
  }
  if (ertek.isQuantity) return { value: ertek.value, unit: ertek.unit };
  if (ertek._json) return `${ertek._json.resourceType}/${ertek._json.id}`;
  return Object.fromEntries(Object.entries(ertek).map(([k, v]) => [k, json(v)]));
}

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
  const konyvtar = new cql.Library(elm, new cql.Repository({ FHIRHelpers: fhirHelpersElm }));
  const [tol, ig] = forgatokonyv.sorozat ?? SOROZAT;
  const parameterek = {
    'Series Period': new cql.Interval(cql.DateTime.parse(tol), cql.DateTime.parse(ig), true, false),
    ...forgatokonyv.parameterek,
  };
  const vegrehajto = new cql.Executor(konyvtar, new cql.CodeService({}), parameterek);

  let betegCsomag = csomag;
  if (forgatokonyv.szuletesiDatum) {
    betegCsomag = structuredClone(csomag);
    betegCsomag.entry.find((b) => b.resource.resourceType === 'Patient').resource.birthDate =
      forgatokonyv.szuletesiDatum;
  }
  const forras = cqlfhir.PatientSource.FHIRv401();
  forras.loadBundles([betegCsomag]);

  const eredmenyek = await vegrehajto.exec(forras, cql.DateTime.parse(KIERTEKELES_IDOPONTJA));
  const betegek = Object.keys(eredmenyek.patientResults);
  if (betegek.length !== 1) throw new Error(`Egy beteget vártam, ennyi jött: ${betegek.length}`);
  const e = json(eredmenyek.patientResults[betegek[0]]['Evaluation Result']);
  return {
    id: forgatokonyv.id,
    leiras: forgatokonyv.leiras,
    parameterek: json(parameterek),
    beteg: `Patient/${betegek[0]}`,
    eredmeny: e,
    magyarazat: magyarazat(e),
  };
}

const elm = await olvas(ELM_FO);
const fhirHelpersElm = await olvas(ELM_FHIRHELPERS);
const csomag = await olvas(CSOMAG);

const kimenet = {
  futtatas: {
    motor: `cql-execution ${await csomagVerzio('cql-execution')}`,
    fhirAdapter: `cql-exec-fhir ${await csomagVerzio('cql-exec-fhir')}, PatientSource.FHIRv401()`,
    node: process.version,
    kiertekelesIdopontja: KIERTEKELES_IDOPONTJA,
    elm: {
      [ELM_FO]: { konyvtar: `${elm.library.identifier.id} ${elm.library.identifier.version}`, sha256: await hash(ELM_FO) },
      [ELM_FHIRHELPERS]: { konyvtar: `${fhirHelpersElm.library.identifier.id} ${fhirHelpersElm.library.identifier.version}`, sha256: await hash(ELM_FHIRHELPERS) },
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
