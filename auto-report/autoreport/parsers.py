"""Parse layer.

Structured records are extracted from HTML with :class:`html.parser.HTMLParser` — a real
tokeniser with an element stack, not regex string splitting. That buys three things a client
pays for:

1. **Robustness to broken markup.** Fields are closed by depth tracking, and a field that is
   never closed (a stray ``<span>``) is recovered as soon as the next sibling field starts.
2. **Nested extraction.** A field can be captured from inside another field (``brand`` lives
   inside the ``title`` element), and its text is kept out of the parent's primary value while
   still being available as a child.
3. **Poison resistance.** ``<script>``/``<style>`` text and HTML comments are skipped, so
   inline JavaScript full of product-shaped strings never reaches the dataset.

Everything the parser looks for (record tag, record class, record attributes, field classes and
field attributes) comes from ``config.json``.
"""

from __future__ import annotations

from html.parser import HTMLParser

from .util import collapse_ws

VOID_ELEMENTS = frozenset([
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
    "param", "source", "track", "wbr",
])

SKIP_CONTENT_TAGS = frozenset(["script", "style"])


class _Capture(object):
    """One in-progress field extraction."""

    __slots__ = ("field", "base_depth", "html_attrs", "all_text", "primary_text",
                 "children", "child_started")

    def __init__(self, field, base_depth, html_attrs):
        self.field = field
        self.base_depth = base_depth
        self.html_attrs = html_attrs
        self.all_text = []
        self.primary_text = []
        self.children = {}
        self.child_started = False


class CatalogHTMLParser(HTMLParser):
    """Extracts product-like records from a listing page according to the selector config."""

    def __init__(self, selectors):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.record_tag = str(selectors.get("record_tag", "article")).lower()
        self.record_class = selectors.get("record_class")
        self.record_attributes = selectors.get("record_attributes", {}) or {}
        self.fields = selectors.get("fields", {}) or {}

        self.class_to_field = {}
        for field_name, spec in self.fields.items():
            css_class = spec.get("class")
            if css_class:
                self.class_to_field[css_class] = field_name

        self.records = []
        self.current = None
        self.order = 0
        self.stack = []                 # open elements: (tag, attrs)
        self.depth = 0
        self.captures = []              # open field captures, outermost first
        self.skip_depth = 0             # >0 while inside <script>/<style>
        self.stats = {
            "cards_seen": 0,
            "script_style_chars_skipped": 0,
            "recovered_unclosed_fields": [],
            "unmatched_end_tags": 0,
            "stray_text_chars_ignored": 0,
        }

    # -- public ------------------------------------------------------------------------
    def run(self, html_text):
        self.feed(html_text)
        self.close()
        self._finalize_record()
        return self.records, self.stats

    # -- element handling --------------------------------------------------------------
    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attr_map = _attrs_to_map(attrs)

        if tag in SKIP_CONTENT_TAGS:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return

        if self.current is None and not self._is_record_start(tag, attr_map):
            return                                   # outside any card: nothing to collect

        if self._is_record_start(tag, attr_map):
            self._finalize_record()
            self._begin_record(attr_map)
        else:
            self._maybe_open_capture(tag, attr_map)

        self._push(tag, attr_map)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag.lower() not in VOID_ELEMENTS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in SKIP_CONTENT_TAGS:
            self.skip_depth = max(0, self.skip_depth - 1)
            return
        if self.skip_depth:
            return

        index = None
        for position in range(len(self.stack) - 1, -1, -1):
            if self.stack[position][0] == tag:
                index = position
                break
        if index is None:
            if tag != self.record_tag:
                self.stats["unmatched_end_tags"] += 1
        else:
            closed = len(self.stack) - index
            del self.stack[index:]
            self.depth -= closed
        self._close_captures_to_depth(self.depth)

        if tag == self.record_tag:
            self._finalize_record()

    def handle_data(self, data):
        if self.skip_depth:
            if data.strip():
                self.stats["script_style_chars_skipped"] += len(data)
            return
        if self.current is None:
            return
        if self.captures:
            capture = self.captures[-1]
            capture.all_text.append(data)
            if not capture.child_started:
                capture.primary_text.append(data)

    # -- record + field plumbing -------------------------------------------------------
    def _is_record_start(self, tag, attr_map):
        if tag != self.record_tag:
            return False
        if self.record_class is None:
            return True
        return self.record_class in _classes(attr_map)

    def _begin_record(self, attr_map):
        record = {}
        for logical, html_attr in self.record_attributes.items():
            record[logical] = attr_map.get(str(html_attr).lower())
        record["_order"] = self.order
        self.order += 1
        self.current = record
        self.captures = []
        self.stats["cards_seen"] += 1

    def _maybe_open_capture(self, tag, attr_map):
        field_name = None
        for css_class in _classes(attr_map):
            if css_class in self.class_to_field:
                field_name = self.class_to_field[css_class]
                break
        if field_name is None:
            return

        allowed_parent = self.fields[field_name].get("nested_in")
        # Recover from unclosed markup: pop any open field that cannot legally contain this one.
        while self.captures and self.captures[-1].field != allowed_parent:
            self.stats["recovered_unclosed_fields"].append(self.captures[-1].field)
            self._close_capture()

        self.captures.append(_Capture(field_name, self.depth, attr_map))

    def _close_captures_to_depth(self, depth):
        while self.captures and self.captures[-1].base_depth >= depth:
            self._close_capture()

    def _close_capture(self):
        capture = self.captures.pop()
        spec = self.fields.get(capture.field, {})

        primary = collapse_ws("".join(capture.primary_text))
        full = collapse_ws("".join(capture.all_text))
        value = {
            "text": primary or full,
            "full_text": full,
            "attrs": {},
            "children": dict(capture.children),
            "value": None,
        }
        for logical, html_attr in (spec.get("attributes") or {}).items():
            value["attrs"][logical] = capture.html_attrs.get(str(html_attr).lower())
        if spec.get("attribute"):
            value["value"] = capture.html_attrs.get(str(spec["attribute"]).lower())

        if self.captures:
            parent = self.captures[-1]
            parent.children[capture.field] = full
            parent.child_started = True
        if spec.get("nested_in"):
            return                       # nested fields are children, never top-level columns
        if self.current is not None:
            self.current[capture.field] = value

    def _finalize_record(self):
        while self.captures:
            self.stats["recovered_unclosed_fields"].append(self.captures[-1].field)
            self._close_capture()
        if self.current is not None:
            self.records.append(self.current)
            self.current = None

    def _push(self, tag, attr_map):
        if tag in VOID_ELEMENTS:
            return
        self.stack.append((tag, attr_map))
        self.depth += 1


def _attrs_to_map(attrs):
    result = {}
    for name, value in attrs or []:
        result[str(name).lower()] = "" if value is None else value
    return result


def _classes(attr_map):
    return [part for part in collapse_ws(attr_map.get("class", "")).split(" ") if part]


# --------------------------------------------------------------------------------------
def parse_documents(outcomes, selectors, logger):
    """Run the parser over every fetched document. Returns (records, per-source stats)."""
    records = []
    stats = []
    skipped = 0

    for outcome in outcomes:
        parser = CatalogHTMLParser(selectors)
        found, parser_stats = parser.run(outcome.content or "")
        for record in found:
            record["_source"] = outcome.source_id
            record["_source_label"] = outcome.label
            record["_source_mode"] = outcome.mode
            record["_order"] = "{}-{:03d}".format(outcome.source_id, record.get("_order", 0))
        records.extend(found)
        skipped += parser_stats["script_style_chars_skipped"]
        stats.append({
            "source_id": outcome.source_id,
            "records": len(found),
            "cards_seen": parser_stats["cards_seen"],
            "recovered_unclosed_fields": len(parser_stats["recovered_unclosed_fields"]),
            "unmatched_end_tags": parser_stats["unmatched_end_tags"],
            "script_style_chars_skipped": parser_stats["script_style_chars_skipped"],
        })
        logger.info("parse", "{}: {} record(s) from {} card(s); recovered {} unclosed field(s){}".format(
            outcome.source_id, len(found), parser_stats["cards_seen"],
            len(parser_stats["recovered_unclosed_fields"]),
            "; skipped {} chars of inline script/style".format(
                parser_stats["script_style_chars_skipped"])
            if parser_stats["script_style_chars_skipped"] else ""))

    logger.ok("parse", "total raw records: {} (inline JS/CSS ignored: {} chars)".format(
        len(records), skipped))
    return records, stats
