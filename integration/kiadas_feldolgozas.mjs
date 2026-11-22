// A PULSE FHIR-kiadásának feldolgozása a külső motorral (M3, K1).
//
// Futtatás: docker compose run --rm kiadas-feldolgozas
// (helyben is: npm ci && node kiadas_feldolgozas.mjs)
//
// Két lépés, ugyanazon a csomagon (adat/pulse_kiadas_bundle.json, a
// kiadas/letoltes.py tölti le a futó PULSE-ból):
//   1. beolvasás a motor FHIR-adapterével (cql-exec-fhir, FHIR 4.0.1): minden
//      Observation, Questionnaire és QuestionnaireResponse úgy, ahogy a motor
//      látja (érték, UCUM-kód, az időpont a motor DateTime-jaként és a belőle
//      számolt helyi nap);
//   2. az M2-es NICE-szabály (elm/PulseHbpmAverage-0.1.0.json) futtatása
//      változatlanul, alapparaméterekkel, a teljes sorozatra.
// Az eredményt az ellenorzes/kiadas_ellenorzes.py veti össze az adatbázis
// soraival (nem a csomaggal).

import { mkdir, writeFile } from 'node:fs/promises';
import {
  ELM_FHIRHELPERS, ELM_FO, cql, cqlfhir, csomagVerzio, elmBetoltes, hash, kiertekeles, konyvtar, olvas,
} from './motor.mjs';

const CSOMAG = 'adat/pulse_kiadas_bundle.json';
const KIMENET = 'eredmeny/kiadas_feldolgozas.json';

// Egy FHIR-primitív értéke (a motor saját típusában), vagy null.
const ertek = (fhirObj) => fhirObj?.get('value') ?? null;

// A motor DateTime-ja: a kiírt alak, az eltolás órában és a helyi nap.
function ido(dt) {
  if (dt == null) return null;
  return { ertek: dt.toString(), eltolasOra: dt.timezoneOffset, helyiNap: dt.getDate().toString() };
}

function mennyiseg(kod, q) {
  return {
    kod,
    ertek: ertek(q.get('value')),
    egysegKod: ertek(q.get('code')),
    rendszer: ertek(q.get('system')),
  };
}

function observation(o) {
  const kod = ertek(o.get('code').get('coding')[0].get('code'));
  const komponensek = o.get('component') ?? [];
  const eredmeny = {
    id: o.getId(),
    statusz: ertek(o.get('status')),
    kod,
    effective: ido(ertek(o.get('effective'))),
    issued: ido(ertek(o.get('issued'))),
    ertekek: komponensek.length
      ? komponensek.map((c) => mennyiseg(ertek(c.get('code').get('coding')[0].get('code')), c.get('value')))
      : [mennyiseg(kod, o.get('value'))],
  };
  return eredmeny;
}

function questionnaire(q) {
  return {
    id: q.getId(),
    url: ertek(q.get('url')),
    verzio: ertek(q.get('version')),
    statusz: ertek(q.get('status')),
    kerdesek: (q.get('item') ?? []).map((i) => ({
      linkId: ertek(i.get('linkId')),
      valaszlehetosegek: (i.get('answerOption') ?? []).map((opt) => ertek(opt.get('value').get('code'))),
    })),
  };
}

function questionnaireResponse(r) {
  return {
    id: r.getId(),
    kerdoiv: ertek(r.get('questionnaire')),
    statusz: ertek(r.get('status')),
    authored: ido(ertek(r.get('authored'))),
    valaszok: (r.get('item') ?? []).map((i) => ({
      linkId: ertek(i.get('linkId')),
      kodok: (i.get('answer') ?? []).map((a) => ertek(a.get('value').get('code'))),
    })),
  };
}

const csomag = await olvas(CSOMAG);

// 1. Beolvasás az adapterrel.
const forras = cqlfhir.PatientSource.FHIRv401();
forras.loadBundles([csomag]);
const beteg = forras.currentPatient();
const beolvasas = {
  beteg: { id: beteg.getId(), szuletesiDatum: ertek(beteg.get('birthDate'))?.toString() ?? null },
  observation: beteg.findRecords('Observation').map(observation),
  questionnaire: beteg.findRecords('Questionnaire').map(questionnaire),
  questionnaireResponse: beteg.findRecords('QuestionnaireResponse').map(questionnaireResponse),
};

// 2. A NICE-szabály a kiadott csomagon. A kiértékelés időpontja a csomag
// időbélyege, így az életkor és a „ma" a kiadás pillanatához igazodik.
const kiertekelesIdopontja = csomag.timestamp;
const { elm, fhirHelpersElm, sha256 } = await elmBetoltes();
const { eredmeny: nice } = await kiertekeles(
  konyvtar(elm, fhirHelpersElm), csomag, {}, cql.DateTime.parse(kiertekelesIdopontja),
);

const kimenet = {
  futtatas: {
    motor: `cql-execution ${await csomagVerzio('cql-execution')}`,
    fhirAdapter: `cql-exec-fhir ${await csomagVerzio('cql-exec-fhir')}, PatientSource.FHIRv401()`,
    node: process.version,
    kiertekelesIdopontja,
    elm: { [ELM_FO]: { sha256: sha256[ELM_FO] }, [ELM_FHIRHELPERS]: { sha256: sha256[ELM_FHIRHELPERS] } },
    csomag: { utvonal: CSOMAG, sha256: await hash(CSOMAG) },
  },
  beolvasas,
  nice: { parameterek: 'alapértékek, Series Period nélkül (a teljes sorozat)', eredmeny: nice },
};

await mkdir('eredmeny', { recursive: true });
await writeFile(KIMENET, JSON.stringify(kimenet, null, 2) + '\n', 'utf8');

console.log(`Beteg: Patient/${beolvasas.beteg.id}`);
console.log(
  `Beolvasva: ${beolvasas.observation.length} Observation, ${beolvasas.questionnaire.length} Questionnaire, ` +
  `${beolvasas.questionnaireResponse.length} QuestionnaireResponse`,
);
console.log(
  `NICE-szabály: n=${nice.includedReadingCount}, napok=${nice.includedDayCount}, ` +
  `átlag=${nice.meanSystolic}/${nice.meanDiastolic}, kizárt nap=${nice.excludedFirstDay}, targetMet=${nice.targetMet}`,
);
console.log(`Mentve: ${KIMENET}`);
