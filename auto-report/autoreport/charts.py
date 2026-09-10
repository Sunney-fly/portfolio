"""Report layer, part 1: charts drawn as inline SVG, generated in pure Python.

No CDN, no JavaScript chart library, no external images. Every chart is a self-contained
``<svg>`` string with a ``viewBox`` so it scales fluidly inside the responsive dashboard, plus
``<title>``/``<desc>`` for screen readers and print/PDF export.
"""

from __future__ import annotations

from html import escape

FONT = "system-ui,-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"

PALETTE = ["#2563eb", "#0ea5e9", "#14b8a6", "#f59e0b", "#8b5cf6",
           "#ef4444", "#ec4899", "#22c55e", "#64748b", "#a16207"]

GRID = "#e2e8f0"
AXIS = "#cbd5e1"
LABEL = "#64748b"
INK = "#0f172a"


def color_for(index):
    return PALETTE[index % len(PALETTE)]


def _text(x, y, content, size=12, weight="400", fill=LABEL, anchor="middle", extra=""):
    return ('<text x="{x}" y="{y}" font-family="{font}" font-size="{size}" '
            'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}" {extra}>{content}</text>'
            ).format(x=_n(x), y=_n(y), font=FONT, size=size, weight=weight, fill=fill,
                     anchor=anchor, content=escape(str(content)), extra=extra)


def _n(value):
    """Compact number formatting for SVG coordinates."""
    return "{:.2f}".format(float(value)).rstrip("0").rstrip(".") or "0"


def _nice_ceiling(value):
    """Round a maximum up to a friendly axis top (1/2/2.5/5 x 10^n)."""
    if value is None or value <= 0:
        return 1.0
    exponent = 0
    scaled = float(value)
    while scaled >= 10:
        scaled /= 10.0
        exponent += 1
    while scaled < 1:
        scaled *= 10.0
        exponent -= 1
    for step in (1.0, 2.0, 2.5, 5.0, 10.0):
        if scaled <= step:
            scaled = step
            break
    return scaled * (10.0 ** exponent)


def _open_svg(width, height, title, description):
    return ('<svg viewBox="0 0 {w} {h}" width="100%" height="auto" preserveAspectRatio="xMidYMid meet" '
            'role="img" aria-label="{label}" xmlns="http://www.w3.org/2000/svg">'
            '<title>{title}</title><desc>{desc}</desc>').format(
        w=_n(width), h=_n(height), label=escape(title), title=escape(title),
        desc=escape(description))


def _defs(uid, accent, top_opacity="0.95", bottom_opacity="0.55"):
    return (
        '<defs>'
        '<linearGradient id="grad-{uid}" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0%" stop-color="{accent}" stop-opacity="{top}"/>'
        '<stop offset="100%" stop-color="{accent}" stop-opacity="{bottom}"/>'
        '</linearGradient>'
        '<linearGradient id="area-{uid}" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0%" stop-color="{accent}" stop-opacity="0.32"/>'
        '<stop offset="100%" stop-color="{accent}" stop-opacity="0.02"/>'
        '</linearGradient>'
        '</defs>'
    ).format(uid=uid, accent=accent, top=top_opacity, bottom=bottom_opacity)


def _gridlines(x0, y0, plot_w, plot_h, top, ticks=5, formatter=None):
    parts = []
    for index in range(ticks + 1):
        fraction = index / float(ticks)
        y = y0 + plot_h - fraction * plot_h
        parts.append('<line x1="{x1}" y1="{y}" x2="{x2}" y2="{y}" stroke="{grid}" '
                     'stroke-width="1" {dash}/>'.format(
                         x1=_n(x0), x2=_n(x0 + plot_w), y=_n(y), grid=GRID,
                         dash='stroke-dasharray="3 4"' if index else ""))
        label = formatter(top * fraction) if formatter else _n(top * fraction)
        parts.append(_text(x0 - 10, y + 4, label, anchor="end", size=11))
    return "".join(parts)


# --------------------------------------------------------------------------------------
def bar_chart(items, accent="#2563eb", uid="bar", value_formatter=None, width=780, height=340,
              caption="", unit_label=""):
    """Vertical bar chart. ``items`` is a list of ``(label, value, sublabel)`` tuples."""
    if not items:
        return _empty_svg("bar", width, height, "No data")
    formatter = value_formatter or (lambda value: _n(value))
    pad_left, pad_right, pad_top, pad_bottom = 84, 18, 34, 68
    plot_w = width - pad_left - pad_right
    plot_h = height - pad_top - pad_bottom
    top = _nice_ceiling(max(value for _, value, _ in items))
    slot = plot_w / float(len(items))
    bar_w = min(slot * 0.58, 96.0)

    parts = [_open_svg(width, height, caption or "Bar chart",
                       "Bar chart of {} categories. ".format(len(items)) +
                       "; ".join("{}: {}".format(label, formatter(value))
                                 for label, value, _ in items)),
             _defs(uid, accent),
             _gridlines(pad_left, pad_top, plot_w, plot_h, top, formatter=formatter)]

    for index, (label, value, sublabel) in enumerate(items):
        centre = pad_left + slot * (index + 0.5)
        bar_h = max(2.0, (value / top) * plot_h) if top else 2.0
        y = pad_top + plot_h - bar_h
        radius = min(7.0, bar_w / 2.0, bar_h)
        path = ("M {x0} {y1} L {x0} {yr} Q {x0} {y0} {x0r} {y0} L {x1r} {y0} "
                "Q {x1} {y0} {x1} {yr} L {x1} {y1} Z").format(
            x0=_n(centre - bar_w / 2), x1=_n(centre + bar_w / 2),
            x0r=_n(centre - bar_w / 2 + radius), x1r=_n(centre + bar_w / 2 - radius),
            y0=_n(y), y1=_n(pad_top + plot_h), yr=_n(y + radius))
        parts.append('<path d="{d}" fill="url(#grad-{uid})"><title>{t}</title></path>'.format(
            d=path, uid=uid, t=escape("{}: {}".format(label, formatter(value)))))
        parts.append(_text(centre, y - 9, formatter(value), size=12, weight="600", fill=INK))
        parts.append(_text(centre, pad_top + plot_h + 20, label, size=12, weight="500", fill=INK))
        if sublabel:
            parts.append(_text(centre, pad_top + plot_h + 36, sublabel, size=11, fill=LABEL))

    parts.append('<line x1="{x1}" y1="{y}" x2="{x2}" y2="{y}" stroke="{axis}" stroke-width="1"/>'
                 .format(x1=_n(pad_left), x2=_n(pad_left + plot_w),
                         y=_n(pad_top + plot_h), axis=AXIS))
    if unit_label:
        parts.append(_text(pad_left - 10, pad_top - 14, unit_label, anchor="end", size=11,
                           weight="600"))
    parts.append("</svg>")
    return "".join(parts)


def line_chart(points, accent="#0ea5e9", uid="line", value_formatter=None, width=780, height=340,
               caption="", sublabel_key="sublabel"):
    """Line chart with an area fill. ``points`` is a list of ``(label, value, sublabel)``."""
    if not points:
        return _empty_svg("line", width, height, "No data")
    formatter = value_formatter or (lambda value: _n(value))
    pad_left, pad_right, pad_top, pad_bottom = 84, 24, 34, 70
    plot_w = width - pad_left - pad_right
    plot_h = height - pad_top - pad_bottom

    values = [value for _, value, _ in points if value is not None]
    if not values:
        return _empty_svg("line", width, height, "No usable values")
    top = _nice_ceiling(max(values) * 1.12)
    slot = plot_w / float(max(1, len(points) - 1)) if len(points) > 1 else plot_w

    def position(index, value):
        x = pad_left + (slot * index if len(points) > 1 else plot_w / 2.0)
        y = pad_top + plot_h - (value / top) * plot_h if top else pad_top + plot_h
        return x, y

    parts = [_open_svg(width, height, caption or "Line chart",
                       "Line chart over {} periods. ".format(len(points)) +
                       "; ".join("{}: {}".format(label, formatter(value)) if value is not None
                                 else "{}: no data".format(label) for label, value, _ in points)),
             _defs(uid, accent),
             _gridlines(pad_left, pad_top, plot_w, plot_h, top, formatter=formatter)]

    segments = []
    current = []
    for index, (_, value, _) in enumerate(points):
        if value is None:
            if current:
                segments.append(current)
                current = []
            continue
        current.append(position(index, value))
    if current:
        segments.append(current)

    for segment in segments:
        if len(segment) > 1:
            line = " ".join("{},{}".format(_n(x), _n(y)) for x, y in segment)
            area = ("M {first} L {rest} L {lastx} {base} L {firstx} {base} Z").format(
                first="{},{}".format(_n(segment[0][0]), _n(segment[0][1])),
                rest=" L ".join("{},{}".format(_n(x), _n(y)) for x, y in segment[1:]),
                lastx=_n(segment[-1][0]), firstx=_n(segment[0][0]),
                base=_n(pad_top + plot_h))
            parts.append('<path d="{d}" fill="url(#area-{uid})"/>'.format(d=area, uid=uid))
            parts.append('<polyline points="{p}" fill="none" stroke="{accent}" stroke-width="2.5" '
                         'stroke-linejoin="round" stroke-linecap="round"/>'.format(
                             p=line, accent=accent))

    for index, (label, value, sublabel) in enumerate(points):
        x = pad_left + (slot * index if len(points) > 1 else plot_w / 2.0)
        if value is not None:
            _, y = position(index, value)
            parts.append('<circle cx="{x}" cy="{y}" r="4.5" fill="#ffffff" stroke="{accent}" '
                         'stroke-width="2.5"><title>{t}</title></circle>'.format(
                             x=_n(x), y=_n(y), accent=accent,
                             t=escape("{}: {}".format(label, formatter(value)))))
            parts.append(_text(x, y - 13, formatter(value), size=12, weight="600", fill=INK))
        else:
            parts.append(_text(x, pad_top + plot_h - 8, "\u2014", size=12, fill=LABEL))
        parts.append(_text(x, pad_top + plot_h + 22, label, size=12, weight="500", fill=INK))
        if sublabel:
            parts.append(_text(x, pad_top + plot_h + 38, sublabel, size=11, fill=LABEL))

    parts.append('<line x1="{x1}" y1="{y}" x2="{x2}" y2="{y}" stroke="{axis}" stroke-width="1"/>'
                 .format(x1=_n(pad_left), x2=_n(pad_left + plot_w), y=_n(pad_top + plot_h),
                         axis=AXIS))
    parts.append("</svg>")
    return "".join(parts)


def donut_chart(items, accent=None, uid="donut", width=360, height=320, caption="",
                value_formatter=None, centre_label="", centre_caption=""):
    """Donut chart of ``(label, value)`` pairs with a centre KPI."""
    if not items:
        return _empty_svg("donut", width, height, "No data")
    formatter = value_formatter or (lambda value: _n(value))
    total = float(sum(value for _, value in items)) or 1.0
    cx, cy = width / 2.0, height / 2.0 - 6
    r_out = min(width, height) * 0.36
    r_in = r_out * 0.62

    parts = [_open_svg(width, height, caption or "Donut chart",
                       "Donut chart: " + "; ".join(
                           "{} {} ({:.1f}%)".format(label, formatter(value), 100.0 * value / total)
                           for label, value in items))]

    if len(items) == 1:
        label, value = items[0]
        ring = ("M {cx} {y0} A {r} {r} 0 1 1 {cx} {y1} A {r} {r} 0 1 1 {cx} {y0} Z "
                "M {cx} {yi0} A {ri} {ri} 0 1 0 {cx} {yi1} A {ri} {ri} 0 1 0 {cx} {yi0} Z").format(
            cx=_n(cx), y0=_n(cy - r_out), y1=_n(cy + r_out), r=_n(r_out),
            yi0=_n(cy - r_in), yi1=_n(cy + r_in), ri=_n(r_in))
        parts.append('<path d="{}" fill="{}" fill-rule="evenodd"><title>{}</title></path>'.format(
            ring, color_for(0), escape("{}: {}".format(label, formatter(value)))))
    else:
        angle = 0.0
        for index, (label, value) in enumerate(items):
            sweep = 360.0 * (float(value) / total)
            if sweep <= 0.01:
                continue
            parts.append(_donut_segment(cx, cy, r_out, r_in, angle, angle + sweep - 0.6,
                                        color_for(index),
                                        "{}: {} ({:.1f}%)".format(label, formatter(value),
                                                                  100.0 * value / total)))
            angle += sweep

    parts.append('<circle cx="{cx}" cy="{cy}" r="{r}" fill="#ffffff" stroke="{grid}" '
                 'stroke-width="1"/>'.format(cx=_n(cx), cy=_n(cy), r=_n(r_in - 1), grid=GRID))
    if centre_label:
        parts.append(_text(cx, cy + 4, centre_label, size=26, weight="700", fill=INK))
    if centre_caption:
        parts.append(_text(cx, cy + 24, centre_caption, size=11, fill=LABEL))
    parts.append("</svg>")
    return "".join(parts)


def _donut_segment(cx, cy, r_out, r_in, start_deg, end_deg, fill, title):
    large = 1 if (end_deg - start_deg) > 180 else 0
    x0, y0 = _polar(cx, cy, r_out, start_deg)
    x1, y1 = _polar(cx, cy, r_out, end_deg)
    x2, y2 = _polar(cx, cy, r_in, end_deg)
    x3, y3 = _polar(cx, cy, r_in, start_deg)
    path = ("M {x0} {y0} A {r} {r} 0 {la} 1 {x1} {y1} L {x2} {y2} "
            "A {ri} {ri} 0 {la} 0 {x3} {y3} Z").format(
        x0=_n(x0), y0=_n(y0), x1=_n(x1), y1=_n(y1), x2=_n(x2), y2=_n(y2), x3=_n(x3), y3=_n(y3),
        r=_n(r_out), ri=_n(r_in), la=large)
    return '<path d="{d}" fill="{fill}" stroke="#ffffff" stroke-width="1.5"><title>{t}</title></path>'.format(
        d=path, fill=fill, t=escape(title))


def _polar(cx, cy, radius, angle_deg):
    import math
    radians = math.radians(angle_deg - 90.0)
    return cx + radius * math.cos(radians), cy + radius * math.sin(radians)


def sparkline(values, accent="#2563eb", width=140, height=34):
    """Tiny inline trend line, used inside KPI cards."""
    clean = [float(value) for value in values if value is not None]
    if len(clean) < 2:
        return ""
    low, high = min(clean), max(clean)
    span = (high - low) or 1.0
    step = width / float(len(clean) - 1)
    coords = [(index * step, height - 4 - ((value - low) / span) * (height - 8))
              for index, value in enumerate(clean)]
    line = " ".join("{},{}".format(_n(x), _n(y)) for x, y in coords)
    last_x, last_y = coords[-1]
    return ('<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" aria-hidden="true" '
            'xmlns="http://www.w3.org/2000/svg">'
            '<polyline points="{p}" fill="none" stroke="{accent}" stroke-width="2" '
            'stroke-linejoin="round" stroke-linecap="round"/>'
            '<circle cx="{cx}" cy="{cy}" r="2.6" fill="{accent}"/></svg>').format(
        w=width, h=height, p=line, accent=accent, cx=_n(last_x), cy=_n(last_y))


def _empty_svg(uid, width, height, message):
    return ('<svg viewBox="0 0 {w} {h}" width="100%" height="auto" role="img" '
            'xmlns="http://www.w3.org/2000/svg">'
            '<rect x="0" y="0" width="{w}" height="{h}" fill="#f8fafc" rx="10"/>'
            '{t}</svg>').format(w=_n(width), h=_n(height),
                                t=_text(width / 2.0, height / 2.0, message, size=13))
