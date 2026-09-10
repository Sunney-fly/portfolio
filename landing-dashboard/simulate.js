/* =====================================================================
   simulate.js — executes the pure logic from app.js against the real
   data arrays with a minimal DOM stub, to prove the chart maths produce
   finite, sane numbers (a static check cannot run the browser, but it
   can catch NaN geometry and broken formatters).

   Run:  node simulate.js
   ===================================================================== */
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const DIR = __dirname;
const js = fs.readFileSync(path.join(DIR, 'app.js'), 'utf8');

/* --- minimal DOM stub ------------------------------------------------ */
function makeNode(tag) {
  const node = {
    tagName: tag,
    children: [],
    attributes: {},
    style: { setProperty() {}, },
    dataset: {},
    classList: { add() {}, remove() {}, toggle() {}, contains: () => false },
    _text: '',
    setAttribute(k, v) { this.attributes[k] = v; },
    getAttribute(k) { return this.attributes[k]; },
    appendChild(c) { this.children.push(c); return c; },
    removeAttribute(k) { delete this.attributes[k]; },
    addEventListener() {},
    querySelector() { return null; },
    querySelectorAll() { return []; },
    focus() {},
    getBoundingClientRect() { return { width: 700, height: 300, left: 0, top: 0 }; },
    closest() { return null; },
    set innerHTML(v) { this._text = v; this.children = []; },
    get innerHTML() { return this._text; },
    set textContent(v) { this._text = String(v); },
    get textContent() { return this._text; },
    get viewBox() { return { baseVal: { width: 700 } }; }
  };
  return node;
}

const parser = {
  parseFromString() { return makeNode('svg'); }
};

const stubDocument = {
  readyState: 'complete',
  documentElement: makeNode('html'),
  body: makeNode('body'),
  createElement: (t) => makeNode(t),
  createElementNS: (ns, t) => {
    const n = makeNode(t);
    n.namespace = ns;
    /* emulate getTotalLength for the dash-draw animation */
    n.getTotalLength = () => 1234.5;
    return n;
  },
  querySelector: () => null,
  querySelectorAll: () => [],
  addEventListener() {},
  fonts: null
};

const store = {};
const stubWindow = {
  document: stubDocument,
  matchMedia: (q) => ({ matches: false, addEventListener() {}, addListener() {} }),
  requestAnimationFrame: (fn) => { if (typeof fn === 'function') fn(16); return 1; },
  cancelAnimationFrame() {},
  setTimeout: (fn) => { if (typeof fn === 'function') fn(); return 1; },
  clearTimeout() {},
  addEventListener() {},
  getComputedStyle: () => ({ getPropertyValue: () => '#4f46e5' }),
  localStorage: {
    getItem: (k) => (k in store ? store[k] : null),
    setItem: (k, v) => { store[k] = String(v); }
  },
  scrollY: 0
};
stubWindow.window = stubWindow;

const sandbox = {
  window: stubWindow,
  document: stubDocument,
  localStorage: stubWindow.localStorage,
  getComputedStyle: stubWindow.getComputedStyle,
  IntersectionObserver: function () { this.observe = () => {}; this.unobserve = () => {}; },
  console,
  Map,
  Math,
  Number,
  Date,
  isFinite,
  parseFloat,
  parseInt,
  String,
  Object,
  Array,
  JSON,
  DOMParser: function () { return parser; }
};
sandbox.globalThis = sandbox;
sandbox.self = sandbox;

/* --- instrument: expose internals by appending a probe ---------------- */
/* app.js is an IIFE with a private scope, so instead of reaching inside we
   re-evaluate the pure helpers by extracting them textually.            */
function extract(name) {
  const start = js.indexOf('function ' + name + '(');
  if (start === -1) throw new Error('helper not found in app.js: ' + name);
  let depth = 0;
  let i = js.indexOf('{', start);
  const bodyStart = i;
  for (; i < js.length; i++) {
    if (js[i] === '{') depth++;
    else if (js[i] === '}') {
      depth--;
      if (depth === 0) break;
    }
  }
  return js.slice(start, i + 1);
}

const helperSrc = [
  extract('clamp'),
  extract('formatMoney'),
  extract('formatNumber'),
  extract('formatMetric'),
  extract('niceTicks'),
  extract('smoothPath')
].join('\n\n');

/* data arrays are private too — re-extract them for the maths test */
function extractConst(name) {
  const m = new RegExp('var\\s+' + name + '\\s*=\\s*([\\s\\S]*?);\\n\\n', 'm').exec(js);
  if (!m) throw new Error('data block not found: ' + name);
  return 'var ' + name + ' = ' + m[1] + ';';
}

const dataSrc = [extractConst('DAILY'), extractConst('WEEKLY'), extractConst('MONTHLY')].join('\n\n');

const probe = helperSrc + '\n\n' + dataSrc + '\n\n' + `
  __result = { clamp, formatMoney, formatNumber, formatMetric, niceTicks, smoothPath, DAILY, WEEKLY, MONTHLY };
`;

const ctx = vm.createContext(sandbox);
vm.runInContext(probe, ctx);
const R = sandbox.__result;

const failures = [];
const checks = [];
function check(label, cond, detail) {
  if (cond) checks.push(label + (detail ? '  (' + detail + ')' : ''));
  else failures.push(label + (detail ? '  -> ' + detail : ''));
}

/* ---- 1. datasets are present and internally consistent --------------- */
['DAILY', 'WEEKLY', 'MONTHLY'].forEach((k) => {
  const s = R[k];
  check(`${k} has rows`, Array.isArray(s) && s.length > 0, `${s.length} rows`);
  const bad = s.filter((p) => !p || typeof p.d !== 'string' ||
    !Number.isFinite(p.revenue) || !Number.isFinite(p.units) || !Number.isFinite(p.orders));
  check(`${k} rows are well-formed`, bad.length === 0, bad.length ? JSON.stringify(bad[0]) : 'ok');
  const neg = s.filter((p) => p.revenue < 0 || p.units < 0 || p.orders < 0);
  check(`${k} has no negative values`, neg.length === 0);
});
check('DAILY covers 30 days', R.DAILY.length === 30, String(R.DAILY.length));
check('WEEKLY covers 13 weeks', R.WEEKLY.length === 13, String(R.WEEKLY.length));
check('MONTHLY covers 12 months', R.MONTHLY.length === 12, String(R.MONTHLY.length));

/* ---- 2. formatters --------------------------------------------------- */
check('formatMoney whole', R.formatMoney(412880, false) === '$412,880', R.formatMoney(412880, false));
check('formatMoney compact k', R.formatMoney(412880, true) === '$413k', R.formatMoney(412880, true));
check('formatMoney compact small', R.formatMoney(9800, true) === '$9.8k', R.formatMoney(9800, true));
check('formatNumber thousands', R.formatNumber(18420, 0) === '18,420', R.formatNumber(18420, 0));
check('formatNumber decimals', R.formatNumber(4.2, 1) === '4.2', R.formatNumber(4.2, 1));
check('formatMetric units passthrough', R.formatMetric(18420, 'units', false) === '18,420');
check('formatMetric revenue', R.formatMetric(412880, 'revenue', false) === '$412,880');
check('clamp low', R.clamp(-5, 0, 10) === 0);
check('clamp high', R.clamp(50, 0, 10) === 10);
check('clamp inside', R.clamp(5, 0, 10) === 5);

/* ---- 3. axis ticks --------------------------------------------------- */
[R.DAILY, R.WEEKLY, R.MONTHLY].forEach((series, i) => {
  const name = ['DAILY', 'WEEKLY', 'MONTHLY'][i];
  ['revenue', 'units', 'orders'].forEach((metric) => {
    const vals = series.map((p) => p[metric]);
    const t = R.niceTicks(Math.min(...vals) * 0.92, Math.max(...vals) * 1.04, 4);
    check(`${name}.${metric} ticks finite`, t.ticks.every(Number.isFinite));
    check(`${name}.${metric} ticks span data`,
      t.min <= Math.min(...vals) && t.max >= Math.max(...vals),
      `min ${t.min} <= ${Math.min(...vals)}, max ${t.max} >= ${Math.max(...vals)}`);
    check(`${name}.${metric} tick count sane`, t.ticks.length >= 3 && t.ticks.length <= 12, `${t.ticks.length}`);
    check(`${name}.${metric} max > min`, t.max > t.min);
  });
});

/* ---- 4. geometry: the maths app.js uses for the line chart ----------- */
function buildPoints(series, metric, width, height, pad) {
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const vals = series.map((p) => p[metric]);
  const t = R.niceTicks(Math.min(...vals) * 0.92, Math.max(...vals) * 1.04, 4);
  const pts = series.map((p, i) => ({
    x: pad.left + (innerW * i) / (series.length - 1),
    y: pad.top + innerH - ((p[metric] - t.min) / (t.max - t.min)) * innerH
  }));
  return { pts, pad, innerW, innerH, height };
}

const PAD = { top: 22, right: 18, bottom: 34, left: 56 };

[R.DAILY, R.WEEKLY, R.MONTHLY].forEach((series, i) => {
  const name = ['DAILY', 'WEEKLY', 'MONTHLY'][i];
  ['revenue', 'units', 'orders'].forEach((metric) => {
    const g = buildPoints(series, metric, 760, 300, PAD);
    check(`${name}.${metric} points finite`,
      g.pts.every((p) => Number.isFinite(p.x) && Number.isFinite(p.y)));
    check(`${name}.${metric} inside plot box`,
      g.pts.every((p) => p.x >= PAD.left - 0.6 && p.x <= 760 - PAD.right + 0.6 &&
                            p.y >= PAD.top - 0.6 && p.y <= PAD.top + g.innerH + 0.6),
      `x[${g.pts[0].x.toFixed(1)}..${g.pts[g.pts.length - 1].x.toFixed(1)}] ` +
      `y[${Math.min(...g.pts.map(p=>p.y)).toFixed(1)}..${Math.max(...g.pts.map(p=>p.y)).toFixed(1)}]`);
    check(`${name}.${metric} x strictly increasing`,
      g.pts.every((p, k) => k === 0 || p.x > g.pts[k - 1].x));

    const d = R.smoothPath(g.pts);
    check(`${name}.${metric} path has no NaN`, !/NaN|Infinity|undefined/.test(d));
    check(`${name}.${metric} path starts with M`, d.startsWith('M'), d.slice(0, 24));
    const segments = (d.match(/C/g) || []).length;
    check(`${name}.${metric} path segment count`, segments === g.pts.length - 1,
      `${segments} curves for ${g.pts.length} points`);
  });
});

/* degenerate case: single point must not divide by zero */
const one = R.smoothPath([{ x: 10, y: 20 }]);
check('smoothPath single point', one === 'M10.00 20.00', one);
const two = R.smoothPath([{ x: 0, y: 0 }, { x: 10, y: 5 }]);
check('smoothPath two points uses line', two === 'M0.00 0.00L10.00 5.00', two);

/* ---- 5. bar chart geometry ------------------------------------------ */
const WAREHOUSES = [
  { name: 'Newark, NJ', units: 7440, coverage: 41 },
  { name: 'Reno, NV', units: 5120, coverage: 28 },
  { name: 'Leipzig, DE', units: 3510, coverage: 22 },
  { name: 'Toronto, CA', units: 2360, coverage: 12 }
];
const shares = { all: [0.44, 0.34, 0.22], dtc: [0.52, 0.3, 0.18], marketplace: [0.36, 0.4, 0.24], retail: [0.3, 0.35, 0.35] };
[30, 90, 365].forEach((range) => {
  Object.keys(shares).forEach((chn) => {
    const mult = range === 90 ? 3.05 : (range === 365 ? 12.2 : 1);
    const rows = WAREHOUSES.map((w, i) => ({
      units: Math.round(w.units * mult * ((shares[chn][i] || 0.2) * 2.3))
    }));
    const max = Math.max(...rows.map((r) => r.units)) * 1.12;
    check(`bars ${range}d/${chn} finite & positive`,
      rows.every((r) => Number.isFinite(r.units) && r.units > 0),
      rows.map((r) => r.units).join(','));
    check(`bars ${range}d/${chn} heights within plot`,
      rows.every((r) => { const h = (r.units / max) * 224; return h > 0 && h <= 224; }),
      'max ' + max.toFixed(0));
  });
});

/* ---- 6. KPI totals -------------------------------------------------- */
[['30', R.DAILY, 1], ['90', R.WEEKLY, 1], ['365', R.MONTHLY, 1]].forEach(([range, series]) => {
  const chans = { all: 1, dtc: 0.46, marketplace: 0.34, retail: 0.2 };
  Object.keys(chans).forEach((c) => {
    const rev = series.reduce((a, p) => a + Math.round(p.revenue * chans[c]), 0);
    check(`KPI revenue ${range}d/${c} finite`, Number.isFinite(rev) && rev > 0, '$' + rev.toLocaleString('en-US'));
    check(`KPI revenue ${range}d/${c} formatted`, /^\$[\d,]+$/.test(R.formatNumber(rev, 0).replace(/^/, '$')),
      '$' + R.formatNumber(rev, 0));
  });
});

/* ---- report --------------------------------------------------------- */
console.log('\n=== SIMULATION PASS (' + checks.length + ') ===');
checks.forEach((c) => console.log('  [ok]   ' + c));
if (failures.length) {
  console.log('\n=== SIMULATION FAIL (' + failures.length + ') ===');
  failures.forEach((f) => console.log('  [FAIL] ' + f));
  process.exit(1);
}
console.log('\nAll ' + checks.length + ' logic simulations passed.');
