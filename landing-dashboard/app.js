/* =====================================================================
   Stocklight — landing page interactions + hand-rolled SVG charts
   Vanilla JS. No frameworks, no libraries, no network calls.
   ---------------------------------------------------------------------
   Modules
     1.  Data
     2.  Helpers
     3.  Theme toggle
     4.  Mobile navigation
     5.  Scroll reveal
     6.  Number counters
     7.  Charts (area/line + bar, with tooltips)
     8.  Dashboard filters, table, leaderboard
     9.  Pricing toggle
     10. Misc (header state, CTA form, year)
   ===================================================================== */
(function () {
  'use strict';

  var SVG_NS = 'http://www.w3.org/2000/svg';
  var root = document.documentElement;
  var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ===================================================================
     1. DATA  (all numbers below are invented demo figures)
     =================================================================== */

  /* Daily series, last 30 days (oldest -> newest). */
  var DAILY = [
    { d: 'Mar 01', revenue: 9800,  units: 402, orders: 168 },
    { d: 'Mar 02', revenue: 10400, units: 431, orders: 181 },
    { d: 'Mar 03', revenue: 12100, units: 498, orders: 209 },
    { d: 'Mar 04', revenue: 11600, units: 470, orders: 196 },
    { d: 'Mar 05', revenue: 9900,  units: 415, orders: 172 },
    { d: 'Mar 06', revenue: 13100, units: 540, orders: 228 },
    { d: 'Mar 07', revenue: 14800, units: 611, orders: 258 },
    { d: 'Mar 08', revenue: 13600, units: 559, orders: 236 },
    { d: 'Mar 09', revenue: 11200, units: 458, orders: 194 },
    { d: 'Mar 10', revenue: 11900, units: 487, orders: 205 },
    { d: 'Mar 11', revenue: 15300, units: 630, orders: 266 },
    { d: 'Mar 12', revenue: 16100, units: 668, orders: 282 },
    { d: 'Mar 13', revenue: 14200, units: 587, orders: 248 },
    { d: 'Mar 14', revenue: 12700, units: 522, orders: 221 },
    { d: 'Mar 15', revenue: 13400, units: 551, orders: 233 },
    { d: 'Mar 16', revenue: 15900, units: 655, orders: 277 },
    { d: 'Mar 17', revenue: 17200, units: 711, orders: 300 },
    { d: 'Mar 18', revenue: 16500, units: 682, orders: 288 },
    { d: 'Mar 19', revenue: 14300, units: 590, orders: 249 },
    { d: 'Mar 20', revenue: 15100, units: 624, orders: 264 },
    { d: 'Mar 21', revenue: 13300, units: 549, orders: 232 },
    { d: 'Mar 22', revenue: 12800, units: 528, orders: 223 },
    { d: 'Mar 23', revenue: 14100, units: 582, orders: 246 },
    { d: 'Mar 24', revenue: 16200, units: 669, orders: 283 },
    { d: 'Mar 25', revenue: 17800, units: 736, orders: 311 },
    { d: 'Mar 26', revenue: 18600, units: 769, orders: 325 },
    { d: 'Mar 27', revenue: 16900, units: 698, orders: 295 },
    { d: 'Mar 28', revenue: 15400, units: 636, orders: 269 },
    { d: 'Mar 29', revenue: 14700, units: 607, orders: 257 },
    { d: 'Mar 30', revenue: 16050, units: 663, orders: 281 }
  ];

  /* Weekly series, last 90 days (13 weeks). */
  var WEEKLY = [
    { d: 'W1',  revenue: 84200,  units: 3480, orders: 1470 },
    { d: 'W2',  revenue: 88900,  units: 3672, orders: 1551 },
    { d: 'W3',  revenue: 92600,  units: 3824, orders: 1616 },
    { d: 'W4',  revenue: 90100,  units: 3720, orders: 1572 },
    { d: 'W5',  revenue: 97400,  units: 4021, orders: 1699 },
    { d: 'W6',  revenue: 101800, units: 4203, orders: 1776 },
    { d: 'W7',  revenue: 105600, units: 4360, orders: 1843 },
    { d: 'W8',  revenue: 99800,  units: 4120, orders: 1741 },
    { d: 'W9',  revenue: 108200, units: 4467, orders: 1888 },
    { d: 'W10', revenue: 114900, units: 4743, orders: 2005 },
    { d: 'W11', revenue: 111300, units: 4595, orders: 1942 },
    { d: 'W12', revenue: 118700, units: 4900, orders: 2071 },
    { d: 'W13', revenue: 124400, units: 5135, orders: 2171 }
  ];

  /* Monthly series, last 12 months. */
  var MONTHLY = [
    { d: 'Apr',  revenue: 286000,  units: 11800, orders: 4990 },
    { d: 'May',  revenue: 302400,  units: 12480, orders: 5276 },
    { d: 'Jun',  revenue: 318900,  units: 13160, orders: 5564 },
    { d: 'Jul',  revenue: 297500,  units: 12280, orders: 5192 },
    { d: 'Aug',  revenue: 324100,  units: 13380, orders: 5656 },
    { d: 'Sep',  revenue: 348700,  units: 14390, orders: 6083 },
    { d: 'Oct',  revenue: 371200,  units: 15320, orders: 6477 },
    { d: 'Nov',  revenue: 429800,  units: 17740, orders: 7501 },
    { d: 'Dec',  revenue: 462300,  units: 19080, orders: 8067 },
    { d: 'Jan',  revenue: 361400,  units: 14920, orders: 6308 },
    { d: 'Feb',  revenue: 378900,  units: 15640, orders: 6612 },
    { d: 'Mar',  revenue: 412880,  units: 17040, orders: 7203 }
  ];

  /* Per-channel multiplier + KPI deltas + warehouse mix. */
  var CHANNELS = {
    all: {
      label: 'All channels',
      short: 'all channels',
      revenue: 1,
      units: 1,
      orders: 1,
      kpi: [
        { delta: '18.4% vs prev.', dir: 'up' },
        { delta: '11.2% vs prev.', dir: 'up' },
        { delta: '4.6 pts vs prev.', dir: 'up' },
        { delta: '9 fewer than prev.', dir: 'down' }
      ],
      share: [0.44, 0.34, 0.22]
    },
    dtc: {
      label: 'DTC store',
      short: 'DTC store',
      revenue: 0.46,
      units: 0.42,
      orders: 0.48,
      kpi: [
        { delta: '22.7% vs prev.', dir: 'up' },
        { delta: '15.4% vs prev.', dir: 'up' },
        { delta: '6.1 pts vs prev.', dir: 'up' },
        { delta: '2 fewer than prev.', dir: 'down' }
      ],
      share: [0.52, 0.3, 0.18]
    },
    marketplace: {
      label: 'Marketplace',
      short: 'marketplace',
      revenue: 0.34,
      units: 0.38,
      orders: 0.33,
      kpi: [
        { delta: '12.1% vs prev.', dir: 'up' },
        { delta: '9.8% vs prev.', dir: 'up' },
        { delta: '2.4 pts vs prev.', dir: 'up' },
        { delta: '6 fewer than prev.', dir: 'down' }
      ],
      share: [0.36, 0.4, 0.24]
    },
    retail: {
      label: 'Wholesale',
      short: 'wholesale',
      revenue: 0.2,
      units: 0.2,
      orders: 0.19,
      kpi: [
        { delta: '9.3% vs prev.', dir: 'up' },
        { delta: '4.1% vs prev.', dir: 'up' },
        { delta: '1.2 pts vs prev.', dir: 'up' },
        { delta: '1 fewer than prev.', dir: 'down' }
      ],
      share: [0.3, 0.35, 0.35]
    }
  };

  var WAREHOUSES = [
    { name: 'Newark, NJ', units: 7440, coverage: 41, capacity: 0.86 },
    { name: 'Reno, NV', units: 5120, coverage: 28, capacity: 0.74 },
    { name: 'Leipzig, DE', units: 3510, coverage: 22, capacity: 0.61 },
    { name: 'Toronto, CA', units: 2360, coverage: 12, capacity: 0.48 }
  ];

  var SKUS = [
    { name: 'Aurora Merino Tee', sku: 'AUR-TEE-M', channel: 'DTC store',   units: 1840, revenue: 73600, cover: 9,   status: 'Low',        swatch: '#6366f1' },
    { name: 'Ridgeline Parka',   sku: 'RDG-PRK-L', channel: 'Marketplace', units: 960,  revenue: 134400, cover: 46, status: 'Healthy',   swatch: '#0ea5e9' },
    { name: 'Cove Linen Shirt',  sku: 'COV-LIN-S', channel: 'DTC store',   units: 1420, revenue: 56800, cover: 27, status: 'Healthy',   swatch: '#14b8a6' },
    { name: 'Halden Wool Sock',  sku: 'HLD-SCK-3', channel: 'Wholesale',   units: 3120, revenue: 37440, cover: 0,  status: 'Stockout',  swatch: '#f59e0b' },
    { name: 'Meridian Tote',     sku: 'MRD-TOT-1', channel: 'Marketplace', units: 1180, revenue: 53100, cover: 18, status: 'Healthy',   swatch: '#8b5cf6' },
    { name: 'Fjord Rain Shell',  sku: 'FJD-RSH-M', channel: 'DTC store',   units: 640,  revenue: 83200, cover: 7,   status: 'Low',       swatch: '#38bdf8' },
    { name: 'Ember Down Vest',   sku: 'EMB-DWN-L', channel: 'Wholesale',   units: 520,  revenue: 46800, cover: 63, status: 'Overstock', swatch: '#f43f5e' },
    { name: 'Slate Chino Pant',  sku: 'SLT-CHN-32', channel: 'Marketplace',units: 1290, revenue: 45150, cover: 31, status: 'Healthy',   swatch: '#64748b' }
  ];

  var CHANNEL_COLORS = {
    'DTC store': '#6366f1',
    'Marketplace': '#0ea5e9',
    'Wholesale': '#f59e0b'
  };

  var STATUS_CLASS = {
    'Healthy': 'badge--ok',
    'Low': 'badge--warn',
    'Stockout': 'badge--bad',
    'Overstock': 'badge--warn'
  };

  var METRICS = {
    revenue: { label: 'Net revenue', money: true },
    units:   { label: 'Units shipped', money: false },
    orders:  { label: 'Orders', money: false }
  };

  /* ===================================================================
     2. HELPERS
     =================================================================== */
  function $(sel, ctx) { return (ctx || document).querySelector(sel); }
  function $$(sel, ctx) { return Array.prototype.slice.call((ctx || document).querySelectorAll(sel)); }

  function el(tag, attrs, children) {
    var node = document.createElementNS(SVG_NS, tag);
    if (attrs) {
      for (var k in attrs) {
        if (Object.prototype.hasOwnProperty.call(attrs, k) && attrs[k] !== null && attrs[k] !== undefined) {
          node.setAttribute(k, String(attrs[k]));
        }
      }
    }
    if (children) {
      children.forEach(function (c) {
        node.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
      });
    }
    return node;
  }

  function clamp(v, min, max) { return Math.min(Math.max(v, min), max); }

  function cssVar(name) {
    return getComputedStyle(root).getPropertyValue(name).trim();
  }

  function formatMoney(v, compact) {
    if (compact && Math.abs(v) >= 1000) {
      return '$' + (v / 1000).toFixed(v >= 100000 ? 0 : 1) + 'k';
    }
    return '$' + Math.round(v).toLocaleString('en-US');
  }

  function formatNumber(v, decimals) {
    var d = decimals || 0;
    return Number(v).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
  }

  function formatMetric(v, metric, compact) {
    if (metric === 'revenue') return formatMoney(v, compact);
    return formatNumber(v, 0);
  }

  /* Catmull-Rom -> cubic Bezier smoothing (no overshoot on x). */
  function smoothPath(pts, tension) {
    if (!pts.length) return '';
    if (pts.length < 3) {
      return 'M' + pts.map(function (p) { return p.x.toFixed(2) + ' ' + p.y.toFixed(2); }).join('L');
    }
    var t = tension === undefined ? 0.19 : tension;
    var d = 'M' + pts[0].x.toFixed(2) + ' ' + pts[0].y.toFixed(2);
    for (var i = 0; i < pts.length - 1; i++) {
      var p0 = pts[i - 1] || pts[i];
      var p1 = pts[i];
      var p2 = pts[i + 1];
      var p3 = pts[i + 2] || p2;
      var c1x = p1.x + (p2.x - p0.x) * t;
      var c1y = p1.y + (p2.y - p0.y) * t;
      var c2x = p2.x - (p3.x - p1.x) * t;
      var c2y = p2.y - (p3.y - p1.y) * t;
      d += 'C' + c1x.toFixed(2) + ' ' + c1y.toFixed(2) + ',' +
                 c2x.toFixed(2) + ' ' + c2y.toFixed(2) + ',' +
                 p2.x.toFixed(2) + ' ' + p2.y.toFixed(2);
    }
    return d;
  }

  /* Human-friendly axis ticks. */
  function niceTicks(min, max, count) {
    var span = max - min || 1;
    var raw = span / count;
    var mag = Math.pow(10, Math.floor(Math.log10(raw)));
    var norm = raw / mag;
    var step;
    if (norm <= 1) step = 1;
    else if (norm <= 2) step = 2;
    else if (norm <= 2.5) step = 2.5;
    else if (norm <= 5) step = 5;
    else step = 10;
    step *= mag;
    var niceMin = Math.floor(min / step) * step;
    var niceMax = Math.ceil(max / step) * step;
    var ticks = [];
    for (var v = niceMin; v <= niceMax + step * 0.001; v += step) ticks.push(v);
    return { min: niceMin, max: niceMax, ticks: ticks };
  }

  /* ===================================================================
     3. THEME TOGGLE
     =================================================================== */
  function initTheme() {
    var btn = $('#theme-toggle');
    if (!btn) return;

    function current() { return root.getAttribute('data-theme') === 'dark' ? 'dark' : 'light'; }

    function sync() {
      var isDark = current() === 'dark';
      btn.setAttribute('aria-pressed', String(isDark));
      btn.setAttribute('aria-label', isDark ? 'Switch to light theme' : 'Switch to dark theme');
      btn.setAttribute('title', isDark ? 'Switch to light theme' : 'Switch to dark theme');
    }

    btn.addEventListener('click', function () {
      var next = current() === 'dark' ? 'light' : 'dark';
      root.setAttribute('data-theme', next);
      try { localStorage.setItem('stocklight-theme', next); } catch (e) { /* private mode */ }
      sync();
      /* Charts read CSS custom properties — redraw so colours stay in sync. */
      window.requestAnimationFrame(function () {
        if (typeof redrawDashboard === 'function') redrawDashboard();
      });
    });

    /* Follow the OS if the visitor has never chosen explicitly. */
    var mq = window.matchMedia('(prefers-color-scheme: dark)');
    var onScheme = function (e) {
      var saved = null;
      try { saved = localStorage.getItem('stocklight-theme'); } catch (err) { saved = null; }
      if (saved) return;
      root.setAttribute('data-theme', e.matches ? 'dark' : 'light');
      sync();
      if (typeof redrawDashboard === 'function') redrawDashboard();
    };
    if (mq.addEventListener) mq.addEventListener('change', onScheme);
    else if (mq.addListener) mq.addListener(onScheme);

    sync();
  }

  /* ===================================================================
     4. MOBILE NAVIGATION
     =================================================================== */
  function initNav() {
    var toggle = $('#nav-toggle');
    var nav = $('#primary-nav');
    if (!toggle || !nav) return;

    var backdrop = document.createElement('div');
    backdrop.className = 'nav-backdrop';
    backdrop.setAttribute('aria-hidden', 'true');
    document.body.appendChild(backdrop);

    function isOpen() { return toggle.getAttribute('aria-expanded') === 'true'; }

    function open() {
      nav.classList.add('is-open');
      backdrop.classList.add('is-visible');
      toggle.setAttribute('aria-expanded', 'true');
      toggle.setAttribute('aria-label', 'Close navigation menu');
      document.body.style.overflow = 'hidden';
    }

    function close(returnFocus) {
      nav.classList.remove('is-open');
      backdrop.classList.remove('is-visible');
      toggle.setAttribute('aria-expanded', 'false');
      toggle.setAttribute('aria-label', 'Open navigation menu');
      document.body.style.overflow = '';
      if (returnFocus) toggle.focus();
    }

    toggle.addEventListener('click', function () { isOpen() ? close(false) : open(); });
    backdrop.addEventListener('click', function () { close(false); });

    $$('#primary-nav a').forEach(function (a) {
      a.addEventListener('click', function () { if (isOpen()) close(false); });
    });

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && isOpen()) close(true);
    });

    /* Reflowing back to desktop must never leave the panel stuck. */
    var mq = window.matchMedia('(min-width: 768px)');
    var reset = function (e) { if (e.matches) close(false); };
    if (mq.addEventListener) mq.addEventListener('change', reset);
    else if (mq.addListener) mq.addListener(reset);
  }

  /* ===================================================================
     5. SCROLL REVEAL
     =================================================================== */
  function initReveal() {
    var items = $$('[data-reveal]');
    if (!items.length) return;

    if (reduceMotion || !('IntersectionObserver' in window)) {
      items.forEach(function (n) { n.classList.add('is-visible'); });
      return;
    }

    /* Small stagger between siblings inside the same block. */
    var groups = new Map();
    items.forEach(function (n) {
      var parent = n.parentElement;
      var i = groups.get(parent) || 0;
      groups.set(parent, i + 1);
      n.style.setProperty('--reveal-delay', Math.min(i, 5) * 70 + 'ms');
    });

    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible');
          io.unobserve(entry.target);
        }
      });
    }, { rootMargin: '0px 0px -8% 0px', threshold: 0.12 });

    items.forEach(function (n) { io.observe(n); });
  }

  /* ===================================================================
     6. NUMBER COUNTERS
     =================================================================== */
  function animateNumber(node, options) {
    var target = options.value;
    var decimals = options.decimals || 0;
    var prefix = options.prefix || '';
    var suffix = options.suffix || '';
    var duration = options.duration || 1500;

    function paint(v) {
      node.textContent = prefix + formatNumber(v, decimals) + suffix;
    }

    if (reduceMotion) { paint(target); return; }

    var start = null;
    function frame(ts) {
      if (start === null) start = ts;
      var p = clamp((ts - start) / duration, 0, 1);
      var eased = 1 - Math.pow(1 - p, 3);
      paint(target * eased);
      if (p < 1) window.requestAnimationFrame(frame);
      else paint(target);
    }
    window.requestAnimationFrame(frame);
  }

  function initCounters() {
    var nodes = $$('[data-count]');
    if (!nodes.length) return;

    function run(node) {
      if (node.dataset.counted === 'true') return;
      node.dataset.counted = 'true';
      animateNumber(node, {
        value: parseFloat(node.dataset.count || '0'),
        decimals: parseInt(node.dataset.decimals || '0', 10),
        prefix: node.dataset.prefix || '',
        suffix: node.dataset.suffix || ''
      });
    }

    if (!('IntersectionObserver' in window)) { nodes.forEach(run); return; }

    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) { run(entry.target); io.unobserve(entry.target); }
      });
    }, { threshold: 0.4 });

    nodes.forEach(function (n) { io.observe(n); });
  }

  /* Re-arm a counter so a filter change animates again. */
  function recount(node, value, prefix, suffix) {
    if (!node) return;
    animateNumber(node, {
      value: value,
      prefix: prefix || node.dataset.prefix || '',
      suffix: suffix || node.dataset.suffix || '',
      duration: 700
    });
  }

  /* ===================================================================
     7. CHARTS
     =================================================================== */
  function makeDefs(uid, color, vertical) {
    var defs = el('defs');

    var grad = el('linearGradient', {
      id: uid + '-fill',
      x1: '0', y1: '0', x2: '0', y2: '1'
    });
    grad.appendChild(el('stop', { offset: '0%', 'stop-color': color, 'stop-opacity': '0.34' }));
    grad.appendChild(el('stop', { offset: '55%', 'stop-color': color, 'stop-opacity': '0.10' }));
    grad.appendChild(el('stop', { offset: '100%', 'stop-color': color, 'stop-opacity': '0' }));
    defs.appendChild(grad);

    if (vertical) {
      var barGrad = el('linearGradient', { id: uid + '-bar', x1: '0', y1: '0', x2: '0', y2: '1' });
      barGrad.appendChild(el('stop', { offset: '0%', 'stop-color': color, 'stop-opacity': '1' }));
      barGrad.appendChild(el('stop', { offset: '100%', 'stop-color': color, 'stop-opacity': '0.62' }));
      defs.appendChild(barGrad);
    }
    return defs;
  }

  /* --- area / line chart ------------------------------------------- */
  function buildAreaChart(host, config) {
    var series = config.series;
    var metric = config.metric;
    var width = 760;
    var height = 300;
    var pad = { top: 22, right: 18, bottom: 34, left: 56 };
    var innerW = width - pad.left - pad.right;
    var innerH = height - pad.top - pad.bottom;

    var values = series.map(function (p) { return p[metric]; });
    var tickInfo = niceTicks(Math.min.apply(null, values) * 0.92, Math.max.apply(null, values) * 1.04, 4);
    var yMin = tickInfo.min;
    var yMax = tickInfo.max;

    var uid = 'area-' + Math.random().toString(36).slice(2, 8);
    var color = cssVar('--series-1') || '#4f46e5';

    var svg = el('svg', {
      viewBox: '0 0 ' + width + ' ' + height,
      role: 'img',
      'aria-label': config.ariaLabel || 'Time series chart',
      preserveAspectRatio: 'xMidYMid meet'
    });
    svg.appendChild(makeDefs(uid, color, false));

    var xAt = function (i) {
      return pad.left + (series.length === 1 ? innerW / 2 : (innerW * i) / (series.length - 1));
    };
    var yAt = function (v) {
      var t = (v - yMin) / (yMax - yMin || 1);
      return pad.top + innerH - t * innerH;
    };

    /* gridlines + y axis labels */
    tickInfo.ticks.forEach(function (t) {
      var y = yAt(t);
      svg.appendChild(el('line', {
        x1: pad.left, y1: y.toFixed(1), x2: pad.left + innerW, y2: y.toFixed(1), class: 'grid-line'
      }));
      var label = el('text', {
        x: pad.left - 10, y: (y + 3.5).toFixed(1), 'text-anchor': 'end', class: 'axis-text'
      }, [formatMetric(t, metric, true)]);
      svg.appendChild(label);
    });

    /* x axis labels */
    var everyN = Math.max(1, Math.ceil(series.length / 7));
    series.forEach(function (p, i) {
      if (i % everyN !== 0 && i !== series.length - 1) return;
      svg.appendChild(el('text', {
        x: xAt(i).toFixed(1),
        y: height - 12,
        'text-anchor': i === 0 ? 'start' : (i === series.length - 1 ? 'end' : 'middle'),
        class: 'axis-text'
      }, [p.d]));
    });

    var pts = series.map(function (p, i) { return { x: xAt(i), y: yAt(p[metric]), data: p }; });
    var lineD = smoothPath(pts);
    var areaD = lineD + 'L' + pts[pts.length - 1].x.toFixed(2) + ' ' + (pad.top + innerH).toFixed(2) +
      'L' + pts[0].x.toFixed(2) + ' ' + (pad.top + innerH).toFixed(2) + 'Z';

    svg.appendChild(el('path', { d: areaD, fill: 'url(#' + uid + '-fill)', class: 'series-area' }));

    var line = el('path', { d: lineD, class: 'series-line', stroke: color });
    svg.appendChild(line);
    /* Animate the stroke drawing where the browser supports it. */
    try {
      var len = line.getTotalLength();
      if (len && isFinite(len)) {
        line.style.setProperty('--len', len.toFixed(0));
      }
    } catch (e) { /* getTotalLength is unavailable in a few engines */ }

    /* crosshair + tracker dot (moved by the hit layer) */
    var crosshair = el('line', {
      class: 'crosshair', y1: pad.top, y2: pad.top + innerH, x1: 0, x2: 0
    });
    var dot = el('circle', { class: 'hit-dot', r: 4.5, cx: 0, cy: 0, stroke: color });
    svg.appendChild(crosshair);
    svg.appendChild(dot);

    var hit = el('g', { class: 'hit-layer' });
    pts.forEach(function (p) {
      hit.appendChild(el('rect', {
        class: 'hit-rect',
        x: (p.x - innerW / (series.length * 2)).toFixed(2),
        y: pad.top,
        width: (innerW / series.length).toFixed(2),
        height: innerH,
        'data-index': pts.indexOf(p)
      }));
    });
    svg.appendChild(hit);

    host.innerHTML = '';
    host.appendChild(svg);

    return {
      svg: svg,
      points: pts,
      pad: pad,
      width: width,
      height: height,
      crosshair: crosshair,
      dot: dot,
      host: host
    };
  }

  /* --- bar chart ---------------------------------------------------- */
  function buildBarChart(host, config) {
    var rows = config.rows;
    var width = 480;
    var height = 300;
    var pad = { top: 30, right: 12, bottom: 44, left: 42 };
    var innerW = width - pad.left - pad.right;
    var innerH = height - pad.top - pad.bottom;

    var max = Math.max.apply(null, rows.map(function (r) { return r.units; })) * 1.12;
    var uid = 'bar-' + Math.random().toString(36).slice(2, 8);
    var color = cssVar('--series-2') || '#0ea5e9';

    var svg = el('svg', {
      viewBox: '0 0 ' + width + ' ' + height,
      role: 'img',
      'aria-label': config.ariaLabel || 'Bar chart of units shipped per warehouse',
      preserveAspectRatio: 'xMidYMid meet'
    });
    svg.appendChild(makeDefs(uid, color, true));

    /* gridlines */
    [0, 0.25, 0.5, 0.75, 1].forEach(function (t) {
      var y = pad.top + innerH - t * innerH;
      svg.appendChild(el('line', {
        x1: pad.left, y1: y.toFixed(1), x2: pad.left + innerW, y2: y.toFixed(1), class: 'grid-line'
      }));
      svg.appendChild(el('text', {
        x: pad.left - 8, y: (y + 3.5).toFixed(1), 'text-anchor': 'end', class: 'axis-text'
      }, [formatNumber(max * t, 0)]));
    });

    var slot = innerW / rows.length;
    var barW = Math.min(52, slot * 0.56);

    rows.forEach(function (row, i) {
      var h = Math.max((row.units / max) * innerH, 3);
      var x = pad.left + slot * i + (slot - barW) / 2;
      var y = pad.top + innerH - h;

      var rect = el('rect', {
        class: 'bar',
        x: x.toFixed(2),
        y: y.toFixed(2),
        width: barW.toFixed(2),
        height: h.toFixed(2),
        rx: Math.min(7, barW / 2),
        fill: 'url(#' + uid + '-bar)',
        tabindex: '0',
        role: 'img',
        'aria-label': row.name + ': ' + formatNumber(row.units) + ' units, ' + row.coverage + ' days of cover',
        'data-index': i
      });
      rect.style.animationDelay = (i * 90) + 'ms';
      svg.appendChild(rect);

      var valueLabel = el('text', {
        x: (x + barW / 2).toFixed(2),
        y: (y - 8).toFixed(2),
        'text-anchor': 'middle',
        class: 'bar-value',
        'data-index': i
      }, [formatNumber(row.units)]);
      svg.appendChild(valueLabel);

      /* warehouse name, wrapped onto two lines when it contains a comma */
      var parts = row.name.split(', ');
      var labelY = pad.top + innerH + 18;
      svg.appendChild(el('text', {
        x: (x + barW / 2).toFixed(2),
        y: labelY.toFixed(2),
        'text-anchor': 'middle',
        class: 'axis-text bar-label'
      }, [parts[0]]));
      if (parts[1]) {
        svg.appendChild(el('text', {
          x: (x + barW / 2).toFixed(2),
          y: (labelY + 12).toFixed(2),
          'text-anchor': 'middle',
          class: 'axis-text bar-label'
        }, [parts[1]]));
      }
    });

    svg.appendChild(el('line', {
      x1: pad.left, y1: pad.top + innerH, x2: pad.left + innerW, y2: pad.top + innerH, class: 'baseline'
    }));

    host.innerHTML = '';
    host.appendChild(svg);

    return { svg: svg, host: host, pad: pad, width: width, height: height };
  }

  /* --- tooltip plumbing -------------------------------------------- */
  function placeTooltip(tip, host, x, y) {
    var hostRect = host.getBoundingClientRect();
    var svg = host.querySelector('svg');
    if (!svg) return;
    var svgRect = svg.getBoundingClientRect();
    var scale = svgRect.width / (svg.viewBox.baseVal.width || svgRect.width);

    var px = (x * scale) + (svgRect.left - hostRect.left);
    var py = (y * scale) + (svgRect.top - hostRect.top);

    /* keep the bubble inside the panel */
    var half = tip.offsetWidth / 2 || 70;
    px = clamp(px, half + 4, hostRect.width - half - 4);
    py = Math.max(py, 44);

    tip.style.left = px + 'px';
    tip.style.top = py + 'px';
  }

  function showTooltip(tip, html) {
    tip.innerHTML = html;
    tip.classList.add('is-visible');
    tip.setAttribute('aria-hidden', 'false');
  }

  function hideTooltip(tip) {
    tip.classList.remove('is-visible');
    tip.setAttribute('aria-hidden', 'true');
  }

  /* ===================================================================
     8. DASHBOARD
     =================================================================== */
  var dashState = {
    range: '30',
    channel: 'all',
    metric: 'revenue',
    sortKey: 'revenue',
    sortDir: 'desc',
    sortedOnce: false
  };

  var areaRef = null;
  var barRef = null;

  function seriesFor(state, channelKey) {
    var base = state.range === '90' ? WEEKLY : (state.range === '365' ? MONTHLY : DAILY);
    var ch = CHANNELS[channelKey];
    return base.map(function (p) {
      return {
        d: p.d,
        revenue: Math.round(p.revenue * ch.revenue),
        units: Math.round(p.units * ch.units),
        orders: Math.round(p.orders * ch.orders)
      };
    });
  }

  function rangeLabel(range) {
    return range === '90' ? 'last 90 days' : (range === '365' ? 'last 12 months' : 'last 30 days');
  }

  function sumBy(series, metric) {
    return series.reduce(function (acc, p) { return acc + p[metric]; }, 0);
  }

  function renderKPIs(state) {
    var series = seriesFor(state, state.channel);
    var ch = CHANNELS[state.channel];
    var revenue = sumBy(series, 'revenue');
    var units = sumBy(series, 'units');
    var sellthrough = state.range === '365' ? 68 : (state.range === '90' ? 71 : 72);
    var stockouts = state.channel === 'all' ? 3 : (state.channel === 'dtc' ? 1 : 2);

    var revNode = $('#kpi-revenue');
    var unitsNode = $('#kpi-units');
    var stNode = $('#kpi-sellthrough');
    var soNode = $('#kpi-stockouts');

    if (revNode) {
      revNode.dataset.prefix = '$';
      recount(revNode, revenue, '$', '');
    }
    if (unitsNode) recount(unitsNode, units, '', '');
    if (stNode) recount(stNode, sellthrough, '', '%');
    if (soNode) recount(soNode, stockouts, '', '');

    [
      ['#kpi-revenue-delta', 0],
      ['#kpi-units-delta', 1],
      ['#kpi-sellthrough-delta', 2],
      ['#kpi-stockouts-delta', 3]
    ].forEach(function (pair) {
      var node = $(pair[0]);
      if (!node) return;
      var info = ch.kpi[pair[1]] || ch.kpi[0];
      node.classList.toggle('delta-up', info.dir === 'up');
      node.classList.toggle('delta-down', info.dir === 'down');
      var span = node.querySelector('span');
      if (span) span.textContent = info.delta;
    });
  }

  function renderAreaChart(state) {
    var host = $('#revenue-chart');
    var tip = $('#revenue-tooltip');
    if (!host) return;

    var series = seriesFor(state, state.channel);
    var metric = state.metric;

    areaRef = buildAreaChart(host, {
      series: series,
      metric: metric,
      ariaLabel: METRICS[metric].label + ' over the ' + rangeLabel(state.range) + ' for ' + CHANNELS[state.channel].label
    });

    var sub = $('#revenue-chart-sub');
    if (sub) sub.textContent = CHANNELS[state.channel].label + ' · ' + rangeLabel(state.range);

    /* hit layer interaction */
    var layer = areaRef.svg.querySelector('.hit-layer');
    if (layer && tip) {
      layer.addEventListener('mousemove', function (e) {
        /* walk up manually: Element.closest() is missing on older SVG engines */
        var rect = e.target;
        while (rect && rect !== layer && !(rect.classList && rect.classList.contains('hit-rect'))) {
          rect = rect.parentNode;
        }
        if (!rect || rect === layer) return;
        var idx = parseInt(rect.getAttribute('data-index'), 10);
        var point = areaRef.points[idx];
        if (!point) return;

        areaRef.crosshair.setAttribute('x1', point.x.toFixed(1));
        areaRef.crosshair.setAttribute('x2', point.x.toFixed(1));
        areaRef.dot.setAttribute('cx', point.x.toFixed(1));
        areaRef.dot.setAttribute('cy', point.y.toFixed(1));
        areaRef.svg.classList.add('is-hover');

        var p = point.data;
        showTooltip(tip,
          '<p class="tooltip-title">' + p.d + '</p>' +
          '<p class="tooltip-row"><span class="tooltip-key"><i style="color:' + (cssVar('--series-1') || '#4f46e5') + '"></i>' +
          METRICS[metric].label + '</span><span class="tooltip-value">' +
          formatMetric(p[metric], metric, false) + '</span></p>' +
          '<p class="tooltip-row"><span>Orders</span><span class="tooltip-value">' + formatNumber(p.orders) + '</span></p>'
        );
        placeTooltip(tip, host, point.x, point.y);
      });

      layer.addEventListener('mouseleave', function () {
        areaRef.svg.classList.remove('is-hover');
        hideTooltip(tip);
      });
    }

    /* keyboard + pointer tooltips on the tracker dots (focus ring per point) */
    var focusIndex = 0;
    areaRef.svg.setAttribute('tabindex', '0');
    areaRef.svg.addEventListener('focus', function () {
      if (!tip) return;
      var point = areaRef.points[focusIndex];
      areaRef.crosshair.setAttribute('x1', point.x.toFixed(1));
      areaRef.crosshair.setAttribute('x2', point.x.toFixed(1));
      areaRef.dot.setAttribute('cx', point.x.toFixed(1));
      areaRef.dot.setAttribute('cy', point.y.toFixed(1));
      areaRef.svg.classList.add('is-hover');
      showTooltip(tip,
        '<p class="tooltip-title">' + point.data.d + '</p>' +
        '<p class="tooltip-row"><span>' + METRICS[metric].label + '</span><span class="tooltip-value">' +
        formatMetric(point.data[metric], metric, false) + '</span></p>'
      );
      placeTooltip(tip, host, point.x, point.y);
    });
    areaRef.svg.addEventListener('blur', function () {
      if (areaRef) areaRef.svg.classList.remove('is-hover');
      if (tip) hideTooltip(tip);
    });
    areaRef.svg.addEventListener('keydown', function (e) {
      var last = areaRef.points.length - 1;
      if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
        focusIndex = clamp(focusIndex + (e.key === 'ArrowRight' ? 1 : -1), 0, last);
        var point = areaRef.points[focusIndex];
        areaRef.crosshair.setAttribute('x1', point.x.toFixed(1));
        areaRef.crosshair.setAttribute('x2', point.x.toFixed(1));
        areaRef.dot.setAttribute('cx', point.x.toFixed(1));
        areaRef.dot.setAttribute('cy', point.y.toFixed(1));
        areaRef.svg.classList.add('is-hover');
        if (tip) {
          showTooltip(tip,
            '<p class="tooltip-title">' + point.data.d + '</p>' +
            '<p class="tooltip-row"><span>' + METRICS[metric].label + '</span><span class="tooltip-value">' +
            formatMetric(point.data[metric], metric, false) + '</span></p>'
          );
          placeTooltip(tip, host, point.x, point.y);
        }
        e.preventDefault();
      }
    });
  }

  function renderBarChart(state) {
    var host = $('#warehouse-chart');
    var tip = $('#warehouse-tooltip');
    if (!host) return;

    var ch = CHANNELS[state.channel];
    /* Redistribute the warehouse mix per channel so the filter visibly moves bars. */
    var rows = WAREHOUSES.map(function (w, i) {
      var mix = ch.share[i] || 0.2;
      return {
        name: w.name,
        units: Math.round(w.units * (state.range === '90' ? 3.05 : (state.range === '365' ? 12.2 : 1)) * (mix * 2.3)),
        coverage: w.coverage
      };
    });

    barRef = buildBarChart(host, { rows: rows });

    var sub = $('#warehouse-sub');
    if (sub) sub.textContent = CHANNELS[state.channel].label + ' · ' + rangeLabel(state.range);

    if (!tip) return;

    barRef.svg.querySelectorAll('.bar').forEach(function (bar) {
      var idx = parseInt(bar.getAttribute('data-index'), 10);
      var row = rows[idx];

      function activate() {
        barRef.svg.classList.add('is-hover');
        barRef.svg.querySelectorAll('.bar').forEach(function (b) { b.classList.remove('is-active'); });
        barRef.svg.querySelectorAll('.bar-value').forEach(function (v) { v.classList.remove('is-visible'); });
        bar.classList.add('is-active');
        var label = barRef.svg.querySelector('.bar-value[data-index="' + idx + '"]');
        if (label) label.classList.add('is-visible');

        var x = parseFloat(bar.getAttribute('x')) + parseFloat(bar.getAttribute('width')) / 2;
        var y = parseFloat(bar.getAttribute('y'));
        showTooltip(tip,
          '<p class="tooltip-title">' + row.name + '</p>' +
          '<p class="tooltip-row"><span class="tooltip-key"><i style="color:' + (cssVar('--series-2') || '#0ea5e9') + '"></i>Units</span>' +
          '<span class="tooltip-value">' + formatNumber(row.units) + '</span></p>' +
          '<p class="tooltip-row"><span>Days cover</span><span class="tooltip-value">' + row.coverage + '</span></p>'
        );
        placeTooltip(tip, host, x, y);
      }

      function deactivate() {
        barRef.svg.classList.remove('is-hover');
        bar.classList.remove('is-active');
        var label = barRef.svg.querySelector('.bar-value[data-index="' + idx + '"]');
        if (label) label.classList.remove('is-visible');
        hideTooltip(tip);
      }

      bar.addEventListener('mouseenter', activate);
      bar.addEventListener('mouseleave', deactivate);
      bar.addEventListener('focus', activate);
      bar.addEventListener('blur', deactivate);
    });
  }

  function renderLeaderboard(state) {
    var list = $('#leader-list');
    if (!list) return;

    var ch = CHANNELS[state.channel];
    var rows = WAREHOUSES.map(function (w, i) {
      return {
        name: w.name,
        units: Math.round(w.units * (ch.share[i] || 0.2) * 2.3),
        coverage: w.coverage
      };
    }).sort(function (a, b) { return b.units - a.units; });

    var max = rows[0] ? rows[0].units : 1;

    list.innerHTML = '';
    rows.forEach(function (row) {
      var li = document.createElement('li');
      li.className = 'leader-item';

      var top = document.createElement('div');
      top.className = 'leader-top';

      var name = document.createElement('span');
      name.className = 'leader-name';
      name.textContent = row.name;

      var value = document.createElement('span');
      value.className = 'leader-value';
      value.textContent = formatNumber(row.units) + ' u · ' + row.coverage + 'd cover';

      top.appendChild(name);
      top.appendChild(value);

      var track = document.createElement('div');
      track.className = 'leader-track';
      var fill = document.createElement('span');
      fill.className = 'leader-fill' + (row.coverage <= 20 ? ' is-low' : '');
      track.appendChild(fill);

      li.appendChild(top);
      li.appendChild(track);
      list.appendChild(li);

      /* animate the fill in on the next frame */
      window.requestAnimationFrame(function () {
        fill.style.width = Math.round((row.units / max) * 100) + '%';
      });
    });
  }

  function renderTable(state) {
    var tbody = $('#sku-tbody');
    if (!tbody) return;

    var rows = SKUS.filter(function (s) {
      if (state.channel === 'all') return true;
      return s.channel === CHANNELS[state.channel].label;
    });

    var dir = state.sortDir === 'asc' ? 1 : -1;
    rows = rows.slice().sort(function (a, b) {
      var av = a[state.sortKey];
      var bv = b[state.sortKey];
      if (typeof av === 'string') {
        return av.localeCompare(bv) * dir;
      }
      return (av - bv) * dir;
    });

    tbody.innerHTML = '';
    rows.forEach(function (row) {
      var tr = document.createElement('tr');

      var tdName = document.createElement('td');
      var wrap = document.createElement('span');
      wrap.className = 'sku-name';
      var swatch = document.createElement('span');
      swatch.className = 'sku-swatch';
      swatch.style.background = row.swatch;
      var textWrap = document.createElement('span');
      var strong = document.createElement('strong');
      strong.textContent = row.name;
      var code = document.createElement('span');
      code.className = 'sku-sku';
      code.textContent = row.sku;
      textWrap.appendChild(strong);
      textWrap.appendChild(code);
      wrap.appendChild(swatch);
      wrap.appendChild(textWrap);
      tdName.appendChild(wrap);

      var tdChannel = document.createElement('td');
      var chKey = document.createElement('span');
      chKey.className = 'tooltip-key';
      var dot = document.createElement('i');
      dot.style.background = CHANNEL_COLORS[row.channel] || 'currentColor';
      var chText = document.createElement('span');
      chText.textContent = row.channel;
      chKey.appendChild(dot);
      chKey.appendChild(chText);
      tdChannel.appendChild(chKey);

      var tdUnits = document.createElement('td');
      tdUnits.className = 'num';
      tdUnits.textContent = formatNumber(row.units);

      var tdRevenue = document.createElement('td');
      tdRevenue.className = 'num';
      tdRevenue.textContent = formatMoney(row.revenue, false);

      var tdCover = document.createElement('td');
      tdCover.className = 'num';
      tdCover.textContent = row.cover === 0 ? '—' : row.cover + 'd';

      var tdStatus = document.createElement('td');
      var badge = document.createElement('span');
      badge.className = 'badge ' + (STATUS_CLASS[row.status] || 'badge--ok');
      badge.textContent = row.status;
      tdStatus.appendChild(badge);

      tr.appendChild(tdName);
      tr.appendChild(tdChannel);
      tr.appendChild(tdUnits);
      tr.appendChild(tdRevenue);
      tr.appendChild(tdCover);
      tr.appendChild(tdStatus);
      tbody.appendChild(tr);
    });

    if (!rows.length) {
      var empty = document.createElement('tr');
      var cell = document.createElement('td');
      cell.colSpan = 6;
      cell.textContent = 'No SKUs for this channel in the demo data.';
      empty.appendChild(cell);
      tbody.appendChild(empty);
    }

    var count = $('#row-count');
    if (count) count.textContent = rows.length + (rows.length === 1 ? ' SKU' : ' SKUs');
  }

  function updateSortIndicators() {
    $$('.sort-btn').forEach(function (btn) {
      var th = btn.closest('th');
      if (!th) return;
      if (btn.dataset.key === dashState.sortKey) {
        th.setAttribute('aria-sort', dashState.sortDir === 'asc' ? 'ascending' : 'descending');
        btn.setAttribute('aria-sort', dashState.sortDir === 'asc' ? 'ascending' : 'descending');
      } else {
        th.removeAttribute('aria-sort');
        btn.removeAttribute('aria-sort');
      }
    });
  }

  function updateStatus(state) {
    var status = $('#dash-status');
    if (!status) return;
    status.textContent = 'Showing ' + CHANNELS[state.channel].label + ', ' +
      rangeLabel(state.range) + ', sorted by ' + state.sortKey + ' ' + state.sortDir + '.';
  }

  function redrawDashboard() {
    renderKPIs(dashState);
    renderAreaChart(dashState);
    renderBarChart(dashState);
    renderLeaderboard(dashState);
    renderTable(dashState);
    updateStatus(dashState);
  }

  function initDashboard() {
    if (!$('#revenue-chart')) return;

    /* channel tabs */
    var tabs = $$('.segmented [role="tab"]');
    tabs.forEach(function (tab, i) {
      tab.addEventListener('click', function () {
        tabs.forEach(function (t) {
          t.classList.remove('is-active');
          t.setAttribute('aria-selected', 'false');
          t.tabIndex = -1;
        });
        tab.classList.add('is-active');
        tab.setAttribute('aria-selected', 'true');
        tab.tabIndex = 0;
        dashState.channel = tab.dataset.channel;
        var panel = $('#dash-panel');
        if (panel) panel.setAttribute('aria-labelledby', tab.id);
        redrawDashboard();
      });

      tab.addEventListener('keydown', function (e) {
        var keys = ['ArrowRight', 'ArrowLeft', 'Home', 'End'];
        if (keys.indexOf(e.key) === -1) return;
        e.preventDefault();
        var next = i;
        if (e.key === 'ArrowRight') next = (i + 1) % tabs.length;
        if (e.key === 'ArrowLeft') next = (i - 1 + tabs.length) % tabs.length;
        if (e.key === 'Home') next = 0;
        if (e.key === 'End') next = tabs.length - 1;
        tabs[next].focus();
        tabs[next].click();
      });
    });

    /* range buttons */
    $$('[data-range]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        $$('[data-range]').forEach(function (b) {
          b.classList.remove('is-active');
          b.setAttribute('aria-pressed', 'false');
        });
        btn.classList.add('is-active');
        btn.setAttribute('aria-pressed', 'true');
        dashState.range = btn.dataset.range;
        redrawDashboard();
      });
    });

    /* metric select */
    var metricSelect = $('#metric-select');
    if (metricSelect) {
      metricSelect.addEventListener('change', function () {
        dashState.metric = metricSelect.value;
        renderAreaChart(dashState);
        updateStatus(dashState);
      });
    }

    /* sortable table headers */
    $$('.sort-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var key = btn.dataset.key;
        if (dashState.sortKey === key) {
          dashState.sortDir = dashState.sortDir === 'asc' ? 'desc' : 'asc';
        } else {
          dashState.sortKey = key;
          dashState.sortDir = btn.dataset.type === 'number' ? 'desc' : 'asc';
        }
        updateSortIndicators();
        renderTable(dashState);
        updateStatus(dashState);
      });
    });

    redrawDashboard();
    updateSortIndicators();

    /* redraw on resize (debounced) so tooltips keep landing in the right place */
    var t = null;
    window.addEventListener('resize', function () {
      window.clearTimeout(t);
      t = window.setTimeout(function () { redrawDashboard(); }, 220);
    });

    /* redraw once fonts/layout settle, keeps the first paint honest */
    if (document.fonts && document.fonts.ready) {
      document.fonts.ready.then(function () { redrawDashboard(); });
    }
  }

  /* ===================================================================
     9. HERO MINI CHART
     =================================================================== */
  function initHeroChart() {
    var host = $('#hero-chart');
    if (!host) return;

    var series = DAILY.map(function (p) {
      return { d: p.d, revenue: p.revenue, units: p.units, orders: p.orders };
    });

    var width = 520;
    var height = 150;
    var pad = { top: 12, right: 8, bottom: 8, left: 8 };
    var values = series.map(function (p) { return p.revenue; });
    var min = Math.min.apply(null, values) * 0.9;
    var max = Math.max.apply(null, values) * 1.05;
    var color = cssVar('--series-1') || '#4f46e5';
    var innerW = width - pad.left - pad.right;
    var innerH = height - pad.top - pad.bottom;

    var svg = el('svg', {
      viewBox: '0 0 ' + width + ' ' + height,
      role: 'img',
      'aria-label': 'Net revenue trending upward over the last 30 days',
      preserveAspectRatio: 'none'
    });
    svg.appendChild(makeDefs('hero', color, false));

    var pts = series.map(function (p, i) {
      return {
        x: pad.left + (innerW * i) / (series.length - 1),
        y: pad.top + innerH - ((p.revenue - min) / (max - min)) * innerH
      };
    });

    var lineD = smoothPath(pts);
    var areaD = lineD + 'L' + pts[pts.length - 1].x.toFixed(2) + ' ' + height +
      'L' + pts[0].x.toFixed(2) + ' ' + height + 'Z';

    svg.appendChild(el('path', { d: areaD, fill: 'url(#hero-fill)', class: 'series-area' }));
    var line = el('path', { d: lineD, class: 'series-line', stroke: color });
    svg.appendChild(line);
    try {
      var len = line.getTotalLength();
      if (len && isFinite(len)) line.style.setProperty('--len', len.toFixed(0));
    } catch (e) { /* ignore */ }

    var last = pts[pts.length - 1];
    svg.appendChild(el('circle', {
      cx: last.x.toFixed(1), cy: last.y.toFixed(1), r: 4.5,
      fill: color, stroke: cssVar('--bg-dash') || '#fff', 'stroke-width': 3
    }));

    host.innerHTML = '';
    host.appendChild(svg);
  }

  /* ===================================================================
     10. PRICING TOGGLE
     =================================================================== */
  function initPricing() {
    var monthly = $('#bill-monthly');
    var annual = $('#bill-annual');
    if (!monthly || !annual) return;

    function apply(mode) {
      var isAnnual = mode === 'annual';
      monthly.classList.toggle('is-active', !isAnnual);
      annual.classList.toggle('is-active', isAnnual);
      monthly.setAttribute('aria-pressed', String(!isAnnual));
      annual.setAttribute('aria-pressed', String(isAnnual));

      $$('.price-value').forEach(function (node) {
        var value = isAnnual ? node.dataset.annual : node.dataset.monthly;
        node.textContent = value;
      });
      $$('[data-billing-note]').forEach(function (node) {
        node.textContent = isAnnual ? 'per month, billed annually' : 'billed monthly';
      });
    }

    monthly.addEventListener('click', function () { apply('monthly'); });
    annual.addEventListener('click', function () { apply('annual'); });
  }

  /* ===================================================================
     11. MISC
     =================================================================== */
  function initHeaderState() {
    var header = $('#site-header');
    if (!header) return;
    var ticking = false;

    function update() {
      header.classList.toggle('is-stuck', window.scrollY > 8);
      ticking = false;
    }

    window.addEventListener('scroll', function () {
      if (!ticking) {
        ticking = true;
        window.requestAnimationFrame(update);
      }
    }, { passive: true });

    update();
  }

  function initCtaForm() {
    var form = $('#cta-form');
    var note = $('#cta-note');
    var input = $('#cta-email');
    if (!form || !note) return;

    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var value = input ? input.value.trim() : '';
      var valid = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(value);

      note.classList.remove('is-success', 'is-error');
      if (value === '') {
        note.textContent = 'Add a work email to continue.';
        note.classList.add('is-error');
        if (input) input.focus();
        return;
      }
      if (!valid) {
        note.textContent = 'That email address looks incomplete.';
        note.classList.add('is-error');
        if (input) input.focus();
        return;
      }
      note.textContent = 'Thanks — a real product would email ' + value + ' a magic link now. This is a demo.';
      note.classList.add('is-success');
      form.reset();
    });
  }

  function initYear() {
    var y = $('#year');
    if (y) y.textContent = String(new Date().getFullYear());
  }

  /* ===================================================================
     BOOT
     =================================================================== */
  function boot() {
    /* mark JS as available for the no-js reveal fallback */
    root.classList.remove('no-js');

    initTheme();
    initNav();
    initHeaderState();
    initHeroChart();
    initDashboard();
    initPricing();
    initCounters();
    initReveal();
    initCtaForm();
    initYear();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
