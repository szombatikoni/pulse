// CQL -> ELM (JSON) fordítás a cql-translation-service segítségével.
//
// Futtatás: docker compose run --rm forditas
// (helyben is: FORDITO_URL=http://127.0.0.1:8080/cql/translator node forditas.mjs,
//  ha a fordítószolgáltatás fut és a 8080-as port ki van nyitva)
//
// A FHIRHelpers 4.0.1 forrása a fordító saját jarjából (quick-4.2.0.jar)
// kibontott, változatlan fájl; a fő könyvtár `include`-ját a szolgáltatás
// ugyanebből a jarból oldja fel. Az ELM-et mindkettőből ugyanaz a fordító
// készíti, ugyanazokkal a kapcsolókkal.

import { readFile, writeFile } from 'node:fs/promises';

const FORDITO_URL = process.env.FORDITO_URL ?? 'http://fordito:8080/cql/translator';

// locators: sor/oszlop az ELM-ben (hibakereséshez); annotations: a CQL-forrás
// az ELM-ben is benne van (a magyarázat a forrásra hivatkozhat);
// signatures=Overloads: a túlterhelt függvények hívásánál az ELM rögzíti a
// paramétertípusokat (a fordító figyelmeztetése alapján; a cql-execution
// 3.3.2 ezt nem olvassa, futásidőben típus szerint választ, de más motornak
// és a 4.x-nek hasznos).
const KAPCSOLOK = 'annotations=true&locators=true&result-types=true&signatures=Overloads';

const KONYVTARAK = [
  { cql: 'cql/FHIRHelpers-4.0.1.cql', elm: 'elm/FHIRHelpers-4.0.1.json' },
  { cql: 'cql/PulseHbpmAverage.cql', elm: 'elm/PulseHbpmAverage-0.1.0.json' },
];

async function forditas(cqlSzoveg) {
  const valasz = await fetch(`${FORDITO_URL}?${KAPCSOLOK}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/cql', Accept: 'application/elm+json' },
    body: cqlSzoveg,
  });
  const szoveg = await valasz.text();
  return { status: valasz.status, szoveg };
}

// A Java-szolgáltatás néhány másodperc alatt indul el; addig újrapróbálkozunk.
async function varakozas(maxMasodperc = 120) {
  const proba = "library Ping version '1'\ndefine X: 1\n";
  const kezdet = Date.now();
  for (;;) {
    try {
      const { status } = await forditas(proba);
      if (status === 200) return;
    } catch {
      // még nem fogad kapcsolatot
    }
    if (Date.now() - kezdet > maxMasodperc * 1000) {
      throw new Error(`A fordítószolgáltatás ${maxMasodperc} s alatt sem válaszolt: ${FORDITO_URL}`);
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
}

// A fordító az ELM library.annotation listájában adja vissza a hibákat és a figyelmeztetéseket.
function uzenetek(elm) {
  return (elm?.library?.annotation ?? [])
    .filter((a) => a.type === 'CqlToElmError')
    .map((a) => ({
      sulyossag: a.errorSeverity,
      tipus: a.errorType,
      hely: a.startLine != null ? `${a.startLine}:${a.startChar}` : '',
      uzenet: a.message,
    }));
}

await varakozas();
let hiba = false;
for (const k of KONYVTARAK) {
  const cqlSzoveg = await readFile(k.cql, 'utf8');
  const { status, szoveg } = await forditas(cqlSzoveg);
  let elm;
  try {
    elm = JSON.parse(szoveg);
  } catch {
    console.error(`${k.cql}: HTTP ${status}, nem JSON válasz:\n${szoveg.slice(0, 2000)}`);
    hiba = true;
    continue;
  }
  const lista = uzenetek(elm);
  for (const u of lista) {
    console.log(`  [${u.sulyossag}] ${k.cql}:${u.hely} ${u.uzenet}`);
  }
  const hibak = lista.filter((u) => u.sulyossag === 'error');
  if (status !== 200 || hibak.length > 0) {
    console.error(`${k.cql}: SIKERTELEN fordítás (HTTP ${status}, ${hibak.length} hiba)`);
    hiba = true;
    continue;
  }
  await writeFile(k.elm, JSON.stringify(elm, null, 2) + '\n', 'utf8');
  const id = elm.library.identifier;
  console.log(`${k.cql} -> ${k.elm} (${id.id} ${id.version}, ${lista.length} üzenet)`);
}
process.exit(hiba ? 1 : 0);
