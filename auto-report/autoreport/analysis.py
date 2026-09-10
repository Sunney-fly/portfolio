"""Analyse layer.

Turns the clean table into the numbers a decision-maker actually wants: price distribution,
category and brand mix, stock exposure, rating quality, a top-N league table and a monthly
trend with a fitted slope. All statistics come from the standard-library ``statistics`` module,
with a hand-rolled least-squares fallback for interpreters older than 3.10.
"""

from __future__ import annotations

import statistics
from collections import Counter, OrderedDict, defaultdict
from datetime import date, datetime

from .cleaning import month_key, month_range

try:                                                    # Python 3.10+
    from statistics import linear_regression as _linear_regression
except ImportError:                                     # pragma: no cover - older interpreters
    _linear_regression = None


def percentile(values, fraction):
    """Linear-interpolation percentile (same convention as numpy's default)."""
    ordered = sorted(values)
    if not ordered:
        return None
    if len(ordered) == 1:
        return float(ordered[0])
    position = (len(ordered) - 1) * float(fraction)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return float(ordered[lower]) * (1.0 - weight) + float(ordered[upper]) * weight


def describe(values):
    """count/min/max/mean/median/stdev/quartiles for a list of numbers."""
    clean = [float(value) for value in values if value is not None]
    if not clean:
        return {"count": 0, "min": None, "max": None, "mean": None, "median": None,
                "stdev": None, "p25": None, "p75": None, "iqr": None, "range": None,
                "total": None}
    p25 = percentile(clean, 0.25)
    p75 = percentile(clean, 0.75)
    return {
        "count": len(clean),
        "min": round(min(clean), 2),
        "max": round(max(clean), 2),
        "mean": round(statistics.fmean(clean), 2),
        "median": round(statistics.median(clean), 2),
        "stdev": round(statistics.stdev(clean), 2) if len(clean) > 1 else 0.0,
        "p25": round(p25, 2),
        "p75": round(p75, 2),
        "iqr": round(p75 - p25, 2),
        "range": round(max(clean) - min(clean), 2),
        "total": round(sum(clean), 2),
    }


def fit_trend(xs, ys):
    """Least-squares fit -> (slope, intercept, r_squared). Uses stdlib stats when available."""
    if len(xs) < 2 or len(set(xs)) < 2:
        return None, None, None
    if _linear_regression is not None:
        try:
            result = _linear_regression(xs, ys)
            slope, intercept = result.slope, result.intercept
        except Exception:                                # noqa: BLE001 - fall through
            slope = intercept = None
    else:
        slope = intercept = None
    if slope is None:
        mean_x = statistics.fmean(xs)
        mean_y = statistics.fmean(ys)
        denominator = sum((x - mean_x) ** 2 for x in xs)
        if denominator == 0:
            return None, None, None
        slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denominator
        intercept = mean_y - slope * mean_x
    mean_y = statistics.fmean(ys)
    total_ss = sum((y - mean_y) ** 2 for y in ys)
    residual_ss = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys))
    r_squared = 1.0 - residual_ss / total_ss if total_ss else 0.0
    return slope, intercept, r_squared


def _group(rows, key_func, price_key="price_base"):
    buckets = OrderedDict()
    for row in rows:
        key = key_func(row)
        buckets.setdefault(key, []).append(row)
    return buckets


def analyse(rows, config, quality, logger):
    """Compute the full metrics dictionary."""
    base = config.section("currency").get("base", "USD")
    top_n = int(config.section("analysis").get("top_n", 5))
    granularity = config.section("analysis").get("trend_granularity", "month")

    prices = [row["price_base"] for row in rows if row["price_base"] is not None]
    price_stats = describe(prices)

    metrics = {
        "base_currency": base,
        "totals": {
            "rows": len(rows),
            "distinct_skus": len({row["sku"] for row in rows}),
            "categories": len({row["category"] for row in rows if row["category"]}),
            "brands": len({row["brand"] for row in rows if row["brand"]}),
            "sources": len({row["source"] for row in rows if row["source"]}),
            "catalog_value": price_stats["total"],
            "units_in_stock": sum(row["stock_qty"] or 0 for row in rows),
            "inventory_value": round(sum((row["price_base"] or 0.0) * (row["stock_qty"] or 0)
                                         for row in rows), 2),
            "with_dates": sum(1 for row in rows if row["listed"]),
            "out_of_stock": sum(1 for row in rows if row["stock_status"] == "out_of_stock"),
            "low_stock": sum(1 for row in rows if row["stock_status"] == "low_stock"),
        },
        "price": price_stats,
        "by_currency": _currency_mix(rows, base),
        "by_category": _breakdown(rows, lambda row: row["category"] or "Uncategorised", len(rows)),
        "by_brand": _breakdown(rows, lambda row: row["brand"] or "Unbranded", len(rows)),
        "by_stock_status": _stock_mix(rows),
        "rating": _rating_stats(rows),
        "top": {
            "most_expensive": _top_rows(rows, "price_base", top_n),
            "best_rated": _top_rows(rows, "rating", top_n, min_reviews=25),
            "best_value": _top_rows(rows, "value_score", top_n, min_reviews=25),
        },
        "trend": _trend(rows, granularity),
    }

    if logger:
        logger.info("analyse", "price n={} min={} mean={} median={} max={}".format(
            price_stats["count"], price_stats["min"], price_stats["mean"],
            price_stats["median"], price_stats["max"]))
        logger.info("analyse", "catalogue value {} {:,}; {} categor(ies), {} brand(s)".format(
            base, int(price_stats["total"] or 0),
            metrics["totals"]["categories"], metrics["totals"]["brands"]))
        trend = metrics["trend"]
        if trend.get("points"):
            logger.info("analyse", "trend {} -> {} mean price {} -> {} ({:+.1f}%)".format(
                trend["points"][0]["label"], trend["points"][-1]["label"],
                trend["points"][0]["mean_price"], trend["points"][-1]["mean_price"],
                trend.get("change_percent") or 0.0))
        logger.ok("analyse", "metrics computed for {} row(s)".format(len(rows)))
    return metrics


def _currency_mix(rows, base):
    counts = Counter(row["currency"] for row in rows if row["currency"])
    groups = _group(rows, lambda row: row["currency"] or base)
    output = []
    for currency, members in groups.items():
        output.append({
            "currency": currency,
            "count": len(members),
            "share_percent": round(100.0 * len(members) / len(rows), 2) if rows else 0.0,
            "mean_price_native": round(statistics.fmean(
                [row["price"] for row in members if row["price"] is not None] or [0.0]), 2),
        })
    output.sort(key=lambda item: -item["count"])
    return {"counts": dict(counts), "groups": output}


def _breakdown(rows, key_func, total_rows):
    groups = _group(rows, key_func)
    output = []
    for key, members in groups.items():
        values = [row["price_base"] for row in members if row["price_base"] is not None]
        ratings = [row["rating"] for row in members if row["rating"] is not None]
        output.append({
            "name": key,
            "count": len(members),
            "share_percent": round(100.0 * len(members) / total_rows, 2) if total_rows else 0.0,
            "mean_price": round(statistics.fmean(values), 2) if values else None,
            "median_price": round(statistics.median(values), 2) if values else None,
            "min_price": round(min(values), 2) if values else None,
            "max_price": round(max(values), 2) if values else None,
            "total_value": round(sum(values), 2) if values else 0.0,
            "mean_rating": round(statistics.fmean(ratings), 2) if ratings else None,
            "out_of_stock": sum(1 for row in members if row["stock_status"] == "out_of_stock"),
        })
    output.sort(key=lambda item: (-item["count"], item["name"]))
    return output


def _stock_mix(rows):
    order = ["in_stock", "low_stock", "out_of_stock", "backorder", "unknown"]
    counts = Counter(row["stock_status"] for row in rows)
    labels = {"in_stock": "In stock", "low_stock": "Low stock", "out_of_stock": "Out of stock",
              "backorder": "Backorder", "unknown": "Unknown"}
    output = []
    for status in order:
        if not counts.get(status):
            continue
        output.append({
            "status": status,
            "label": labels[status],
            "count": counts[status],
            "share_percent": round(100.0 * counts[status] / len(rows), 2) if rows else 0.0,
        })
    return output


def _rating_stats(rows):
    ratings = [(row["rating"], row["rating_count"] or 0) for row in rows if row["rating"] is not None]
    if not ratings:
        return {"count": 0, "mean": None, "median": None, "total_reviews": 0, "weighted_mean": None}
    values = [value for value, _ in ratings]
    total_reviews = sum(count for _, count in ratings)
    weighted = (sum(value * count for value, count in ratings) / total_reviews
                if total_reviews else None)
    return {
        "count": len(values),
        "mean": round(statistics.fmean(values), 2),
        "median": round(statistics.median(values), 2),
        "min": round(min(values), 2),
        "max": round(max(values), 2),
        "total_reviews": total_reviews,
        "weighted_mean": round(weighted, 2) if weighted is not None else None,
    }


def _value_score(row):
    """Price relative to the category median, adjusted by rating. Lower is better value."""
    return row.get("_value_score")


def _top_rows(rows, key, limit, min_reviews=0):
    if key == "value_score":
        _attach_value_scores(rows)
    candidates = []
    for row in rows:
        value = row.get(key)
        if value is None:
            continue
        if min_reviews and (row.get("rating_count") or 0) < min_reviews:
            continue
        candidates.append(row)
    candidates.sort(key=lambda row: row[key], reverse=(key != "value_score"))
    output = []
    for row in candidates[:limit]:
        output.append({
            "sku": row["sku"],
            "title": row["title"],
            "brand": row["brand"],
            "category": row["category"],
            "price_base": row["price_base"],
            "currency": row["currency"],
            "price_native": row["price"],
            "rating": row["rating"],
            "rating_count": row["rating_count"],
            "stock_status": row["stock_status"],
            "listed": row["listed"].isoformat() if isinstance(row["listed"], (date, datetime)) else None,
        })
    return output


def _attach_value_scores(rows):
    medians = {}
    groups = _group(rows, lambda row: row["category"] or "Uncategorised")
    for category, members in groups.items():
        values = sorted(row["price_base"] for row in members if row["price_base"] is not None)
        medians[category] = statistics.median(values) if values else None
    for row in rows:
        median = medians.get(row["category"] or "Uncategorised")
        price = row["price_base"]
        rating = row["rating"]
        if not median or price is None or rating is None:
            row["value_score"] = None
            continue
        # 100 = exactly the category median at a perfect 5.0 rating; higher is better value.
        row["value_score"] = round((median / price) * (rating / 5.0) * 100.0, 1)


def _trend(rows, granularity):
    dated = [row for row in rows if row["listed"]]
    if not dated:
        return {"granularity": granularity, "points": [], "note": "no usable dates"}
    dated.sort(key=lambda row: row["listed"])
    keyed = defaultdict(list)
    for row in dated:
        keyed[month_key(row["listed"])].append(row)

    months = month_range(dated[0]["listed"], dated[-1]["listed"])
    points = []
    for month_start in months:
        key = month_start.strftime("%Y-%m")
        members = keyed.get(key, [])
        values = [row["price_base"] for row in members if row["price_base"] is not None]
        points.append({
            "period": key,
            "label": month_start.strftime("%b %Y"),
            "count": len(members),
            "mean_price": round(statistics.fmean(values), 2) if values else None,
            "median_price": round(statistics.median(values), 2) if values else None,
            "total_value": round(sum(values), 2) if values else 0.0,
        })

    fitted = [point for point in points if point["mean_price"] is not None]
    trend = {
        "granularity": granularity,
        "first_period": points[0]["period"] if points else None,
        "last_period": points[-1]["period"] if points else None,
        "periods": len(points),
        "points": points,
        "undated_rows": len(rows) - len(dated),
    }
    if len(fitted) >= 2:
        xs = [float(index) for index, _ in enumerate(fitted)]
        ys = [point["mean_price"] for point in fitted]
        slope, intercept, r_squared = fit_trend(xs, ys)
        first, last = fitted[0]["mean_price"], fitted[-1]["mean_price"]
        change = last - first
        trend.update({
            "first_mean_price": first,
            "last_mean_price": last,
            "change": round(change, 2),
            "change_percent": round(100.0 * change / first, 2) if first else None,
            "direction": "up" if change > 0 else ("down" if change < 0 else "flat"),
            "slope_per_period": round(slope, 2) if slope is not None else None,
            "r_squared": round(r_squared, 3) if r_squared is not None else None,
            "months_covered": len(fitted),
        })
    else:
        trend["note"] = "not enough dated periods to fit a trend"
    return trend
