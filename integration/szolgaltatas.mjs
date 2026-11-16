// A CQL-motor hosszan futó HTTP-szolgáltatásként (M3, K2, 1. lépés).
//
// Indítás: node szolgaltatas.mjs (a gyökér docker-compose.yml `cql`
// szolgáltatása ezt futtatja). A port a PORT környezeti változóból jön
// (alapból 8080). Új függőség nincs: a Node beépített http modulja.
//
// Az ELM induláskor EGYSZER töltődik be és fordul a motor könyvtárává; a
// kérések csak a csomagot, a paramétereket és az időpontot adják hozzá.
//
// Végpontok:
//   GET  /health    200, ha az ELM betöltődött (a compose healthcheckje ezt kérdezi)
//   POST /evaluate  törzs: { bundle, parameters?, evaluationTime? }
//                   válasz: { library, engine, evaluationTime, result, durationMs }
// Hibák JSON-ban: { error: <kód>, message: <magyarázat> }; 400 hibás bemenet
// vagy nem értelmezhető kérés-cím (invalid_request), 404 ismeretlen útvonal, 405 rossz metódus, 413 túl nagy törzs, 500 hiba a
// kiértékelésben (a folyamat ilyenkor is fut tovább).

import http from 'node:http';
import { performance } from 'node:perf_hooks';
import { pathToFileURL } from 'node:url';
import { ELM_FO, cql, csomagVerzio, elmBetoltes, kiertekeles, konyvtar } from './motor.mjs';

// A kérés törzsének felső korlátja (egy beteg csomagja ennél jóval kisebb).
export const TORZS_KORLAT = 1024 * 1024;

const ELM_TIPUS = '{urn:hl7-org:elm-types:r1}';

// Egy ELM-paraméter típusa rövid alakban: Boolean, Integer, Decimal, String,
// Interval<DateTime>; ismeretlen szerkezetnél null.
function parameterTipus(def) {
  const t = def.parameterTypeSpecifier;
  if (t?.type === 'NamedTypeSpecifier') return t.name.replace(ELM_TIPUS, '');
  if (t?.type === 'IntervalTypeSpecifier' && t.pointType?.type === 'NamedTypeSpecifier') {
    return `Interval<${t.pointType.name.replace(ELM_TIPUS, '')}>`;
  }
  return null;
}

class BemenetiHiba extends Error {
  constructor(kod, uzenet) {
    super(uzenet);
    this.kod = kod;
  }
}

const idopont = (szoveg, mezo) => {
  const dt = typeof szoveg === 'string' ? cql.DateTime.parse(szoveg) : null;
  if (dt == null) throw new BemenetiHiba('invalid_datetime', `${mezo}: ISO 8601 időpont kell, ez nem az: ${JSON.stringify(szoveg)}`);
  return dt;
};

// A kérés paramétereinek átalakítása a motor típusaira, a könyvtár
// paraméterlistája szerint. Ismeretlen név vagy rossz típus: BemenetiHiba.
function parameterekAtalakitasa(nyers, tipusok) {
  if (nyers == null) return {};
  if (typeof nyers !== 'object' || Array.isArray(nyers)) {
    throw new BemenetiHiba('invalid_parameters', 'parameters: objektum kell (név → érték)');
  }
  const kimenet = {};
  for (const [nev, ertek] of Object.entries(nyers)) {
    if (!tipusok.has(nev)) {
      throw new BemenetiHiba('unknown_parameter', `Ismeretlen paraméter: ${JSON.stringify(nev)}; ismertek: ${[...tipusok.keys()].join(', ')}`);
    }
    const tipus = tipusok.get(nev);
    const rossz = () => new BemenetiHiba('invalid_parameter', `${nev}: ${tipus} típusú érték kell, ez nem az: ${JSON.stringify(ertek)}`);
    switch (tipus) {
      case 'Boolean':
        if (typeof ertek !== 'boolean') throw rossz();
        kimenet[nev] = ertek;
        break;
      case 'String':
        if (typeof ertek !== 'string') throw rossz();
        kimenet[nev] = ertek;
        break;
      case 'Integer':
        if (!Number.isInteger(ertek)) throw rossz();
        kimenet[nev] = ertek;
        break;
      case 'Decimal':
        if (typeof ertek !== 'number' || !Number.isFinite(ertek)) throw rossz();
        kimenet[nev] = ertek;
        break;
      case 'Interval<DateTime>': {
        // { low, high, lowClosed?, highClosed? }; alapból [low, high), mint a futtatas.mjs-ben.
        if (ertek == null || typeof ertek !== 'object' || Array.isArray(ertek)) throw rossz();
        const { low, high, lowClosed = true, highClosed = false } = ertek;
        if (typeof lowClosed !== 'boolean' || typeof highClosed !== 'boolean') throw rossz();
        kimenet[nev] = new cql.Interval(idopont(low, `${nev}.low`), idopont(high, `${nev}.high`), lowClosed, highClosed);
        break;
      }
      default:
        throw new BemenetiHiba('unsupported_parameter', `${nev}: a szolgáltatás ezt a paramétertípust nem kezeli`);
    }
  }
  return kimenet;
}

// A FHIR-csomag minimális ellenőrzése: Bundle, entry-lista, pontosan egy Patient.
function csomagEllenorzes(bundle) {
  if (bundle == null || typeof bundle !== 'object' || bundle.resourceType !== 'Bundle') {
    throw new BemenetiHiba('invalid_bundle', 'bundle: FHIR R4 Bundle kell (resourceType: "Bundle")');
  }
  if (!Array.isArray(bundle.entry)) {
    throw new BemenetiHiba('invalid_bundle', 'bundle.entry: lista kell');
  }
  const betegek = bundle.entry.filter((e) => e?.resource?.resourceType === 'Patient').length;
  if (betegek !== 1) {
    throw new BemenetiHiba('invalid_bundle', `A csomagban pontosan egy Patient kell, ennyi van: ${betegek}`);
  }
}

function valasz(res, statusz, torzs, fejlecek = {}) {
  const szoveg = JSON.stringify(torzs);
  res.writeHead(statusz, {
    'Content-Type': 'application/json; charset=utf-8',
    'Content-Length': Buffer.byteLength(szoveg),
    ...fejlecek,
  });
  res.end(szoveg);
}

// A törzs beolvasása a korlátig; túllépésnél null.
// Túl nagy törzsnél a maradékot eldobva végigolvassuk, és csak a kérés végén
// válaszolunk. Ha a 413 a feltöltés közben menne ki, a kapcsolat lezárása
// megszakítaná a még író klienst, amely így a választ sem látná (ez okozta a
// teszt ritka "fetch failed" hibáját). A végtelen feltöltés ellen a
// requestTimeout véd.
function torzsOlvasas(req) {
  return new Promise((resolve, reject) => {
    const hossz = Number(req.headers['content-length']);
    let tulNagy = Number.isFinite(hossz) && hossz > TORZS_KORLAT;
    const darabok = [];
    let meret = 0;
    req.on('data', (d) => {
      if (tulNagy) return;
      meret += d.length;
      if (meret > TORZS_KORLAT) {
        tulNagy = true;
        darabok.length = 0;
        return;
      }
      darabok.push(d);
    });
    req.on('end', () => resolve(tulNagy ? null : Buffer.concat(darabok).toString('utf8')));
    req.on('error', reject);
  });
}

// A szolgáltatás felépítése (az ELM betöltésével), még figyelés nélkül; a
// tesztek ezt használják, a közvetlen indítás alább a listen-t is meghívja.
export async function szolgaltatasLetrehozas() {
  const { elm, fhirHelpersElm, sha256 } = await elmBetoltes();
  const lib = konyvtar(elm, fhirHelpersElm);
  const tipusok = new Map(elm.library.parameters.def.map((d) => [d.name, parameterTipus(d)]));
  const library = {
    id: elm.library.identifier.id,
    version: elm.library.identifier.version,
    sha256: sha256[ELM_FO],
  };
  const engine = {
    'cql-execution': await csomagVerzio('cql-execution'),
    'cql-exec-fhir': await csomagVerzio('cql-exec-fhir'),
    node: process.version,
  };

  async function evaluate(req, res) {
    const nyers = await torzsOlvasas(req);
    if (nyers == null) {
      valasz(res, 413, { error: 'payload_too_large', message: `A törzs legfeljebb ${TORZS_KORLAT} bájt lehet` }, { Connection: 'close' });
      return;
    }
    let torzs;
    try {
      torzs = JSON.parse(nyers);
    } catch {
      throw new BemenetiHiba('invalid_json', 'A törzs nem érvényes JSON');
    }
    if (torzs == null || typeof torzs !== 'object' || Array.isArray(torzs)) {
      throw new BemenetiHiba('invalid_json', 'A törzs JSON-objektum kell legyen');
    }
    csomagEllenorzes(torzs.bundle);
    const parameterek = parameterekAtalakitasa(torzs.parameters, tipusok);
    // Időpont nélkül a szolgáltatás órája számít (UTC); a megismételhető
    // futáshoz a hívó adja meg.
    const ido = torzs.evaluationTime == null
      ? cql.DateTime.fromJSDate(new Date(), 0)
      : idopont(torzs.evaluationTime, 'evaluationTime');

    const kezdet = performance.now();
    const { eredmeny } = await kiertekeles(lib, torzs.bundle, parameterek, ido);
    const durationMs = Math.round((performance.now() - kezdet) * 10) / 10;
    valasz(res, 200, { library, engine, evaluationTime: ido.toString(), result: eredmeny, durationMs });
  }

  const utvonalak = {
    '/health': { GET: (req, res) => valasz(res, 200, { status: 'ok', library }) },
    '/evaluate': { POST: evaluate },
  };

  const server = http.createServer(async (req, res) => {
    const kezdet = performance.now();
    // A nyers kérés-cím a naplóhoz, ha nem értelmezhető (pl. `GET //`: a
    // new URL ezt nem fogadja el bázissal sem). Az értelmezés a hibakezelésen
    // belül van, hogy egy hibás cím ne állítsa le a folyamatot.
    let utvonal = req.url;
    try {
      try {
        utvonal = new URL(req.url, 'http://localhost').pathname;
      } catch {
        throw new BemenetiHiba('invalid_request', `A kérés címe nem értelmezhető: ${JSON.stringify(req.url)}`);
      }
      const metodusok = utvonalak[utvonal];
      if (!metodusok) {
        valasz(res, 404, { error: 'not_found', message: `Ismeretlen útvonal: ${utvonal}` });
      } else if (!metodusok[req.method]) {
        valasz(res, 405, { error: 'method_not_allowed', message: `Ezen az útvonalon csak: ${Object.keys(metodusok).join(', ')}` }, { Allow: Object.keys(metodusok).join(', ') });
      } else {
        await metodusok[req.method](req, res);
      }
    } catch (hiba) {
      if (res.headersSent) {
        res.destroy();
      } else if (hiba instanceof BemenetiHiba) {
        valasz(res, 400, { error: hiba.kod, message: hiba.message });
      } else {
        // A motor kivétele: a hívó 500-at kap, a folyamat fut tovább.
        console.error(`Hiba a kiértékelésben: ${hiba?.stack ?? hiba}`);
        valasz(res, 500, { error: 'evaluation_failed', message: String(hiba?.message ?? hiba) });
      }
    } finally {
      // Naplósor betegadat nélkül: metódus, útvonal, státusz, idő. A sikeres
      // healthcheck (5 s-onként) nem kerül a naplóba.
      if (!(utvonal === '/health' && res.statusCode === 200)) {
        console.log(`${req.method} ${utvonal} ${res.statusCode} ${Math.round(performance.now() - kezdet)} ms`);
      }
    }
  });
  // Egy kérés legfeljebb 30 s-ig tarthat (a lassú, félbehagyott kérések ellen).
  server.requestTimeout = 30_000;
  server.on('clientError', (_hiba, socket) => {
    if (socket.writable) socket.end('HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n');
  });
  return { server, library, engine };
}

// Közvetlen indításkor (node szolgaltatas.mjs) figyel a porton; importáláskor
// (tesztek) nem.
if (process.argv[1] && pathToFileURL(process.argv[1]).href === import.meta.url) {
  const port = Number(process.env.PORT ?? 8080);
  const { server, library, engine } = await szolgaltatasLetrehozas();
  server.listen(port, () => {
    console.log(
      `CQL-szolgáltatás: ${library.id} ${library.version} (ELM sha256 ${library.sha256.slice(0, 12)}...), ` +
      `cql-execution ${engine['cql-execution']}, cql-exec-fhir ${engine['cql-exec-fhir']}, Node ${engine.node}; port ${port}`,
    );
  });
  // A konténer leállításakor (SIGTERM) azonnal kilép; PID 1-ként a Node ezt
  // magától nem tenné, és a docker stop 10 s-ot várna.
  for (const jel of ['SIGTERM', 'SIGINT']) {
    process.on(jel, () => {
      server.close();
      process.exit(0);
    });
  }
}
