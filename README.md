# Portfolio

This repository holds five self-contained projects. Each one runs with no third-party dependencies,
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

## 4. Support agent (tool calling with guardrails)

A customer-support agent that shows what "production-shaped" tool calling looks like:
intent → tool call → permission check → human handoff.

- Tools are declared with a parameter schema plus a permission predicate, so adding one is a dict
  entry rather than another branch in an ever-growing if-chain
- Ownership is verified **before** the tool runs, so the model cannot read someone else's order
- Refunds above ¥500 escalate to a human without asking the model to decide
- Handoff is a first-class outcome: unknown intent, tool failure and over-limit all hand off **and
  say why**, instead of pretending the request was handled
- Every decision leaves a trace (intent, matched keywords, tool, arguments, outcome, handoff reason)
- 6/6 scripted turns behave as expected, including two permission denials and one over-limit handoff

```bash
cd support-agent
python agent.py "我要退款 A1002，咖啡机坏了"
```

Stack: Python standard library. Intent matching is rule-based on purpose — it is explainable and
testable, and the point of the demo is orchestration and permissions, not another classifier.

## 5. Research agent (cited extraction)

Given a topic or a list of URLs, it extracts key points and writes a report where every bullet is
bound to the URL it came from.

- search → fetch → extract → compose, with per-stage timing and failures reported separately
- Each sentence keeps its source URL from extraction time, so a claim cannot appear without provenance
- Sources that failed to fetch are listed in a "Not fetched" section and the report is marked partial
- Chinese segmentation uses bigrams instead of a tokenizer dependency, so a sentence saying 「循环」
  still matches a query for 「事件循环」
- One real run: two pages, 0.3 s, 4 cited points, report written to disk

```bash
cd research-agent
python research.py --query "asyncio 协程 事件循环" --urls <url1> <url2> --out report.md
```

Stack: Python standard library (`urllib`, `html.parser`, `re`). Auto-search can be degraded by
Bing anti-bot behaviour; prefer the `--urls` mode when you need reproducible output.

## About

Software Engineering undergraduate and independent developer. I ship complete, runnable systems.

All five projects were run end-to-end before I published them here.

Contact: https://www.fiverr.com/sunny_dreamf
