"""Clean layer — the part clients actually pay for.

Takes the raw parser output and turns it into a trustworthy table:

* prices are normalised from ``$1,299.00`` / ``US$ 45.50`` / ``€689,99`` / ``1.299,00 EUR``
  into a float plus an ISO currency code, then converted to the configured base currency;
* dates are parsed from five different layouts, with impossible dates rejected;
* ratings, review counts and stock levels are split into typed values;
* invalid rows are dropped, with the reason recorded;
* duplicate SKUs are collapsed, keeping the most complete record;
* statistical outliers are flagged for human review (never silently deleted);
* the whole run produces a data-quality summary: rows in, rows out, what was dropped and why.

Nothing is dropped without a reason, and nothing is repaired without a warning. That
distinction is the difference between a scrape and a dataset.
"""

from __future__ import annotations

import re
import statistics
from collections import Counter, OrderedDict
from datetime import date, datetime

from .util import collapse_ws, num

# --------------------------------------------------------------------------------------
# price grammar
# --------------------------------------------------------------------------------------
_PRICE_NUM = r"(?:\d{1,3}(?:[\s\u00a0,.']\d{3})*(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)"
_PRICE_RE = re.compile(
    r"^(?:(?P<prefix>[A-Za-z]{0,3}[$\u20ac\u00a3\u00a5\u20b9]|[$\u20ac\u00a3\u00a5\u20b9])\s*)?"
    r"(?P<num>" + _PRICE_NUM + r")"
    r"(?:\s*(?P<suffix>[A-Za-z]{2,3}))?$"
)
_CODE_RE = re.compile(r"\b(USD|EUR|GBP|CAD|AUD|JPY|INR|NZD|CHF)\b")

DROP_REASONS = OrderedDict([
    ("missing_sku", "Missing or blank SKU"),
    ("invalid_sku_format", "SKU does not match the configured pattern"),
    ("missing_title", "Missing or too-short product title"),
    ("missing_price", "No numeric price present in the record"),
    ("price_unparseable", "Price text is malformed in the source"),
    ("price_below_minimum", "Price below cleaning.min_price"),
    ("price_above_maximum", "Price above cleaning.max_price (likely data-entry error)"),
    ("duplicate_sku", "Duplicate SKU (the most complete record was kept)"),
])

WARNING_LABELS = OrderedDict([
    ("missing_date", "Listing date absent"),
    ("invalid_date", "Listing date could not be parsed"),
    ("missing_rating", "No rating"),
    ("rating_out_of_range", "Rating outside the configured range"),
    ("missing_stock", "No stock status"),
    ("missing_brand", "Brand not present in the markup"),
    ("missing_category", "No category attribute"),
    ("missing_url", "No product URL"),
    ("currency_inferred", "Currency inferred from the price text"),
    ("currency_assumed_base", "Currency unknown, base currency assumed"),
    ("currency_mismatch", "Currency attribute disagreed with the price text"),
    ("fx_rate_missing", "No FX rate configured for the currency"),
    ("price_outlier_review", "Price is a statistical outlier, flagged for review"),
    ("duplicate_product_name", "Same product name listed under a different SKU"),
])


# --------------------------------------------------------------------------------------
# field normalisers
# --------------------------------------------------------------------------------------
def normalise_price(text, currency_attr, currency_cfg, warnings):
    """Return ``(amount, currency)`` or ``(None, currency)`` when the text is unusable."""
    raw = collapse_ws(text)
    if not raw:
        warnings.append("missing_price")
        return None, None
    if not re.search(r"\d", raw):
        warnings.append("missing_price")
        return None, None

    match = _PRICE_RE.match(raw)
    if not match:
        warnings.append("price_unparseable")
        return None, None

    upper = raw.upper()
    detected = None
    code_match = _CODE_RE.search(upper)
    if code_match:
        detected = code_match.group(1)
    if detected is None:
        for prefix in sorted(currency_cfg.get("prefixes", {}), key=len, reverse=True):
            if prefix.upper() in upper:
                detected = currency_cfg["prefixes"][prefix]
                break
    if detected is None:
        for symbol, code in (currency_cfg.get("symbols") or {}).items():
            if symbol in raw:
                detected = code
                break

    attr_currency = (currency_attr or "").strip().upper() or None
    base = currency_cfg.get("base", "USD")
    if detected and attr_currency and detected != attr_currency:
        warnings.append("currency_mismatch")
        currency = detected                      # the visible price wins over the attribute
    elif detected:
        currency = detected
        if not attr_currency:
            warnings.append("currency_inferred")
    elif attr_currency:
        currency = attr_currency
    else:
        currency = base
        warnings.append("currency_assumed_base")

    try:
        amount = _decimal_to_float(match.group("num"))
    except (ValueError, TypeError):
        warnings.append("price_unparseable")
        return None, currency
    return amount, currency


def _decimal_to_float(number_text):
    """Resolve ',' and '.' separators into a float, tolerating US and European layouts."""
    text = number_text.replace("\u00a0", "").replace(" ", "").replace("'", "")
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):          # 1.299,00 -> 1299.00
            text = text.replace(".", "").replace(",", ".")
        else:                                          # 1,299.00 -> 1299.00
            text = text.replace(",", "")
    elif "," in text:
        head, _, tail = text.rpartition(",")
        text = head.replace(",", "") + "." + tail if len(tail) in (1, 2) else text.replace(",", "")
    elif "." in text:
        parts = text.split(".")
        if len(parts) > 2:
            text = text.replace(".", "")
        elif len(parts) == 2 and len(parts[1]) == 3 and 1 <= len(parts[0]) <= 3:
            # "1.299" is ambiguous; a 3-digit trailing group is read as a thousands separator.
            text = text.replace(".", "")
    return float(text)


def convert_to_base(amount, currency, currency_cfg, warnings):
    if amount is None:
        return None
    base = currency_cfg.get("base", "USD")
    rates = currency_cfg.get("rates_to_base", {}) or {}
    if currency == base:
        return round(float(amount), 2)
    rate = rates.get(currency)
    if rate is None:
        warnings.append("fx_rate_missing")
        return None
    return round(float(amount) * float(rate), 2)


def build_date_parsers(cleaning_cfg):
    formats = list(cleaning_cfg.get("date_input_formats", []))
    if not cleaning_cfg.get("date_day_first", True):
        for day_first, month_first in (("%d/%m/%Y", "%m/%d/%Y"), ("%d-%m-%Y", "%m-%d-%Y")):
            if day_first in formats and month_first in formats:
                formats.remove(month_first)
                formats.insert(formats.index(day_first), month_first)
    return formats


def parse_date_value(raw, formats, logger=None):
    text = collapse_ws(raw)
    if not text:
        return None, "missing"
    for fmt in formats:
        try:
            parsed = datetime.strptime(text, fmt).date()
        except ValueError:
            continue
        if parsed.year < 2000 or parsed.year > date.today().year + 1:
            return None, "invalid"
        return parsed, None
    return None, "invalid"


def parse_rating(rating_field, rating_range, warnings):
    if not rating_field:
        warnings.append("missing_rating")
        return None, None
    score = _to_float((rating_field.get("attrs") or {}).get("score"))
    count = _to_int((rating_field.get("attrs") or {}).get("count"))
    if score is None:
        score = _to_float(rating_field.get("text"))
    if score is None:
        warnings.append("missing_rating")
        return None, None
    low, high = (rating_range or [0.0, 5.0])[:2]
    if not (float(low) <= score <= float(high)):
        warnings.append("rating_out_of_range")
        return None, count
    return score, count


_STOCK_QTY_RE = re.compile(r"(\d+)")


def parse_stock(stock_field, low_stock_max, warnings):
    if not stock_field:
        warnings.append("missing_stock")
        return "unknown", None
    text = collapse_ws(stock_field.get("text")).lower()
    if not text:
        warnings.append("missing_stock")
        return "unknown", None
    quantity = None
    qty_match = _STOCK_QTY_RE.search(text)
    if qty_match:
        quantity = int(qty_match.group(1))
    if "out of stock" in text or "sold out" in text or "unavailable" in text:
        return "out_of_stock", quantity if quantity is not None else 0
    if "backorder" in text or "pre-order" in text or "preorder" in text:
        return "backorder", quantity
    if "only" in text and "left" in text:
        status = "low_stock" if quantity is None or quantity <= low_stock_max else "in_stock"
        return status, quantity
    if "in stock" in text:
        status = "low_stock" if quantity is not None and quantity <= low_stock_max else "in_stock"
        return status, quantity
    return "unknown", quantity


def _to_float(value):
    if value is None:
        return None
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _to_int(value):
    parsed = _to_float(value)
    return None if parsed is None else int(round(parsed))


def _field_text(record, key):
    field = record.get(key)
    if isinstance(field, dict):
        return collapse_ws(field.get("text"))
    return collapse_ws(field)


def _field_attr(record, key, attr):
    field = record.get(key)
    if isinstance(field, dict):
        return (field.get("attrs") or {}).get(attr)
    return None


def _field_child(record, key, child):
    field = record.get(key)
    if isinstance(field, dict):
        return collapse_ws((field.get("children") or {}).get(child))
    return ""


# --------------------------------------------------------------------------------------
# quality report
# --------------------------------------------------------------------------------------
class QualityReport(object):
    def __init__(self):
        self.rows_in = 0
        self.rows_out = 0
        self.dropped = Counter()
        self.warnings = Counter()
        self.drop_samples = {}
        self.per_source = OrderedDict()
        self.script_chars_ignored = 0
        self.duplicates_collapsed = 0

    def drop(self, reason, record):
        self.dropped[reason] += 1
        if reason not in self.drop_samples:
            self.drop_samples[reason] = _describe_record(record)

    @property
    def drop_total(self):
        return sum(self.dropped.values())

    def to_dict(self):
        return {
            "rows_parsed": self.rows_in,
            "rows_clean": self.rows_out,
            "rows_dropped": self.drop_total,
            "rows_dropped_duplicate": self.duplicates_collapsed,
            "pass_rate_percent": round(100.0 * self.rows_out / self.rows_in, 2) if self.rows_in else 0.0,
            "dropped_by_reason": [
                {"reason": reason, "label": DROP_REASONS.get(reason, reason), "count": count,
                 "example": self.drop_samples.get(reason)}
                for reason, count in self.dropped.most_common()
            ],
            "warnings_by_type": [
                {"warning": key, "label": WARNING_LABELS.get(key, key), "count": count}
                for key, count in self.warnings.most_common()
            ],
            "by_source": list(self.per_source.values()),
            "inline_script_css_chars_ignored": self.script_chars_ignored,
        }


def _describe_record(record):
    sku = collapse_ws(record.get("sku")) or "(no sku)"
    title = _field_text(record, "title") or "(no title)"
    price = _field_text(record, "price_raw") or "(no price)"
    return "{} | {} | {}".format(sku, title[:48], price[:24])


# --------------------------------------------------------------------------------------
# main cleaning pass
# --------------------------------------------------------------------------------------
def clean_records(raw_records, config, logger, parse_stats=None):
    """Normalise, validate, deduplicate. Returns ``(rows, QualityReport)``."""
    cleaning = config.section("cleaning")
    currency_cfg = config.section("currency")
    analysis_cfg = config.section("analysis")
    brands = [b.lower() for b in config.get("brands", [])]
    base = currency_cfg.get("base", "USD")
    low_stock_max = int((analysis_cfg.get("stock_bands") or {}).get("low_stock_max", 5))
    rating_range = cleaning.get("rating_range", [0.0, 5.0])
    date_formats = build_date_parsers(cleaning)
    sku_re = re.compile(cleaning["sku_pattern"]) if cleaning.get("sku_pattern") else None
    min_price = float(cleaning.get("min_price", 0.0))
    max_price = float(cleaning.get("max_price", 1e12))
    min_title = int(cleaning.get("min_title_length", 3))

    quality = QualityReport()
    quality.rows_in = len(raw_records)
    quality.script_chars_ignored = sum(s.get("script_style_chars_skipped", 0)
                                       for s in (parse_stats or []))

    staged = []
    warned_rows = 0
    for record in raw_records:
        warnings = []
        sku = collapse_ws(record.get("sku"))
        title = _field_text(record, "title")
        brand = _field_child(record, "title", "brand")
        if not brand:
            brand = _infer_brand(title, brands)
            if not brand:
                warnings.append("missing_brand")

        category = collapse_ws(record.get("category")) or None
        if not category:
            warnings.append("missing_category")

        price_native, currency = normalise_price(
            _field_text(record, "price_raw"),
            _field_attr(record, "price_raw", "currency_attr"),
            currency_cfg, warnings)
        price_base = convert_to_base(price_native, currency, currency_cfg, warnings)

        listed, date_issue = parse_date_value(record.get("listed_raw"), date_formats)
        if date_issue == "missing":
            warnings.append("missing_date")
        elif date_issue == "invalid":
            warnings.append("invalid_date")

        rating, rating_count = parse_rating(record.get("rating"), rating_range, warnings)
        stock_status, stock_qty = parse_stock(record.get("stock_raw"), low_stock_max, warnings)

        url = None
        url_field = record.get("url")
        if isinstance(url_field, dict):
            url = url_field.get("value")
        if not url:
            warnings.append("missing_url")

        row = {
            "sku": sku,
            "title": title,
            "brand": brand or None,
            "category": category,
            "currency": currency,
            "price": price_native,
            "price_base": price_base,
            "base_currency": base,
            "listed": listed,
            "rating": rating,
            "rating_count": rating_count,
            "stock_status": stock_status,
            "stock_qty": stock_qty,
            "url": url,
            "source": record.get("_source"),
            "source_label": record.get("_source_label"),
            "source_mode": record.get("_source_mode"),
            "order": record.get("_order"),
            "warnings": sorted(set(warnings)),
        }
        row["completeness"] = _completeness(row)

        reason = _validate(row, sku_re, min_title, min_price, max_price, url)
        if reason:
            quality.drop(reason, record)
            continue
        quality.warnings.update(set(warnings))
        if warnings:
            warned_rows += 1
            if logger:
                logger.debug("clean", "{}: {}".format(sku, ", ".join(sorted(set(warnings)))))
        staged.append((row, record))

    rows = _deduplicate(staged, cleaning.get("dedupe", {}), quality, logger)
    _flag_duplicate_names(rows, cleaning.get("dedupe", {}), quality, logger)
    _flag_outliers(rows, cleaning.get("outliers", {}), quality, logger)

    quality.rows_out = len(rows)
    if logger:
        logger.ok("clean", "{} raw -> {} clean row(s); {} dropped; {} row(s) carry warnings".format(
            quality.rows_in, quality.rows_out, quality.drop_total, warned_rows))
        for reason, count in quality.dropped.most_common():
            logger.info("clean", "dropped {:>3} x {} ({})".format(
                count, reason, DROP_REASONS.get(reason, "")))
        for key, count in quality.warnings.most_common():
            logger.info("clean", "flagged {:>3} x {} ({})".format(
                count, key, WARNING_LABELS.get(key, "")))
    return rows, quality


def _completeness(row):
    keys = ["sku", "title", "brand", "category", "price", "listed", "rating",
            "rating_count", "stock_qty", "url"]
    present = 0
    for key in keys:
        value = row.get(key)
        if value is None or value == "":
            continue
        present += 1
    return round(100.0 * present / len(keys), 1)


def _infer_brand(title, brands):
    lowered = (title or "").lower()
    for brand in brands:
        if lowered.startswith(brand + " ") or lowered == brand:
            return brand
    return ""


def _validate(row, sku_re, min_title, min_price, max_price, url):
    if not row["sku"]:
        return "missing_sku"
    if sku_re is not None and not sku_re.match(row["sku"]):
        return "invalid_sku_format"
    if not row["title"] or len(row["title"]) < min_title:
        return "missing_title"
    if row["price"] is None:
        prior = set(row["warnings"])
        return "price_unparseable" if "price_unparseable" in prior else "missing_price"
    if row["price"] < min_price:
        return "price_below_minimum"
    if row["price"] > max_price:
        return "price_above_maximum"
    if row["price_base"] is None:
        return "price_unparseable"
    return None


def _deduplicate(staged, dedupe_cfg, quality, logger):
    key_name = dedupe_cfg.get("key", "sku")
    strategy = dedupe_cfg.get("strategy", "keep_most_complete")
    groups = OrderedDict()
    for row, record in staged:
        groups.setdefault(row.get(key_name), []).append((row, record))

    rows = []
    for key, members in groups.items():
        if len(members) == 1:
            rows.append(members[0][0])
            continue
        winner = _pick_winner(members, strategy)
        for row, record in members:
            if row is not winner[0]:
                quality.drop("duplicate_sku", record)
                quality.duplicates_collapsed += 1
        if logger:
            logger.info("clean", "duplicate {}={!r}: kept {} of {} rows ({})".format(
                key_name, key, winner[0]["title"][:34], len(members), strategy))
        rows.append(winner[0])
    return rows


def _pick_winner(members, strategy):
    if strategy == "keep_first":
        return members[0]
    if strategy == "keep_lowest_price":
        return min(members, key=lambda pair: (pair[0]["price"] if pair[0]["price"] is not None else 1e18))
    return max(members, key=lambda pair: (pair[0]["completeness"],
                                          -(pair[0]["price"] or 0.0)))


def _flag_duplicate_names(rows, dedupe_cfg, quality, logger):
    if not dedupe_cfg.get("flag_duplicate_product_names", True):
        return
    seen = {}
    for row in rows:
        key = collapse_ws(row["title"]).lower()
        if not key:
            continue
        if key in seen:
            for target in (seen[key], row):
                if "duplicate_product_name" not in target["warnings"]:
                    target["warnings"].append("duplicate_product_name")
                    target["warnings"].sort()
            quality.warnings["duplicate_product_name"] += 1
        else:
            seen[key] = row


def _flag_outliers(rows, outlier_cfg, quality, logger):
    if str(outlier_cfg.get("method", "modified_zscore")) != "modified_zscore":
        return
    prices = [row["price_base"] for row in rows if row["price_base"] is not None]
    if len(prices) < 4:
        return
    median = statistics.median(prices)
    deviations = [abs(value - median) for value in prices]
    mad = statistics.median(deviations)
    if mad == 0:
        return
    threshold = float(outlier_cfg.get("threshold", 5.0))
    flagged = []
    for row in rows:
        value = row["price_base"]
        if value is None:
            continue
        score = 0.6745 * (value - median) / mad
        row["outlier_score"] = round(score, 2)
        if abs(score) >= threshold:
            row["warnings"].append("price_outlier_review")
            row["warnings"].sort()
            quality.warnings["price_outlier_review"] += 1
            flagged.append((row["sku"], value, score))
    if logger and flagged:
        logger.warn("clean", "{} price outlier(s) flagged for review (modified z >= {:.1f}): {}".format(
            len(flagged), threshold,
            ", ".join("{}={} (z={:.1f})".format(sku, num(value), score)
                      for sku, value, score in flagged[:6])))


# --------------------------------------------------------------------------------------
def to_serialisable(row):
    """JSON/CSV-safe copy of a row (dates become ISO strings)."""
    output = dict(row)
    listed = output.get("listed")
    if isinstance(listed, (date, datetime)):
        output["listed"] = listed.isoformat()
        output["listed_month"] = listed.strftime("%Y-%m")
    else:
        output["listed"] = None
        output["listed_month"] = None
    output["warnings"] = ";".join(output.get("warnings") or [])
    return output


def month_key(value):
    if isinstance(value, (date, datetime)):
        return value.strftime("%Y-%m")
    return None


def add_months(value, count):
    month_index = value.month - 1 + count
    year = value.year + month_index // 12
    return date(year, month_index % 12 + 1, 1)


def month_range(start, end):
    """Inclusive list of first-of-month dates between two dates."""
    if start is None or end is None:
        return []
    cursor = date(start.year, start.month, 1)
    last = date(end.year, end.month, 1)
    months = []
    while cursor <= last and len(months) < 600:
        months.append(cursor)
        cursor = add_months(cursor, 1)
    return months


def days_between(first, second):
    if first is None or second is None:
        return None
    return (second - first).days
