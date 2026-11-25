/* =====================================================================
   verify.js — static self-checks for the portfolio demo.
   Run:  node verify.js
   Checks:
     A. local file references from index.html all exist
     B. zero external URLs / CDN references in html, css and js
     C. HTML tag balance (void + self-closing aware)
     D. duplicate id detection
     E. CSS brace balance
     F. every var(--token) referenced is actually defined somewhere
     G. every #id used by app.js exists in index.html
     H. every CSS class used by app.js is present in styles.css
   ===================================================================== */
'use strict';

const fs = require('fs');
const path = require('path');

const DIR = __dirname;
const read = (f) => fs.readFileSync(path.join(DIR, f), 'utf8');

const html = read('index.html');
const css = read('styles.css');
const js = read('app.js');

const failures = [];
const warnings = [];
const passes = [];
const fail = (m) => failures.push(m);
const warn = (m) => warnings.push(m);
const pass = (m) => passes.push(m);

/* --- strip comments/strings so scans do not produce false hits ------- */
const htmlNoComments = html.replace(/<!--[\s\S]*?-->/g, '');
const cssNoComments = css.replace(/\/\*[\s\S]*?\*\//g, '');
const jsNoComments = js
  .replace(/\/\*[\s\S]*?\*\//g, '')
  .replace(/(^|[^:"'\\])\/\/[^\n]*/g, '$1');

/* =====================================================================
   A. local references exist
   ===================================================================== */
const refs = [];
const refRe = /(?:href|src)\s*=\s*"([^"]+)"/gi;
let m;
while ((m = refRe.exec(htmlNoComments)) !== null) refs.push(m[1]);

const localFiles = refs.filter(
  (r) => !/^(#|data:|mailto:|tel:)/i.test(r) && !/^https?:/i.test(r)
);
if (localFiles.length === 0) fail('A: no local stylesheet/script references found at all');
localFiles.forEach((r) => {
  const clean = r.split('?')[0].split('#')[0];
  if (!fs.existsSync(path.join(DIR, clean))) fail(`A: missing local file referenced by index.html -> ${r}`);
});
pass(`A: ${localFiles.length} local reference(s) verified: ${localFiles.join(', ')}`);

/* anchor targets */
const ids = new Set();
const idRe = /\sid\s*=\s*"([^"]+)"/g;
while ((m = idRe.exec(htmlNoComments)) !== null) ids.add(m[1]);
const anchors = [...new Set(refs.filter((r) => r.startsWith('#')).map((r) => r.slice(1)))];
const missingAnchors = anchors.filter((a) => a !== '' && !ids.has(a));
if (missingAnchors.length) fail(`A: in-page anchors with no target: ${missingAnchors.join(', ')}`);
else pass(`A: all ${anchors.length} in-page anchors resolve to a real id`);

/* =====================================================================
   B. zero external *assets* (meta/canonical self-URLs are allowed)
   --------------------------------------------------------------------
   The invariant that matters is "renders with no network request": no CDN
   script, no remote font, no remote image. Absolute URLs in <link rel=
   "canonical"> and og:/twitter: meta are share metadata, not fetches, so
   they are exempt — but they must point at this same site.
   ===================================================================== */
const SITE = 'https://nanmount-r-ain.cn/';
const externals = [];
const metaOnlyAllowed = (line) =>
  /rel="canonical"/i.test(line) ||
  /(property|name)="(og|twitter):[^"]*"/i.test(line);

[['index.html', htmlNoComments], ['styles.css', cssNoComments], ['app.js', jsNoComments]].forEach(
  ([name, text]) => {
    text.split('\n').forEach((line, i) => {
      if (/https?:\/\//i.test(line) || /\/\/cdn/i.test(line) || /fonts\.googleapis/i.test(line) ||
          /fonts\.gstatic/i.test(line) || /unpkg|jsdelivr|cdnjs|googleapis/i.test(line)) {
        /* allow the svg/xml namespace declaration, it is not a network fetch */
        if (/www\.w3\.org\/2000\/svg/.test(line)) return;
        /* allow share metadata that points at our own deployment */
        if (metaOnlyAllowed(line) && line.includes(SITE)) return;
        externals.push(`${name}:${i + 1}: ${line.trim().slice(0, 120)}`);
      }
    });
  }
);
if (externals.length) {
  fail(`B: ${externals.length} external reference(s) found:\n      ` + externals.join('\n      '));
} else {
  pass('B: no external assets (CDN / font host / remote image); share metadata points at this site');
}

/* =====================================================================
   B2. share metadata present and pointing at a file we actually ship
   ===================================================================== */
{
  const grab = (re) => (htmlNoComments.match(re) || [])[1];
  const ogImage = grab(/property="og:image"\s+content="([^"]+)"/i);
  const ogTitle = grab(/property="og:title"\s+content="([^"]+)"/i);
  const twCard = grab(/name="twitter:card"\s+content="([^"]+)"/i);
  const problems = [];
  if (!ogTitle) problems.push('missing og:title');
  if (!twCard) problems.push('missing twitter:card');
  if (!ogImage) {
    problems.push('missing og:image');
  } else {
    const file = ogImage.split('/').pop();
    if (!fs.existsSync(path.join(DIR, file))) problems.push(`og:image target ${file} is not in the bundle`);
    if (!/^https?:\/\//i.test(ogImage)) problems.push('og:image must be absolute for crawlers');
  }
  if (problems.length) fail(`B2: share metadata — ${problems.join('; ')}`);
  else pass(`B2: share metadata present, og:image ships with the bundle (${ogImage.split('/').pop()})`);
}

/* =====================================================================
   B3. counters ship their real value (no "0%" before JS runs)
   --------------------------------------------------------------------
   Regression guard: counters used to be authored as 0 and only filled in by
   IntersectionObserver, so no-JS / reduced-motion / prerender saw "0%".
   ===================================================================== */
{
  const counters = [...htmlNoComments.matchAll(/<span[^>]*data-count="[^"]+"[^>]*>([^<]*)<\/span>/gi)];
  const zeroed = counters.filter((m) => /^[\s$€]*0(\.0+)?\s*(%|hrs|M|k)?$/i.test(m[1].trim()));
  if (!counters.length) fail('B3: no [data-count] elements found');
  else if (zeroed.length) fail(`B3: ${zeroed.length} counter(s) still ship a zero placeholder: ${zeroed.map((m) => m[0].slice(0, 60)).join(' | ')}`);
  else pass(`B3: all ${counters.length} counters ship their real value in the markup`);
}

/* =====================================================================
   C. HTML tag balance
   ===================================================================== */
const VOID = new Set([
  'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta',
  'param', 'source', 'track', 'wbr', 'path', 'circle', 'rect', 'line', 'polyline',
  'polygon', 'stop', 'use', 'ellipse'
]);
const OPTIONAL_CLOSE = new Set(['li', 'p', 'td', 'th', 'tr', 'option', 'dt', 'dd', 'thead', 'tbody', 'tfoot']);

/* Inline <script> bodies would confuse the tag scanner, so mask them. */
const maskedHtml = htmlNoComments.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, '<script></script>');

const stack = [];
const tagRe = /<(\/?)([a-zA-Z][a-zA-Z0-9-]*)((?:"[^"]*"|'[^']*'|[^>"'])*?)(\/?)>/g;
let tagErrors = 0;
let depth = 0;
let maxDepth = 0;
while ((m = tagRe.exec(maskedHtml)) !== null) {
  const closing = m[1] === '/';
  const name = m[2].toLowerCase();
  const selfClosed = m[4] === '/';
  if (VOID.has(name) || selfClosed) {
    if (closing) { fail(`C: void/self-closed tag </${name}> closed explicitly`); tagErrors++; }
    continue;
  }
  if (!closing) {
    stack.push({ name, index: m.index });
    depth++;
    maxDepth = Math.max(maxDepth, depth);
  } else {
    /* unwind optional-close tags */
    let idx = -1;
    for (let i = stack.length - 1; i >= 0; i--) {
      if (stack[i].name === name) { idx = i; break; }
    }
    if (idx === -1) {
      fail(`C: stray closing tag </${name}> at offset ${m.index}`);
      tagErrors++;
    } else {
      const dropped = stack.splice(idx);
      if (dropped.length > 1) {
        const unclosed = dropped.slice(1).map((d) => `<${d.name}>`);
        const soft = dropped.slice(1).every((d) => OPTIONAL_CLOSE.has(d.name));
        if (soft) warn(`C: implicitly closed ${unclosed.join(' ')} before </${name}> (valid HTML5)`);
        else { fail(`C: unclosed ${unclosed.join(' ')} before </${name}>`); tagErrors++; }
      }
      depth -= dropped.length;
    }
  }
}
if (stack.length) {
  fail(`C: unclosed tags at EOF: ${stack.map((s) => '<' + s.name + '>').join(', ')}` + tagErrors);
} else if (tagErrors === 0) {
  pass(`C: HTML tags balanced (max nesting depth ${maxDepth}, void/self-closing aware)`);
}

/* =====================================================================
   D. duplicate ids
   ===================================================================== */
const idCounts = {};
while ((m = idRe.exec(htmlNoComments)) !== null) idCounts[m[1]] = (idCounts[m[1]] || 0) + 1;
const dupes = Object.keys(idCounts).filter((k) => idCounts[k] > 1);
if (dupes.length) fail(`D: duplicate ids: ${dupes.join(', ')}`);
else pass(`D: ${Object.keys(idCounts).length} ids, all unique`);

/* =====================================================================
   E. CSS brace balance  (+ basic paren balance per declaration)
   ===================================================================== */
let braceDepth = 0;
let braceMin = 0;
let lineOfFirstNegative = null;
cssNoComments.split('\n').forEach((line, i) => {
  for (const ch of line) {
    if (ch === '{') braceDepth++;
    else if (ch === '}') {
      braceDepth--;
      if (braceDepth < 0 && lineOfFirstNegative === null) lineOfFirstNegative = i + 1;
    }
  }
  braceMin = Math.min(braceMin, braceDepth);
});
if (braceDepth !== 0) fail(`E: CSS braces unbalanced — final depth ${braceDepth}`);
else if (braceMin < 0) fail(`E: CSS has an extra } near line ${lineOfFirstNegative}`);
else pass('E: CSS braces balanced');

const parenOpen = (cssNoComments.match(/\(/g) || []).length;
const parenClose = (cssNoComments.match(/\)/g) || []).length;
if (parenOpen !== parenClose) fail(`E: CSS parentheses unbalanced (${parenOpen} open vs ${parenClose} close)`);
else pass('E: CSS parentheses balanced');

/* =====================================================================
   F. custom properties: every referenced token is defined
   ===================================================================== */
/* A custom property is `--name:` NOT preceded by an identifier char, which also
   excludes BEM modifiers such as `.price-card--featured`. */
const defined = new Set();
const defRe = /(^|[^a-zA-Z0-9_-])(--[a-zA-Z0-9-]+)\s*:/gm;
while ((m = defRe.exec(cssNoComments)) !== null) defined.add(m[2]);

/* tokens set from JS count as defined too */
const jsDefined = new Set();
const jsDefRe = /setProperty\(\s*'(--[a-zA-Z0-9-]+)'/g;
while ((m = jsDefRe.exec(js)) !== null) jsDefined.add(m[1]);

/* tokens *read* from JS via cssVar('--x') also count as used */
const jsUsed = new Set();
const jsVarRe = /cssVar\(\s*'(--[a-zA-Z0-9-]+)'/g;
while ((m = jsVarRe.exec(js)) !== null) jsUsed.add(m[1]);

const used = new Set(jsUsed);
const useRe = /var\(\s*(--[a-zA-Z0-9-]+)/g;
while ((m = useRe.exec(cssNoComments)) !== null) used.add(m[1]);

const undefinedTokens = [...used].filter((t) => !defined.has(t) && !jsDefined.has(t));
if (undefinedTokens.length) fail(`F: CSS custom properties used but never defined: ${undefinedTokens.join(', ')}`);
else pass(`F: ${defined.size} custom properties defined, all ${used.size} referenced tokens resolve`);

const unusedTokens = [...defined].filter((t) => !used.has(t));
if (unusedTokens.length) warn(`F: defined but unreferenced tokens (informational): ${unusedTokens.join(', ')}`);

/* =====================================================================
   G. ids referenced by app.js exist in the markup
   ===================================================================== */
const jsIds = new Set();
const jsIdRe = /(?:getElementById\(|querySelector\(\s*['"]#|\$\(\s*['"]#)([a-zA-Z][a-zA-Z0-9_-]*)/g;
while ((m = jsIdRe.exec(js)) !== null) jsIds.add(m[1]);
const missingIds = [...jsIds].filter((id) => !ids.has(id));
if (missingIds.length) fail(`G: app.js targets ids missing from index.html: ${missingIds.join(', ')}`);
else pass(`G: all ${jsIds.size} ids targeted by app.js exist in index.html`);

/* =====================================================================
   H. classes used by app.js exist in styles.css
   ===================================================================== */
const cssClasses = new Set();
const classDefRe = /\.(-?[a-zA-Z_][a-zA-Z0-9_-]*)/g;
while ((m = classDefRe.exec(cssNoComments)) !== null) cssClasses.add(m[1]);

const jsClasses = new Set();
const classUseRe = /(?:classList\.(?:add|remove|toggle)\(|className\s*=\s*|class:\s*)['"]([^'"]+)['"]/g;
while ((m = classUseRe.exec(js)) !== null) {
  m[1].split(/\s+/).filter(Boolean).forEach((c) => jsClasses.add(c));
}
/* classes only ever applied as CSS hooks by JS (state classes) */
const jsOnly = new Set(['is-visible', 'is-hover', 'is-active', 'is-open', 'is-stuck', 'is-low',
  'is-success', 'is-error', 'no-js', 'is-visible']);
const missingClasses = [...jsClasses].filter((c) => !cssClasses.has(c) && !jsOnly.has(c));
if (missingClasses.length) warn(`H: classes used by app.js with no CSS rule: ${missingClasses.join(', ')}`);
else pass(`H: all classes toggled by app.js are styled in styles.css`);

/* =====================================================================
   REPORT
   ===================================================================== */
console.log('\n=== PASS ===');
passes.forEach((p) => console.log('  [ok]   ' + p));
if (warnings.length) {
  console.log('\n=== WARN ===');
  warnings.forEach((w) => console.log('  [warn] ' + w));
}
if (failures.length) {
  console.log('\n=== FAIL ===');
  failures.forEach((f) => console.log('  [FAIL] ' + f));
  console.log(`\n${failures.length} check(s) failed.`);
  process.exit(1);
}
console.log('\nAll static checks passed.');
