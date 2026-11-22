/* PULSE felületterv · alapok: segédfüggvények, ikonok, példaadat, grafikonok.
   Minden név és érték mesterséges példaadat (a demó seed neveivel és szabályaival). */
'use strict';

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));
const esc = (s) =>
  String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);

/* ---------- idő és számok, magyar formában ---------- */
const NOW = new Date(2026, 9, 30, 12, 40); // a bemutató „most”-ja: péntek 12:40
const DAY = 86400000;
const MONTHS = ['jan.', 'febr.', 'márc.', 'ápr.', 'máj.', 'jún.', 'júl.', 'aug.', 'szept.', 'okt.', 'nov.', 'dec.'];
const MONTHS_LONG = ['január', 'február', 'március', 'április', 'május', 'június', 'július', 'augusztus',
  'szeptember', 'október', 'november', 'december'];
const WEEKDAYS = ['vasárnap', 'hétfő', 'kedd', 'szerda', 'csütörtök', 'péntek', 'szombat'];
const pad2 = (n) => String(n).padStart(2, '0');
const sod = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
const daysAgo = (d) => Math.round((sod(NOW) - sod(d)) / DAY);
const at = (off, hh, mm) => {
  const d = sod(NOW);
  d.setDate(d.getDate() - off);
  d.setHours(hh, mm, 0, 0);
  return d;
};
const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
const fTime = (d) => `${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
const fDay = (d) => `${MONTHS[d.getMonth()]} ${d.getDate()}.`;
const fDayTime = (d) => `${fDay(d)} ${fTime(d)}`;
const fDayLong = (d) => `${fDay(d)}, ${WEEKDAYS[d.getDay()]}`;
const fLongDate = (d) => `${cap(WEEKDAYS[d.getDay()])}, ${MONTHS_LONG[d.getMonth()]} ${d.getDate()}.`;
const fRel = (d) => {
  const n = daysAgo(d);
  if (n === 0) return `ma ${fTime(d)}`;
  if (n === 1) return `tegnap ${fTime(d)}`;
  if (n < 7) return `${n} napja`;
  return fDay(d);
};
const fNum = (v, dec = 0) => v.toFixed(dec).replace('.', ',');
const ageOf = (b) => {
  let a = NOW.getFullYear() - b[0];
  if (NOW < new Date(NOW.getFullYear(), b[1] - 1, b[2])) a -= 1;
  return a;
};
const fBorn = (b) => `${b[0]}. ${MONTHS_LONG[b[1] - 1]} ${b[2]}.`;

/* ---------- determinisztikus véletlen a példaadathoz ---------- */
function rng(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const gauss = (r) => {
  let u = 0;
  for (let i = 0; i < 12; i += 1) u += r();
  return u - 6;
};
const weekly = (first, n) => Array.from({ length: n }, (_, i) => first + 7 * i);

/* ---------- ikonok: választható készlet (pulse-icons.js) ---------- */
const iconKey = () => (ICONSETS[document.documentElement.dataset.icons] ? document.documentElement.dataset.icons : 'phosphor');
const icon = (name, cls = '') => {
  const k = iconKey();
  const body = ICONSETS[k].ic[name] || '';
  return k === 'phosphor'
    ? `<svg class="ic ${cls}" viewBox="0 0 256 256" fill="currentColor" aria-hidden="true">${body}</svg>`
    : `<svg class="ic ${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;
};
const BRAND = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 12.5h3.7l2.3-5.6 3.8 11 2.5-7.1 1.4 1.7H21"/></svg>';

/* ---------- státusz: teli forma, fehér jel; a forma is különbözik ---------- */
const ST = {
  severe: { label: 'Súlyos', v: '--s-severe' },
  attention: { label: 'Figyelem', v: '--s-attention' },
  no_data: { label: 'Adathiány', v: '--s-nodata' },
  handled: { label: 'Kezelve', v: '--s-handled' },
  ok: { label: 'Rendben', v: '--s-ok' },
};
const ST_ORDER = ['severe', 'attention', 'no_data', 'handled', 'ok'];
const W = 'var(--on-fill)';
// teli kör a státusz színében, benne fehér jel az ikonkészletből; a jel is különbözik
function sicon(s, size = 18, inverse = false) {
  const k = iconKey();
  const g = ICONSETS[k].gl[s];
  const fill = inverse ? W : `var(${ST[s].v})`;
  const mark = inverse ? `var(${ST[s].v})` : W;
  const glyph = k === 'phosphor'
    ? `<svg x="3.7" y="3.7" width="12.6" height="12.6" viewBox="0 0 256 256" fill="${mark}">${g}</svg>`
    : `<svg x="3.9" y="3.9" width="12.2" height="12.2" viewBox="0 0 24 24" fill="none" stroke="${mark}" stroke-width="2.7" stroke-linecap="round" stroke-linejoin="round">${g}</svg>`;
  return `<svg class="si" width="${size}" height="${size}" viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="10" fill="${fill}"/>${glyph}</svg>`;
}
function statusTag(s, opts = {}) {
  // teli címke: a Megjelenés panelen választható, hogy mind teli, vagy csak a Súlyos
  const all = document.documentElement.dataset.pills !== 'sulyos';
  if (!opts.plain && (all || s === 'severe')) {
    return `<span class="st-pill" style="--pill:var(${ST[s].v}-pill, var(${ST[s].v}))">${sicon(s, 18, true)}${ST[s].label}</span>`;
  }
  const loud = s === 'severe' || s === 'attention';
  return `<span class="st ${loud ? 'loud' : ''}">${sicon(s, opts.size || 22)}${ST[s].label}</span>`;
}

/* ---------- példaadat ---------- */
const DR = { kovacs: 'Dr. Kovács Éva', nagy: 'Dr. Nagy Péter' };
const DISCLAIMER =
  'Demonstrációs rendszer, kizárólag mesterséges adatokkal. Nem orvostechnikai eszköz, és nem helyettesíti az orvosi döntést.';
const UNIT = { bp: 'Hgmm', pulse: '/perc', weight: 'kg', glucose: 'mmol/l' };

// A „Közérzet” kérdőív (seed/questionnaires.py): több pont = rosszabb; 0–5 rendben,
// 6–10 figyelmeztető, 11–13 kritikus.
const QUESTIONNAIRE = {
  name: 'Közérzet',
  max: 13,
  questions: [
    { id: 'q1', text: 'Hogyan aludt az elmúlt éjszaka?', kind: 'scale', min: 'nagyon rosszul', maxL: 'nagyon jól' },
    { id: 'q2', text: 'Mennyire fáradt ma?', kind: 'scale', min: 'egyáltalán nem', maxL: 'nagyon' },
    { id: 'q3', text: 'Tapasztalt-e szédülést az elmúlt héten?', kind: 'single',
      options: [{ v: 'never', l: 'Nem', s: 0 }, { v: 'rarely', l: 'Ritkán', s: 2 }, { v: 'daily', l: 'Naponta', s: 5 }] },
  ],
};
const bandOf = (score) => (score >= 11 ? 'critical' : score >= 6 ? 'warning' : 'normal');
const BAND_LABEL = { normal: 'rendben', warning: 'figyelmeztető', critical: 'kritikus' };
const BAND_STATUS = { normal: null, warning: 'attention', critical: 'severe' };
// pontszám → egy lehetséges válaszsor (alvás 1–5, fáradtság 1–5, szédülés)
const ANSWERS = {
  0: [5, 1, 'never'], 1: [5, 2, 'never'], 2: [4, 2, 'never'], 3: [4, 3, 'never'], 4: [4, 2, 'rarely'],
  5: [3, 2, 'rarely'], 6: [3, 3, 'rarely'], 7: [2, 3, 'rarely'], 8: [2, 4, 'rarely'], 9: [2, 5, 'rarely'],
  10: [1, 5, 'rarely'], 11: [2, 4, 'daily'], 12: [1, 4, 'daily'], 13: [1, 5, 'daily'],
};

// Szabó János utolsó 30 napja kézzel (a riasztás története ezen áll); null = elmaradt mérés.
const SZABO_BP = {
  29: [132, 84], 28: [129, 83], 27: [134, 85], 26: [131, 82], 25: [128, 81], 24: [133, 84], 23: [136, 86],
  22: [132, 84], 21: [128, 82], 20: [135, 86], 19: [130, 83], 18: [134, 85], 17: [129, 81], 16: [137, 87],
  15: [138, 88], 14: [136, 86], 13: [133, 85], 12: [135, 84], 11: [131, 83], 10: [134, 86], 9: [137, 88],
  8: [139, 88], 7: [136, 87], 6: [138, 89], 5: null, 4: [139, 88], 3: [146, 92], 2: [138, 88], 1: [144, 91],
  0: [152, 95],
};

const PATIENTS = [
  { id: 'varga', name: 'Varga Béla', born: [1949, 7, 21], seed: 11,
    bp: { sys: 135, dia: 85, sd: 3, rise: [16, 26, 10], hh: 7, mm: 24, exact: { 1: [162, 98], 0: [186, 104] }, trig: [0] },
    pulse: { base: 84, sd: 4, every: 1, hh: 7, mm: 25 }, weight: { base: 91.6, drift: -0.004 },
    q: { offs: weekly(3, 13), scores: [4, 3, 4, 3, 3, 4, 3, 3, 2, 3, 3, 2, 3], hh: 18, mm: 10 },
    tasks: { tone: 'ok', text: 'a teendők rendben' } },
  { id: 'szabo', name: 'Szabó János', born: [1958, 3, 14], seed: 22,
    bp: { sys: 131, dia: 84, sd: 3, hh: 7, mm: 30, exact: SZABO_BP, trig: [3, 1, 0] },
    pulse: { base: 74, sd: 3.5, every: 2, hh: 7, mm: 31 }, weight: { base: 86.7, drift: -0.01, missing: [11] },
    q: { offs: weekly(1, 13), scores: [6, 5, 5, 4, 3, 2, 3, 2, 2, 3, 2, 2, 3], hh: 19, mm: 0 },
    tasks: { tone: 'ok', text: 'a teendők rendben' },
    notes: [{ t: at(10, 14, 20), by: DR.kovacs,
      text: 'Telefonon egyeztetve: a reggeli mérést ülve, öt perc pihenés után végezze, mindig ugyanazon a karon.' }] },
  { id: 'horvath', name: 'Horváth Erzsébet', born: [1955, 2, 3], seed: 33, stop: 1,
    bp: { sys: 129, dia: 81, sd: 3.5, hh: 7, mm: 40 }, pulse: { base: 77, sd: 3, every: 3, hh: 7, mm: 41 },
    weight: { base: 72.3, drift: 0.004 },
    q: { offs: weekly(2, 13), scores: [9, 5, 5, 4, 3, 3, 2, 3, 2, 2, 3, 2, 2], hh: 18, mm: 40 },
    tasks: { tone: 'late', text: 'Vérnyomás: lejárt határidő' } },
  { id: 'kiss', name: 'Kiss Ilona', born: [1971, 5, 9], seed: 44, stop: 12,
    bp: { sys: 124, dia: 79, sd: 3.5, hh: 8, mm: 5 }, pulse: { base: 71, sd: 3, every: 2, hh: 8, mm: 6 },
    weight: { base: 64.1, drift: 0 }, q: { offs: weekly(13, 11), scores: [2, 3, 2, 2, 1, 2, 3, 2, 2, 1, 2], hh: 20, mm: 15 },
    tasks: { tone: 'late', text: 'Vérnyomás: lejárt határidő +1' } },
  { id: 'papp', name: 'Papp László', born: [1968, 9, 12], seed: 55, empty: true,
    tasks: { tone: 'late', text: 'Vérnyomás: lejárt határidő' } },
  { id: 'nagy', name: 'Nagy Gábor', born: [1962, 4, 18], seed: 66,
    bp: { sys: 132, dia: 83, sd: 2.5, hh: 7, mm: 50, exact: { 2: [148, 93] } }, pulse: { base: 79, sd: 4, every: 2, hh: 7, mm: 51 },
    weight: { base: 95.2, drift: -0.006 }, q: { offs: weekly(4, 13), scores: [3, 3, 2, 4, 3, 2, 3, 3, 2, 3, 2, 3, 2], hh: 17, mm: 30 },
    tasks: { tone: 'due', text: 'Közérzet: esedékes vasárnap 20:00' } },
  { id: 'molnar', name: 'Molnár Katalin', born: [1966, 1, 30], seed: 77,
    bp: { sys: 122, dia: 78, sd: 3, hh: 7, mm: 30 }, pulse: { base: 68, sd: 3, every: 3, hh: 7, mm: 31 },
    weight: { base: 61.8, drift: 0 }, q: { offs: weekly(5, 13), scores: [1, 2, 1, 1, 2, 1, 1, 2, 1, 1, 2, 1, 1], hh: 19, mm: 30 },
    tasks: { tone: 'ok', text: 'a teendők rendben' } },
  { id: 'balogh', name: 'Balogh Péter', born: [1960, 6, 2], seed: 88,
    bp: { sys: 127, dia: 82, sd: 3, hh: 6, mm: 55 }, pulse: { base: 72, sd: 3, every: 2, hh: 6, mm: 56 },
    weight: { base: 83.5, drift: -0.003 }, q: { offs: weekly(1, 13), scores: [2, 2, 3, 2, 2, 1, 2, 2, 3, 2, 2, 2, 1], hh: 20, mm: 5 },
    tasks: { tone: 'due', text: 'Testsúly: esedékes ma 20:00' } },
  { id: 'farkas', name: 'Farkas Zsuzsanna', born: [1967, 10, 22], seed: 99,
    bp: { sys: 118, dia: 76, sd: 3, hh: 20, mm: 10, lag: 1 }, pulse: { base: 70, sd: 3, every: 2, hh: 20, mm: 11 },
    weight: { base: 58.9, drift: 0 }, q: { offs: weekly(6, 13), scores: [1, 1, 2, 1, 1, 2, 1, 1, 1, 2, 1, 1, 1], hh: 20, mm: 30 },
    tasks: { tone: 'ok', text: 'a teendők rendben' } },
  { id: 'takacs', name: 'Takács Judit', born: [1953, 12, 8], seed: 111,
    bp: { sys: 126, dia: 80, sd: 3.5, hh: 8, mm: 5 }, pulse: { base: 73, sd: 3, every: 2, hh: 8, mm: 6 },
    weight: { base: 69.4, drift: 0 }, q: { offs: weekly(2, 13), scores: [3, 2, 2, 3, 2, 2, 2, 3, 2, 2, 2, 3, 2], hh: 16, mm: 45 },
    tasks: { tone: 'ok', text: 'a teendők rendben' } },
  { id: 'juhasz', name: 'Juhász Ferenc', born: [1957, 8, 27], seed: 122,
    bp: { sys: 130, dia: 83, sd: 3, hh: 7, mm: 2, missing: [1] }, pulse: { base: 76, sd: 3, every: 2, hh: 7, mm: 3 },
    weight: { base: 88.1, drift: 0 }, q: { offs: weekly(3, 13), scores: [2, 3, 2, 2, 3, 2, 2, 2, 3, 2, 2, 2, 3], hh: 19, mm: 20 },
    tasks: { tone: 'late', text: 'Vérnyomás: az előző elmaradt' } },
  { id: 'lakatos', name: 'Lakatos Anna', born: [1964, 3, 3], seed: 133,
    bp: { sys: 121, dia: 77, sd: 3, hh: 21, mm: 30, lag: 1 }, pulse: { base: 69, sd: 3, every: 2, hh: 21, mm: 31 },
    weight: { base: 66.2, drift: 0 }, q: { offs: weekly(5, 13), scores: [1, 2, 1, 2, 1, 1, 2, 1, 1, 2, 1, 1, 1], hh: 21, mm: 0 },
    tasks: { tone: 'ok', text: 'a teendők rendben' } },
];
const PAT = Object.fromEntries(PATIENTS.map((p) => [p.id, p]));

// A beteg nézetének szereplője (Dr. Nagy Péter betege a seedben).
const MARIA = { id: 'toth', name: 'Tóth Mária', first: 'Mária', born: [1962, 11, 2], seed: 144,
  bp: { sys: 124, dia: 79, sd: 3, hh: 7, mm: 12, exact: { 3: [158, 96], 0: [124, 79] } },
  pulse: { base: 71, sd: 2.5, every: 1, hh: 20, mm: 32, missing: [1], lag: 1 },
  weight: { base: 68.9, drift: -0.006 },
  q: { offs: weekly(7, 8), scores: [2, 1, 2, 2, 1, 2, 3, 2], hh: 19, mm: 40 } };

function genBP(p) {
  if (!p.bp) return [];
  const r = rng(p.seed);
  const out = [];
  const stop = Math.max(p.stop || 0, p.bp.lag || 0);
  for (let off = 89; off >= stop; off -= 1) {
    const ex = p.bp.exact ? p.bp.exact[off] : undefined;
    const noiseS = gauss(r) * p.bp.sd;
    const noiseD = gauss(r) * p.bp.sd * 0.6;
    const jitter = Math.round((r() - 0.5) * 12);
    if (ex === null || (p.bp.missing && p.bp.missing.includes(off))) continue;
    let sys;
    let dia;
    if (ex) [sys, dia] = ex;
    else {
      // emelkedés: az utolsó rise[0] napban lineárisan rise[1] / rise[2] Hgmm-mel
      const k = p.bp.rise ? Math.max(0, 1 - off / p.bp.rise[0]) : 0;
      const [rs, rd] = p.bp.rise ? [p.bp.rise[1], p.bp.rise[2]] : [0, 0];
      sys = Math.round(p.bp.sys + k * rs + noiseS);
      dia = Math.round(p.bp.dia + k * rd + noiseD);
    }
    const t = ex ? at(off, p.bp.hh, p.bp.mm) : at(off, p.bp.hh, p.bp.mm + jitter);
    if (t > NOW) continue; // a mai esti mérés még nem történt meg
    out.push({ t, sys, dia, trig: !!(p.bp.trig && p.bp.trig.includes(off)) });
  }
  return out;
}
function genSeries(spec, p, salt, dec) {
  if (!spec) return [];
  const r = rng(p.seed * 7 + salt);
  const out = [];
  const stop = Math.max(p.stop || 0, spec.lag || 0);
  for (let off = 89; off >= stop; off -= 1) {
    const n = gauss(r);
    if (spec.every && off % spec.every !== 0) continue;
    if (spec.missing && spec.missing.includes(off)) continue;
    const v = spec.base + n * spec.sd;
    const t = at(off, spec.hh, spec.mm + Math.round((r() - 0.5) * 10));
    if (t > NOW) continue;
    out.push({ t, v: +v.toFixed(dec) });
  }
  return out;
}
function genWeight(p) {
  if (!p.weight) return [];
  const r = rng(p.seed * 13 + 5);
  const out = [];
  const stop = p.stop || 0;
  for (let off = 89; off >= stop; off -= 1) {
    if (at(off, 12, 0).getDay() !== 1) continue; // hétfőnként
    if (p.weight.missing && p.weight.missing.includes(off)) continue;
    const v = p.weight.base + p.weight.drift * (89 - off) + gauss(r) * 0.18;
    out.push({ t: at(off, 7, 5 + Math.round(r() * 8)), v: +v.toFixed(1) });
  }
  return out;
}
function genSubs(p) {
  if (!p.q) return [];
  return p.q.offs.map((off, i) => {
    const score = p.q.scores[i];
    return { t: at(off, p.q.hh, p.q.mm), score, band: bandOf(score), version: 1, answers: ANSWERS[score] };
  }).filter((s) => s.t <= NOW && daysAgo(s.t) >= (p.stop || 0) && daysAgo(s.t) < 90);
}
function buildData(p) {
  if (p.empty) return Object.assign(p, { bpS: [], pulseS: [], weightS: [], subs: [], lastAt: null });
  p.bpS = genBP(p);
  p.pulseS = genSeries(p.pulse, p, 1, 0);
  p.weightS = genWeight(p);
  p.subs = genSubs(p).sort((a, b) => b.t - a.t);
  const all = [...p.bpS, ...p.pulseS, ...p.weightS, ...p.subs].map((x) => +x.t);
  p.lastAt = all.length ? new Date(Math.max(...all)) : null;
  return p;
}
PATIENTS.forEach(buildData);
buildData(MARIA);

/* riasztások (riasztás-életút: keletkezett, megtekintve, felelőshöz rendelve, lezárva) */
const EVENT_LABEL = {
  created: 'Keletkezett', re: 'Ismételt aktiválódás', seen: 'Megtekintve', assigned: 'Felelőshöz rendelve',
  closed: 'Lezárva', rule: 'A szabály módosult', corrected: 'Kiváltó adat javítva',
};
const ALERTS = [
  { id: 'a3', pid: 'varga', sev: 'severe', kind: 'threshold', title: 'Vérnyomás a súlyos határ fölött',
    rule: 'Küszöbszabály', ver: 1, value: '186/104', unit: 'Hgmm', at: at(0, 7, 24),
    cond: 'Szisztolés > 180 Hgmm',
    why: 'A ma reggeli szisztolés érték 6 Hgmm-rel a súlyos határ fölött van. Az előző napokban 150 és 165 között mozgott.',
    reason: 'Szisztolés <b>186</b> Hgmm, a súlyos határ 180',
    events: [{ t: at(0, 7, 26), type: 'created', data: '186/104 Hgmm' }] },
  { id: 'a4', pid: 'varga', sev: 'moderate', kind: 'threshold', title: 'Vérnyomás a határ fölött',
    rule: 'Küszöbszabály', ver: 1, value: '162/98', unit: 'Hgmm', at: at(1, 7, 22),
    cond: 'Szisztolés > 140 Hgmm vagy diasztolés > 90 Hgmm',
    why: 'Tíz napja minden mérés a határ fölött van. A riasztás azóta nyitott, az új mérések ismételt aktiválódásként kerülnek bele.',
    reason: 'Vérnyomás 10 napja a 140/90 fölött',
    events: [{ t: at(10, 7, 26), type: 'created', data: '146/89 Hgmm' }, { t: at(9, 9, 3), type: 'seen', who: DR.kovacs },
      { t: at(1, 7, 24), type: 're', data: '162/98 Hgmm' }] },
  { id: 'a1', pid: 'szabo', sev: 'moderate', kind: 'threshold', title: 'Vérnyomás a határ fölött',
    rule: 'Küszöbszabály', ver: 1, value: '152/95', unit: 'Hgmm', at: at(0, 7, 30),
    cond: 'Szisztolés > 140 Hgmm vagy diasztolés > 90 Hgmm',
    why: 'A ma reggeli mérés mindkét határt átlépte (szisztolés +12, diasztolés +5). Négy napon belül ez a harmadik ilyen mérés.',
    reason: 'Vérnyomás <b>152/95</b> Hgmm, a határ 140/90',
    events: [{ t: at(3, 7, 32), type: 'created', data: '146/92 Hgmm' }, { t: at(1, 7, 32), type: 're', data: '144/91 Hgmm' },
      { t: at(0, 7, 32), type: 're', data: '152/95 Hgmm' }, { t: at(0, 8, 12), type: 'seen', who: DR.kovacs }] },
  { id: 'a2', pid: 'szabo', sev: 'moderate', kind: 'questionnaire', title: 'Közérzet: figyelmeztető sáv',
    rule: 'Kérdőívszabály', ver: 1, value: '6', unit: '/13 pont', at: at(1, 19, 0),
    cond: '„Közérzet” pontszáma a figyelmeztető vagy kritikus sávban',
    why: 'A 6 pont a figyelmeztető sáv (6–10) alsó határa. Az előző két kitöltés 5 pont volt.',
    reason: '„Közérzet” kérdőív: <b>6/13</b> pont, figyelmeztető sáv',
    events: [{ t: at(1, 19, 2), type: 'created', data: '6/13 pont' }] },
  { id: 'a5', pid: 'horvath', sev: 'moderate', kind: 'questionnaire', title: 'Közérzet: figyelmeztető sáv',
    rule: 'Kérdőívszabály', ver: 1, value: '9', unit: '/13 pont', at: at(2, 18, 40),
    cond: '„Közérzet” pontszáma a figyelmeztető vagy kritikus sávban',
    why: 'Az előző héten 5 pont volt, most 9. A szédülésre adott válasz „Ritkán”, a fáradtság 5-ös.',
    reason: '„Közérzet” kérdőív: <b>9/13</b> pont, figyelmeztető sáv',
    events: [{ t: at(2, 18, 42), type: 'created', data: '9/13 pont' }] },
  { id: 'a6', pid: 'nagy', sev: 'moderate', kind: 'threshold', title: 'Vérnyomás a határ fölött',
    rule: 'Küszöbszabály', ver: 1, value: '148/93', unit: 'Hgmm', at: at(2, 7, 50),
    cond: 'Szisztolés > 140 Hgmm vagy diasztolés > 90 Hgmm',
    why: 'Egyetlen mérés volt a határ fölött, azóta 127 és 138 között mér.',
    reason: 'Riasztás felelősnél: Dr. Kovács Éva, tegnap 09:05',
    events: [{ t: at(2, 7, 52), type: 'created', data: '148/93 Hgmm' }, { t: at(2, 11, 40), type: 'seen', who: DR.kovacs },
      { t: at(1, 9, 5), type: 'assigned', who: DR.kovacs }] },
];
const has = (a, type) => a.events.some((e) => e.type === type);
const openAlerts = (pid) => ALERTS.filter((a) => (!pid || a.pid === pid) && !has(a, 'closed'));
function statusOf(p) {
  const open = openAlerts(p.id);
  const active = open.filter((a) => !has(a, 'assigned'));
  if (active.some((a) => a.sev === 'severe')) return 'severe';
  if (active.length) return 'attention';
  if (open.length) return 'handled';
  if (!p.lastAt || daysAgo(p.lastAt) > 3) return 'no_data';
  return 'ok';
}
function reasonsOf(p) {
  const open = openAlerts(p.id).sort((a, b) => (a.sev === b.sev ? b.at - a.at : a.sev === 'severe' ? -1 : 1));
  if (open.length) {
    return open.map((a) => ({
      s: has(a, 'assigned') ? 'handled' : a.sev === 'severe' ? 'severe' : 'attention',
      text: has(a, 'assigned') && !a.reason.startsWith('Riasztás') ? `Riasztás felelősnél: ${a.title.toLowerCase()}` : a.reason,
    }));
  }
  if (!p.lastAt) return [{ s: 'no_data', text: 'Még nem érkezett adat' }];
  if (daysAgo(p.lastAt) > 3) return [{ s: 'no_data', text: `Nincs friss adat: ${daysAgo(p.lastAt)} napja nem érkezett mérés` }];
  return [{ s: 'ok', text: 'Friss adat, nincs nyitott riasztás', calm: true }];
}

/* ---------- grafikonok: kézzel rajzolt SVG, egy tengely, halk rács ---------- */
const CHARTS = new Map();
let chartSeq = 0;
function chart(spec) {
  const id = `ch${(chartSeq += 1)}`;
  CHARTS.set(id, spec);
  return `<div class="chart" data-chart="${id}" style="height:${spec.h}px"></div>`;
}
function drawCharts(root = document) {
  $$('[data-chart]', root).forEach((el) => {
    const spec = CHARTS.get(el.dataset.chart);
    if (!spec) return;
    const w = Math.max(220, Math.floor(el.getBoundingClientRect().width));
    const out = spec.kind === 'bp' ? drawBP(w, spec) : spec.kind === 'score' ? drawScore(w, spec) : drawLine(w, spec);
    el.innerHTML = out.svg;
    bindHover(el, out.hover);
  });
}
const lin = (d0, d1, r0, r1) => (v) => r0 + ((v - d0) * (r1 - r0)) / (d1 - d0 || 1);
function nice(lo, hi, count) {
  const raw = (hi - lo || 1) / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const f = raw / mag;
  const step = (f >= 7.5 ? 10 : f >= 3.5 ? 5 : f >= 1.5 ? 2 : 1) * mag;
  const a = Math.floor(lo / step) * step;
  const b = Math.ceil(hi / step) * step;
  const ticks = [];
  for (let v = a; v <= b + step * 1e-6; v += step) ticks.push(Math.round(v * 1e6) / 1e6);
  return { lo: a, hi: b, ticks };
}
function frame(w, spec, m) {
  const n = spec.days;
  const x0 = m.l;
  const x1 = w - m.r;
  const dw = (x1 - x0) / n;
  return { n, x0, x1, dw, xt: (t) => x0 + (n - 1 - daysAgo(t) + 0.5) * dw };
}
function xAxis(f, h) {
  // legalább ~58 px a feliratok között, hogy keskeny grafikonon se fedjék egymást
  const min = Math.ceil(58 / f.dw);
  const step = [1, 2, 7, 14, 21, 28, 35, 42].find((s) => s >= min) || 45;
  let s = '';
  for (let k = 0; k < f.n; k += step) {
    const d = at(k, 12, 0);
    s += `<text class="xt" x="${(f.x0 + (f.n - 1 - k + 0.5) * f.dw).toFixed(1)}" y="${h - 6}" text-anchor="middle">${fDay(d)}</text>`;
  }
  return s;
}
function yGrid(ticks, y, f, fmt = String) {
  return ticks
    .map((v) => `<line class="gl" x1="${f.x0}" x2="${f.x1}" y1="${y(v).toFixed(1)}" y2="${y(v).toFixed(1)}"/><text class="yt" x="${f.x0 - 8}" y="${(y(v) + 3.8).toFixed(1)}" text-anchor="end">${fmt(v)}</text>`)
    .join('');
}
function svgWrap(w, h, label, inner, m) {
  return `<svg viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" role="img" tabindex="0" aria-label="${esc(label)}">${inner.grid}<line class="xh" x1="0" x2="0" y1="${m.t}" y2="${h - m.b}"/>${inner.marks}</svg>`;
}

function drawBP(w, spec) {
  const h = spec.h;
  const m = { l: 36, r: spec.thresholds ? 40 : 24, t: 10, b: 26 };
  const f = frame(w, spec, m);
  const pts = spec.points.filter((p) => daysAgo(p.t) < f.n);
  const vals = pts.flatMap((p) => [p.sys, p.dia]);
  const thr = spec.thresholds || [];
  let lo = Math.min(...vals, ...thr.map((t) => t.v)) - 8;
  let hi = Math.max(...vals, ...thr.map((t) => t.v)) + 8;
  const nk = nice(lo, hi, 5);
  lo = nk.lo;
  hi = nk.hi;
  const y = lin(lo, hi, h - m.b, m.t);
  let grid = yGrid(nk.ticks, y, f) + xAxis(f, h);
  for (const t of thr) {
    const yy = y(t.v).toFixed(1);
    grid += `<line class="thr thr-${t.kind}" x1="${f.x0}" x2="${f.x1}" y1="${yy}" y2="${yy}"/><text class="thl" x="${f.x1 + 6}" y="${(+yy + 3.8).toFixed(1)}">${t.v}</text>`;
  }
  const r = Math.max(2.6, Math.min(4.5, f.dw * 0.3));
  const sw = Math.max(1.5, Math.min(2, r * 0.45));
  const limS = thr.find((t) => t.comp === 'sys' && t.kind === 'mod');
  const limD = thr.find((t) => t.comp === 'dia' && t.kind === 'mod');
  const sevS = thr.find((t) => t.comp === 'sys' && t.kind === 'sev');
  let marks = '';
  const xs = [];
  const ys = [];
  pts.forEach((p, i) => {
    const X = f.xt(p.t);
    const cs = sevS && p.sys > sevS.v ? 'sev' : limS && p.sys > limS.v ? 'mod' : '';
    const cd = limD && p.dia > limD.v ? 'mod' : '';
    marks += `<line class="stem" x1="${X.toFixed(1)}" x2="${X.toFixed(1)}" y1="${y(p.sys).toFixed(1)}" y2="${y(p.dia).toFixed(1)}" stroke-width="${sw}"/>`;
    marks += `<circle class="dot dia ${cd}" cx="${X.toFixed(1)}" cy="${y(p.dia).toFixed(1)}" r="${r}"/>`;
    marks += `<circle class="dot sys ${cs}" data-i="${i}" cx="${X.toFixed(1)}" cy="${y(p.sys).toFixed(1)}" r="${r}"/>`;
    if (p.trig && spec.thresholds) marks += `<circle class="trig" cx="${X.toFixed(1)}" cy="${y(p.sys).toFixed(1)}" r="${r + 3.5}"/>`;
    xs.push(X);
    ys.push(y(p.sys));
  });
  const tip = (i) => {
    const p = pts[i];
    let s = `<span class="tl">${fDayLong(p.t)} · ${fTime(p.t)}</span><span class="tv">${p.sys}/${p.dia} <small class="muted">Hgmm</small></span>`;
    if (spec.thresholds) {
      if (sevS && p.sys > sevS.v) s += `<span class="tf">${sicon('severe', 14)}A súlyos határ (${sevS.v}) fölött</span>`;
      else if ((limS && p.sys > limS.v) || (limD && p.dia > limD.v)) s += `<span class="tf">${sicon('attention', 14)}A határ (${limS.v}/${limD.v}) fölött</span>`;
      if (p.trig) s += `<span class="tf">${icon('bell')}Riasztást váltott ki</span>`;
    }
    return s;
  };
  return { svg: svgWrap(w, h, spec.label, { grid, marks }, m), hover: { w, h, xs, ys, tip } };
}

function drawLine(w, spec) {
  const h = spec.h;
  const m = { l: 34, r: 40, t: 12, b: 26 };
  const f = frame(w, spec, m);
  const pts = spec.points.filter((p) => daysAgo(p.t) < f.n);
  const vs = pts.map((p) => p.v);
  const span = Math.max(...vs) - Math.min(...vs);
  const pad = Math.max(span * 0.3, spec.minPad || 2);
  const nk = nice(Math.min(...vs) - pad, Math.max(...vs) + pad, 3);
  const y = lin(nk.lo, nk.hi, h - m.b, m.t);
  const fmt = (v) => fNum(v, spec.dec || 0);
  const grid = yGrid(nk.ticks, y, f, (v) => fNum(v, Number.isInteger(v) ? 0 : 1)) + xAxis(f, h);
  // a vonal megszakad, ha két mérés között a megszokottnál nagyobb a szünet
  const segs = [];
  let cur = [];
  pts.forEach((p, i) => {
    if (i && daysAgo(pts[i - 1].t) - daysAgo(p.t) > (spec.gap || 2)) {
      segs.push(cur);
      cur = [];
    }
    cur.push(p);
  });
  if (cur.length) segs.push(cur);
  let marks = '';
  for (const s of segs) {
    // terület nincs: a tengely nem nulláról indul, a kitöltés nagyságot sugallna
    const d = s.map((p, i) => `${i ? 'L' : 'M'}${f.xt(p.t).toFixed(1)},${y(p.v).toFixed(1)}`).join('');
    if (s.length > 1) marks += `<path class="line" d="${d}"/>`;
    if (s.length === 1 || spec.dots) {
      s.forEach((p) => { marks += `<circle class="dot pt" cx="${f.xt(p.t).toFixed(1)}" cy="${y(p.v).toFixed(1)}" r="3.5"/>`; });
    }
  }
  const last = pts[pts.length - 1];
  const lx = f.xt(last.t);
  const ly = y(last.v);
  marks += `<circle class="end" data-i="${pts.length - 1}" cx="${lx.toFixed(1)}" cy="${ly.toFixed(1)}" r="4.5"/>`;
  marks += `<text class="endl" x="${(lx + 9).toFixed(1)}" y="${(ly + 4).toFixed(1)}">${fmt(last.v)}</text>`;
  const tip = (i) => `<span class="tl">${fDayLong(pts[i].t)} · ${fTime(pts[i].t)}</span><span class="tv">${fmt(pts[i].v)} <small class="muted">${esc(spec.unit)}</small></span>`;
  return { svg: svgWrap(w, h, spec.label, { grid, marks }, m), hover: { w, h, xs: pts.map((p) => f.xt(p.t)), ys: pts.map((p) => y(p.v)), tip } };
}

function drawScore(w, spec) {
  const h = spec.h;
  const m = { l: 34, r: 40, t: 12, b: 26 };
  const f = frame(w, spec, m);
  const pts = spec.points.filter((p) => daysAgo(p.t) < f.n).sort((a, b) => a.t - b.t);
  const y = lin(0, 13, h - m.b, m.t);
  // a sávhatár ugyanaz a nyelv, mint a vérnyomásnál: szaggatott vonal a státusz színében
  let grid = yGrid([0, 5, 10], y, f) + xAxis(f, h);
  for (const [v, cls, lbl] of [[5.5, 'thr-mod', '6'], [10.5, 'thr-sev', '11']]) {
    grid += `<line class="thr ${cls}" x1="${f.x0}" x2="${f.x1}" y1="${y(v).toFixed(1)}" y2="${y(v).toFixed(1)}"/><text class="thl" x="${f.x1 + 6}" y="${(y(v) + 3.8).toFixed(1)}">${lbl}</text>`;
  }
  let marks = '';
  if (pts.length > 1) marks += `<path class="line thin" d="${pts.map((p, i) => `${i ? 'L' : 'M'}${f.xt(p.t).toFixed(1)},${y(p.score).toFixed(1)}`).join('')}"/>`;
  pts.forEach((p, i) => {
    const cls = p.band === 'critical' ? 'sev' : p.band === 'warning' ? 'mod' : 'pt';
    marks += `<circle class="dot ${cls}" data-i="${i}" cx="${f.xt(p.t).toFixed(1)}" cy="${y(p.score).toFixed(1)}" r="4.5"/>`;
  });
  if (pts.length) {
    const l = pts[pts.length - 1];
    marks += `<text class="endl" x="${(f.xt(l.t) + 9).toFixed(1)}" y="${(y(l.score) + 4).toFixed(1)}">${l.score}</text>`;
  }
  const tip = (i) => {
    const p = pts[i];
    const st = BAND_STATUS[p.band];
    return `<span class="tl">${fDayLong(p.t)} · ${fTime(p.t)}</span><span class="tv">${p.score}<small class="muted">/13 pont</small></span><span class="tf">${st ? sicon(st, 14) : sicon('ok', 14)}${cap(BAND_LABEL[p.band])} sáv</span>`;
  };
  return { svg: svgWrap(w, h, spec.label, { grid, marks }, m), hover: { w, h, xs: pts.map((p) => f.xt(p.t)), ys: pts.map((p) => y(p.score)), tip } };
}

/* kis görbe a listasorokba és csempékbe */
function spark(values, opts = {}) {
  if (values.length < 2) return '';
  const w = opts.w || 120;
  const h = opts.h || 30;
  const all = opts.thr != null ? [...values, opts.thr] : values;
  let lo = Math.min(...all);
  let hi = Math.max(...all);
  if (hi - lo < 1) { hi += 1; lo -= 1; }
  const p = 3;
  const x = (i) => p + (i * (w - 2 * p)) / (values.length - 1);
  const y = (v) => p + ((hi - v) * (h - 2 * p)) / (hi - lo);
  const line = values.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
  const thr = opts.thr != null ? `<line class="sp-thr ${opts.thrSev ? 'sev' : ''}" x1="0" x2="${w}" y1="${y(opts.thr).toFixed(1)}" y2="${y(opts.thr).toFixed(1)}"/>` : '';
  return `<svg class="spark" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" aria-hidden="true">${thr}<polyline class="sp-line" points="${line}"/><circle class="sp-end ${opts.end || ''}" cx="${x(values.length - 1).toFixed(1)}" cy="${y(values[values.length - 1]).toFixed(1)}" r="3.2"/></svg>`;
}

/* ---------- tooltip: egérrel és billentyűvel is ---------- */
function showTip(html, x, y) {
  const t = $('#tip');
  t.innerHTML = html;
  t.classList.add('on');
  const r = t.getBoundingClientRect();
  let L = x + 14;
  let T = y - r.height - 12;
  if (L + r.width > window.innerWidth - 8) L = x - r.width - 14;
  if (T < 8) T = y + 18;
  t.style.transform = `translate(${Math.max(8, Math.round(L))}px, ${Math.round(T)}px)`;
}
function hideTip() {
  $('#tip').classList.remove('on');
}
function bindHover(el, H) {
  if (!H || !H.xs.length) return;
  const svg = el.querySelector('svg');
  const xh = svg.querySelector('.xh');
  let cur = -1;
  const place = (i) => {
    cur = i;
    const X = H.xs[i];
    xh.setAttribute('x1', X);
    xh.setAttribute('x2', X);
    xh.style.opacity = '1';
    svg.querySelectorAll('.is-hot').forEach((n) => n.classList.remove('is-hot'));
    const hot = svg.querySelector(`[data-i="${i}"]`);
    if (hot) hot.classList.add('is-hot');
    const r = svg.getBoundingClientRect();
    const k = r.width / H.w;
    showTip(H.tip(i), r.left + X * k, r.top + H.ys[i] * k);
  };
  const clear = () => {
    cur = -1;
    xh.style.opacity = '0';
    svg.querySelectorAll('.is-hot').forEach((n) => n.classList.remove('is-hot'));
    hideTip();
  };
  svg.addEventListener('pointermove', (e) => {
    const r = svg.getBoundingClientRect();
    const px = (e.clientX - r.left) * (H.w / r.width);
    let best = 0;
    let bd = Infinity;
    H.xs.forEach((v, i) => {
      const d = Math.abs(v - px);
      if (d < bd) { bd = d; best = i; }
    });
    place(best);
  });
  svg.addEventListener('pointerleave', clear);
  svg.addEventListener('blur', clear);
  svg.addEventListener('focus', () => place(H.xs.length - 1));
  svg.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
      e.preventDefault();
      const n = H.xs.length;
      const i = cur < 0 ? n - 1 : Math.min(n - 1, Math.max(0, cur + (e.key === 'ArrowRight' ? 1 : -1)));
      place(i);
    } else if (e.key === 'Escape') clear();
  });
}
