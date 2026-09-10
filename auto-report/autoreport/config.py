"""Configuration loading.

Every knob the pipeline uses lives in ``config.json`` so that adapting the pipeline to a
different client site never requires editing Python. This module loads the file, deep-merges
it over built-in defaults, validates the result and resolves all paths relative to the
config file so the project can be run from any working directory.
"""

from __future__ import annotations

import copy
import json
import os

DEFAULTS = {
    "project": {
        "name": "AutoReport",
        "client": "n/a",
        "prepared_by": "n/a",
        "notes": "",
    },
    "fetch": {
        "mode": "auto",
        "user_agent": "AutoReportBot/1.0 (+https://example.com/bot)",
        "accept_language": "en-US,en;q=0.9",
        "timeout_seconds": 8,
        "max_retries": 2,
        "backoff_base_seconds": 0.6,
        "backoff_max_seconds": 6.0,
        "rate_limit_min_interval_seconds": 1.0,
        "probe_timeout_seconds": 1.5,
        "fixture_encoding": "utf-8",
        "sources": [],
    },
    "selectors": {
        "record_tag": "article",
        "record_class": "product-card",
        "record_attributes": {},
        "fields": {},
    },
    "brands": [],
    "cleaning": {
        "required_fields": ["sku", "title", "price_base"],
        "min_price": 0.01,
        "max_price": 1.0e9,
        "min_title_length": 3,
        "sku_pattern": "",
        "date_input_formats": ["%Y-%m-%d", "%d/%m/%Y", "%d %b %Y", "%b %d, %Y"],
        "date_day_first": True,
        "dedupe": {"key": "sku", "strategy": "keep_most_complete",
                   "flag_duplicate_product_names": True},
        "outliers": {"method": "modified_zscore", "threshold": 5.0, "action": "flag"},
        "rating_range": [0.0, 5.0],
    },
    "currency": {
        "base": "USD",
        "rates_to_base": {"USD": 1.0},
        "symbols": {"$": "USD"},
        "prefixes": {"US$": "USD"},
    },
    "analysis": {
        "top_n": 5,
        "trend_granularity": "month",
        "stock_bands": {"low_stock_max": 5},
    },
    "report": {
        "title": "Data Report",
        "subtitle": "",
        "accent": "#2563eb",
        "accent_dark": "#1e40af",
        "max_table_rows": 40,
        "output_dir": "output",
        "files": {
            "html": "report.html",
            "csv": "report.csv",
            "json": "summary.json",
            "xlsx": "report.xlsx",
            "log": "run.log",
        },
    },
}


class ConfigError(Exception):
    pass


def _deep_merge(base, override):
    """Recursively merge ``override`` into a copy of ``base`` (dicts merge, everything else wins)."""
    result = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if key.startswith("$"):
            continue
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


class Config(object):
    """Merged configuration plus resolved, absolute paths."""

    def __init__(self, data, path):
        self.data = data
        self.path = os.path.abspath(path)
        self.root = os.path.dirname(self.path)

    # -- convenience accessors ---------------------------------------------------------
    def __getitem__(self, key):
        return self.data[key]

    def get(self, key, default=None):
        return self.data.get(key, default)

    def section(self, name):
        return self.data.get(name, {})

    def resolve(self, *parts):
        """Resolve a path from the config file, allowing absolute paths through untouched."""
        candidate = os.path.join(*[p for p in parts if p])
        if os.path.isabs(candidate):
            return os.path.normpath(candidate)
        return os.path.normpath(os.path.join(self.root, candidate))

    @property
    def output_dir(self):
        return self.resolve(self.section("report").get("output_dir", "output"))

    def output_file(self, kind):
        name = self.section("report").get("files", {}).get(kind, kind)
        return os.path.join(self.output_dir, name)

    def source_fixture_path(self, source):
        """Absolute path of a source's local fixture, or None when it has none."""
        fixture = source.get("fixture")
        if not fixture:
            return None
        return self.resolve(fixture)


def load(path):
    """Read, merge and validate ``config.json``. Raises :class:`ConfigError` on bad input."""
    if not os.path.isfile(path):
        raise ConfigError("config file not found: {}".format(path))
    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except ValueError as exc:
        raise ConfigError("config file is not valid JSON: {}".format(exc))
    if not isinstance(raw, dict):
        raise ConfigError("config root must be a JSON object")

    data = _deep_merge(DEFAULTS, raw)
    config = Config(data, path)
    _validate(config)
    return config


def _validate(config):
    problems = []

    mode = str(config.section("fetch").get("mode", "auto")).lower()
    if mode not in ("auto", "online", "offline"):
        problems.append("fetch.mode must be one of auto|online|offline (got {!r})".format(mode))

    sources = config.section("fetch").get("sources") or []
    if not sources:
        problems.append("fetch.sources must list at least one source")
    seen = set()
    for index, source in enumerate(sources):
        if not source.get("id"):
            problems.append("fetch.sources[{}] is missing 'id'".format(index))
        elif source["id"] in seen:
            problems.append("fetch.sources[{}] repeats id {!r}".format(index, source["id"]))
        else:
            seen.add(source["id"])
        if not source.get("url") and not source.get("fixture"):
            problems.append("source {!r} has neither 'url' nor 'fixture'".format(source.get("id")))
        if source.get("fixture") and not os.path.isfile(config.source_fixture_path(source)):
            problems.append("source {!r} fixture missing: {}".format(
                source.get("id"), config.source_fixture_path(source)))

    selectors = config.section("selectors")
    if not selectors.get("record_tag"):
        problems.append("selectors.record_tag is required")
    if not selectors.get("fields"):
        problems.append("selectors.fields must define at least one field")

    cleaning = config.section("cleaning")
    if float(cleaning.get("min_price", 0)) >= float(cleaning.get("max_price", 1)):
        problems.append("cleaning.min_price must be below cleaning.max_price")

    base = config.section("currency").get("base")
    rates = config.section("currency").get("rates_to_base", {})
    if base not in rates:
        problems.append("currency.rates_to_base must contain the base currency {!r}".format(base))

    if problems:
        raise ConfigError("invalid configuration:\n  - " + "\n  - ".join(problems))
