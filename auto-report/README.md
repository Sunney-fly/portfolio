# auto-report

A configurable pipeline that collects product data, cleans it, and writes an analytical report. It
uses only the Python standard library, so there is nothing to install.

## Running it

```bash
python run.py
```

Output lands in `output/`:

| File | Contents |
| --- | --- |
| `report.csv` | the cleaned dataset |
| `report.html` | self-contained report with charts, opens offline |
| `summary.json` | machine-readable metrics and the data-quality log |
| `run.log` | the full run, stage by stage |

If `openpyxl` is installed, the script also writes `report.xlsx`. If it is not, it logs the skip and
carries on.

### Options

```bash
python run.py --offline          # skip the network, read fixtures/ only
python run.py --online           # require live HTTP, never fall back to fixtures
python run.py --config my.json   # use a different config file
python run.py --outdir out2      # override the output directory
python run.py --verbose          # include debug logging
python run.py --version
```

By default the fetcher probes the configured host first. If the host is unreachable it retries with
exponential backoff and then falls back to the local fixtures, logging which route it took. That is
why the pipeline runs offline out of the box.

## How it is put together

Six stages run in order, each one timed and logged.

configure reads `config.json`: the sources, the fields to extract, the cleaning rules and the output
settings.

fetch requests each source with a proper user agent, a timeout, retry with exponential backoff, and
rate limiting.

parse extracts records from the HTML using a custom `HTMLParser` subclass. It excludes inline
`<script>` and `<style>` blocks so that code is never read as data. In the demo dataset that skips
445 characters.

clean normalises prices and dates, drops duplicates and invalid records, and records a reason for
every row it drops. On the demo dataset it takes 40 raw records down to 32 valid ones, and logs all
8 drops against a specific cause.

analyse computes counts, price statistics, category and brand breakdowns, and a monthly trend.

report writes the CSV, the JSON summary and a self-contained HTML report. The charts in that report
are inline SVG generated in Python, so the file has no external requests and opens correctly with no
network connection.

## Configuration

Everything a client would need to change lives in `config.json`. The sources, the CSS selectors,
the cleaning thresholds and the output directory are all read from there, so adapting the pipeline
to a different site normally means editing that file rather than the code.

## Data quality

The cleaning stage writes a log that names every row it removed and why. Reasons include a missing
price, a price above the configured ceiling, an unparseable price, a missing SKU, and a duplicate
SKU. A modified z-score also flags price outliers for human review rather than silently deleting
them. On the demo dataset it flagged a $2,899 entry at z=5.9.

That log is the part of this pipeline worth reading first, because the summary numbers are only as
trustworthy as the rows that went into them.

## Layout

```
run.py                  entry point
config.json             sources, selectors, cleaning rules, output settings
autoreport/
  config.py             config loading and validation
  fetchers.py           HTTP with probe, retry, backoff, fixture fallback
  parsers.py            HTMLParser subclass producing raw records
  cleaning.py           normalisation, deduplication, quality log
  analysis.py           aggregate metrics
  charts.py             inline SVG chart generation
  reporting.py          CSV, JSON and HTML writers
  util.py               logging, timing and formatting helpers
fixtures/               local HTML used when the network is unavailable
output/                 generated reports
```
