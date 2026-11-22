// A CQL-motor közös része: az ELM betöltése, egy betegcsomag kiértékelése és a
// motor értékeinek JSON-alakja. A futtatas.mjs, a kiadas_feldolgozas.mjs és a
// szolgaltatas.mjs (M3, K2) ugyanezt használja, hogy a három út ugyanúgy
// számoljon.
//
// Az útvonalak e fájl helyéhez képest értendők, nem a munkakönyvtárhoz: a
// próbakonténerben a fájl a /app/work alatt van (a node_modules egy szinttel
// feljebb), a szolgáltatás image-ében a /app alatt (a node_modules mellette).

import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import cql from 'cql-execution';
import cqlfhir from 'cql-exec-fhir';

export { cql, cqlfhir };

const ITT = new URL('./', import.meta.url);

export const ELM_FO = 'elm/PulseHbpmAverage-0.1.0.json';
export const ELM_FHIRHELPERS = 'elm/FHIRHelpers-4.0.1.json';

export const olvas = async (utvonal) => JSON.parse(await readFile(utvonal, 'utf8'));
export const hash = async (utvonal) =>
  createHash('sha256').update(await readFile(utvonal)).digest('hex');

// A telepített csomag verziója (a node_modules a fájl mellett vagy egy szinttel feljebb).
export async function csomagVerzio(nev) {
  for (const hely of [`node_modules/${nev}/package.json`, `../node_modules/${nev}/package.json`]) {
    try {
      return (await olvas(new URL(hely, ITT))).version;
    } catch {
      // következő hely
    }
  }
  return 'ismeretlen';
}

// A motor értékeinek olvasható JSON-alakja.
export function json(ertek) {
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

// A két ELM-fájl beolvasása (a fájl helyéhez képest). Visszaadja a nyers
// ELM-et és a fájlok sha256-ját, hogy a kimenet a pontos változatot rögzítse.
export async function elmBetoltes() {
  const foUt = new URL(ELM_FO, ITT);
  const helperUt = new URL(ELM_FHIRHELPERS, ITT);
  return {
    elm: await olvas(foUt),
    fhirHelpersElm: await olvas(helperUt),
    sha256: { [ELM_FO]: await hash(foUt), [ELM_FHIRHELPERS]: await hash(helperUt) },
  };
}

export const konyvtar = (elm, fhirHelpersElm) =>
  new cql.Library(elm, new cql.Repository({ FHIRHelpers: fhirHelpersElm }));

// Egy (egybeteges) FHIR-csomag kiértékelése a megadott paraméterekkel és
// időponttal. A paraméterek már a motor típusaiban érkeznek (pl. cql.Interval).
// Visszaadja a beteg azonosítóját és az `Evaluation Result` JSON-alakját.
export async function kiertekeles(lib, csomag, parameterek, idopont) {
  const vegrehajto = new cql.Executor(lib, new cql.CodeService({}), parameterek);
  const forras = cqlfhir.PatientSource.FHIRv401();
  forras.loadBundles([csomag]);
  const eredmenyek = await vegrehajto.exec(forras, idopont);
  const betegek = Object.keys(eredmenyek.patientResults);
  if (betegek.length !== 1) throw new Error(`Egy beteget vártam, ennyi jött: ${betegek.length}`);
  return {
    betegId: betegek[0],
    eredmeny: json(eredmenyek.patientResults[betegek[0]]['Evaluation Result']),
  };
}
