#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Research agent: query -> search -> fetch -> extract -> report with citations.

Standard library only (urllib + html.parser + re). No API key required.

    python research.py --query "python asyncio best practices"
    python research.py --urls https://docs.python.org/3/library/asyncio.html
    python research.py --query "..." --top 3 --out notes.md

Why it is built this way:

1. **Every sentence carries its source.** Extraction keeps (sentence, url)
   pairs from the start, so the report cannot end up with an unattributed
   claim. A summary you cannot trace back is worse than no summary.

2. **Fetch failures are reported, not silently dropped.** If 2 of 5 pages
   fail, the report says so. A silent partial result reads like a complete one.

3. **Scoring is transparent.** Sentences are ranked by coverage of query terms
   weighted by document frequency over *this* result set, plus a small prior
   for early sentences. No model, no magic — you can print the scores.
"""

import argparse
import html as htmllib
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
TIMEOUT = 20
MAX_PAGE_BYTES = 900_000

STOP = set("""
a an the and or but if then than that this these those of to in on for with without
is are was were be been being do does did have has had it its as at by from into
can could should would may might will just also more most some such no not only
你 我 他 她 它 的 了 和 与 是 在 有 不 就 也 都 而 及 或 被 把 对 从 到 之 其
""".split())

SENT_SPLIT = re.compile(r"(?<=[.!?。！？])\s+|\n{2,}")

# Boilerplate that survives HTML stripping but carries no content.
NOISE = re.compile(
    r"(?:welcome to|javascript|cookie|subscribe|newsletter|sign in|log in|"
    r"登录|注册|版权所有|copyright|隐私政策|点击这里|扫码|关注我们|"
    r"本页显示|备用内容|广告)",
    re.I)


def is_noise(sentence, page_title):
    if NOISE.search(sentence):
        return True
    # A sentence that opens with the page title is the title again, not content.
    if page_title and sentence[:20] and sentence.startswith(page_title[:20]):
        return True
    return False


# --------------------------------------------------------------------------
# Step 1: search (Bing HTML; no key, no JS)
# --------------------------------------------------------------------------

def search_bing(query, limit=5):
    """Return [{title, url}] from a Bing results page."""
    url = "https://www.bing.com/search?" + urllib.parse.urlencode({"q": query})
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        page = response.read().decode("utf-8", errors="ignore")
    hits, seen = [], set()
    pattern = re.compile(r'<h2>\s*<a[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a>', re.S)
    for match in pattern.finditer(page):
        link = match.group(1)
        title = re.sub(r"<[^>]+>", "", match.group(2)).strip()
        host = urllib.parse.urlparse(link).netloc
        if not title or host.endswith("bing.com") or link in seen:
            continue
        seen.add(link)
        hits.append({"title": htmllib.unescape(title), "url": link})
        if len(hits) >= limit:
            break
    return hits


# --------------------------------------------------------------------------
# Step 2: fetch + strip to text
# --------------------------------------------------------------------------

class TextExtractor(HTMLParser):
    """Collect visible text, skipping script/style/nav/footer/aside."""

    SKIP = {"script", "style", "noscript", "nav", "footer", "aside", "header",
            "form", "svg", "iframe", "video", "audio"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth_skip = 0
        self.parts = []
        self.title = ""
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self.in_title = True
        if tag in self.SKIP:
            self.depth_skip += 1

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        if tag in self.SKIP and self.depth_skip:
            self.depth_skip -= 1

    def handle_data(self, data):
        if self.in_title:
            self.title += data.strip() + " "
        elif not self.depth_skip and data.strip():
            self.parts.append(data.strip())


def fetch_text(url):
    request = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        raw = response.read(MAX_PAGE_BYTES)
        charset = response.headers.get_content_charset() or "utf-8"
    page = raw.decode(charset, errors="ignore")
    parser = TextExtractor()
    parser.feed(page)
    text = " ".join(parser.parts)
    return re.sub(r"\s{2,}", " ", text), re.sub(r"\s{2,}", " ", parser.title).strip()


# --------------------------------------------------------------------------
# Step 3: sentence-level extraction with document-frequency weighting
# --------------------------------------------------------------------------

def terms(text):
    """Latin words stay whole; CJK runs become character bigrams.

    Bigrams are the cheap way to stay language-agnostic without a segmenter:
    "事件循环" and "循环事件" both produce overlapping pairs, so a sentence
    mentioning only "循环" still matches a query that said "事件循环".
    """
    out = []
    for word in re.findall(r"[a-zA-Z][a-zA-Z0-9_+#.-]{1,}", text.lower()):
        if word not in STOP:
            out.append(word)
    for run in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        for i in range(len(run) - 1):
            bigram = run[i:i + 2]
            if bigram not in STOP:
                out.append(bigram)
    return out


def split_sentences(text, min_len=40):
    out = []
    for chunk in SENT_SPLIT.split(text):
        chunk = chunk.strip()
        if min_len <= len(chunk) <= 400:
            out.append(chunk)
    return out


def extract(pages, query, per_page=2):
    """Return [{sentence, url, title, score}] — the report is built from this."""
    query_terms = set(terms(query))
    if not query_terms:
        return []

    # document frequency over this result set (not a global corpus)
    df = {}
    docs = []
    for page in pages:
        sents = split_sentences(page["text"])
        doc_terms = set()
        for s in sents:
            doc_terms |= set(terms(s))
        docs.append((page, sents, doc_terms))
        for t in doc_terms:
            df[t] = df.get(t, 0) + 1

    n = max(1, len(docs))
    scored = []
    for page, sents, _doc_terms in docs:
        local = []
        for pos, sentence in enumerate(sents):
            if is_noise(sentence, page["title"]):
                continue
            st = set(terms(sentence))
            if not st & query_terms:
                continue
            # Require more than a single incidental term overlap, but scale the
            # bar down as the query grows (a 8-term query rarely appears whole).
            coverage = len(st & query_terms) / len(query_terms)
            floor = min(0.5, max(0.15, 2.0 / len(query_terms)))
            if len(query_terms) > 1 and coverage < floor:
                continue
            weight = sum(1.0 + (1.0 - df[t] / n) for t in (st & query_terms))
            prior = 1.0 / (1.0 + pos / 10.0)
            score = coverage * weight * (0.6 + 0.4 * prior)
            local.append({"sentence": sentence, "url": page["url"],
                          "title": page["title"], "score": round(score, 4)})
        local.sort(key=lambda x: -x["score"])
        scored.extend(local[:per_page])
    scored.sort(key=lambda x: -x["score"])
    return scored


# --------------------------------------------------------------------------
# Step 4: compose
# --------------------------------------------------------------------------

def compose(query, hits, notes, failures, elapsed):
    lines = ["# Research: %s" % query, "",
             "> Generated by `research.py` in %.1fs · %d/%d sources fetched"
             % (elapsed, len(hits) - len(failures), len(hits)), ""]

    by_url = {}
    for note in notes:
        by_url.setdefault(note["url"], []).append(note)

    lines += ["## Sources", ""]
    for i, hit in enumerate(hits, 1):
        lines.append("%d. [%s](%s)" % (i, hit["title"], hit["url"]))
    lines.append("")

    lines += ["## Key points (each traceable to a source)", ""]
    for hit in hits:
        selected = by_url.get(hit["url"], [])
        if not selected:
            continue
        lines.append("### %s" % hit["title"])
        lines.append("")
        for note in selected:
            lines.append("- %s" % note["sentence"].strip())
            lines.append("  \n  — [%s](%s)" % (hit["title"], hit["url"]))
        lines.append("")

    if failures:
        lines += ["## Not fetched", ""]
        for url, reason in failures:
            lines.append("- %s — `%s`" % (url, reason))
        lines.append("")
        lines.append("> A partial report. Do not read this as complete coverage.")
        lines.append("")

    return "\n".join(lines)


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------

def run(query, urls, top, out_path):
    started = time.time()
    hits, failures = [], []

    if urls:
        for url in urls:
            hits.append({"title": url, "url": url})
    else:
        print("[1/4] search  %s" % query)
        try:
            hits = search_bing(query, top)
        except Exception as exc:
            print("      search failed: %s: %s" % (type(exc).__name__, exc))
            return 2
        if not hits:
            print("      no results")
            return 2
        for hit in hits:
            print("      - %s" % hit["url"])

    print("[2/4] fetch   %d page(s)" % len(hits))
    pages = []
    for hit in hits:
        try:
            text, title = fetch_text(hit["url"])
            if len(text) < 200:
                raise ValueError("too little text (%d chars)" % len(text))
            if title:
                hit["title"] = title
            pages.append({"title": hit["title"], "url": hit["url"], "text": text})
            print("      ok   %5d chars  %s" % (len(text), hit["url"]))
        except Exception as exc:
            failures.append((hit["url"], "%s: %s" % (type(exc).__name__, exc)))
            print("      fail %s  (%s)" % (hit["url"], type(exc).__name__))

    if not pages:
        print("      nothing fetched; aborting")
        return 2

    print("[3/4] extract query terms over %d page(s)" % len(pages))
    notes = extract(pages, query or " ".join(p["title"] for p in pages))
    print("      %d sentence(s) kept" % len(notes))

    print("[4/4] compose")
    report = compose(query, hits, notes, failures,
                     time.time() - started)
    with open(out_path, "w", encoding="utf-8") as handle:
        handle.write(report)
    print("      wrote %s (%d bytes)" % (out_path, len(report.encode("utf-8"))))
    return 0


def main():
    ap = argparse.ArgumentParser(description="Research agent (stdlib only)")
    ap.add_argument("--query", default="")
    ap.add_argument("--urls", nargs="*", default=[])
    ap.add_argument("--top", type=int, default=4)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    if not args.query and not args.urls:
        ap.error("need --query or --urls")

    slug = re.sub(r"[^a-z0-9]+", "-", (args.query or "urls").lower()).strip("-")[:50]
    out_path = args.out or ("research-%s.md" % (slug or "notes"))
    return run(args.query, args.urls, args.top, out_path)


if __name__ == "__main__":
    sys.exit(main())
