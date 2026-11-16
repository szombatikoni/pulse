// A CQL-szolgáltatás tesztjei (M3, K2, 1. lépés), a Node beépített
// tesztfuttatójával, új függőség nélkül.
//
// Futtatás az integration/ mappából: npm ci && npm run teszt
// (Dockerben, Node 24-gyel: docker compose run --rm motor npm run teszt)
//
// Az elvárt eredmények a korábbi, egyszer lefutó szkriptek rögzített kimenetei
// (eredmeny/eredmeny.json, eredmeny/kiadas_feldolgozas.json): a szolgáltatásnak
// ugyanazon a csomagon ugyanazt kell adnia. Mind a 7 forgatókönyv ugyanazon a
// szolgáltatáspéldányon fut egymás után, így az is látszik, hogy az egyszer
// betöltött könyvtár nem visz át állapotot a különböző paraméterű futások közt.

import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { after, before, describe, test } from 'node:test';
import { TORZS_KORLAT, szolgaltatasLetrehozas } from '../szolgaltatas.mjs';

const olvas = async (ut) => JSON.parse(await readFile(new URL(ut, import.meta.url), 'utf8'));

const rogzitett = await olvas('../eredmeny/eredmeny.json');
const kiadasRogzitett = await olvas('../eredmeny/kiadas_feldolgozas.json');
const kezicsomag = await olvas('../adat/beteg_hbpm_bundle.json');
const kiadasCsomag = await olvas('../adat/pulse_kiadas_bundle.json');

// Ugyanaz az időpont, mint a futtatas.mjs-ben.
const KIERTEKELES_IDOPONTJA = rogzitett.futtatas.kiertekelesIdopontja;

let server;
let cim;

before(async () => {
  ({ server } = await szolgaltatasLetrehozas());
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  cim = `http://127.0.0.1:${server.address().port}`;
});

after(() => new Promise((resolve) => server.close(resolve)));

const post = (torzs, ut = '/evaluate') =>
  fetch(`${cim}${ut}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: typeof torzs === 'string' ? torzs : JSON.stringify(torzs),
  });

// Egy forgatókönyv kérése a rögzített sorból: a paraméterek a kimenetben már
// JSON-alakban vannak (a Series Period { low, high, lowClosed, highClosed }).
function keres(sor) {
  let bundle = kezicsomag;
  const szuletes = sor.leiras.match(/születési dátum a memóriában átírva: (\d{4}-\d{2}-\d{2})/);
  if (szuletes) {
    bundle = structuredClone(kezicsomag);
    bundle.entry.find((b) => b.resource.resourceType === 'Patient').resource.birthDate = szuletes[1];
  }
  return { bundle, parameters: sor.parameterek, evaluationTime: KIERTEKELES_IDOPONTJA };
}

describe('GET /health', () => {
  test('200, a betöltött könyvtár azonosítójával', async () => {
    const res = await fetch(`${cim}/health`);
    assert.equal(res.status, 200);
    const torzs = await res.json();
    assert.equal(torzs.status, 'ok');
    assert.deepEqual(torzs.library, {
      id: 'PulseHbpmAverage',
      version: '0.1.0',
      sha256: rogzitett.futtatas.elm['elm/PulseHbpmAverage-0.1.0.json'].sha256,
    });
  });
});

describe('POST /evaluate: a kézi csomag forgatókönyvei', () => {
  test('a válasz szerkezete és az A-alap eredménye (135 / 84,4166..., targetMet false)', async () => {
    const sor = rogzitett.forgatokonyvek.find((f) => f.id === 'A-alap');
    const res = await post(keres(sor));
    assert.equal(res.status, 200);
    const torzs = await res.json();
    assert.deepEqual(Object.keys(torzs).sort(), ['durationMs', 'engine', 'evaluationTime', 'library', 'result']);
    assert.equal(torzs.library.sha256, rogzitett.futtatas.elm['elm/PulseHbpmAverage-0.1.0.json'].sha256);
    assert.equal(torzs.engine['cql-execution'], '3.3.2');
    assert.equal(torzs.engine['cql-exec-fhir'], '2.2.0');
    assert.match(torzs.engine.node, /^v\d+\./);
    assert.equal(torzs.evaluationTime, KIERTEKELES_IDOPONTJA);
    assert.equal(typeof torzs.durationMs, 'number');
    assert.equal(torzs.result.meanSystolic, 135);
    assert.equal(torzs.result.meanDiastolic, 84.41666666666667);
    assert.equal(torzs.result.targetMet, false);
    assert.deepEqual(torzs.result, sor.eredmeny);
  });

  for (const sor of rogzitett.forgatokonyvek) {
    test(`${sor.id}: a result egyezik az eredmeny.json sorával`, async () => {
      const res = await post(keres(sor));
      assert.equal(res.status, 200);
      assert.deepEqual((await res.json()).result, sor.eredmeny);
    });
  }
});

describe('POST /evaluate: a PULSE kiadott csomagja', () => {
  test('alapparaméterekkel, a csomag időbélyegével: egyezik a kiadas_feldolgozas.json NICE-eredményével', async () => {
    const res = await post({ bundle: kiadasCsomag, evaluationTime: kiadasCsomag.timestamp });
    assert.equal(res.status, 200);
    assert.deepEqual((await res.json()).result, kiadasRogzitett.nice.eredmeny);
  });

  test('időpont nélkül is lefut (a szolgáltatás órájával)', async () => {
    const res = await post({ bundle: kezicsomag });
    assert.equal(res.status, 200);
    const torzs = await res.json();
    assert.ok(Math.abs(Date.parse(torzs.evaluationTime) - Date.now()) < 60_000);
  });
});

describe('Hibás bemenet: 400', () => {
  const eset = async (torzs, kod) => {
    const res = await post(torzs);
    assert.equal(res.status, 400);
    assert.match(res.headers.get('content-type'), /application\/json/);
    const valasz = await res.json();
    assert.equal(valasz.error, kod);
    assert.equal(typeof valasz.message, 'string');
  };

  test('nem JSON a törzs', () => eset('{nem json', 'invalid_json'));
  test('a törzs nem objektum', () => eset('[1, 2]', 'invalid_json'));
  test('hiányzó bundle', () => eset({ parameters: {} }, 'invalid_bundle'));
  test('nem Bundle', () => eset({ bundle: { resourceType: 'Patient' } }, 'invalid_bundle'));
  test('nincs entry-lista', () => eset({ bundle: { resourceType: 'Bundle' } }, 'invalid_bundle'));
  test('nincs Patient', () => eset({ bundle: { resourceType: 'Bundle', entry: [] } }, 'invalid_bundle'));
  test('két Patient', () => {
    const ketto = structuredClone(kezicsomag);
    const beteg = ketto.entry.find((b) => b.resource.resourceType === 'Patient');
    ketto.entry.push({ resource: { ...beteg.resource, id: 'masik' } });
    return eset({ bundle: ketto }, 'invalid_bundle');
  });
  test('ismeretlen paraméter', () => eset({ bundle: kezicsomag, parameters: { 'Nincs Ilyen': 1 } }, 'unknown_parameter'));
  test('a parameters nem objektum', () => eset({ bundle: kezicsomag, parameters: [1] }, 'invalid_parameters'));
  test('Boolean helyett szöveg', () => eset({ bundle: kezicsomag, parameters: { 'Exclude First Day': 'false' } }, 'invalid_parameter'));
  test('Integer helyett tört', () => eset({ bundle: kezicsomag, parameters: { 'Min Included Days': 3.5 } }, 'invalid_parameter'));
  test('Decimal helyett szöveg', () => eset({ bundle: kezicsomag, parameters: { 'Target Systolic Below Age Threshold': '135' } }, 'invalid_parameter'));
  test('Series Period hibás időponttal', () =>
    eset({ bundle: kezicsomag, parameters: { 'Series Period': { low: 'tegnap', high: '2026-10-09T00:00:00+02:00' } } }, 'invalid_datetime'));
  test('Series Period nem objektum', () => eset({ bundle: kezicsomag, parameters: { 'Series Period': '2026-10' } }, 'invalid_parameter'));
  test('hibás evaluationTime', () => eset({ bundle: kezicsomag, evaluationTime: '2026-13-45' }, 'invalid_datetime'));
});

describe('Útvonal, metódus, méret', () => {
  test('ismeretlen útvonal: 404', async () => {
    const res = await fetch(`${cim}/nincs`);
    assert.equal(res.status, 404);
    assert.equal((await res.json()).error, 'not_found');
  });

  test('GET /evaluate: 405, Allow: POST', async () => {
    const res = await fetch(`${cim}/evaluate`);
    assert.equal(res.status, 405);
    assert.equal(res.headers.get('allow'), 'POST');
    assert.equal((await res.json()).error, 'method_not_allowed');
  });

  test('POST /health: 405', async () => {
    const res = await post({}, '/health');
    assert.equal(res.status, 405);
  });

  test('a korlátnál nagyobb törzs: 413', async () => {
    const res = await post('x'.repeat(TORZS_KORLAT + 1));
    assert.equal(res.status, 413);
    assert.equal((await res.json()).error, 'payload_too_large');
  });
});

describe('Kivétel a kiértékelésben', () => {
  test('500 JSON-nal, és a szolgáltatás utána is válaszol', async () => {
    // A Patient megvan, de egy Observation szerkezete a motor számára
    // feldolgozhatatlan (az effectiveDateTime nem szöveg).
    const rossz = structuredClone(kezicsomag);
    const obs = rossz.entry.find((b) => b.resource.resourceType === 'Observation');
    obs.resource.effectiveDateTime = { nem: 'időpont' };
    const res = await post({ bundle: rossz, evaluationTime: KIERTEKELES_IDOPONTJA });
    // Ha a motor ezt mégis elnyeli, a teszt ezt jelzi; a lényeg a második fele.
    assert.equal(res.status, 500, `váratlan státusz: ${res.status} ${await res.clone().text()}`);
    assert.equal((await res.json()).error, 'evaluation_failed');
    const utana = await fetch(`${cim}/health`);
    assert.equal(utana.status, 200);
  });
});
