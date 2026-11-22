/* PULSE felületterv · nézetek, beállítások, interakciók. */
'use strict';

/* ---------- megjelenési változatok ---------- */
const FONTS = [
  { id: 'anthropic', name: 'Anthropic-hangulat', pair: 'Source Serif 4 + Instrument Sans', dw: 500,
    d: '"Source Serif 4", Georgia, serif', u: '"Instrument Sans", system-ui, sans-serif',
    note: 'Éles serif címek, keskeny groteszk felület. A claude.ai hangulatát közelíti; az Anthropic saját betűi nem szabadon elérhetők.' },
  { id: 'jelenlegi', name: 'Okt. 28-i pár', pair: 'Newsreader + Inter', dw: 500,
    d: '"Newsreader", Georgia, serif', u: '"Inter", system-ui, sans-serif',
    note: 'A legutóbb kiválasztott páros, összehasonlításnak.' },
  { id: 'szerkesztosegi', name: 'Szerkesztőségi', pair: 'Fraunces + Manrope', dw: 560,
    d: '"Fraunces", Georgia, serif', u: '"Manrope", system-ui, sans-serif',
    note: 'Lágyabb, melegebb serif és kerekded groteszk. A másik korábbi jelölt.' },
  { id: 'svajci', name: 'Svájci', pair: 'Geist', dw: 600,
    d: '"Geist", system-ui, sans-serif', u: '"Geist", system-ui, sans-serif',
    note: 'Serif nélkül: feszes, technikai, nagyon egységes.' },
  { id: 'konyv', name: 'Könyv', pair: 'Literata', dw: 500,
    d: '"Literata", Georgia, serif', u: '"Literata", Georgia, serif',
    note: 'Serif a címeken és a felületen is. Nyugodt, olvasós hangulat.' },
  { id: 'olvashato', name: 'Nagyon olvasható', pair: 'Atkinson Hyperlegible Next', dw: 700,
    d: '"Atkinson Hyperlegible Next", system-ui, sans-serif', u: '"Atkinson Hyperlegible Next", system-ui, sans-serif',
    note: 'Gyengénlátóknak tervezett betű, nagyobb alapmérettel. Idős betegeknél előny.' },
];
const ACCENTS = [
  { id: 'kobalt', name: 'Kobalt', hex: '#2f64d6',
    note: 'Megszokott, nyugodt akciószín, nem ütközik a Súlyos és a Figyelem színével. A Kezelve kékje rokon vele: ott az orvos már lépett.' },
  { id: 'agyag', name: 'Agyag', hex: '#b5552f',
    note: 'Anthropic-szerű meleg narancs. Szép, de közel esik a Súlyos és a Figyelem színéhez.' },
  { id: 'fenyo', name: 'Fenyő', hex: '#11766d',
    note: 'Sötét kékeszöld, nyugodt. Közel esik a Rendben zöldjéhez.' },
  { id: 'feher', name: 'Fehér', hex: '#f2ede6',
    note: 'Inverz: világos gomb sötét felirattal. Nagyon „patikás”, semmilyen státuszszínnel nem ütközik, de a felhasználó itt sötét feliratot lát, nem fehéret.' },
  { id: 'ocean', name: 'Óceán', hex: '#0f6f9e',
    note: 'Mély kékeszöld-kék, hűvös és orvosi. A kobaltnál csendesebb, a Kezelve kékjétől jól elválik.' },
  { id: 'indigo', name: 'Indigó', hex: '#4b4fd0',
    note: 'Kékes ibolya, élénk és jól megtalálható. Egyik státuszszínnel sem ütközik.' },
  { id: 'ejkek', name: 'Éjkék', hex: '#2c4a8a',
    note: 'Sötét, visszafogott kék. Elegáns, de a sötét háttéren halkabb, a gomb kevésbé ugrik ki.' },
  { id: 'szilva', name: 'Szilva', hex: '#8b3a74',
    note: 'Meleg bordós lila, egyedi hangulat. A Súlyos pirosától a lila árnyalat választja el.' },
  { id: 'oliva', name: 'Olíva', hex: '#56652a',
    note: 'Földes zöld, nyugodt és szokatlan. A Rendben zöldjéhez közelebb esik, mint a kék árnyalatok.' },
];
const RADII = [{ id: 'szogletes', name: 'Szögletes' }, { id: 'lagy', name: 'Lágy' }, { id: 'kerek', name: 'Kerek' }];
const DENSITIES = [{ id: 'kenyelmes', name: 'Kényelmes' }, { id: 'tomor', name: 'Tömör' }];
const TONES = [{ id: 'meleg', name: 'Meleg szürke' }, { id: 'grafit', name: 'Grafit' }];
const PILLS = [{ id: 'mind', name: 'Minden státusz' }, { id: 'sulyos', name: 'Csak a Súlyos' }];
const ICONS = [{ id: 'phosphor', name: 'Phosphor' }, { id: 'lucide', name: 'Lucide' }, { id: 'tabler', name: 'Tabler' }];
const PREF_LISTS = { font: FONTS, accent: ACCENTS, icons: ICONS, pills: PILLS, radius: RADII, density: DENSITIES, tone: TONES };
const PREF_NAMES = { font: 'Betűpár', accent: 'Gombszín', icons: 'Ikonkészlet', pills: 'Teli státuszcímke', radius: 'Sarkok', density: 'Sűrűség', tone: 'Háttér' };
const PREF_DEFAULT = { font: 'anthropic', accent: 'feher', icons: 'phosphor', pills: 'mind', radius: 'lagy', density: 'kenyelmes', tone: 'meleg' };
const PREF_KEY = 'pulse-felulet-v1';

function loadPrefs() {
  const p = { ...PREF_DEFAULT };
  try {
    const raw = JSON.parse(localStorage.getItem(PREF_KEY) || '{}');
    for (const k of Object.keys(p)) if (PREF_LISTS[k].some((o) => o.id === raw[k])) p[k] = raw[k];
  } catch (e) {
    /* privát ablakban nincs tárolás: alapértékek */
  }
  return p;
}
function savePrefs() {
  try {
    localStorage.setItem(PREF_KEY, JSON.stringify(S.prefs));
  } catch (e) {
    /* nem baj, csak nem emlékszik */
  }
}
function applyPrefs() {
  const r = document.documentElement;
  for (const [k, v] of Object.entries(S.prefs)) r.dataset[k] = v;
}
const prefLabel = (k) => PREF_LISTS[k].find((o) => o.id === S.prefs[k]).name;
function prefsText() {
  const f = FONTS.find((x) => x.id === S.prefs.font);
  return `PULSE megjelenés: betűpár = ${f.name} (${f.pair}); gombszín = ${prefLabel('accent')}; ikonok = ${prefLabel('icons')}; teli címke = ${prefLabel('pills')}; sarkok = ${prefLabel('radius')}; sűrűség = ${prefLabel('density')}; háttér = ${prefLabel('tone')}.`;
}

/* ---------- állapot ---------- */
const S = {
  prefs: loadPrefs(), view: 'betegeim', pid: 'szabo', filter: 'all', query: '', tab: 'attekintes',
  period: 30, mode: 'grafikon', panel: false, modal: null, alertFilter: 'all', adminTab: 'felhasznalok',
  answers: { q1: '4' }, qSent: false, mtype: 'bp', mVals: {}, mErr: null, timeOther: false, mTime: '',
  catchup: false, caughtUp: false, open: null, noteOpen: false, noteText: '', loginEmail: '', loginErr: false,
  ruleSel: 'r1', rule: { sys: '140', dia: '90', sev: 'moderate' }, ruleCur: { sys: '140', dia: '90', sev: 'moderate' },
  ruleVersions: [{ no: 1, t: at(29, 9, 14), by: DR.kovacs, cond: 'Szisztolés > 140 Hgmm vagy diasztolés > 90 Hgmm, közepes' }],
  unassigned: {},
};

/* ---------- útvonalak ---------- */
const VIEWS = {
  belepes: () => vLogin(), betegeim: () => vList(), adatlap: () => vDetail(), riasztasok: () => vAlerts(),
  teendoim: () => vHome(), kitoltes: () => vFill(), elozmenyek: () => vHistory(), admin: () => vAdmin(), elemtar: () => vKit(),
};
const ROLE = { betegeim: 'orvos', adatlap: 'orvos', riasztasok: 'orvos', elemtar: 'orvos', teendoim: 'beteg', kitoltes: 'beteg', elozmenyek: 'beteg', admin: 'admin' };
const HOME = { orvos: 'betegeim', beteg: 'teendoim', admin: 'admin' };
const ROLE_LABEL = { orvos: 'Orvos', beteg: 'Beteg', admin: 'Admin' };
function parseHash() {
  const h = decodeURIComponent(location.hash.replace(/^#/, ''));
  if (h.startsWith('adatlap-') && PAT[h.slice(8)]) {
    S.pid = h.slice(8);
    return 'adatlap';
  }
  if (h === 'adatlap') return 'adatlap';
  return VIEWS[h] ? h : 'betegeim';
}
let lastKey = '';
function route() {
  S.view = parseHash();
  const key = `${S.view}:${S.pid}`;
  if (key !== lastKey && S.view === 'adatlap') S.tab = S.pendingTab || 'attekintes';
  S.pendingTab = null;
  document.body.classList.remove('nav-open');
  hideTip();
  render();
  if (key !== lastKey) window.scrollTo(0, 0);
  lastKey = key;
  if (S.pendingModal) {
    const id = S.pendingModal;
    S.pendingModal = null;
    openClose(id);
  }
}

/* ---------- kirajzolás ---------- */
function render() {
  CHARTS.clear();
  const a = document.activeElement;
  const key = a && a.dataset ? a.dataset.key : null;
  $('#app').innerHTML = S.view === 'belepes' ? vLogin() : shell(VIEWS[S.view]());
  renderOverlay();
  renderPanel();
  drawCharts($('#app'));
  if (S.view === 'betegeim') applySearch();
  if (key) {
    const el = document.querySelector(`[data-key="${CSS.escape(key)}"]`);
    if (el) el.focus({ preventScroll: true });
  }
}
function renderOverlay() {
  $('#overlay').innerHTML = S.modal ? modalHtml() : '';
}
const brandMark = () => `<span class="brand-mark">${BRAND}</span>`;
const seg = (act, opts, value, o = {}) =>
  `<div class="seg ${o.accent ? 'accent' : ''}" role="group" aria-label="${esc(o.label || '')}">${opts
    .map(([v, l]) => `<button type="button" data-act="${act}" data-v="${v}" data-key="${act}-${v}" aria-pressed="${String(v) === String(value)}">${l}</button>`)
    .join('')}</div>`;
const prefSeg = (k) =>
  `<div class="seg" role="group" aria-label="${PREF_NAMES[k]}">${PREF_LISTS[k]
    .map((o) => `<button type="button" data-act="pref" data-k="${k}" data-v="${o.id}" data-key="pref-${k}-${o.id}" aria-pressed="${S.prefs[k] === o.id}">${o.name}</button>`)
    .join('')}</div>`;
const footer = () =>
  `<footer class="foot"><p>${DISCLAIMER}</p><p>Felületterv, 2026. október 30. Minden név és érték mesterséges példaadat.</p></footer>`;

function decisionCount() {
  return PATIENTS.filter((p) => ['severe', 'attention'].includes(statusOf(p))).length;
}
function navItems(role) {
  if (role === 'beteg') {
    return [
      { v: 'teendoim', label: 'Teendőim', ic: 'home', n: mariaTasks().filter((t) => t.state !== 'done').length },
      { v: 'elozmenyek', label: 'Előzményeim', ic: 'chart' },
    ];
  }
  if (role === 'admin') {
    return [{ v: 'admin', label: 'Felhasználók', ic: 'shield' }];
  }
  return [
    { v: 'betegeim', label: 'Betegeim', ic: 'users', n: decisionCount(), hot: PATIENTS.some((p) => statusOf(p) === 'severe') },
    { v: 'riasztasok', label: 'Riasztások', ic: 'bell', n: openAlerts().filter((a) => !has(a, 'assigned')).length },
  ];
}
const ME = {
  orvos: { name: DR.kovacs, sub: 'Orvos', ini: 'KÉ' },
  beteg: { name: 'Tóth Mária', sub: 'Beteg', ini: 'TM' },
  admin: { name: 'Adminisztrátor', sub: 'admin@pulse.example', ini: 'A' },
};
function shell(content) {
  const role = ROLE[S.view];
  const current = S.view === 'adatlap' ? 'betegeim' : S.view === 'kitoltes' ? 'teendoim' : S.view;
  const items = navItems(role)
    .map((it) => `<a href="#${it.v}" ${it.v === current ? 'aria-current="page"' : ''}>${icon(it.ic)}<span>${it.label}</span>${it.n ? `<span class="badge-n ${it.hot ? 'hot' : ''}">${it.n}</span>` : ''}</a>`)
    .join('');
  const me = ME[role];
  return `<div class="app">
    <aside class="side" aria-label="Fő navigáció">
      <a class="brand" href="#${HOME[role]}">${brandMark()}<span class="brand-name">PULSE</span></a>
      <div class="side-sec">
        <span class="side-label">Bemutató szerepkör</span>
        <div class="roles" role="group" aria-label="Szerepkör">${['orvos', 'beteg', 'admin']
          .map((r) => `<button type="button" data-act="role" data-v="${r}" data-key="role-${r}" aria-pressed="${r === role}">${ROLE_LABEL[r]}</button>`)
          .join('')}</div>
      </div>
      <nav class="nav" aria-label="Menü">${items}</nav>
      <div class="side-foot">
        <div class="me"><span class="avatar">${me.ini}</span><span class="me-text"><span class="me-name">${esc(me.name)}</span><span class="me-role">${esc(me.sub)}</span></span>
          <a class="ibtn" href="#belepes" aria-label="Kijelentkezés" data-tip="Kijelentkezés">${icon('logout')}</a></div>
      </div>
    </aside>
    <div class="scrim" data-act="nav"></div>
    <div class="col">
      <header class="topbar">
        <button class="ibtn" type="button" data-act="nav" aria-label="Menü megnyitása">${icon('menu')}</button>
        <a class="brand" href="#${HOME[role]}">${brandMark()}<span class="brand-name">PULSE</span></a>
        <span class="avatar" aria-hidden="true">${me.ini}</span>
      </header>
      <main class="main" id="main">${content}${footer()}</main>
    </div>
  </div>`;
}

/* ---------- Belépés ---------- */
const DEMO_ACC = [
  ['orvos', 'Dr. Kovács Éva', 'dr.kovacs@pulse.example', 'KÉ'],
  ['beteg', 'Tóth Mária', 'toth.maria@pulse.example', 'TM'],
  ['admin', 'Adminisztrátor', 'admin@pulse.example', 'A'],
];
function vLogin() {
  return `<div class="login">
    <section class="login-brand">
      <div class="login-hero">
        <h1 class="login-word">PULSE</h1>
        <p class="acro"><b>P</b>atient <b>U</b>nderstanding through <b>L</b>imits, <b>S</b>ignals and <b>E</b>valuation</p>
        <p class="login-tag">Krónikus betegkövető telemedicina platform</p>
      </div>
    </section>
    <section class="login-main">
      <form class="login-card" data-form="login" novalidate>
        <div class="login-title"><h2 class="h-display">Belépés</h2><p class="meta">Az e-mail-címeddel és a jelszavaddal.</p></div>
        <div class="field"><label for="login-email">E-mail-cím</label>
          <input id="login-email" class="input" type="email" autocomplete="username" data-key="login-email" value="${esc(S.loginEmail)}">
          ${S.loginErr ? `<span class="err">${sicon('severe', 14)}Add meg az e-mail-címedet.</span>` : ''}</div>
        <div class="field"><label for="login-pw">Jelszó</label>
          <input id="login-pw" class="input" type="password" autocomplete="current-password" value="${S.loginEmail ? 'bemutato' : ''}"></div>
        <button class="btn btn-primary btn-lg btn-block" type="submit">Belépés</button>
        <div class="field"><span class="field-label">Bemutató fiókok <span class="tag">javaslat</span></span>
          <div class="demo-acc">${DEMO_ACC.map(([r, n, e, ini]) => `<button type="button" data-act="login-fill" data-v="${e}"><span class="avatar">${ini}</span><span class="who"><b>${n}</b><span>${e}</span></span><span class="chip">${ROLE_LABEL[r]}</span></button>`).join('')}</div>
        </div>
        <p class="disclaimer">${DISCLAIMER}</p>
      </form>
    </section>
  </div>`;
}

/* ---------- Orvos: Betegeim ---------- */
const GROUPS = [
  { title: 'Döntésre vár', st: ['severe', 'attention'], loud: true },
  { title: 'Figyelendő', st: ['no_data'] },
  { title: 'Kezelés alatt', st: ['handled'] },
  { title: 'Rendben', st: ['ok'] },
];
const byUrgency = (a, b) => ST_ORDER.indexOf(a.s) - ST_ORDER.indexOf(b.s) || (b.p.lastAt || 0) - (a.p.lastAt || 0);
const sevSort = (a, b) => (a.sev === b.sev ? b.at - a.at : a.sev === 'severe' ? -1 : 1);
function trendCell(p) {
  const top = openAlerts(p.id).sort(sevSort)[0];
  if (!top) return '';
  if (top.kind === 'questionnaire') {
    const subs = p.subs.slice(0, 6).reverse();
    const last = subs[subs.length - 1];
    return `${spark(subs.map((x) => x.score), { thr: 5.5, end: last.band === 'critical' ? 'sev' : last.band === 'warning' ? 'mod' : '' })}<span class="spark-l">Közérzet, 6 hét</span>`;
  }
  const bp = p.bpS.slice(-14);
  const l = bp[bp.length - 1];
  const sev = l.sys > 180;
  return `${spark(bp.map((x) => x.sys), { thr: sev ? 180 : 140, thrSev: sev, end: sev ? 'sev' : l.sys > 140 || l.dia > 90 ? 'mod' : '' })}<span class="spark-l">Szisztolés, 14 nap</span>`;
}
function prow(p, s, loud) {
  const [r1, ...rest] = reasonsOf(p);
  return `<a class="prow cols ${loud ? 'loud' : ''}" data-s="${s}" href="#adatlap-${p.id}" data-name="${esc(p.name.toLocaleLowerCase('hu'))}">
    <span class="c-status">${statusTag(s)}</span>
    <span class="c-name"><span class="name">${esc(p.name)}</span><span class="age">${ageOf(p.born)} éves</span></span>
    <span class="c-reason"><span class="r-main ${r1.calm ? 'calm' : ''}">${r1.text}</span>${rest.map((r) => `<span class="r-sub">${sicon(r.s, 16)}<span>${r.text}</span></span>`).join('')}</span>
    <span class="c-trend">${loud ? trendCell(p) : ''}</span>
    <span class="c-tasks ${p.tasks.tone === 'late' ? 'late' : ''}">${esc(p.tasks.text)}</span>
    <span class="c-fresh">${p.lastAt ? fRel(p.lastAt) : 'még nincs adat'}</span>
    <span class="c-chev">${icon('chevR')}</span>
  </a>`;
}
function vList() {
  const rows = PATIENTS.map((p) => ({ p, s: statusOf(p) }));
  const count = (s) => rows.filter((r) => r.s === s).length;
  const decide = count('severe') + count('attention');
  const tile = (s, n, label, glyph) =>
    `<button type="button" class="tile ${n ? '' : 'zero'}" data-act="filter" data-v="${s}" data-key="f-${s}" aria-pressed="${S.filter === s}" ${n ? '' : 'aria-disabled="true"'}>${glyph}<span class="tile-n">${n}</span><span class="tile-l">${label}</span></button>`;
  const tiles = tile('all', rows.length, 'Mind', `<span class="tile-all">${icon('users')}</span>`) +
    ST_ORDER.map((s) => tile(s, count(s), ST[s].label, sicon(s, 26))).join('');
  const groups = GROUPS.map((g) => {
    const list = rows.filter((r) => g.st.includes(r.s) && (S.filter === 'all' || r.s === S.filter)).sort(byUrgency);
    if (!list.length) return '';
    const body = list.map((r) => prow(r.p, r.s, g.loud)).join('');
    return `<section class="group" aria-label="${g.title}"><div class="group-head"><h2>${g.title}</h2><span class="group-n">${list.length}</span></div>${g.loud ? `<div class="group-loud">${body}</div>` : `<div class="plist">${body}</div>`}</section>`;
  }).join('');
  const urgent = rows.filter((r) => r.s === 'severe' || r.s === 'attention').sort(byUrgency)[0];
  return `<div class="page">
    <header class="ph">
      <div class="ph-text"><span class="eyebrow">${fLongDate(NOW)}</span><h1 class="h-display">Betegeim</h1>
        <div class="ph-meta"><span>${rows.length} beteg</span><span>${decide} döntésre vár</span><span>Frissítve ${fTime(NOW)}</span></div></div>
      <div class="ph-actions">
        <label class="search">${icon('search')}<span class="sr">Keresés név szerint</span><input id="q-search" class="input" type="search" placeholder="Keresés név szerint" autocomplete="off" data-key="q-search" value="${esc(S.query)}"></label>
        ${urgent ? `<a class="btn btn-primary" href="#adatlap-${urgent.p.id}">Legsürgősebb: ${esc(urgent.p.name)}${icon('arrowR')}</a>` : ''}
      </div>
    </header>
    <div class="tiles" role="group" aria-label="Szűrés státusz szerint">${tiles}</div>
    <div class="stack">
      <div class="cols cols-head" aria-hidden="true"><span>Státusz</span><span>Beteg</span><span>Ok</span><span class="h-trend">Trend</span><span>Teendők</span><span class="r">Utolsó adat</span><span></span></div>
      ${groups}
      <p class="card no-match" id="no-match" hidden>Nincs a keresésnek megfelelő beteg.</p>
    </div>
  </div>`;
}
function applySearch() {
  const q = S.query.trim().toLocaleLowerCase('hu');
  let any = false;
  $$('.group').forEach((g) => {
    let n = 0;
    $$('.prow', g).forEach((r) => {
      const hit = !q || r.dataset.name.includes(q);
      r.hidden = !hit;
      if (hit) n += 1;
    });
    g.hidden = n === 0;
    const c = $('.group-n', g);
    if (c) c.textContent = n;
    if (n) any = true;
  });
  const nm = $('#no-match');
  if (nm) nm.hidden = any;
}

/* ---------- Orvos: Adatlap ---------- */
function vDetail() {
  const p = PAT[S.pid];
  const s = statusOf(p);
  const open = openAlerts(p.id);
  const assigned = open.filter((a) => has(a, 'assigned')).length;
  const sentence = open.length
    ? `${open.length} nyitott riasztás${assigned ? `, ebből ${assigned} felelősnél` : ''}`
    : reasonsOf(p)[0].text;
  const tabs = [['attekintes', 'Áttekintés'], ['szabalyok', 'Szabályok', 'M3'], ['terv', 'Követési terv', 'M3']];
  const body = S.tab === 'szabalyok' ? tabRules(p) : S.tab === 'terv' ? tabPlan(p) : tabOverview(p);
  return `<div class="page">
    <header class="pt-head">
      <nav class="crumbs" aria-label="Vissza"><a href="#betegeim">${icon('arrowL')}Betegeim</a></nav>
      <div class="ph">
        <div class="ph-text">
          <h1 class="h-display">${esc(p.name)}</h1>
          <div class="ph-meta"><span>${ageOf(p.born)} éves</span><span>Született ${fBorn(p.born)}</span><span>Utolsó adat: ${p.lastAt ? fRel(p.lastAt) : 'még nincs'}</span></div>
        </div>
        <div class="ph-actions"><button class="btn btn-secondary" type="button" data-act="note-open">${icon('note')}Megjegyzés</button></div>
      </div>
      <div class="pt-status">${statusTag(s, { size: 20 })}<span class="why">${sentence}</span></div>
    </header>
    <div class="tabs" role="tablist" aria-label="Adatlap részei">${tabs
      .map(([id, l, tag]) => `<button type="button" role="tab" data-act="tab" data-v="${id}" data-key="tab-${id}" aria-selected="${S.tab === id}">${l}${tag ? `<span class="tag">${tag}</span>` : ''}</button>`)
      .join('')}</div>
    ${body}
  </div>`;
}
function tabOverview(p) {
  const open = openAlerts(p.id).sort(sevSort);
  const closed = ALERTS.filter((a) => a.pid === p.id && has(a, 'closed'));
  const alertsHtml = open.length
    ? open.map(alertCard).join('')
    : `<div class="card empty">${sicon('ok', 22)}<span>Nincs nyitott riasztás.</span></div>`;
  return `<div class="grid-2">
    <div class="stack-lg">
      <section class="sec" aria-labelledby="h-alerts">
        <div class="sec-head"><div class="left"><h2 class="h-sec" id="h-alerts">Nyitott riasztások</h2>${open.length ? `<span class="badge-n ${open.some((a) => a.sev === 'severe') ? 'hot' : ''}">${open.length}</span>` : ''}</div></div>
        ${alertsHtml}${closed.map(alertClosed).join('')}
      </section>
      ${measurementsSection(p, true)}
    </div>
    <div class="stack-lg">${adherenceCard(p)}${submissionsCard(p)}${notesCard(p)}</div>
  </div>`;
}
const CHECK_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m5 12.5 4.5 4.5L19 7.5"/></svg>';
function alertCard(a) {
  const st = has(a, 'assigned') ? 'handled' : a.sev === 'severe' ? 'severe' : 'attention';
  const steps = [['created', 'Keletkezett'], ['seen', 'Megtekintve'], ['assigned', 'Felelőshöz rendelve'], ['closed', 'Lezárva']];
  const firstTodo = steps.findIndex(([t]) => !has(a, t));
  const stepsHtml = steps
    .map(([t, l], i) => {
      const ev = a.events.find((e) => e.type === t);
      const cls = ev ? 'done' : i === firstTodo ? 'now' : 'todo';
      return `<li class="step ${cls}"><span class="dot">${ev ? CHECK_SVG : ''}</span><span class="lbl">${l}</span><span>${ev ? fRel(ev.t) : ''}</span></li>`;
    })
    .join('');
  const evs = [...a.events]
    .reverse()
    .map((e) => `<li><span class="d"></span><span class="w">${fRel(e.t)}</span><span><span class="e">${EVENT_LABEL[e.type]}</span>${e.data ? ` · ${esc(e.data)}` : ''}${e.who ? ` · ${esc(e.who)}` : ''}</span></li>`)
    .join('');
  return `<article class="alert" aria-label="${esc(a.title)}">
    <div class="alert-head">
      ${sicon(st, 22)}
      <div><h3 class="alert-title">${esc(a.title)}${has(a, 'seen') ? '' : '<span class="chip fill">Új</span>'}</h3>
        <p class="alert-rule">${a.rule} · ${a.ver}. verzió · ${a.sev === 'severe' ? 'súlyos' : 'közepes'}</p></div>
      <div class="alert-val"><span class="v">${a.value}</span><span class="u">${esc(a.unit)}</span><span class="t">${fRel(a.at)}</span></div>
    </div>
    <div class="why-box"><span class="k">Miért jelzett?</span><span><b>Feltétel:</b> ${esc(a.cond)}.</span><span>${esc(a.why)}</span></div>
    <ol class="steps" aria-label="Riasztás-életút">${stepsHtml}</ol>
    <div class="alert-foot">
      <details class="events"><summary>${icon('chevR')}Eseménytörténet · ${a.events.length} esemény</summary><ol class="timeline">${evs}</ol></details>
      <div class="alert-actions">
        ${has(a, 'assigned') ? '' : `<button class="btn btn-secondary" type="button" data-act="assign" data-id="${a.id}" data-key="as-${a.id}">${icon('assign')}Felelőshöz rendelés</button>`}
        <button class="btn btn-primary" type="button" data-act="close-alert" data-id="${a.id}" data-key="cl-${a.id}">Lezárás…</button>
      </div>
    </div>
  </article>`;
}
function alertClosed(a) {
  const ev = a.events.find((e) => e.type === 'closed');
  return `<article class="alert closed" aria-label="${esc(a.title)}, lezárva">
    <div class="alert-head">${sicon('ok', 22)}
      <div><h3 class="alert-title">${esc(a.title)}</h3><p class="alert-rule">Lezárva ${fRel(ev.t)} · ${esc(ev.who)}</p></div>
      <div class="alert-val sm"><span class="v">${a.value}</span><span class="u">${esc(a.unit)}</span></div></div>
    <div class="why-box"><span class="k">Indoklás</span><span>${esc(ev.note)}</span>${ev.msg ? `<span class="k">Visszajelzés a betegnek</span><span>${esc(ev.msg)}</span>` : ''}</div>
  </article>`;
}
const legendDot = (c) => `<svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true"><circle cx="5" cy="5" r="4" fill="${c}"/></svg>`;
const legendDash = (c) => `<svg width="18" height="6" viewBox="0 0 18 6" aria-hidden="true"><path d="M0 3h5M8 3h5M16 3h2" stroke="${c}" stroke-width="1.6"/></svg>`;
const legendRing = () => `<svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><circle cx="7" cy="7" r="5.5" fill="none" stroke="var(--ink-1)" stroke-width="1.5"/></svg>`;
const BP_THR = [{ v: 140, kind: 'mod', comp: 'sys' }, { v: 90, kind: 'mod', comp: 'dia' }, { v: 180, kind: 'sev', comp: 'sys' }];
function measurementsSection(p, doctor) {
  const per = S.period;
  const inRange = (arr) => arr.filter((x) => daysAgo(x.t) < per);
  const bp = inRange(p.bpS);
  const pulse = inRange(p.pulseS);
  const weight = inRange(p.weightS);
  const subs = inRange(p.subs);
  const head = `<div class="sec-head"><div class="left"><h2 class="h-sec">${doctor ? 'Mérések' : 'Méréseim'}</h2></div>
    <div class="filters">${seg('period', [[14, '14 nap'], [30, '30 nap'], [90, '90 nap']], per, { label: 'Időszak' })}${seg('mode', [['grafikon', 'Grafikon'], ['tablazat', 'Táblázat']], S.mode, { label: 'Nézet' })}</div></div>`;
  if (!p.bpS.length && !p.pulseS.length && !p.weightS.length) {
    return `<section class="sec">${head}<div class="card"><div class="chart-empty">Még nem érkezett mérés. Az első mérés után itt jelenik meg a görbe.</div></div></section>`;
  }
  const table = S.mode === 'tablazat';
  const lastBP = p.bpS[p.bpS.length - 1];
  const legend = `<div class="legend"><span class="k">${legendDot('var(--ink-1)')}Szisztolés (felső pont)</span><span class="k">${legendDot('var(--ink-3)')}Diasztolés (alsó pont)</span>${doctor ? `<span class="k">${legendDash('var(--s-attention)')}140/90, közepes határ</span><span class="k">${legendDash('var(--s-severe)')}180, súlyos határ</span><span class="k">${legendRing()}Riasztást váltott ki</span>` : ''}</div>`;
  let bpBody;
  if (!bp.length) bpBody = '<div class="chart-empty">Ebben az időszakban nincs vérnyomásmérés.</div>';
  else if (table) bpBody = bpTable(bp, doctor);
  else bpBody = chart({ kind: 'bp', h: 270, days: per, points: bp, thresholds: doctor ? BP_THR : null, label: `Vérnyomás, utolsó ${per} nap` });
  const bpCard = `<div class="card chart-card">
    <div class="card-head"><div class="left"><h3 class="h-card">Vérnyomás</h3><span class="meta">Hgmm · ${bp.length} mérés ebben az időszakban</span></div>
      ${lastBP ? `<div class="mult-head"><span class="v">${lastBP.sys}/${lastBP.dia}<small>Hgmm, ${fRel(lastBP.t)}</small></span></div>` : ''}</div>
    ${table ? '' : legend}${bpBody}</div>`;
  const mult = (title, unit, pts, dec, gap) => {
    const last = pts[pts.length - 1];
    let b;
    if (!pts.length) b = '<div class="chart-empty">Nincs mérés ebben az időszakban.</div>';
    else if (table) b = lineTable(pts, unit, dec);
    else b = chart({ kind: 'line', h: 150, days: per, points: pts, unit, dec, gap, dots: gap > 3, minPad: dec ? 1 : 4, label: `${title}, utolsó ${per} nap` });
    return `<div class="card"><div class="mult-head"><h3 class="h-card">${title}</h3>${last ? `<span class="v">${fNum(last.v, dec)}<small>${unit}</small></span>` : ''}</div>${b}</div>`;
  };
  let scoreCard = '';
  if (doctor) {
    const last = subs[0];
    let b;
    if (!subs.length) b = '<div class="chart-empty">Nincs kitöltés ebben az időszakban.</div>';
    else if (table) b = scoreTable(subs);
    else b = chart({ kind: 'score', h: 150, days: per, points: subs, label: `Közérzet pontszám, utolsó ${per} nap` });
    scoreCard = `<div class="card"><div class="mult-head"><h3 class="h-card">Közérzet</h3>${last ? `<span class="v">${last.score}<small>/13 pont</small></span>` : ''}</div>${b}</div>`;
  }
  return `<section class="sec" aria-label="Mérések">${head}${bpCard}
    <div class="multiples ${doctor ? '' : 'two'}">${mult('Pulzus', '/perc', pulse, 0, 3)}${mult('Testsúly', 'kg', weight, 1, 10)}${scoreCard}</div></section>`;
}
function bpTable(bp, doctor) {
  const rows = [...bp].reverse().map((x) => {
    let flag = '';
    if (doctor) {
      if (x.sys > 180) flag = `<span class="flag">${sicon('severe', 14)}súlyos határ fölött</span>`;
      else if (x.sys > 140 || x.dia > 90) flag = `<span class="flag">${sicon('attention', 14)}határ fölött</span>`;
      if (x.trig) flag += ' <span class="muted">· riasztás</span>';
    }
    return `<tr><td>${fDayTime(x.t)}</td><td class="n strong">${x.sys}</td><td class="n strong">${x.dia}</td>${doctor ? `<td>${flag}</td>` : ''}</tr>`;
  }).join('');
  return `<div class="tbl-wrap"><table class="tbl"><thead><tr><th>Időpont</th><th class="n">Szisztolés</th><th class="n">Diasztolés</th>${doctor ? '<th>Megjegyzés</th>' : ''}</tr></thead><tbody>${rows}</tbody></table></div>`;
}
function lineTable(pts, unit, dec) {
  return `<div class="tbl-wrap"><table class="tbl"><thead><tr><th>Időpont</th><th class="n">${unit}</th></tr></thead><tbody>${[...pts]
    .reverse()
    .map((x) => `<tr><td>${fDayTime(x.t)}</td><td class="n strong">${fNum(x.v, dec)}</td></tr>`)
    .join('')}</tbody></table></div>`;
}
function scoreTable(subs) {
  return `<div class="tbl-wrap"><table class="tbl"><thead><tr><th>Kitöltve</th><th class="n">Pont</th><th>Sáv</th></tr></thead><tbody>${subs
    .map((x) => `<tr><td>${fDay(x.t)}</td><td class="n strong">${x.score}</td><td>${BAND_LABEL[x.band]}</td></tr>`)
    .join('')}</tbody></table></div>`;
}
const WEEKDAYS_ON = ['vasárnap', 'hétfőn', 'kedden', 'szerdán', 'csütörtökön', 'pénteken', 'szombaton'];
const CELL_LABEL = { done: 'teljesítve', miss: 'elmaradt', due: 'ma esedékes', off: 'nincs előírva' };
function adherenceRows(p, days = 30) {
  const set = (arr) => new Set(arr.map((x) => daysAgo(x.t)));
  const bpD = set(p.bpS);
  const wD = set(p.weightS);
  const qD = set(p.subs);
  const qDow = p.q ? at(p.q.offs[0], 12, 0).getDay() : 4;
  const start = p.empty ? 6 : 89;
  const mk = (name, fr, fn) => {
    const cells = [];
    for (let off = days - 1; off >= 0; off -= 1) cells.push({ off, c: off > start ? 'off' : fn(off) });
    const req = cells.filter((x) => x.c !== 'off' && x.c !== 'due').length;
    const done = cells.filter((x) => x.c === 'done').length;
    return { name, fr, cells, req, done };
  };
  return [
    mk('Vérnyomás', 'naponta, 10:00-ig', (off) => (bpD.has(off) ? 'done' : off === 0 && NOW.getHours() < 10 ? 'due' : 'miss')),
    mk('Testsúly', 'hetente, hétfőn', (off) => (at(off, 12, 0).getDay() !== 1 ? 'off' : wD.has(off) ? 'done' : 'miss')),
    mk('Közérzet', `hetente, ${WEEKDAYS_ON[qDow]}`, (off) => (at(off, 12, 0).getDay() !== qDow ? 'off' : qD.has(off) ? 'done' : off === 0 ? 'due' : 'miss')),
  ];
}
const stripHtml = (cells) =>
  `<div class="strip" style="grid-template-columns:repeat(${cells.length},minmax(0,1fr))">${cells
    .map((x) => `<i class="${x.c}" data-tip="${fDay(at(x.off, 12, 0))}: ${CELL_LABEL[x.c]}"></i>`)
    .join('')}</div>`;
function adherenceCard(p) {
  const rows = adherenceRows(p);
  return `<section class="card" aria-labelledby="h-adh">
    <div class="card-head"><div class="left"><h2 class="h-card" id="h-adh">Teendők teljesítése</h2><span class="meta">Utolsó 30 nap</span></div></div>
    <div class="adh">${rows
      .map((r) => `<div class="adh-row"><div class="adh-top"><span><span class="nm">${r.name}</span> <span class="fr">${r.fr}</span></span><span class="sc">${r.done}/${r.req}</span></div>${stripHtml(r.cells)}</div>`)
      .join('')}
      <div class="strip-axis"><span>${fDay(at(29, 12, 0))}</span><span>ma</span></div>
      <div class="key"><span><i class="done"></i>teljesítve</span><span><i class="miss"></i>elmaradt</span><span><i class="due"></i>ma esedékes</span><span><i class="off"></i>nincs előírva</span></div>
    </div>
  </section>`;
}
function answerList(s) {
  return QUESTIONNAIRE.questions
    .map((q, i) => {
      const v = s.answers[i];
      let label;
      let pts;
      if (q.kind === 'scale') {
        label = `${v}${v === 1 ? `, ${q.min}` : v === 5 ? `, ${q.maxL}` : ''}`;
        pts = q.id === 'q1' ? 5 - v : v - 1;
      } else {
        const o = q.options.find((x) => x.v === v);
        label = o.l;
        pts = o.s;
      }
      return `<li><span>${i + 1}. ${esc(q.text)}</span><span class="a">${esc(label)} <span class="muted">(${pts} pont)</span></span></li>`;
    })
    .join('');
}
function submissionsCard(p) {
  const list = p.subs.slice(0, 6);
  const body = list.length
    ? `<div class="subs">${list
        .map((s) => {
          const st = BAND_STATUS[s.band];
          return `<details class="sub"><summary><span class="when">${fDay(s.t)}</span>
            <span class="scorebar" aria-hidden="true"><i class="${s.band === 'warning' ? 'warn' : s.band === 'critical' ? 'crit' : ''}" style="width:${((s.score / 13) * 100).toFixed(1)}%"></i><b style="left:${((5.5 / 13) * 100).toFixed(1)}%"></b><b style="left:${((10.5 / 13) * 100).toFixed(1)}%"></b></span>
            <span class="score">${s.score}/13</span>
            <span class="band">${st ? sicon(st, 14) : sicon('ok', 14)}${BAND_LABEL[s.band]}</span></summary>
            <ol class="answers" aria-label="Válaszok">${answerList(s)}</ol></details>`;
        })
        .join('')}</div>`
    : '<p class="muted">Még nincs kitöltés.</p>';
  return `<section class="card" aria-labelledby="h-subs">
    <div class="card-head"><div class="left"><h2 class="h-card" id="h-subs">Kérdőív-kitöltések</h2><span class="meta">Közérzet · 1. verzió · kattints a válaszokért</span></div></div>
    ${body}</section>`;
}
function notesCard(p) {
  const notes = p.notes || [];
  const form = S.noteOpen
    ? `<form class="note-form" data-form="note"><label class="sr" for="note-text">Új megjegyzés</label><textarea id="note-text" class="textarea" data-key="note-text" placeholder="Pl. telefonon egyeztetve, a következő lépés…">${esc(S.noteText)}</textarea>
      <div class="modal-foot"><button class="btn btn-quiet btn-sm" type="button" data-act="note-cancel">Mégse</button><button class="btn btn-primary btn-sm" type="submit">Mentés</button></div></form>`
    : '';
  return `<section class="card" id="jegyzet" aria-labelledby="h-notes">
    <div class="card-head"><div class="left"><h2 class="h-card" id="h-notes">Megjegyzések</h2></div>${S.noteOpen ? '' : `<button class="btn btn-secondary btn-sm" type="button" data-act="note-open">${icon('plus')}Új</button>`}</div>
    <div class="notes">${form}${notes.length ? notes.map((n) => `<div class="note"><span>${esc(n.text)}</span><span class="by">${esc(n.by)} · ${fDayTime(n.t)}</span></div>`).join('') : '<p class="muted">Még nincs megjegyzés.</p>'}</div>
  </section>`;
}

/* szabályok (M3 terv) */
const RULE_TYPES = [
  ['threshold', 'Küszöbszabály', 'Egyszeri átlépés: egy mérés a határon kívül.'],
  ['window', 'Időablakos szabály', 'Ismétlődés: legalább N eltérés M napon belül.'],
  ['questionnaire', 'Kérdőívszabály', 'Pontszámsáv vagy romló trend K kitöltésen át.'],
  ['missing', 'Elmaradt adat', 'Az előírt mérés vagy kitöltés nem érkezik be határidőre.'],
];
function rulesFor(p) {
  const openOf = (kind, sev) => openAlerts(p.id).filter((a) => a.kind === kind && a.sev === sev).length;
  const cur = S.ruleCur;
  return [
    { id: 'r1', type: 'threshold', mt: 'Vérnyomás', cond: `Szisztolés > ${cur.sys} Hgmm vagy diasztolés > ${cur.dia} Hgmm`, sev: cur.sev, ver: S.ruleVersions[0].no, since: S.ruleVersions[0].t, open: openOf('threshold', 'moderate') },
    { id: 'r2', type: 'threshold', mt: 'Vérnyomás', cond: 'Szisztolés > 180 Hgmm', sev: 'severe', ver: 1, since: at(29, 9, 14), open: openOf('threshold', 'severe') },
    { id: 'r5', type: 'window', mt: 'Vérnyomás', cond: 'Legalább 3 mérés a 140/90 fölött 7 napon belül', sev: 'moderate', draft: true },
    { id: 'r3', type: 'questionnaire', mt: 'Közérzet', cond: 'Figyelmeztető vagy kritikus sáv (6 pont fölött)', sev: 'moderate', ver: 1, since: at(29, 9, 16), open: openOf('questionnaire', 'moderate') },
    { id: 'r4', type: 'questionnaire', mt: 'Közérzet', cond: 'Kritikus sáv (11 pont fölött)', sev: 'severe', ver: 1, since: at(29, 9, 16), open: openOf('questionnaire', 'severe') },
    { id: 'r6', type: 'missing', mt: 'Vérnyomás', cond: 'A napi mérés 10:00-ig nem érkezik be', sev: 'moderate', draft: true },
  ];
}
const sevDot = (sev) => `<span class="sev-dot" style="background:var(${sev === 'severe' ? '--s-severe' : '--s-attention'})"></span>`;
function ruleValid() {
  const s = Number(S.rule.sys);
  const d = Number(S.rule.dia);
  return Number.isInteger(s) && s >= 60 && s <= 250 && Number.isInteger(d) && d >= 40 && d <= 150;
}
function ruleChanged() {
  return ['sys', 'dia', 'sev'].some((k) => String(S.rule[k]) !== String(S.ruleCur[k]));
}
function rulePreview() {
  if (!ruleValid()) return `<span class="k">Új feltétel</span><span class="err">${sicon('severe', 14)}A szisztolés 60 és 250, a diasztolés 40 és 150 közötti egész szám lehet.</span>`;
  const v = (k, txt) => (String(S.rule[k]) !== String(S.ruleCur[k]) ? `<span class="chg">${esc(txt)}</span>` : esc(txt));
  return `<span class="k">Új feltétel</span><span>Szisztolés &gt; ${v('sys', S.rule.sys)} Hgmm vagy diasztolés &gt; ${v('dia', S.rule.dia)} Hgmm esetén ${v('sev', S.rule.sev === 'severe' ? 'súlyos' : 'közepes')} riasztás.</span>`;
}
function tabRules(p) {
  const rules = rulesFor(p);
  const groups = RULE_TYPES.map(([type, name, desc]) => {
    const list = rules.filter((r) => r.type === type);
    return `<div class="rule-type"><div class="sec-head"><div class="left"><h3 class="h-card">${name}</h3><span class="meta">${desc}</span></div></div>
      ${list
        .map((r) => `<div class="rule ${S.ruleSel === r.id ? 'sel' : ''}"><div><div class="cond">${esc(r.mt)}: ${esc(r.cond)}</div>
          <div class="info"><span class="sv">${sevDot(r.sev)}${r.sev === 'severe' ? 'súlyos' : 'közepes'}</span>${r.draft ? '<span class="tag">M3 példa</span>' : `<span>${r.ver}. verzió, ${fDay(r.since)} óta</span>`}${r.open ? `<span>${r.open} nyitott riasztás</span>` : ''}</div></div>
          <button class="btn btn-secondary btn-sm" type="button" data-act="rule-edit" data-v="${r.id}" data-key="re-${r.id}">Szerkesztés</button></div>`)
        .join('')}</div>`;
  }).join('');
  return `<div class="grid-2">
    <section class="sec" aria-label="Szabályok">
      <div class="sec-head"><div class="left"><h2 class="h-sec">${esc(p.name)} szabályai</h2><span class="tag">M3 terv</span></div><button class="btn btn-primary" type="button" data-act="todo">${icon('plus')}Új szabály</button></div>
      <p class="meta">Négy paraméterezhető szabálytípus. Minden módosítás új, változtathatatlan verziót hoz létre.</p>
      <div class="rules">${groups}</div>
    </section>
    ${ruleEditor()}
  </div>`;
}
function ruleEditor() {
  if (S.ruleSel !== 'r1') {
    return `<aside class="card editor"><div class="card-head flush"><div class="left"><span class="eyebrow">Szerkesztő</span><h2 class="h-card">Ez a szabálytípus az M3-ban kap szerkesztőt</h2></div></div>
      <p class="meta">A felépítése ugyanaz lesz, mint a küszöbszabályé: mezők, élő előnézet, mentés új verzióként, verziólista.</p>
      <button class="btn btn-secondary" type="button" data-act="rule-edit" data-v="r1">A küszöbszabály megnyitása</button></aside>`;
  }
  const next = S.ruleVersions[0].no + 1;
  const ok = ruleValid() && ruleChanged();
  return `<aside class="card editor" aria-labelledby="h-ed">
    <div class="card-head flush"><div class="left"><span class="eyebrow">Küszöbszabály · Vérnyomás</span><h2 class="h-card" id="h-ed">Szabály szerkesztése</h2></div><span class="chip">${S.ruleVersions[0].no}. verzió érvényes</span></div>
    <div class="two">
      <div class="field"><label for="r-sys">Szisztolés felső határ</label><div class="unit-wrap"><input id="r-sys" class="input input-mid" inputmode="numeric" autocomplete="off" data-rule="sys" data-key="r-sys" value="${esc(S.rule.sys)}"><span class="unit">Hgmm</span></div></div>
      <div class="field"><label for="r-dia">Diasztolés felső határ</label><div class="unit-wrap"><input id="r-dia" class="input input-mid" inputmode="numeric" autocomplete="off" data-rule="dia" data-key="r-dia" value="${esc(S.rule.dia)}"><span class="unit">Hgmm</span></div></div>
    </div>
    <div class="field"><span class="field-label">Súlyosság</span>${seg('rsev', [['moderate', 'Közepes'], ['severe', 'Súlyos']], S.rule.sev, { accent: true, label: 'Súlyosság' })}</div>
    <div class="preview" id="rule-preview" aria-live="polite">${rulePreview()}</div>
    <p class="hint">Mentéskor új, változtathatatlan verzió jön létre. A régi riasztások a saját verziójukra hivatkoznak, a jelentésük nem változik.</p>
    <div class="modal-foot"><button class="btn btn-quiet" type="button" data-act="rule-reset">Visszaállítás</button><button class="btn btn-primary" type="button" id="rule-save" data-act="rule-save" ${ok ? '' : 'disabled'}>Mentés ${next}. verzióként</button></div>
    <div><h3 class="eyebrow">Verziók</h3><ol class="versions">${S.ruleVersions
      .map((v, i) => `<li><span class="vn">${v.no}. verzió</span><span class="muted">${esc(v.cond)}</span><span class="muted">${fDay(v.t)}${i === 0 ? ' · érvényes' : ''}</span></li>`)
      .join('')}</ol></div>
  </aside>`;
}
function updateRuleEditor() {
  const pv = $('#rule-preview');
  if (pv) pv.innerHTML = rulePreview();
  const b = $('#rule-save');
  if (b) b.disabled = !(ruleValid() && ruleChanged());
}

/* követési terv (M3 terv) */
function tabPlan(p) {
  const rows = adherenceRows(p, 14);
  const meta = [
    { ic: 'gauge', freq: 'Naponta', due: 'határidő 10:00, ajánlott 07:30', since: 'okt. 1. óta' },
    { ic: 'scale', freq: 'Hetente, hétfőn', due: 'határidő 20:00', since: 'szept. 1. óta' },
    { ic: 'clipboard', freq: rows[2].fr.replace('hetente', 'Hetente'), due: 'határidő 20:00', since: 'szept. 1. óta' },
  ];
  return `<section class="sec" aria-label="Követési terv">
    <div class="sec-head"><div class="left"><h2 class="h-sec">Követési terv</h2><span class="tag">M3 terv</span></div><button class="btn btn-primary" type="button" data-act="todo">${icon('plus')}Új előírás</button></div>
    <p class="life">Egy alkalom útja: Kirendelve ${icon('chevR')} Esedékes ${icon('chevR')} Teljesítve vagy Elmulasztva. Az elmulasztás az Elmaradt adat szabályhoz fut be.</p>
    <div class="plan">${rows
      .map((r, i) => `<div class="plan-item"><span class="tico">${icon(meta[i].ic)}</span>
        <div><div class="strong">${i === 2 ? 'Közérzet kérdőív' : r.name}</div><div class="meta">${meta[i].freq} · ${meta[i].due} · ${meta[i].since}</div></div>
        <div class="strip-wrap"><div class="adh-top"><span class="fr">Utolsó 14 nap</span><span class="sc">${r.done}/${r.req}</span></div>${stripHtml(r.cells)}</div>
        <div class="pi-actions row-wrap"><button class="btn btn-secondary btn-sm" type="button" data-act="todo">Módosítás</button><button class="btn btn-quiet btn-sm" type="button" data-act="todo">Visszavonás</button></div></div>`)
      .join('')}</div>
  </section>`;
}

/* ---------- Orvos: Riasztások (M3 terv) ---------- */
const ASTATE = (a) => (has(a, 'assigned') ? 'assigned' : has(a, 'seen') ? 'seen' : 'new');
const ASTATE_LABEL = { new: 'Új', seen: 'Megtekintve', assigned: 'Felelősnél' };
function vAlerts() {
  const all = openAlerts().sort(sevSort);
  const n = (k) => all.filter((a) => ASTATE(a) === k).length;
  const list = all.filter((a) => S.alertFilter === 'all' || ASTATE(a) === S.alertFilter);
  const rows = list
    .map((a) => {
      const p = PAT[a.pid];
      const st = has(a, 'assigned') ? 'handled' : a.sev === 'severe' ? 'severe' : 'attention';
      return `<div class="arow">${sicon(st, 20)}
        <span class="a-pat c-name"><span class="name">${esc(p.name)}</span><span class="age">${ageOf(p.born)} éves</span></span>
        <span class="a-what"><span class="tt">${esc(a.title)}</span><span class="meta"> · ${a.rule}, ${a.ver}. verzió</span></span>
        <span class="vv">${a.value}<small>${esc(a.unit)}</small></span>
        <span class="a-state"><span class="chip ${ASTATE(a) === 'new' ? 'fill' : ''}">${ASTATE_LABEL[ASTATE(a)]}</span> <span class="meta">${fRel(a.at)}</span></span>
        <a class="btn btn-secondary btn-sm a-go" href="#adatlap-${p.id}">Megnyitás</a></div>`;
    })
    .join('');
  return `<div class="page">
    <header class="ph"><div class="ph-text"><span class="eyebrow">Minden betegem</span><h1 class="h-display">Riasztások</h1>
      <div class="ph-meta"><span>${all.length} nyitott</span><span>${n('new')} új</span><span class="tag">M3 terv</span></div></div></header>
    <div class="filters">${seg('afilter', [['all', `Mind (${all.length})`], ['new', `Új (${n('new')})`], ['seen', `Megtekintve (${n('seen')})`], ['assigned', `Felelősnél (${n('assigned')})`]], S.alertFilter, { label: 'Szűrés állapot szerint' })}</div>
    <div class="plist">${rows || '<p class="no-match">Nincs ilyen állapotú riasztás.</p>'}</div>
  </div>`;
}

/* ---------- Beteg: Teendőim ---------- */
const MTYPES = [['bp', 'Vérnyomás', 'gauge'], ['pulse', 'Pulzus', 'heart'], ['weight', 'Testsúly', 'scale'], ['glucose', 'Vércukor', 'drop']];
const MFIELDS = {
  bp: [['sys', 'Szisztolés', 'Hgmm'], ['dia', 'Diasztolés', 'Hgmm']],
  pulse: [['v', 'Pulzus', '/perc']],
  weight: [['v', 'Testsúly', 'kg']],
  glucose: [['v', 'Vércukor', 'mmol/l']],
};
const toLocalInput = (d) => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}T${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
function mariaTasks() {
  const lastBP = MARIA.bpS[MARIA.bpS.length - 1];
  const pulseToday = MARIA.pulseS.find((x) => daysAgo(x.t) === 0 && !x.catch);
  return [
    { code: 'bp', kind: 'm', ic: 'gauge', name: 'Vérnyomás', freq: 'Naponta', deadline: 'határidő: ma 10:00', state: 'done', text: `Ma ${fTime(lastBP.t)} rögzítve.` },
    { code: 'pulse', kind: 'm', ic: 'heart', name: 'Pulzus', freq: 'Naponta', deadline: 'határidő: ma 21:00',
      state: pulseToday ? 'done' : 'due', text: pulseToday ? `Ma ${fTime(pulseToday.t)} rögzítve.` : 'Ma még nincs mérés.',
      missed: S.caughtUp ? null : 'Az előző mérés elmaradt, ma éjfélig pótolható.' },
    { code: 'q', kind: 'q', ic: 'clipboard', name: 'Közérzet', freq: 'Hetente', deadline: 'határidő: vasárnap 20:00',
      state: S.qSent ? 'done' : 'due', text: S.qSent ? `Ma ${fTime(NOW)} kitöltve.` : 'Ebben az időszakban még nincs kitöltve.' },
  ];
}
const TASK_STATE = { done: 'Kész', due: 'Esedékes', late: 'Lejárt határidő' };
function taskCard(t) {
  // vízszintes sor: ikon, szöveg, jobb szélen a gomb; a rögzítés a kártyán belül nyílik ki,
  // az elmaradt alkalom külön alsó sávban
  const ico = t.state === 'done' ? 'ok' : t.state === 'late' ? 'late' : 'due';
  const open = S.open === t.code;
  let action = '';
  if (t.state !== 'done' && !open) {
    action = t.kind === 'q'
      ? `<button class="btn btn-primary btn-lg" type="button" data-act="go-q">Kitöltés</button>`
      : `<button class="btn btn-primary btn-lg" type="button" data-act="go-m" data-v="${t.code}">Rögzítés</button>`;
  }
  const missed = t.missed && !open
    ? `<div class="task-missed">${sicon('attention', 22)}<span>${t.missed}</span><button class="btn btn-secondary" type="button" data-act="catchup">Pótlás</button></div>`
    : '';
  return `<article class="task ${open ? 'is-open' : ''}" data-state="${t.state}" id="task-${t.code}"><span class="tico ${ico}">${t.state === 'done' ? icon('check') : icon(t.ic)}</span>
    <div class="task-body"><h3>${t.name}<span class="tm">${t.freq} · ${t.deadline}</span></h3><p class="ts"><b>${TASK_STATE[t.state]}.</b> ${t.text}</p></div>
    ${action ? `<div class="task-actions">${action}</div>` : ''}${missed}
    ${open ? `<div class="task-form">${measureForm(true)}</div>` : ''}</article>`;
}
function measureForm(inTask = false) {
  // teendőből nyitva nincs típusválasztó; a Mentés kicsi, a mérés idejével egy sorban, jobbra
  const fields = MFIELDS[S.mtype];
  const earliest = new Date(NOW.getTime() - 2 * DAY);
  const time = S.timeOther
    ? `<input id="m-time" class="input" type="datetime-local" data-key="m-time" value="${S.mTime || toLocalInput(NOW)}" min="${toLocalInput(earliest)}" max="${toLocalInput(NOW)}">`
    : `<div class="row-wrap"><span class="timechip">${icon('clock')}Most · ${fTime(NOW)}</span><button type="button" class="linkbtn" data-act="time-other">Másik időpont</button></div>`;
  const form = `<form class="form" data-form="measure" novalidate>
    ${inTask ? '' : `<div class="card-head flush"><div class="left"><h2 class="h-sec" id="h-m">Előírás nélküli mérés</h2><span class="meta">Ha a teendőiden kívül is mértél valamit.</span></div></div>`}
    ${S.catchup ? `<div class="receipt">${sicon('attention', 22)}<div><b>Pótlás: az elmaradt pulzusmérés (tegnap 20:30)</b><p class="hint">Írd be az értéket, és mentsd el. Az időpontot átírhatod, legfeljebb két napra visszamenőleg.</p></div></div>` : ''}
    ${inTask ? '' : `<div class="typeseg" role="group" aria-label="Méréstípus">${MTYPES.map(([c, l, ic]) => `<button type="button" data-act="mtype" data-v="${c}" data-key="mt-${c}" aria-pressed="${S.mtype === c}">${icon(ic)}${l}</button>`).join('')}</div>`}
    <div class="${fields.length > 1 ? 'two' : 'one'}">${fields
      .map(([k, l, u]) => `<div class="field"><label for="m-${k}">${l}<span class="sr"> (${u})</span></label><div class="unit-wrap"><input id="m-${k}" class="input input-big" inputmode="${S.mtype === 'weight' || S.mtype === 'glucose' ? 'decimal' : 'numeric'}" autocomplete="off" data-key="m-${k}" value="${esc(S.mVals[k] || '')}"><span class="unit">${u}</span></div>${S.mErr === k ? `<span class="err">${sicon('severe', 14)}Add meg ezt az értéket is: ${l}.</span>` : ''}</div>`)
      .join('')}</div>
    <div class="form-foot">
      <div class="field"><span class="field-label">A mérés ideje</span>${time}</div>
      <div class="form-actions">
        <button class="btn btn-quiet btn-lg" type="button" data-act="m-close">Mégse</button>
        <button class="btn btn-primary btn-lg" type="submit">Mentés</button>
      </div>
    </div>
    ${S.timeOther ? `<div class="row-wrap"><span class="hint">Legfeljebb két napra visszamenőleg.</span><button type="button" class="linkbtn" data-act="time-now">Inkább most</button></div>` : ''}
  </form>`;
  return inTask ? form : `<section class="card" id="meres" aria-labelledby="h-m">${form}</section>`;
}
function questionnaireCard() {
  if (S.qSent) {
    return `<section class="card" id="kerdoiv" aria-labelledby="h-q"><div class="card-head"><h2 class="h-sec" id="h-q">Közérzet</h2></div>
      <div class="receipt" role="status">${sicon('ok', 22)}<div><b>Köszönjük, a kitöltés beérkezett.</b><p class="hint">Beküldve: ma ${fTime(NOW)}. A teendőid között most „Kész” a jelölése.</p></div></div></section>`;
  }
  const qs = QUESTIONNAIRE.questions;
  const answered = qs.filter((q) => S.answers[q.id]).length;
  const items = qs
    .map((q, i) => {
      const opts = q.kind === 'scale' ? [1, 2, 3, 4, 5].map((v) => [String(v), String(v)]) : q.options.map((o) => [o.v, o.l]);
      const btns = opts
        .map(([v, l]) => `<button type="button" role="radio" class="choice ${q.kind === 'scale' ? '' : 'txt'}" data-act="choice" data-q="${q.id}" data-v="${v}" data-key="ch-${q.id}-${v}" aria-checked="${S.answers[q.id] === v}">${l}</button>`)
        .join('');
      return `<div class="q"><span class="q-text" id="qt-${q.id}">${i + 1}. ${esc(q.text)}</span>
        <div class="choices" role="radiogroup" aria-labelledby="qt-${q.id}" style="grid-template-columns:repeat(${opts.length},minmax(0,1fr))">${btns}</div>
        ${q.kind === 'scale' ? `<div class="scale-ends"><span>${q.min}</span><span>${q.maxL}</span></div>` : ''}</div>`;
    })
    .join('');
  return `<section class="card" id="kerdoiv" aria-label="Közérzet kérdőív"><form class="form" data-form="q">
    <div class="qs">${items}</div>
    <div class="q-foot"><button class="btn btn-primary btn-lg" type="submit" ${answered === qs.length ? '' : 'disabled'}>Beküldés</button><span class="meta">${answered}/${qs.length} kérdés megválaszolva</span></div>
  </form></section>`;
}
function latestValues() {
  const bp = MARIA.bpS;
  const lb = bp[bp.length - 1];
  const pl = MARIA.pulseS[MARIA.pulseS.length - 1];
  const wl = MARIA.weightS[MARIA.weightS.length - 1];
  const tile = (k, v, u, t, series) => `<div class="lt"><span class="k">${k}</span><span class="v">${v}<small>${u}</small></span><span class="w">${fRel(t)}</span>${spark(series)}</div>`;
  return `<section class="sec" aria-labelledby="h-lv"><h2 class="h-sec" id="h-lv">Legutóbbi értékeim</h2><div class="latest">
    ${tile('Vérnyomás', `${lb.sys}/${lb.dia}`, 'Hgmm', lb.t, bp.slice(-10).map((x) => x.sys))}
    ${tile('Pulzus', fNum(pl.v), '/perc', pl.t, MARIA.pulseS.slice(-10).map((x) => x.v))}
    ${tile('Testsúly', fNum(wl.v, 1), 'kg', wl.t, MARIA.weightS.slice(-8).map((x) => x.v))}
  </div></section>`;
}
function historyDays(limit = 4, more = true) {
  const items = [
    ...MARIA.bpS.map((x) => ({ t: x.t, k: 'Vérnyomás', v: `${x.sys}/${x.dia}`, u: 'Hgmm' })),
    ...MARIA.pulseS.map((x) => ({ t: x.t, k: 'Pulzus', v: fNum(x.v), u: '/perc' })),
    ...MARIA.weightS.map((x) => ({ t: x.t, k: 'Testsúly', v: fNum(x.v, 1), u: 'kg' })),
  ]
    .filter((x) => daysAgo(x.t) < limit)
    .sort((a, b) => b.t - a.t);
  const days = [];
  for (const it of items) {
    const d = daysAgo(it.t);
    if (!days.length || days[days.length - 1].d !== d) days.push({ d, list: [] });
    days[days.length - 1].list.push(it);
  }
  const label = (d) => {
    const t = at(d, 12, 0);
    if (d === 0) return `Ma, ${WEEKDAYS[t.getDay()]}`;
    if (d === 1) return `Tegnap, ${WEEKDAYS[t.getDay()]}`;
    return `${cap(WEEKDAYS[t.getDay()])}, ${fDay(t)}`;
  };
  return `<section class="sec" aria-labelledby="h-hist"><div class="sec-head"><h2 class="h-sec" id="h-hist">Mérési napló</h2>${more ? '<a class="linkbtn" href="#elozmenyek">Grafikonok és régebbi mérések</a>' : ''}</div>
    <div class="days">${days
      .map((g) => `<div class="day"><h4>${label(g.d)}</h4><ul>${g.list.map((x) => `<li><span class="tm">${fTime(x.t)}</span><span>${x.k}</span><span class="vl">${x.v} <small>${x.u}</small></span></li>`).join('')}</ul></div>`)
      .join('')}</div></section>`;
}
function vHome() {
  // Teendőim: csak a mai teendők; a rögzítés a teendőből nyílik, a kérdőív saját nézetben
  const tasks = mariaTasks();
  const done = tasks.filter((t) => t.state === 'done').length;
  const h = NOW.getHours();
  const greet = h < 9 ? 'Jó reggelt' : h < 18 ? 'Jó napot' : 'Jó estét';
  return `<div class="page patient home">
    <header class="ph"><div class="ph-text"><span class="eyebrow">${fLongDate(NOW)}</span><h1 class="h-display">${greet}, ${MARIA.first}!</h1>
      <div class="progress"><div class="pbar" style="--n:${tasks.length}" aria-hidden="true">${tasks.map((t) => `<i class="${t.state === 'done' ? 'on' : ''}"></i>`).join('')}</div><span class="meta">Mára ${tasks.length} teendőd van, ebből ${done} kész.</span></div></div></header>
    <article class="msg"><span class="avatar">NP</span><div>
      <div class="from"><span class="name">${DR.nagy}</span><span>visszajelzése a vérnyomás-riasztás lezárásakor · ${fDay(at(2, 9, 40))}</span><span class="tag">M3 terv</span></div>
      <blockquote>Átnéztem a keddi mérését. Az egyszeri magas érték után minden mérése rendben volt, gyógyszerváltásra nincs szükség. Ha újra 160 fölött mér, pihenjen öt percet, és mérjen még egyszer.</blockquote></div></article>
    <section class="tasks" aria-label="Mai teendők">${tasks.map(taskCard).join('')}</section>
    ${S.open === 'free'
      ? measureForm(false)
      : `<div class="home-more"><button class="btn btn-secondary" type="button" data-act="m-free">Előírás nélküli mérés</button><a class="linkbtn" href="#elozmenyek">Előzményeim és grafikonok</a></div>`}
  </div>`;
}
function vFill() {
  if (S.qSent) {
    return `<div class="page patient narrow">
      <nav class="crumbs" aria-label="Vissza"><a href="#teendoim">${icon('arrowL')}Teendőim</a></nav>
      <div class="receipt" role="status">${sicon('ok', 22)}<div><b>Köszönjük, a kitöltés beérkezett.</b><p class="hint">Beküldve: ma ${fTime(NOW)}. A teendőid között most „Kész” a jelölése.</p></div></div>
      <div class="row-wrap"><a class="btn btn-primary btn-lg" href="#teendoim">Vissza a teendőkhöz</a></div></div>`;
  }
  return `<div class="page patient narrow">
    <nav class="crumbs" aria-label="Vissza"><a href="#teendoim">${icon('arrowL')}Teendőim</a></nav>
    <header class="ph"><div class="ph-text"><h1 class="h-display">Közérzet</h1><p class="meta">3 kérdés, kb. 1 perc · Legutóbb kitöltve: ${fDayTime(MARIA.subs[0].t)}</p></div></header>
    ${questionnaireCard()}
  </div>`;
}
function vHistory() {
  return `<div class="page patient">
    <header class="ph"><div class="ph-text"><h1 class="h-display">Előzményeim</h1><p class="meta">A grafikonok a saját méréseidet mutatják, értékelés nélkül.</p></div></header>
    ${latestValues()}
    ${measurementsSection(MARIA, false)}
    ${historyDays(10, false)}
  </div>`;
}

/* ---------- Admin ---------- */
const USERS = [
  ['Adminisztrátor', 'admin@pulse.example', 'Adminisztrátor', at(0, 8, 2)],
  ['Dr. Kovács Éva', 'dr.kovacs@pulse.example', 'Orvos', at(0, 8, 10)],
  ['Dr. Nagy Péter', 'dr.nagy@pulse.example', 'Orvos', at(1, 16, 45)],
  ['Szabó János', 'szabo.janos@pulse.example', 'Beteg', at(0, 7, 28)],
  ['Tóth Mária', 'toth.maria@pulse.example', 'Beteg', at(0, 7, 10)],
  ['Varga Béla', 'varga.bela@pulse.example', 'Beteg', at(0, 7, 22)],
  ['Kiss Ilona', 'kiss.ilona@pulse.example', 'Beteg', at(12, 8, 3)],
  ['Molnár Katalin', 'molnar.katalin@pulse.example', 'Beteg', at(0, 7, 29)],
];
const ASSIGN = [
  [DR.kovacs, ['Szabó János', 'Varga Béla', 'Kiss Ilona', 'Molnár Katalin']],
  [DR.nagy, ['Tóth Mária']],
];
function vAdmin() {
  const tabs = [['felhasznalok', 'Felhasználók'], ['osszerendelesek', 'Összerendelések']];
  let body;
  if (S.adminTab === 'osszerendelesek') {
    body = `<div class="stack">${ASSIGN.map(([doc, pats]) => `<section class="card"><div class="card-head"><div class="left"><h2 class="h-card name">${doc}</h2><span class="meta">${pats.length} beteg a seedből${doc === DR.kovacs ? ', a felületi minta további 7 példabetege nélkül' : ''}</span></div><button class="btn btn-secondary btn-sm" type="button" data-act="todo">${icon('link')}Új összerendelés</button></div>
      <div class="tbl-wrap"><table class="tbl"><thead><tr><th>Beteg</th><th>Érvényes</th><th></th></tr></thead><tbody>${pats
        .map((pn) => {
          const k = `${doc}|${pn}`;
          const ended = S.unassigned[k];
          return `<tr><td class="strong">${pn}</td><td>${ended ? `okt. 5. és ${fRel(ended)} között` : 'okt. 5. óta'}</td><td class="n">${ended ? '<span class="muted">Megszüntetve</span>' : `<button class="btn btn-quiet btn-sm" type="button" data-act="unassign" data-v="${esc(k)}">${icon('unlink')}Megszüntetés</button>`}</td></tr>`;
        })
        .join('')}</tbody></table></div></section>`).join('')}
      <p class="meta">A megszüntetés azonnal elveszi az orvos hozzáférését; a korábbi összerendelés a történetben megmarad.</p></div>`;
  } else {
    body = `<div class="card"><div class="tbl-wrap"><table class="tbl"><thead><tr><th>Név</th><th>E-mail-cím</th><th>Szerepkör</th><th>Állapot</th><th>Utolsó belépés</th><th></th></tr></thead><tbody>${USERS
      .map(([n, e, r, t]) => `<tr><td class="strong">${n}</td><td>${e}</td><td>${r}</td><td><span class="band"><span class="sev-dot" style="background:var(--s-ok)"></span>Aktív</span></td><td>${fRel(t)}</td><td class="n"><button class="btn btn-quiet btn-sm" type="button" data-act="todo">Szerkesztés</button></td></tr>`)
      .join('')}</tbody></table></div></div>`;
  }
  return `<div class="page">
    <header class="ph"><div class="ph-text"><span class="eyebrow">Adminisztráció</span><h1 class="h-display">Felhasználók</h1>
      <div class="ph-meta"><span>8 felhasználó</span><span>2 orvos · 5 beteg · 1 adminisztrátor</span></div></div>
      <div class="ph-actions"><button class="btn btn-primary" type="button" data-act="todo">${icon('plus')}Új felhasználó</button></div></header>
    <div class="tabs" role="tablist" aria-label="Adminisztráció">${tabs.map(([id, l]) => `<button type="button" role="tab" data-act="atab" data-v="${id}" data-key="atab-${id}" aria-selected="${S.adminTab === id}">${l}</button>`).join('')}</div>
    ${body}
  </div>`;
}

/* ---------- Elemtár ---------- */
function rgbOf(name) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const m = v.match(/^#([0-9a-f]{6})$/i);
  if (!m) return null;
  const n = parseInt(m[1], 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
function lum(rgb) {
  const f = (c) => {
    const x = c / 255;
    return x <= 0.04045 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * f(rgb[0]) + 0.7152 * f(rgb[1]) + 0.0722 * f(rgb[2]);
}
function ratio(a, b) {
  if (!a || !b) return '';
  const x = lum(a);
  const y = lum(b);
  return `${fNum((Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05), 1)} : 1`;
}
const PRINCIPLES = [
  ['A hangerő a sürgősséget követi', 'A sürgős sorok külön csoportban, nagyobb sorban állnak, elöl a Súlyos. A státusz teli címkét kap a saját színében; a panelen állítható, hogy csak a Súlyos legyen teli.'],
  ['Egy terület, egy fő gomb', 'A fő gomb teli, fehér feliratú, és mindig a terület jobb szélén vagy alján van. A másodlagos semleges kitöltésű, a harmadlagos csak szöveg.'],
  ['Ember: serif, adat: groteszk', 'A nevek és az oldalcímek serifek, a számok és a vezérlők groteszkek. A nagy számok arányos, az oszlopok táblázatos számjegyekkel.'],
  ['A szín jelentést hordoz', 'Akció, státusz, határérték. Díszítő szín, színátmenet és ragyogás nincs; a rétegeket a felület árnyalata és hajszálvonal választja el.'],
  ['Grafikon: egy tengely, halk rács', 'Küszöb: szaggatott vonal a státusz színében. Rács: folytonos hajszálvonal. Minden érték tooltipben és táblázatban is elérhető.'],
  ['Az adathiány látszik', 'A hiányzó nap üres hely a grafikonon és keretes négyzet a teljesítési sávon, nem nulla és nem rendben.'],
];
const ST_DESC = {
  severe: 'Súlyos szabály nyitott, kezeletlen riasztása. Az egyetlen teli címke.',
  attention: 'Közepes riasztás, orvosi döntésre vár.',
  no_data: 'Nincs elég friss adat. Soha nem ad kedvező státuszt.',
  handled: 'Minden nyitott riasztás felelősnél van.',
  ok: 'Friss adat, nincs nyitott riasztás.',
};
function vKit() {
  const white = [255, 255, 255];
  const surf = rgbOf('--surface');
  const fontCards = FONTS.map((f) => `<button type="button" class="fcard" data-act="pref" data-k="font" data-v="${f.id}" data-key="fc-${f.id}" aria-pressed="${S.prefs.font === f.id}" style="--font-display:${esc(f.d)};--font-ui:${esc(f.u)};--display-weight:${f.dw}">
      <span class="eyebrow">${f.name}</span>
      <span class="fx-name">Szabó János</span>
      <span class="fx-ui"><b>Vérnyomás a határ fölött.</b> Árvíztűrő tükörfúrógép: ő, ű, Ő, Ű. ${esc(f.note)}</span>
      <span class="fx-num"><span>Szisztolés</span><span>152</span><span>Diasztolés</span><span>95</span><span>Testsúly</span><span>85,8</span><span>Pulzus</span><span>111</span></span>
      <footer><span>${f.pair}</span>${S.prefs.font === f.id ? '<span class="chip fill">Kiválasztva</span>' : '<span>Kiválasztás</span>'}</footer>
    </button>`).join('');
  const sw = (name, v, note = '') => {
    const rgb = rgbOf(v);
    return `<div class="sw"><div class="chip-c" style="background:var(${v})"></div><span class="nm">${name}</span><span class="hx">${getComputedStyle(document.documentElement).getPropertyValue(v).trim()}${note}</span></div>`;
  };
  const stRows = ST_ORDER.map((s) => `<div class="principle"><span>${sicon(s, 30)}</span><div><h3>${ST[s].label}</h3><p>${ST_DESC[s]}</p>
      <p class="tnum">Fehér jel: ${ratio(white, rgbOf(ST[s].v))} · kártyán: ${ratio(rgbOf(ST[s].v), surf)}</p></div></div>`).join('');
  const sample = PAT.szabo.bpS.filter((x) => daysAgo(x.t) < 14);
  return `<div class="page kit">
    <header class="ph"><div class="ph-text"><span class="eyebrow">Tervezői nézet</span><h1 class="h-display">Elemtár</h1>
      <p class="meta">Minden elem egy helyen. A jobb alsó Megjelenés gombbal a betűpár, a gombszín, a sarkok, a sűrűség és a háttér is állítható.</p></div></header>

    <section class="kit-sec"><header><h2 class="h-sec">Elvek</h2><p>Hat szabály, amitől a felület nyugodt marad, és mindig látszik, hova kell nézni.</p></header>
      <div class="principles">${PRINCIPLES.map(([t, d], i) => `<div class="principle"><span class="n">${i + 1}</span><div><h3>${t}</h3><p>${d}</p></div></div>`).join('')}</div></section>

    <section class="kit-sec"><header><h2 class="h-sec">Betűpárok</h2><p>Kattints egy kártyára: az egész felület átvált. A jobb oszlop számai táblázatos számjegyekkel állnak; ha egy betűnél elcsúsznak, az a betű nem való adatoszlopba.</p></header>
      <div class="fonts">${fontCards}</div></section>

    <section class="kit-sec"><header><h2 class="h-sec">Gombok</h2><p>Teli kitöltés, fehér felirat. Egy területen egy akciószínű gomb van.</p></header>
      <div class="demo-panel">
        <div class="row-wrap"><button class="btn btn-primary btn-lg" type="button">Mentés</button><button class="btn btn-primary" type="button">Lezárás…</button><button class="btn btn-primary btn-sm" type="button">Rögzítés</button><button class="btn btn-primary" type="button">${icon('plus')}Új előírás</button><button class="btn btn-primary" type="button" disabled>Beküldés</button></div>
        <div class="row-wrap"><button class="btn btn-secondary" type="button">${icon('assign')}Felelőshöz rendelés</button><button class="btn btn-secondary btn-sm" type="button">Szerkesztés</button><button class="btn btn-quiet" type="button">Mégse</button><button class="btn btn-danger" type="button">${icon('unlink')}Megszüntetés</button></div>
        <div class="row-wrap"><span class="ibtn accent">${icon('plus')}</span><span class="ibtn">${icon('menu')}</span><span class="ibtn">${icon('x')}</span><span class="tico ok">${icon('check')}</span><span class="tico due">${icon('heart')}</span><span class="tico late">${icon('gauge')}</span><span class="tico">${icon('clipboard')}</span><span class="chip fill">Új</span><span class="badge-n hot">3</span><span class="badge-n">12</span></div>
        <p class="meta">Akciószín fehér felirattal: ${ratio(white, rgbOf('--accent'))} · semleges gomb: ${ratio(white, rgbOf('--fill'))} · veszélyes művelet: ${ratio(white, rgbOf('--danger'))}</p>
      </div></section>

    <section class="kit-sec"><header><h2 class="h-sec">Státuszok</h2><p>Teli kör a státusz színében, fehér jellel: sziréna, figyelmeztető háromszög, áthúzott felhő, pipás alak, pipa. A jel szín nélkül is megkülönbözteti őket; a piros és a zöld színtévesztővel összemosódhat, ezért mindig ikon és szó együtt jelenik meg.</p></header>
      <div class="principles">${stRows}<div class="principle"><span class="st-pill" style="--pill:var(--s-attention-pill)">${sicon('attention', 18, true)}Figyelem</span><div><h3>Teli címke</h3><p>A Figyelem címkéje sötétebb borostyán, hogy a fehér felirat olvasható legyen (4,6 : 1).</p></div></div></div></section>

    <section class="kit-sec"><header><h2 class="h-sec">Színek</h2><p>Meleg szürke rétegek; a kártya egy árnyalattal világosabb a háttérnél, a határt hajszálvonal adja.</p></header>
      <div class="swatches">${sw('Háttér', '--bg')}${sw('Oldalsáv', '--sunk')}${sw('Kártya', '--surface')}${sw('Kiemelt', '--raised')}${sw('Semleges gomb', '--fill')}${sw('Szöveg 1', '--ink-1')}${sw('Szöveg 2', '--ink-2')}${sw('Szöveg 3', '--ink-3')}${sw('Akció', '--accent')}${sw('Veszélyes', '--danger')}</div></section>

    <section class="kit-sec"><header><h2 class="h-sec">Űrlapelemek</h2><p>Nagy mezők, egység a mező jobb szélén; a kiválasztott elem teli.</p></header>
      <div class="demo-panel">
        <div class="two"><div class="field"><label for="k1">Szisztolés</label><div class="unit-wrap"><input id="k1" class="input input-big" value="128" inputmode="numeric"><span class="unit">Hgmm</span></div></div>
          <div class="field"><label for="k2">Keresés</label><label class="search">${icon('search')}<input id="k2" class="input" type="search" placeholder="Keresés név szerint" style="width:100%"></label><span class="hint">Segédszöveg a mező alatt.</span></div></div>
        <div class="row-wrap">${seg('kit-x', [[14, '14 nap'], [30, '30 nap'], [90, '90 nap']], 30, { label: 'Minta' })}${seg('kit-y', [['moderate', 'Közepes'], ['severe', 'Súlyos']], 'moderate', { accent: true, label: 'Minta' })}</div>
        <div class="choices" style="grid-template-columns:repeat(5,minmax(0,1fr));max-width:420px">${[1, 2, 3, 4, 5].map((v) => `<span class="choice" style="display:grid;place-items:center" aria-checked="${v === 4}">${v}</span>`).join('')}</div>
      </div></section>

    <section class="kit-sec"><header><h2 class="h-sec">Grafikonnyelv</h2><p>Vérnyomás: egy függőleges vonal mérésenként, fent a szisztolés, lent a diasztolés. A határ fölötti pont a státusz színét kapja; a karika a riasztást kiváltó mérés. Vidd fölé az egeret, vagy fókuszálj rá, és lépkedj a nyilakkal.</p></header>
      <div class="card chart-card"><div class="legend"><span class="k">${legendDot('var(--ink-1)')}Szisztolés</span><span class="k">${legendDot('var(--ink-3)')}Diasztolés</span><span class="k">${legendDash('var(--s-attention)')}140/90</span><span class="k">${legendDash('var(--s-severe)')}180</span><span class="k">${legendRing()}Riasztás</span></div>
        ${chart({ kind: 'bp', h: 230, days: 14, points: sample, thresholds: BP_THR, label: 'Minta: Szabó János vérnyomása, 14 nap' })}</div></section>
  </div>`;
}

/* ---------- Megjelenés panel ---------- */
const SCREENS = [
  ['belepes', 'Belépés'], ['betegeim', 'Betegeim'], ['adatlap-szabo', 'Adatlap'], ['riasztasok', 'Riasztások', 'M3'],
  ['adatlap-szabo|szabalyok', 'Szabályok', 'M3'], ['adatlap-szabo|terv', 'Követési terv', 'M3'],
  ['adatlap-szabo|modal', 'Lezárás'], ['teendoim', 'Teendőim'], ['kitoltes', 'Kérdőív kitöltése'], ['elozmenyek', 'Előzményeim'], ['admin', 'Admin'],
  ['elemtar', 'Elemtár'],
];
function renderPanel() {
  const el = $('#panel');
  el.classList.toggle('open', S.panel);
  el.setAttribute('aria-hidden', String(!S.panel));
  $('#fab').setAttribute('aria-expanded', String(S.panel));
  const here = S.view === 'adatlap' ? `adatlap-${S.pid}` : S.view;
  const acc = ACCENTS.find((a) => a.id === S.prefs.accent);
  el.innerHTML = `<div class="sheet-in">
    <div class="sheet-head"><h2>Megjelenés</h2><button class="ibtn" type="button" data-act="panel" aria-label="Bezárás">${icon('x')}</button></div>
    <p class="meta">Minden beállítás azonnal az egész felületre hat. Ha megvan a kedvenc, másold ki, és küldd el.</p>
    <section class="psec"><span class="eyebrow">Képernyők</span><div class="screens">${SCREENS
      .map(([h, l, tag]) => {
        const [v, extra] = h.split('|');
        const cur = !extra && v === here && (v !== 'adatlap-szabo' || S.tab === 'attekintes');
        const tabCur = extra && extra !== 'modal' && here === v && S.tab === extra;
        return `<a href="#${v}" data-act="screen" data-v="${h}" ${cur || tabCur ? 'aria-current="page"' : ''}><span>${l}</span>${tag ? `<span class="tag">${tag}</span>` : ''}</a>`;
      })
      .join('')}</div></section>
    <section class="psec"><span class="eyebrow">Betűpár</span><div class="opts">${FONTS.map((f) => `<button type="button" class="opt" data-act="pref" data-k="font" data-v="${f.id}" data-key="pf-${f.id}" aria-pressed="${S.prefs.font === f.id}">
        <span class="o-name">${f.name}</span><span class="o-mark">${icon('check')}</span><span class="o-note">${f.pair}</span>
        <span class="o-sample"><span class="d" style="font-family:${esc(f.d)};font-weight:${f.dw}">Szabó János</span><span class="u" style="font-family:${esc(f.u)}">152/95 Hgmm · ő ű</span></span></button>`).join('')}</div>
      <p class="acc-note">${esc(FONTS.find((f) => f.id === S.prefs.font).note)}</p></section>
    <section class="psec"><span class="eyebrow">Gombszín</span><div class="acc-opts">${ACCENTS.map((a) => `<button type="button" class="acc" data-act="pref" data-k="accent" data-v="${a.id}" data-key="pa-${a.id}" aria-pressed="${S.prefs.accent === a.id}"><span class="dot" style="background:${a.hex};color:${a.id === 'feher' ? 'var(--sunk)' : '#fff'}">${icon('check')}</span>${a.name}</button>`).join('')}</div>
      <p class="acc-note">${esc(acc.note)}</p></section>
    <section class="psec"><span class="eyebrow">Ikonkészlet</span>${prefSeg('icons')}<div class="row-wrap icon-prev">${['users', 'bell', 'heart', 'gauge', 'clipboard', 'search'].map((n) => icon(n)).join('')}${ST_ORDER.map((s) => sicon(s, 20)).join('')}</div></section>
    <section class="psec"><span class="eyebrow">Teli státuszcímke</span>${prefSeg('pills')}</section>
    <section class="psec"><span class="eyebrow">Sarkok</span>${prefSeg('radius')}</section>
    <section class="psec"><span class="eyebrow">Sűrűség</span>${prefSeg('density')}</section>
    <section class="psec"><span class="eyebrow">Háttér</span>${prefSeg('tone')}</section>
    <div class="sheet-foot"><button class="btn btn-secondary" type="button" data-act="reset">Alaphelyzet</button><button class="btn btn-primary" type="button" data-act="copy">${icon('copy')}Beállítás másolása</button></div>
    <textarea id="prefs-text" class="textarea prefs-text" readonly hidden aria-label="A beállítás szövege"></textarea>
  </div>`;
}

/* ---------- párbeszédek ---------- */
const QUICK = ['Telefonon egyeztetve', 'Gyógyszerelés módosítva', 'Mérési hiba volt', 'Nem igényel beavatkozást'];
function modalHtml() {
  const md = S.modal;
  if (md.kind === 'unassign') {
    const [doc, pat] = md.key.split('|');
    return `<div class="modal-back" data-act="modal-bg"><div class="modal" role="dialog" aria-modal="true" aria-labelledby="m-title">
      <div class="modal-head"><h2 id="m-title">Összerendelés megszüntetése</h2><button class="ibtn" type="button" data-act="modal-x" aria-label="Bezárás">${icon('x')}</button></div>
      <p>${esc(doc)} a megszüntetés pillanatától nem éri el ${esc(pat)} adatait. A korábbi összerendelés a történetben megmarad.</p>
      <div class="modal-foot"><button class="btn btn-quiet" type="button" data-act="modal-x">Mégse</button><button class="btn btn-danger" type="button" data-act="confirm-unassign" data-key="m-ok">${icon('unlink')}Megszüntetés</button></div>
    </div></div>`;
  }
  const a = ALERTS.find((x) => x.id === md.id);
  const p = PAT[a.pid];
  return `<div class="modal-back" data-act="modal-bg"><div class="modal" role="dialog" aria-modal="true" aria-labelledby="m-title">
    <div class="modal-head"><h2 id="m-title">Riasztás lezárása</h2><button class="ibtn" type="button" data-act="modal-x" aria-label="Bezárás">${icon('x')}</button></div>
    <div class="modal-sum">${sicon(a.sev === 'severe' ? 'severe' : 'attention', 22)}<div><div class="t">${esc(a.title)} · ${esc(p.name)}</div><div class="meta">${a.value} ${esc(a.unit)} · ${a.rule}, ${a.ver}. verzió · ${fRel(a.at)}</div></div></div>
    <div class="field"><label for="close-reason">Indoklás <span class="muted">(kötelező)</span></label>
      <div class="quick" role="group" aria-label="Gyakori indoklások">${QUICK.map((q) => `<button type="button" data-act="quick" data-v="${esc(q)}" data-key="qk-${esc(q)}" aria-pressed="${md.reason.includes(q)}">${q}</button>`).join('')}</div>
      <textarea id="close-reason" class="textarea" data-key="close-reason" placeholder="Mit tettél, és miért zárható le?">${esc(md.reason)}</textarea>
      ${md.err ? `<span class="err" id="close-err">${sicon('severe', 14)}Az indoklás kötelező.</span>` : ''}</div>
    <div class="field"><label for="close-msg">Visszajelzés a betegnek <span class="muted">(nem kötelező)</span> <span class="tag">M3 terv</span></label>
      <textarea id="close-msg" class="textarea" data-key="close-msg" placeholder="Pl. Átnéztem a mérését, a gyógyszerelés marad.">${esc(md.msg)}</textarea>
      <span class="hint">A beteg a Teendőim oldalon olvassa. Válaszolni nem tud rá.</span></div>
    <div class="modal-foot"><button class="btn btn-quiet" type="button" data-act="modal-x">Mégse</button><button class="btn btn-primary" type="button" data-act="confirm-close" data-key="m-ok">Lezárás</button></div>
  </div></div>`;
}
function openClose(id) {
  S.modal = { kind: 'close', id, reason: '', msg: '', err: false, back: `cl-${id}` };
  renderOverlay();
  $('#close-reason').focus();
}
function closeModal() {
  const back = S.modal && S.modal.back;
  S.modal = null;
  renderOverlay();
  const el = back && document.querySelector(`[data-key="${CSS.escape(back)}"]`);
  if (el) el.focus();
}

/* ---------- értesítés ---------- */
let toastTimer = 0;
function toast(msg) {
  const t = $('#toast');
  t.innerHTML = `${sicon('ok', 18)}<span>${esc(msg)}</span>`;
  t.classList.add('on');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove('on'), 3600);
}
function goTo(id) {
  const el = document.getElementById(id);
  if (!el) return;
  const smooth = !window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  el.scrollIntoView({ behavior: smooth ? 'smooth' : 'auto', block: 'start' });
}

/* ---------- műveletek ---------- */
const ACT = {
  nav: () => document.body.classList.toggle('nav-open'),
  role: (el) => { location.hash = HOME[el.dataset.v]; },
  filter: (el) => {
    if (el.getAttribute('aria-disabled') === 'true') return;
    S.filter = S.filter === el.dataset.v ? 'all' : el.dataset.v;
    render();
  },
  tab: (el) => { S.tab = el.dataset.v; render(); },
  atab: (el) => { S.adminTab = el.dataset.v; render(); },
  period: (el) => { S.period = Number(el.dataset.v); render(); },
  mode: (el) => { S.mode = el.dataset.v; render(); },
  afilter: (el) => { S.alertFilter = el.dataset.v; render(); },
  panel: () => {
    S.panel = !S.panel;
    renderPanel();
    if (S.panel) $('#panel .ibtn').focus();
    else $('#fab').focus();
  },
  pref: (el) => {
    S.prefs[el.dataset.k] = el.dataset.v;
    savePrefs();
    applyPrefs();
    if (S.view === 'elemtar' || el.dataset.k === 'icons' || el.dataset.k === 'pills') render();
    else renderPanel();
    requestAnimationFrame(() => drawCharts());
  },
  reset: () => {
    S.prefs = { ...PREF_DEFAULT };
    savePrefs();
    applyPrefs();
    render();
    requestAnimationFrame(() => drawCharts());
  },
  copy: () => {
    const text = prefsText();
    const fallback = () => {
      const ta = $('#prefs-text');
      ta.hidden = false;
      ta.value = text;
      ta.focus();
      ta.select();
      toast('Jelöld ki, és másold ki a szöveget.');
    };
    try {
      navigator.clipboard.writeText(text).then(() => toast('Kimásolva. Illeszd be a beszélgetésbe.'), fallback);
    } catch (e) {
      fallback();
    }
  },
  screen: (el, e) => {
    e.preventDefault();
    const [v, extra] = el.dataset.v.split('|');
    S.panel = false;
    if (extra === 'modal') S.pendingModal = 'a1';
    if (extra && extra !== 'modal') S.pendingTab = extra;
    if (`#${v}` === location.hash) {
      if (extra && extra !== 'modal') S.tab = extra;
      else if (!extra && v.startsWith('adatlap')) S.tab = 'attekintes';
      S.pendingTab = null;
      render();
      if (S.pendingModal) { S.pendingModal = null; openClose('a1'); }
      window.scrollTo(0, 0);
    } else {
      if (!extra && v.startsWith('adatlap')) S.pendingTab = 'attekintes';
      lastKey = '';
      location.hash = v;
    }
  },
  assign: (el) => {
    const a = ALERTS.find((x) => x.id === el.dataset.id);
    if (!has(a, 'seen')) a.events.push({ t: new Date(NOW), type: 'seen', who: DR.kovacs });
    a.events.push({ t: new Date(NOW.getTime() + 60000), type: 'assigned', who: DR.kovacs });
    render();
    toast(`Felelős: ${DR.kovacs}. A riasztás „Kezelés alatt” állapotba került.`);
  },
  'close-alert': (el) => openClose(el.dataset.id),
  quick: (el) => {
    const q = el.dataset.v;
    const md = S.modal;
    if (md.reason.includes(q)) md.reason = md.reason.replace(q, '').replace(/^[.\s]+|[.\s]+$/g, '').replace(/\.\s*\./g, '.');
    else md.reason = md.reason.trim() ? `${md.reason.trim().replace(/\.$/, '')}. ${q}.` : `${q}.`;
    md.err = false;
    renderOverlay();
    $(`[data-key="${CSS.escape(`qk-${q}`)}"]`).focus();
  },
  'modal-x': () => closeModal(),
  'modal-bg': () => closeModal(),
  'confirm-close': () => {
    const md = S.modal;
    if (!md.reason.trim()) {
      md.err = true;
      renderOverlay();
      $('#close-reason').focus();
      return;
    }
    const a = ALERTS.find((x) => x.id === md.id);
    a.events.push({ t: new Date(NOW.getTime() + 120000), type: 'closed', who: DR.kovacs, note: md.reason.trim(), msg: md.msg.trim() });
    const p = PAT[a.pid];
    S.modal = null;
    render();
    toast(`A riasztás lezárva. ${p.name} státusza most: ${ST[statusOf(p)].label}.`);
  },
  unassign: (el) => {
    S.modal = { kind: 'unassign', key: el.dataset.v };
    renderOverlay();
    $('[data-key="m-ok"]').focus();
  },
  'confirm-unassign': () => {
    S.unassigned[S.modal.key] = new Date(NOW);
    S.modal = null;
    render();
    toast('Az összerendelés megszűnt, a hozzáférés azonnal lezárult.');
  },
  'rule-edit': (el) => {
    S.ruleSel = el.dataset.v;
    render();
  },
  rsev: (el) => {
    S.rule.sev = el.dataset.v;
    render();
  },
  'rule-reset': () => {
    S.rule = { ...S.ruleCur };
    render();
  },
  'rule-save': () => {
    if (!(ruleValid() && ruleChanged())) return;
    const no = S.ruleVersions[0].no + 1;
    S.ruleCur = { ...S.rule };
    S.ruleVersions.unshift({ no, t: new Date(NOW), by: DR.kovacs, cond: `Szisztolés > ${S.rule.sys} Hgmm vagy diasztolés > ${S.rule.dia} Hgmm, ${S.rule.sev === 'severe' ? 'súlyos' : 'közepes'}` });
    openAlerts(S.pid).filter((a) => a.kind === 'threshold' && a.sev === 'moderate').forEach((a) => a.events.push({ t: new Date(NOW), type: 'rule', data: `${no}. verzió` }));
    render();
    toast(`Elmentve ${no}. verzióként. A nyitott riasztás továbbra is az 1. verzióra hivatkozik.`);
  },
  'note-open': () => {
    S.noteOpen = true;
    if (S.tab !== 'attekintes') S.tab = 'attekintes';
    render();
    goTo('jegyzet');
    $('#note-text').focus({ preventScroll: true });
  },
  'note-cancel': () => { S.noteOpen = false; S.noteText = ''; render(); },
  todo: () => toast('Ez a gomb a mintában még nem működik.'),
  'login-fill': (el) => {
    S.loginEmail = el.dataset.v;
    S.loginErr = false;
    render();
    $('#login-email').focus();
  },
  mtype: (el) => {
    S.mtype = el.dataset.v;
    S.mVals = {};
    S.mErr = null;
    if (S.mtype !== 'pulse') S.catchup = false;
    render();
  },
  'time-other': () => { S.timeOther = true; S.mTime = toLocalInput(NOW); render(); $('#m-time').focus(); },
  'time-now': () => { S.timeOther = false; S.catchup = false; render(); },
  'go-m': (el) => {
    S.mtype = el.dataset.v;
    S.open = el.dataset.v;
    S.catchup = false;
    S.timeOther = false;
    S.mVals = {};
    S.mErr = null;
    render();
    $(`#m-${MFIELDS[S.mtype][0][0]}`).focus({ preventScroll: true });
  },
  'm-free': () => {
    S.open = 'free';
    S.mtype = 'weight';
    S.catchup = false;
    S.timeOther = false;
    S.mVals = {};
    S.mErr = null;
    render();
    goTo('meres');
  },
  'm-close': () => {
    S.open = null;
    S.catchup = false;
    S.timeOther = false;
    S.mVals = {};
    S.mErr = null;
    render();
  },
  catchup: () => {
    S.mtype = 'pulse';
    S.open = 'pulse';
    S.catchup = true;
    S.timeOther = true;
    S.mTime = toLocalInput(at(1, 20, 30));
    S.mVals = {};
    render();
    $('#m-v').focus({ preventScroll: true });
  },
  'catchup-cancel': () => { S.catchup = false; S.timeOther = false; render(); },
  'go-q': () => { location.hash = 'kitoltes'; },
  choice: (el) => {
    S.answers[el.dataset.q] = el.dataset.v;
    render();
  },
};
const FORMS = {
  login: () => {
    const e = (S.loginEmail || '').trim().toLowerCase();
    if (!e) {
      S.loginErr = true;
      render();
      $('#login-email').focus();
      return;
    }
    S.loginErr = false;
    location.hash = e.startsWith('dr.') ? 'betegeim' : e.startsWith('admin') ? 'admin' : 'teendoim';
  },
  measure: () => {
    const fields = MFIELDS[S.mtype];
    const empty = fields.find(([k]) => !String(S.mVals[k] || '').trim());
    if (empty) {
      S.mErr = empty[0];
      render();
      $(`#m-${empty[0]}`).focus();
      return;
    }
    const vals = fields.map(([k]) => parseFloat(String(S.mVals[k]).replace(',', '.')));
    const when = S.timeOther && S.mTime ? new Date(S.mTime) : new Date(NOW);
    const dec = S.mtype === 'weight' || S.mtype === 'glucose' ? 1 : 0;
    const label = S.mtype === 'bp' ? `${vals[0]}/${vals[1]} Hgmm` : `${fNum(vals[0], dec)} ${UNIT[S.mtype]}`;
    const byTime = (a, b) => a.t - b.t;
    if (S.mtype === 'bp') MARIA.bpS.push({ t: when, sys: vals[0], dia: vals[1] });
    if (S.mtype === 'pulse') MARIA.pulseS.push({ t: when, v: vals[0], catch: S.catchup });
    if (S.mtype === 'weight') MARIA.weightS.push({ t: when, v: vals[0] });
    [MARIA.bpS, MARIA.pulseS, MARIA.weightS].forEach((arr) => arr.sort(byTime));
    const wasCatch = S.catchup;
    if (wasCatch) S.caughtUp = true;
    S.mVals = {};
    S.mErr = null;
    S.catchup = false;
    S.timeOther = false;
    S.open = null;
    render();
    toast(wasCatch ? `Az elmaradt mérés pótolva: ${label}.` : `A mérés elmentve: ${label}, ${fRel(when)}.`);
  },
  q: () => {
    if (!QUESTIONNAIRE.questions.every((q) => S.answers[q.id])) return;
    S.qSent = true;
    location.hash = 'teendoim';
    toast('Köszönjük, a kitöltés beérkezett.');
  },
  note: () => {
    const txt = (S.noteText || '').trim();
    if (!txt) {
      $('#note-text').focus();
      return;
    }
    const p = PAT[S.pid];
    p.notes = [{ t: new Date(NOW), by: DR.kovacs, text: txt }, ...(p.notes || [])];
    S.noteOpen = false;
    S.noteText = '';
    render();
    toast('Megjegyzés elmentve.');
  },
};

/* ---------- eseménykezelés ---------- */
document.addEventListener('click', (e) => {
  const el = e.target.closest('[data-act]');
  if (!el) return;
  if (el.dataset.act === 'modal-bg' && e.target !== el) return;
  const fn = ACT[el.dataset.act];
  if (fn) fn(el, e);
});
document.addEventListener('input', (e) => {
  const t = e.target;
  if (t.id === 'q-search') {
    S.query = t.value;
    applySearch();
  } else if (t.id === 'close-reason' && S.modal) {
    S.modal.reason = t.value;
    if (S.modal.err && t.value.trim()) {
      S.modal.err = false;
      const er = $('#close-err');
      if (er) er.remove();
    }
  } else if (t.id === 'close-msg' && S.modal) {
    S.modal.msg = t.value;
  } else if (t.dataset.rule) {
    S.rule[t.dataset.rule] = t.value.trim();
    updateRuleEditor();
  } else if (t.id === 'm-time') {
    S.mTime = t.value;
  } else if (t.id && t.id.startsWith('m-') && t.closest('[data-form="measure"]')) {
    const k = t.id.slice(2);
    S.mVals[k] = t.value;
    if (S.mErr === k) {
      S.mErr = null;
      const er = t.closest('.field').querySelector('.err');
      if (er) er.remove();
    }
  } else if (t.id === 'note-text') {
    S.noteText = t.value;
  } else if (t.id === 'login-email') {
    S.loginEmail = t.value;
  }
});
document.addEventListener('submit', (e) => {
  const f = e.target.dataset.form;
  if (!f || !FORMS[f]) return;
  e.preventDefault();
  FORMS[f](e.target);
});
document.addEventListener('keydown', (e) => {
  if (e.key !== 'Escape') return;
  if (S.modal) closeModal();
  else if (S.panel) ACT.panel();
  else if (document.body.classList.contains('nav-open')) document.body.classList.remove('nav-open');
});
document.addEventListener('pointerover', (e) => {
  const el = e.target.closest('[data-tip]');
  if (!el) return;
  const r = el.getBoundingClientRect();
  showTip(`<span>${esc(el.dataset.tip)}</span>`, r.left + r.width / 2, r.top);
});
document.addEventListener('pointerout', (e) => {
  if (e.target.closest('[data-tip]')) hideTip();
});
window.addEventListener('hashchange', route);
let resizeTimer = 0;
window.addEventListener('resize', () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => drawCharts(), 120);
});

/* ---------- indulás ---------- */
document.documentElement.lang = 'hu';
applyPrefs();
$('#fab').innerHTML = `${icon('type')}<span>Megjelenés</span>`;
route();
if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => drawCharts());
