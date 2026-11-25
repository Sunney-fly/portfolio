# Stocklight: SaaS landing page + analytics dashboard

A portfolio work sample for a web development / landing pages / dashboards service.
It is a single, self-contained marketing site for a fictional product ("Stocklight", an
inventory-intelligence SaaS) with a fully working analytics dashboard built into the page.

Open `index.html` in any browser. That is the whole install. No build step, no
`npm install`, no dev server, no network access required.

## What it is

A realistic SaaS marketing page, the kind of thing a buyer would commission, plus the
part most landing-page sellers cannot show: a live, interactive data dashboard.

The page follows the conversion structure a real product site would use:

| Section | Purpose |
| --- | --- |
| Sticky nav | Persistent navigation, theme toggle, primary CTA |
| Hero | Positioning headline, sub-copy, dual CTA, floating product preview |
| Social proof | Six invented customer wordmarks (inline SVG) |
| Features | Three-column benefit grid with inline SVG icons |
| Stats | Animated counters that count up on scroll |
| Dashboard | KPI cards, area/line chart, bar chart, sortable table, leaderboard |
| Pricing | Three tiers with a working monthly/annual toggle |
| Testimonials | One feature quote with metrics, plus three short quotes |
| FAQ | Native `<details>` accordions, styled |
| Final CTA | Email capture with client-side validation |
| Footer | Four-column footer with navigation |

Everything on the page is real, specific copy. There is no lorem ipsum anywhere.

## Design decisions

A real design system, not ad-hoc styling. All visual decisions live in CSS custom
properties on `:root`: colour ramps, semantic surfaces, text tones, five elevation
levels, seven radii, a 4 px spacing scale (`--sp-1` … `--sp-12`), a ten-step type scale,
and motion tokens (durations plus two easing curves). Change a token, and the change
propagates through the whole page.

Light and dark are equal citizens. Dark mode is not an inverted filter; it is a
second hand-tuned palette. The theme is applied by an inline script *before first paint*
so there is no flash of the wrong theme. Resolution order:

1. `localStorage['stocklight-theme']` if the visitor has chosen explicitly
2. otherwise the OS `prefers-color-scheme` value
3. the toggle writes to `localStorage` and takes over from then on

Mobile-first and genuinely fluid. Base styles target small screens; `560px`, `768px`
and `992px` breakpoints add columns. There is no horizontal scroll at 360 px. Wide
content such as the dashboard table scrolls inside its own `overflow-x` container rather
than pushing the page. The hamburger menu appears below 768 px, moves focus correctly,
sets `aria-expanded`, closes on `Escape` and on backdrop click, and resets itself if the
viewport crosses back to desktop while open.

Motion is tasteful and optional. Scroll reveals stagger slightly between siblings via
`IntersectionObserver`. The hero background is three blurred gradient "blobs" animated on
`transform` only (compositor-friendly, no layout thrash) behind a masked grid. Charts
draw themselves in, bars grow from the baseline, counters ease out on a cubic curve.
Every one of these is disabled under `prefers-reduced-motion: reduce`.

Charts are hand-drawn SVG. There is no chart library. `app.js` generates the markup
from plain data arrays, computes "nice" axis ticks, and smooths the line with a
Catmull-Rom to cubic Bézier conversion written by hand. Both the line chart and the bar
chart have hover tooltips with a crosshair; the bar chart also highlights and reveals the
value label of the hovered bar.

Accessibility is treated as visible craft. Skip link, semantic landmarks, one `<h1>`,
visible `:focus-visible` rings everywhere, `aria-pressed` on toggles, a proper
`role="tablist"` with arrow-key navigation for the channel filter, `aria-sort` on the
sortable table, an `aria-live` status region that announces every filter change, and
keyboard support on the charts (focus the chart, then use the left and right arrow keys to walk the data points).
The table carries a real `<caption>` and scoped headers.

Dependency-free by design. No CDN, no Google Fonts, no icon font, no external image.
The system font stack does the typography, all icons and customer wordmarks are inline
SVG, and every gradient, glow and grid pattern is CSS. The page therefore loads instantly
from `file://` and works fully offline, which also makes it safe to hand to a client with
no build pipeline.

## Files

```
index.html    semantic markup + all inline SVG artwork
styles.css    the design system + every component + both themes
app.js        theme, nav, reveal, counters, charts, filters, table
verify.js     static self-check harness (dev tool, not shipped to the page)
README.md     this file
```

`verify.js` is a development aid, not part of the site. Run it after editing:

```bash
node verify.js
```

## How to customise it for a client

### 1. Colour: the fast path

Edit the tokens at the top of `styles.css`. For a rebrand, these are the ones that matter:

```css
:root {
  --accent:        var(--indigo-600);   /* primary buttons, links, focus rings */
  --accent-hover:  var(--indigo-700);
  --accent-soft:   rgba(99, 102, 241, 0.10);
  --grad-brand:    linear-gradient(120deg, ...);  /* logo mark, flags, progress bars */
  --grad-text:     linear-gradient(100deg, ...);  /* gradient headline + stat numbers */
  --series-1:      #4f46e5;   /* line chart */
  --series-2:      #0ea5e9;   /* bar chart  */
  --series-3:      #f59e0b;   /* legend swatch */
}
```

Also update the dark-theme accent block (`--series-*`, `--accent`, `--grad-text`) in both
`:root[data-theme="dark"]` and the `@media (prefers-color-scheme: dark)` block so the
charts stay legible on dark backgrounds. To change the whole feel at once, rewrite the
`--indigo-*` / `--cyan-*` ramp anchors and every derived token follows.

### 2. Copy slots

Copy lives directly in `index.html` and is easy to find:

- Product name: search for `Stocklight` (nav brand, footer, `<title>`, meta description)
- Hero: `#hero-title`, `.hero-lede`, `.pill` (the announcement), `.hero-trust` bullets
- Features: the three `.feature-card` blocks: `<h3>`, `<p>`, and the two `.feature-list` bullets each
- Stats: `.stat` blocks; the animated value comes from `data-count` (plus optional
  `data-decimals`, `data-prefix`, `data-suffix`). Change the number in `data-count`, or
  the counter will animate to the old value.
- Pricing: `.price-card` blocks. Each `.price-value` carries both
  `data-monthly` and `data-annual`, so update both numbers.
- Testimonials: `.quote-feature` blockquote and the three `.testimonial` cards
- FAQ: each `<details>`; the first `<summary>` text is the question
- CTA + footer: `#cta` section and `.site-footer`

### 3. Data and charts

All dashboard data lives in plain arrays at the top of `app.js`:

- `DAILY`, `WEEKLY`, `MONTHLY`: the time series. Each entry is `{ d, revenue, units, orders }`.
- `CHANNELS`: the four channel tabs, each with multipliers, KPI deltas and a warehouse share.
- `WAREHOUSES`: bar chart rows and the leaderboard.
- `SKUS`: the table rows.
- `METRICS`: the metric dropdown options.

Replace those arrays with a client's real numbers and both charts, the KPI counters, the
table and the leaderboard update together. Nothing else needs to change.

### 4. Swapping the fake wordmarks

The customer logos are inline `<svg>` elements in `.logo-row`. Each is a simple `<text>`
plus a small geometric mark. Replace the `<text>` content and keep the `role="img"` +
`aria-label` pair accurate, or drop in the client's own SVG path data.

## What a client gets

- A page they can open and use immediately: two files plus markup, no dependencies,
  no build step, no hosting requirements beyond static file serving. It works from a USB
  stick, a `file://` path or any static host.
- Light and dark themes out of the box, with a toggle that remembers the visitor's
  choice and honours their OS preference on the first visit.
- Responsive down to 360 px with a working mobile menu, plus layouts that reflow
  properly rather than merely shrinking.
- A dashboard they can demonstrate: real charts drawn from data arrays, hover and
  keyboard tooltips, channel tabs, a time-range filter, a metric switcher and a sortable
  table. This is the section that sells the "dashboards" part of the service.
- Accessibility built in, not bolted on: keyboard navigable throughout, real ARIA
  semantics, visible focus states, and full `prefers-reduced-motion` support.
- A documented design system so future edits are token changes rather than CSS
  archaeology, documented in this README and self-evident in the file structure.

## Known limitations

- Visual appearance is unverified. This build was produced and checked without a
  browser, so the rendered result has never been seen. All checks are static (see below).
  Open `index.html` and review it visually before showing it to a buyer.
- The CTA form is deliberately non-functional; it validates the address client-side and
  says so in the page text. Wire it to a real endpoint (Formspree, a serverless function,
  or the client's ESP) before launch.
- Charts cover hover and keyboard interaction but not touch-drag scrubbing; on touch
  devices the tooltips respond to tap on the bars.
- All figures, testimonials, customer names and statistics are invented for demonstration.

## Appendix: what `verify.js` checks

Run `node verify.js`. It is a static harness, not a browser:

1. Local references: every `href`/`src` in `index.html` resolves to a real file
2. Anchors: every in-page `#fragment` has a matching `id`
3. Zero external references: no `http(s)://`, `//cdn`, `fonts.googleapis`, or
   `unpkg`/`jsdelivr`/`cdnjs` anywhere in the HTML, CSS or JS
4. HTML tag balance: full open/close stack check that understands void and
   self-closing elements, with HTML5 optional-close tags reported as warnings not errors
5. Duplicate ids: every `id` in the document is unique
6. CSS brace and parenthesis balance
7. Custom properties: every `var(--token)` referenced in CSS, and every
   `cssVar('--token')` read from JS, is actually defined
8. JS to DOM wiring: every `id` that `app.js` queries exists in the markup
9. JS to CSS wiring: every class `app.js` toggles has a rule in the stylesheet

`node --check app.js` is also used to prove the JavaScript parses.

---

## Round 2 — hardening pass (2026-10-25)

Four issues were found by rendering the page at 360 / 390 / 768 / 1024 / 1440 px
through the Chrome DevTools Protocol, in both the light and dark palettes, with and
without `prefers-reduced-motion`.

| # | Issue found | Fix |
| --- | --- | --- |
| 1 | Every counter was authored as `0`, so anything that never scrolls the stats row into view — no-JS, reduced-motion users, prerenderers, link-preview bots — read **0% / 0 hrs / $0M**. | The markup now ships the real figure (`38%`, `4.2 hrs`, `$1.9M`, `99.98%`); JS zeroes the glyphs only when it is actually going to animate them back up. |
| 2 | The floating "Reorder now" card sat at `top: 22%`, directly on top of the hero's headline metric (`$412,880`), and "Forecast synced" covered the Stockouts value. | Repositioned to `top: 44%` (over the chart, not the number) and `bottom: -1.7rem` (clear of the chip row). |
| 3 | Zero share metadata: no `og:` / `twitter:` tags, no `theme-color`, no `canonical`. A pasted link produced a bare URL. | Added Open Graph, Twitter card, `theme-color` (light/dark) and `canonical`, plus a 1200×630 `og.jpg`. |
| 4 | `verify.js` check B treated *any* absolute URL as a violation, which made legitimate share metadata impossible. | Rewrote B to ban external **assets** only (CDN, remote font, remote image) and to require share metadata to point at this deployment. Added **B2** (og:image exists in the bundle and is absolute) and **B3** (no counter ships a zero placeholder). |

Run the checks again with:

```bash
node verify.js
```

Expected: `All static checks passed.` — 12 checks, of which B2 and B3 are the new guards.

Known limitation, deliberately unchanged: counters below the fold still start at zero
and count up on scroll when motion is enabled. That is the intended effect; the markup
fallback only matters when the animation will not run.