"""Report layer, part 2: the deliverables.

Produces, in ``output/``:

* ``report.html``  — a self-contained responsive dashboard (inline CSS + inline SVG charts,
  zero external requests, zero JavaScript);
* ``report.csv``   — the cleaned dataset, UTF-8 with BOM so Excel opens it correctly;
* ``summary.json`` — the same metrics in machine-readable form, for APIs and BI tools;
* ``report.xlsx``  — written **only** when ``openpyxl`` happens to be importable.
"""

from __future__ import annotations

import csv
import json
import os
import platform
import sys

from html import escape

from . import __version__
from .charts import bar_chart, color_for, donut_chart, line_chart
from .cleaning import to_serialisable
from .util import integer, money, num, pct, utc_now_text

CSV_COLUMNS = ["sku", "title", "brand", "category", "currency", "price", "price_base",
               "base_currency", "listed", "listed_month", "rating", "rating_count",
               "stock_status", "stock_qty", "url", "source", "source_label", "source_mode",
               "completeness", "warnings"]

CURRENCY_SYMBOLS = {"USD": "$", "EUR": "\u20ac", "GBP": "\u00a3", "JPY": "\u00a5",
                    "INR": "\u20b9", "CAD": "C$", "AUD": "A$"}

STOCK_CLASS = {"in_stock": "ok", "low_stock": "warn", "out_of_stock": "bad",
               "backorder": "info", "unknown": "muted"}
STOCK_LABEL = {"in_stock": "In stock", "low_stock": "Low stock", "out_of_stock": "Out of stock",
               "backorder": "Backorder", "unknown": "Unknown"}

CSS = """
:root{
  --accent:__ACCENT__; --accent-dark:__ACCENT_DARK__; --ink:#0f172a; --body:#334155;
  --muted:#64748b; --line:#e2e8f0; --bg:#f1f5f9; --card:#ffffff;
  --ok:#0f766e; --ok-bg:#ccfbf1; --warn:#b45309; --warn-bg:#fef3c7;
  --bad:#b91c1c; --bad-bg:#fee2e2; --info:#1d4ed8; --info-bg:#dbeafe; --muted-bg:#e2e8f0;
  --shadow:0 1px 2px rgba(15,23,42,.06),0 8px 24px -12px rgba(15,23,42,.18);
  --radius:14px;
}
*,*::before,*::after{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{
  margin:0; background:var(--bg); color:var(--body);
  font-family:system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  font-size:15px; line-height:1.55;
}
.wrap{max-width:1180px;margin:0 auto;padding:0 20px 64px}
a{color:var(--accent)}
h1,h2,h3{color:var(--ink);line-height:1.25;margin:0}
code,kbd{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:.86em}

/* ---------- header ---------- */
.hero{
  background:linear-gradient(135deg,var(--accent-dark) 0%,var(--accent) 55%,#0ea5e9 100%);
  color:#fff;padding:44px 0 38px;margin-bottom:26px;
}
.hero .wrap{padding-bottom:0}
.hero h1{color:#fff;font-size:clamp(1.5rem,3.4vw,2.35rem);letter-spacing:-.02em}
.hero p.lede{margin:.6rem 0 0;max-width:70ch;color:rgba(255,255,255,.92)}
.hero .meta{margin-top:1.15rem;display:flex;flex-wrap:wrap;gap:8px}
.pill{
  display:inline-flex;align-items:center;gap:6px;background:rgba(255,255,255,.16);
  border:1px solid rgba(255,255,255,.28);color:#fff;border-radius:999px;
  padding:4px 12px;font-size:.79rem;font-weight:600;letter-spacing:.01em;
}
.pill.is-solid{background:#fff;color:var(--accent-dark);border-color:#fff}

/* ---------- cards + grid ---------- */
.card{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);
  box-shadow:var(--shadow);padding:22px 22px 18px;margin:0 0 22px}
.card>h2{font-size:1.06rem;margin-bottom:2px}
.card>p.hint{margin:.15rem 0 1.1rem;color:var(--muted);font-size:.86rem}
.grid{display:grid;gap:22px}
.grid.two{grid-template-columns:minmax(0,1.55fr) minmax(0,1fr)}
.grid.kpi{grid-template-columns:repeat(auto-fit,minmax(186px,1fr));gap:14px;margin-bottom:22px}
@media (max-width:880px){.grid.two{grid-template-columns:1fr}}

.kpi{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);
  box-shadow:var(--shadow);padding:16px 18px}
.kpi .label{display:block;font-size:.75rem;font-weight:700;letter-spacing:.06em;
  text-transform:uppercase;color:var(--muted)}
.kpi .value{display:block;font-size:1.62rem;font-weight:700;color:var(--ink);
  letter-spacing:-.02em;margin-top:6px}
.kpi .sub{display:block;font-size:.79rem;color:var(--muted);margin-top:3px}
.kpi.accent{border-top:3px solid var(--accent)}

/* ---------- charts ---------- */
.chart{width:100%}
.chart svg{display:block;width:100%;height:auto;overflow:visible}
.legend{list-style:none;margin:14px 0 0;padding:0;display:grid;gap:8px}
.legend li{display:flex;align-items:center;gap:10px;font-size:.87rem}
.swatch{width:11px;height:11px;border-radius:3px;flex:0 0 auto}
.legend .name{flex:1 1 auto;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.legend .val{font-variant-numeric:tabular-nums;color:var(--ink);font-weight:600}

/* ---------- tables ---------- */
.table-wrap{overflow-x:auto;border:1px solid var(--line);border-radius:10px}
table{border-collapse:collapse;width:100%;font-size:.86rem}
caption{caption-side:top;text-align:left;color:var(--muted);font-size:.82rem;padding:0 0 8px}
th,td{padding:9px 12px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}
thead th{background:#f8fafc;color:var(--muted);font-size:.72rem;letter-spacing:.06em;
  text-transform:uppercase;font-weight:700;position:sticky;top:0;z-index:1}
tbody tr:nth-child(even){background:#fbfdff}
tbody tr:hover{background:#f1f7ff}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
tbody tr:last-child td{border-bottom:none}
.scroll-y{max-height:620px;overflow-y:auto}

.chip{display:inline-block;padding:1px 8px;border-radius:999px;font-size:.72rem;
  font-weight:700;white-space:nowrap;border:1px solid transparent}
.chip.ok{background:var(--ok-bg);color:var(--ok)}
.chip.warn{background:var(--warn-bg);color:var(--warn)}
.chip.bad{background:var(--bad-bg);color:var(--bad)}
.chip.info{background:var(--info-bg);color:var(--info)}
.chip.muted{background:var(--muted-bg);color:var(--muted)}

/* ---------- quality ---------- */
.funnel{display:flex;height:34px;border-radius:9px;overflow:hidden;border:1px solid var(--line);
  margin:4px 0 16px}
.funnel span{display:flex;align-items:center;justify-content:center;color:#fff;
  font-size:.79rem;font-weight:700;letter-spacing:.02em}
.funnel .kept{background:linear-gradient(180deg,#14b8a6,#0d9488)}
.funnel .lost{background:linear-gradient(180deg,#f87171,#dc2626)}
.bars{list-style:none;margin:0;padding:0;display:grid;gap:11px}
.bars li{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:4px 12px;font-size:.86rem}
.bars .track{grid-column:1 / -1;height:8px;background:#eef2f7;border-radius:999px;
  overflow:hidden;margin-top:4px}
.bars .fill{height:100%;border-radius:999px;background:linear-gradient(90deg,var(--accent),#0ea5e9)}
.bars .fill.bad{background:linear-gradient(90deg,#f87171,#dc2626)}
.bars .fill.warn{background:linear-gradient(90deg,#fbbf24,#d97706)}
.bars .cnt{font-variant-numeric:tabular-nums;font-weight:700;color:var(--ink)}

.note{background:#f8fafc;border-left:3px solid var(--accent);border-radius:0 8px 8px 0;
  padding:11px 14px;font-size:.86rem;color:var(--body);margin:12px 0 0}
.note b{color:var(--ink)}
ul.plain{margin:.4rem 0 0;padding-left:1.1rem;font-size:.88rem}
ul.plain li{margin:.22rem 0}
.example{color:var(--muted);font-size:.8rem}
footer.rpt{margin-top:30px;color:var(--muted);font-size:.8rem;text-align:center}
.two-col{columns:2;column-gap:28px}
@media (max-width:700px){.two-col{columns:1}}

@media print{
  body{background:#fff;font-size:11.5pt}
  .hero{background:var(--accent-dark) !important;-webkit-print-color-adjust:exact;
    print-color-adjust:exact}
  .card{box-shadow:none;break-inside:avoid;page-break-inside:avoid}
  .scroll-y{max-height:none;overflow:visible}
  thead th{position:static}
}
"""


# --------------------------------------------------------------------------------------
# small rendering helpers
# --------------------------------------------------------------------------------------
def _e(value):
    return escape("" if value is None else str(value))


def _sym(currency):
    return CURRENCY_SYMBOLS.get(currency, currency + " ")


def _money(value, currency="USD"):
    return money(value, _sym(currency)) if value is not None else "n/a"


def _kpi(label, value, sub="", accent=False):
    return ('<div class="kpi{a}"><span class="label">{l}</span>'
            '<span class="value">{v}</span><span class="sub">{s}</span></div>').format(
        a=" accent" if accent else "", l=_e(label), v=value, s=_e(sub))


def _table(headers, rows, numeric=(), caption="", scroll=False):
    head = "".join(
        '<th class="{cls}">{title}</th>'.format(cls="num" if index in numeric else "",
                                                title=_e(title))
        for index, title in enumerate(headers))
    body = []
    for row in rows:
        cells = []
        for index, cell in enumerate(row):
            cls = "num" if index in numeric else ""
            cells.append('<td class="{cls}">{value}</td>'.format(cls=cls, value=cell))
        body.append("<tr>{}</tr>".format("".join(cells)))
    caption_html = "<caption>{}</caption>".format(_e(caption)) if caption else ""
    return ('<div class="table-wrap{r}">{c}<table>{cap}<thead><tr>{h}</tr></thead>'
            '<tbody>{b}</tbody></table></div>').format(
        r=" scroll-y" if scroll else "", c="", cap=caption_html, h=head, b="".join(body))


def _bar_list(items, total, css_class=""):
    rows = []
    for label, count, extra in items:
        width = (100.0 * count / total) if total else 0.0
        rows.append(
            '<li><span>{l}{x}</span><span class="cnt">{c}</span>'
            '<span class="track"><span class="fill {cls}" style="width:{w:.1f}%"></span></span></li>'
            .format(l=_e(label), x=(" \u2014 " + _e(extra)) if extra else "", c=integer(count),
                    cls=css_class, w=width))
    return '<ul class="bars">{}</ul>'.format("".join(rows))


def _warning_chips(warnings):
    if not warnings:
        return '<span class="chip ok">clean</span>'
    chips = ['<span class="chip warn" title="{t}">{n}</span>'.format(
        t=_e("; ".join(warnings)), n=len(warnings))]
    return "".join(chips)


# --------------------------------------------------------------------------------------
# writers
# --------------------------------------------------------------------------------------
def write_csv(rows, path, logger):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    serialised = [to_serialisable(row) for row in rows]
    with open(path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in serialised:
            writer.writerow(row)
    size = os.path.getsize(path)
    logger.ok("report", "wrote {} ({} rows, {} bytes)".format(os.path.basename(path),
                                                              len(serialised), size))
    return path


def write_json(payload, path, logger):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=False)
        handle.write("\n")
    size = os.path.getsize(path)
    logger.ok("report", "wrote {} ({} bytes)".format(os.path.basename(path), size))
    return path


def write_xlsx(rows, path, logger):
    """Optional: only runs when openpyxl is importable. Never a hard dependency."""
    try:
        from openpyxl import Workbook                     # noqa: PLC0415
        from openpyxl.styles import Font                  # noqa: PLC0415
    except Exception as exc:                              # noqa: BLE001
        logger.info("report", "report.xlsx skipped \u2014 openpyxl not importable ({})".format(
            type(exc).__name__))
        return None
    serialised = [to_serialisable(row) for row in rows]
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "clean data"
    sheet.append(CSV_COLUMNS)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for row in serialised:
        sheet.append([row.get(column) for column in CSV_COLUMNS])
    sheet.freeze_panes = "A2"
    workbook.save(path)
    logger.ok("report", "wrote {} via optional openpyxl ({} rows)".format(
        os.path.basename(path), len(serialised)))
    return path


# --------------------------------------------------------------------------------------
# HTML dashboard
# --------------------------------------------------------------------------------------
def build_html(rows, metrics, quality, config, outcomes, parse_stats, run):
    report_cfg = config.section("report")
    accent = report_cfg.get("accent", "#2563eb")
    accent_dark = report_cfg.get("accent_dark", "#1e40af")
    base = metrics.get("base_currency", "USD")
    totals = metrics["totals"]
    price = metrics["price"]
    trend = metrics["trend"]
    limit = int(report_cfg.get("max_table_rows", 40))

    network_sources = [o for o in outcomes if o.used_network]
    fallback_sources = [o for o in outcomes if o.mode == "fixture-fallback"]
    mode_badge = ("live HTTP" if network_sources and not fallback_sources
                  else ("offline fixture" if not network_sources else "mixed"))
    mode_detail = "; ".join("{}: {}".format(o.source_id, o.mode) for o in outcomes)

    # ---- charts ---------------------------------------------------------------------
    categories = metrics["by_category"]
    bar_items = [(item["name"], item["mean_price"] or 0.0, "{} item(s)".format(item["count"]))
                 for item in categories]
    bar_svg = bar_chart(bar_items, accent=accent, uid="cat",
                        value_formatter=lambda value: _money(value, base),
                        caption="Average price by category ({})".format(base),
                        unit_label="mean price ({})".format(base))

    trend_points = [(point["label"], point["mean_price"],
                     "{} item(s)".format(point["count"])) for point in trend.get("points", [])]
    line_svg = line_chart(trend_points, accent="#0ea5e9", uid="trend",
                          value_formatter=lambda value: _money(value, base),
                          caption="Mean price per month ({})".format(base),
                          sublabel_key="count")

    donut_items = [(item["name"], item["count"]) for item in categories]
    donut_svg = donut_chart(donut_items, uid="mix", width=340, height=300,
                            caption="Items by category",
                            centre_label=integer(totals["rows"]), centre_caption="clean rows")
    legend = "".join(
        '<li><span class="swatch" style="background:{colour}"></span>'
        '<span class="name">{name}</span><span class="val">{count} \u00b7 {share}</span></li>'.format(
            colour=color_for(index), name=_e(item["name"]), count=integer(item["count"]),
            share=pct(item["count"], totals["rows"]))
        for index, item in enumerate(categories))

    # ---- KPI cards ------------------------------------------------------------------
    direction = trend.get("direction", "flat")
    arrow = {"up": "\u25b2", "down": "\u25bc", "flat": "\u25ac"}.get(direction, "\u25ac")
    change_text = "{}{:.1f}%".format("\u002b" if (trend.get("change_percent") or 0) >= 0 else "",
                                     trend.get("change_percent") or 0.0)
    kpis = [
        _kpi("Catalogue value", _money(totals["catalog_value"], base),
             "sum of {} clean prices".format(integer(totals["rows"])), accent=True),
        _kpi("Mean price", _money(price["mean"], base),
             "median {} \u00b7 stdev {}".format(_money(price["median"], base),
                                                _money(price["stdev"], base))),
        _kpi("Price range", "{} \u2013 {}".format(_money(price["min"], base),
                                                  _money(price["max"], base)),
             "IQR {} \u00b7 p25 {} \u00b7 p75 {}".format(_money(price["iqr"], base),
                                                          _money(price["p25"], base),
                                                          _money(price["p75"], base))),
        _kpi("Distinct SKUs", integer(totals["distinct_skus"]),
             "{} brand(s), {} categor(ies)".format(totals["brands"], totals["categories"])),
        _kpi("Availability", "{} / {}".format(
            integer(totals["rows"] - totals["out_of_stock"] - totals["low_stock"]),
            integer(totals["rows"])),
            "{} low stock \u00b7 {} out of stock".format(integer(totals["low_stock"]),
                                                          integer(totals["out_of_stock"]))),
        _kpi("Inventory value", _money(totals["inventory_value"], base),
             "{} units on the page".format(integer(totals["units_in_stock"]))),
        _kpi("Mean rating", num(metrics["rating"]["mean"], 2) if metrics["rating"]["mean"] is not None else "n/a",
             "{} review(s) \u00b7 weighted {}".format(
                 integer(metrics["rating"]["total_reviews"]),
                 num(metrics["rating"]["weighted_mean"], 2))),
        _kpi("Price trend", "{} {}".format(arrow, change_text),
             "{} \u2192 {} \u00b7 R\u00b2 {}".format(
                 trend.get("first_period") or "n/a", trend.get("last_period") or "n/a",
                 num(trend.get("r_squared"), 2))),
    ]

    # ---- tables ---------------------------------------------------------------------
    category_table = _table(
        ["Category", "Items", "Share", "Mean", "Median", "Min", "Max", "Total value",
         "Mean rating", "Out of stock"],
        [[_e(item["name"]), integer(item["count"]), pct(item["count"], totals["rows"]),
          _money(item["mean_price"], base), _money(item["median_price"], base),
          _money(item["min_price"], base), _money(item["max_price"], base),
          _money(item["total_value"], base),
          num(item["mean_rating"], 2) if item["mean_rating"] is not None else "n/a",
          integer(item["out_of_stock"])] for item in categories],
        numeric=(1, 2, 3, 4, 5, 6, 7, 8, 9),
        caption="Distribution by category")

    def top_table(rows_, caption):
        return _table(
            ["SKU", "Product", "Category", "Price", "Price ({})".format(base), "Rating",
             "Reviews", "Stock"],
            [['<code>{}</code>'.format(_e(item["sku"])), _e(item["title"]),
              _e(item["category"]),
              "{} {}".format(_money(item["price_native"], item["currency"]), _e(item["currency"])),
              _money(item["price_base"], base),
              num(item["rating"], 1) if item["rating"] is not None else "n/a",
              integer(item["rating_count"]) if item["rating_count"] is not None else "n/a",
              '<span class="chip {cls}">{label}</span>'.format(
                  cls=STOCK_CLASS.get(item["stock_status"], "muted"),
                  label=STOCK_LABEL.get(item["stock_status"], item["stock_status"]))]
             for item in rows_],
            numeric=(3, 4, 5, 6), caption=caption)

    top_expensive = top_table(metrics["top"]["most_expensive"],
                              "Top {} by price".format(len(metrics["top"]["most_expensive"])))
    top_rated = top_table(metrics["top"]["best_rated"],
                          "Top {} by rating (25+ reviews)".format(len(metrics["top"]["best_rated"])))

    shown = rows[:limit]
    data_rows = []
    for row in shown:
        data_rows.append([
            '<code>{}</code>'.format(_e(row["sku"])),
            _e(row["title"]),
            _e(row["brand"] or "\u2014"),
            _e(row["category"] or "\u2014"),
            _e(row["currency"]),
            _money(row["price"], row["currency"]),
            _money(row["price_base"], base),
            num(row["rating"], 1) if row["rating"] is not None else "\u2014",
            integer(row["rating_count"]) if row["rating_count"] is not None else "\u2014",
            '<span class="chip {cls}">{label}</span>'.format(
                cls=STOCK_CLASS.get(row["stock_status"], "muted"),
                label=STOCK_LABEL.get(row["stock_status"], row["stock_status"])),
            row["listed"].isoformat() if row["listed"] else "\u2014",
            _warning_chips(row.get("warnings")),
        ])
    data_table = _table(
        ["SKU", "Title", "Brand", "Category", "Ccy", "Price", "Price ({})".format(base),
         "Rating", "Reviews", "Stock", "Listed", "Flags"],
        data_rows, numeric=(5, 6, 7, 8),
        caption="Cleaned dataset \u2014 showing {} of {} rows (full data in report.csv)".format(
            len(shown), len(rows)), scroll=True)

    # ---- data quality ---------------------------------------------------------------
    dropped_rows = [[_e(item["label"]), integer(item["count"]),
                     pct(item["count"], quality.rows_in),
                     '<span class="example">{}</span>'.format(_e(item["example"] or ""))]
                    for item in quality.to_dict()["dropped_by_reason"]]
    dropped_table = _table(["Reason", "Rows", "Share of input", "Example record"],
                           dropped_rows, numeric=(1, 2),
                           caption="Rows dropped, with the reason and one example")

    warning_rows = [[_e(item["label"]), integer(item["count"]),
                     pct(item["count"], quality.rows_out)]
                    for item in quality.to_dict()["warnings_by_type"]]
    warning_table = _table(["Data-quality flag", "Rows", "Share of clean rows"],
                           warning_rows, numeric=(1, 2),
                           caption="Anomalies retained but flagged (nothing hidden)")

    source_rows = []
    for outcome, stats in zip(outcomes, parse_stats or []):
        source_rows.append([
            _e(outcome.source_id), _e(outcome.label),
            '<span class="chip {cls}">{label}</span>'.format(
                cls="ok" if outcome.used_network else "info",
                label=_e(outcome.mode)),
            integer(stats.get("cards_seen", 0)), integer(stats.get("records", 0)),
            integer(stats.get("recovered_unclosed_fields", 0)),
            integer(stats.get("script_style_chars_skipped", 0)),
            "{:.2f}s".format(outcome.elapsed or 0.0),
        ])
    source_table = _table(["Source", "Label", "Route", "Cards", "Records", "Recovered markup",
                           "Inline JS/CSS skipped", "Fetch time"],
                          source_rows, numeric=(3, 4, 5, 6, 7),
                          caption="Collection log \u2014 which route each source took")

    kept = quality.rows_out
    lost = quality.drop_total
    kept_pct = 100.0 * kept / quality.rows_in if quality.rows_in else 0.0
    funnel = ('<div class="funnel">'
              '<span class="kept" style="width:{kp:.2f}%">kept {kept} ({kpct})</span>'
              '<span class="lost" style="width:{lp:.2f}%">{lost} dropped</span>'
              '</div>').format(kp=kept_pct, kept=integer(kept), kpct=pct(kept, quality.rows_in),
                               lp=100.0 - kept_pct, lost=integer(lost))

    warning_bars = _bar_list(
        [(item["label"], item["count"], "") for item in quality.to_dict()["warnings_by_type"]],
        max(1, quality.rows_out), css_class="warn")

    stage_rows = [[_e(label), "{:.3f}s".format(seconds), _e(note)]
                  for label, seconds, note in run.get("timings", [])]
    stage_table = _table(["Pipeline stage", "Duration", "Detail"], stage_rows, numeric=(1,),
                         caption="Stage timings for this run")

    # ---- assemble -------------------------------------------------------------------
    parts = []
    parts.append('<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">')
    parts.append('<meta name="viewport" content="width=device-width, initial-scale=1">')
    parts.append("<title>{}</title>".format(_e(report_cfg.get("title", "Report"))))
    parts.append('<meta name="description" content="Self-contained data pipeline report: '
                 'scraped, cleaned, analysed and rendered with the Python standard library.">')
    parts.append("<style>{}</style>".format(
        CSS.replace("__ACCENT__", accent).replace("__ACCENT_DARK__", accent_dark)))
    parts.append("</head>\n<body>")

    parts.append(
        '<header class="hero"><div class="wrap">'
        '<h1>{title}</h1>'
        '<p class="lede">{subtitle}</p>'
        '<div class="meta">'
        '<span class="pill is-solid">{client}</span>'
        '<span class="pill">generated {ts}</span>'
        '<span class="pill">{rows} clean rows / {parsed} parsed</span>'
        '<span class="pill">source: {mode}</span>'
        '<span class="pill">stdlib-only \u00b7 Python {py}</span>'
        '</div></div></header>'.format(
            title=_e(report_cfg.get("title", "Report")),
            subtitle=_e(report_cfg.get("subtitle", "")),
            client=_e(config.section("project").get("client", "")),
            ts=_e(run.get("generated_at", utc_now_text())),
            rows=integer(totals["rows"]), parsed=integer(quality.rows_in),
            mode=_e(mode_badge), py=_e(run.get("python", ""))))

    parts.append('<main class="wrap">')
    parts.append('<div class="grid kpi">{}</div>'.format("".join(kpis)))

    parts.append('<section class="card"><h2>Price by category</h2>'
                 '<p class="hint">Mean price per category, in {} (all currencies converted). '
                 'Bar labels show the mean; the sub-label shows how many rows back it.</p>'
                 '<div class="chart">{}</div></section>'.format(_e(base), bar_svg))

    parts.append('<div class="grid two">')
    parts.append('<section class="card"><h2>Trend over time</h2>'
                 '<p class="hint">Mean price of products listed each month. '
                 '{} dated rows; slope {}/month, R\u00b2 {}.</p>'
                 '<div class="chart">{}</div></section>'.format(
                     integer(totals["with_dates"]), _money(trend.get("slope_per_period"), base),
                     num(trend.get("r_squared"), 2), line_svg))
    parts.append('<section class="card"><h2>Category mix</h2>'
                 '<p class="hint">Share of clean rows.</p>'
                 '<div class="chart">{}</div><ul class="legend">{}</ul></section>'.format(
                     donut_svg, legend))
    parts.append("</div>")

    parts.append('<section class="card"><h2>Category breakdown</h2>'
                 '<p class="hint">Everything below is computed from the cleaned table, not the raw scrape.</p>'
                 '{}</section>'.format(category_table))

    parts.append('<div class="grid two">'
                 '<section class="card"><h2>Most expensive</h2>{}</section>'
                 '<section class="card"><h2>Best rated</h2>{}</section></div>'.format(
                     top_expensive, top_rated))

    parts.append('<section class="card" id="data"><h2>Clean dataset</h2>'
                 '<p class="hint">Every surviving row with its lineage: native price, converted '
                 'price, typed stock status and a flag count. Sorted as produced by the pipeline.</p>'
                 '{}</section>'.format(data_table))

    parts.append(
        '<section class="card"><h2>Data quality</h2>'
        '<p class="hint">{parsed} records were parsed and {clean} survived \u2014 '
        '{passrate} of the input. Nothing is dropped silently: each removal has a reason, and '
        'each repair has a flag.</p>'
        '{funnel}'
        '<div class="grid two"><div>{dropped}</div><div><h3 style="font-size:.95rem;margin-bottom:8px">'
        'Flags on retained rows</h3>{warnbars}</div></div>'
        '<div style="margin-top:20px">{warn}</div>'
        '<div style="margin-top:20px">{sources}</div>'
        '<div class="note"><b>How the cleaning works.</b> Prices are matched against a strict money '
        'grammar (so <code>$1,2x9.00</code> is rejected rather than silently read as 129.00), then '
        'normalised from US (<code>1,299.00</code>) and European (<code>1.299,00</code>) layouts and '
        'converted to {base} with the rates in <code>config.json</code>. Dates are tried against '
        'the configured formats in order; impossible dates are rejected. Duplicate SKUs are '
        'collapsed to the most complete record. Statistical outliers are <i>flagged for review</i>, '
        'never deleted.</div>'
        '</section>'.format(
            parsed=integer(quality.rows_in), clean=integer(quality.rows_out),
            passrate=pct(quality.rows_out, quality.rows_in), funnel=funnel,
            dropped=dropped_table, warnbars=warning_bars, warn=warning_table,
            sources=source_table, base=_e(base)))

    parts.append('<section class="card"><h2>Run details</h2>'
                 '<p class="hint">Fetched via <code>{route}</code>; parser recovered '
                 '{recovered} unclosed field(s) and ignored {scripts} characters of inline '
                 'JavaScript/CSS that would poison a naive scraper.</p>{stages}'
                 '<div class="note"><b>Reproduce this report:</b> <code>python run.py</code> \u2014 '
                 'no arguments, no internet, no third-party packages. Add '
                 '<code>--offline</code> to skip the network attempt entirely, or point '
                 '<code>config.json</code> at a client URL and delete the fixture entry.</div>'
                 '</section>'.format(
                     route=_e(mode_detail), recovered=integer(sum(
                         s.get("recovered_unclosed_fields", 0) for s in (parse_stats or []))),
                     scripts=integer(sum(s.get("script_style_chars_skipped", 0)
                                         for s in (parse_stats or []))),
                     stages=stage_table))

    parts.append('<footer class="rpt"><p>{title} \u00b7 prepared by {by} \u00b7 '
                 'generated {ts} \u00b7 AutoReport v{version} \u00b7 Python {py} on {os_name} '
                 '\u00b7 no external assets, no JavaScript, no cookies.</p></footer>'.format(
                     title=_e(report_cfg.get("title", "Report")),
                     by=_e(config.section("project").get("prepared_by", "")),
                     ts=_e(run.get("generated_at", "")), version=__version__,
                     py=_e(run.get("python", "")), os_name=_e(run.get("platform", ""))))

    parts.append("</main></body></html>")
    return "\n".join(parts)


def write_html(rows, metrics, quality, config, outcomes, parse_stats, run, path, logger):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    document = build_html(rows, metrics, quality, config, outcomes, parse_stats, run)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(document)
    logger.ok("report", "wrote {} ({} bytes, {} rows, {} chart(s))".format(
        os.path.basename(path), os.path.getsize(path), len(rows), 3))
    return path


def build_summary(rows, metrics, quality, config, outcomes, parse_stats, run):
    return {
        "report": {
            "name": config.section("report").get("title", "Report"),
            "client": config.section("project").get("client", ""),
            "prepared_by": config.section("project").get("prepared_by", ""),
            "generated_at": run.get("generated_at"),
            "auto_report_version": __version__,
            "python": run.get("python"),
            "platform": run.get("platform"),
            "config_file": os.path.basename(config.path),
        },
        "collection": {
            "sources": [{
                "id": outcome.source_id,
                "label": outcome.label,
                "url": outcome.url,
                "route": outcome.mode,
                "http_status": outcome.status,
                "attempts": outcome.attempts,
                "elapsed_seconds": round(outcome.elapsed or 0.0, 3),
                "bytes": outcome.bytes,
                "note": outcome.error,
                "parser": stats,
            } for outcome, stats in zip(outcomes, parse_stats or [])],
            "pipeline_timings": [{"stage": label, "seconds": round(seconds, 4), "detail": note}
                                 for label, seconds, note in run.get("timings", [])],
        },
        "data_quality": quality.to_dict(),
        "metrics": metrics,
        "sample_rows": [to_serialisable(row) for row in rows[:5]],
        "row_count": len(rows),
    }


def write_all(rows, metrics, quality, config, outcomes, parse_stats, run, logger):
    """Write every configured output. Returns the list of paths actually created."""
    os.makedirs(config.output_dir, exist_ok=True)
    written = []
    written.append(write_csv(rows, config.output_file("csv"), logger))
    written.append(write_html(rows, metrics, quality, config, outcomes, parse_stats, run,
                              config.output_file("html"), logger))
    written.append(write_json(build_summary(rows, metrics, quality, config, outcomes,
                                           parse_stats, run),
                              config.output_file("json"), logger))
    optional = write_xlsx(rows, config.output_file("xlsx"), logger)
    if optional:
        written.append(optional)
    return written


def runtime_info():
    return {
        "python": "{}.{}.{}".format(*sys.version_info[:3]),
        "platform": "{} {}".format(platform.system(), platform.release()),
        "generated_at": utc_now_text(),
    }
