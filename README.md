# Portfolio

This repository holds three self-contained projects. Each one runs with no third-party dependencies,
so you can clone a repository and run it without installing anything.

## 1. AI support assistant (retrieval-augmented generation)

A customer-support assistant that answers strictly from a supplied set of documents and cites the
source of every reply.

I wrote the retrieval layer myself: an inverted index with BM25 scoring (k1=1.5, b=0.75). That keeps
control over ranking, and it keeps answers inside the supplied documents.

- Indexes 6 documents into 31 retrievable chunks
- Every answer returns ranked source passages with document and section attribution
- When nothing clears the relevance threshold it says so, instead of inventing an answer
- Runs in live LLM mode or fully offline extractive mode, so it can be demonstrated with no
  credentials and no API spend
- 9-check self-test suite covering retrieval accuracy, grounding, and out-of-scope refusal

```bash
cd ai-support-bot
python app.py          # then open the printed localhost URL
python selftest.py     # optional: run the 9-check suite
```

Stack: Python standard library only (`http.server`, `urllib`).

## 2. Data collection and automated reporting pipeline

A configurable ETL pipeline that collects data, cleans it, and produces a self-contained analytical
report. Most of the work went into data quality.

- Six stages with per-stage timing: configure, fetch, parse, clean, analyse, report
- Custom HTML parser built on `HTMLParser`, with inline `<script>` and `<style>` excluded. It skipped
  445 characters of embedded code so that code is never read as data
- Cleaning reduced 40 raw records to 32 valid ones. All 8 dropped rows are logged against a specific
  reason: missing price, price above ceiling, unparseable price, missing SKU, duplicate SKU, and
  others. You can see what was removed and why
- A modified z-score flags price outliers for human review. It caught a $2,899 entry at z=5.9
- Charts are drawn as inline SVG from Python and written into a self-contained HTML report with no
  external requests, so it opens correctly offline in any browser
- Reachability probing, retry with exponential backoff, and automatic fallback to local fixtures when
  the source host is unavailable

```bash
cd auto-report
python run.py          # writes CSV + HTML report + JSON summary into output/
```

Stack: Python standard library. No pandas, no openpyxl. If `openpyxl` happens to be available the
script also emits an `.xlsx`; otherwise it logs the skip and carries on.

## 3. Responsive landing page and dashboard

A hand-built marketing page with an analytics dashboard.

- CSS design system with 97 custom properties covering colour tokens, spacing scale, type scale,
  radii and shadows
- Light and dark themes, stored in `localStorage` and defaulting to `prefers-color-scheme`
- The layout is mobile-first, with no horizontal scroll at a 360 px viewport width
- Keyboard navigation, visible `:focus-visible` states, correct ARIA, and `prefers-reduced-motion`
  support
- Line and bar charts drawn in hand-written SVG, with hover tooltips and a working data filter
- No CDN, no web fonts and no icon packs. Every icon is inline SVG, so the page makes no external
  requests

```bash
# no build step and no server required
open landing-dashboard/index.html
```

Stack: HTML5, CSS3, vanilla JavaScript.

## About

Software Engineering undergraduate and independent developer. I ship complete, runnable systems.

All three projects were run end-to-end before I published them here.

Contact: https://www.fiverr.com/sunny_dreamf
