#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Self-check and demo-transcript generator for the Brightpath Goods support bot.

    python selftest.py                                  # offline (in-process retrieval + MOCK answers)
    python selftest.py --url http://127.0.0.1:8000      # end-to-end through the running HTTP API

Exit code 0 means every question was answered from the expected source document.
"""

import argparse
import json
import sys
import textwrap
import urllib.request

import app

# question -> the document the answer must be grounded in
CASES = [
    ("How long does standard shipping take?", "shipping.md"),
    ("Do you ship to Norway and are there customs fees?", "shipping.md"),
    ("Can I return an item after 30 days?", "returns.md"),
    ("How long does a refund take to arrive?", "returns.md"),
    ("My card payment was declined, what happens now?", "payments.md"),
    ("What does the 2-year warranty cover?", "warranty.md"),
    ("How do I reset my password?", "account.md"),
    ("What are your support opening hours?", "contact.md"),
    ("What is the capital of France?", None),  # must be refused, not answered
]

RULE = "-" * 78


def via_http(base, question):
    request = urllib.request.Request(
        base.rstrip("/") + "/api/chat",
        data=json.dumps({"message": question}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def report(question, result, expected, failures):
    print(RULE)
    print("Q: " + question)
    print(textwrap.fill(result["answer"], 96, initial_indent="A: ", subsequent_indent="   "))
    print("   mode=%s  model=%s  %d ms" % (result["mode"], result["model"], result["latency_ms"]))
    if result.get("note"):
        print("   note: " + result["note"])
    if result["sources"]:
        print("   sources:")
        for source in result["sources"]:
            print("     [%d] %s > %s   score=%s" % (
                source["n"], source["doc"], source["section"], source["score"]))
            print(textwrap.fill(source["snippet"], 92,
                                initial_indent="         ", subsequent_indent="         "))
    else:
        print("   sources: (none)")

    docs = [s["doc"] for s in result["sources"]]
    if expected is None:
        ok = not docs and "could not find" in result["answer"].lower()
        print("   [%s] correctly refused an out-of-scope question" % ("PASS" if ok else "FAIL"))
    else:
        ok = expected in docs and result["answer"].strip()
        print("   [%s] grounded in %s" % ("PASS" if ok else "FAIL", expected))
    if not ok:
        failures.append(question)
    return ok


def compare_rerank():
    """Stage 1 vs stage 1+2: does reranking actually change the top hit?

    Runs the graded questions through both pipelines and reports hit@1. This is
    the only honest way to claim a reranker helps: measure it, do not assume it.
    """
    graded = [(q, d) for q, d in CASES if d]
    stage1 = stage2 = 0
    flips = []
    for question, expected in graded:
        raw = app.INDEX.search(question, app.TOP_K)
        new = app.rerank(question, raw)
        first_raw = raw[0]["chunk"]["doc"] if raw else None
        first_new = new[0]["chunk"]["doc"] if new else None
        stage1 += first_raw == expected
        stage2 += first_new == expected
        if first_raw != first_new:
            flips.append((question, first_raw, first_new, expected))

    print(RULE)
    print("Retrieval: stage 1 (BM25) vs stage 1+2 (BM25 then rerank)")
    print("  graded questions : %d" % len(graded))
    print("  hit@1  BM25      : %d/%d" % (stage1, len(graded)))
    print("  hit@1  + rerank  : %d/%d" % (stage2, len(graded)))
    if stage1 == stage2:
        print("  -> baseline is already saturated on this set; rerank adds no hit@1 here")

    # Diversity is where a reranker earns its place on a small, easy set:
    # plain BM25 happily fills every slot from one long document.
    docs1 = docs2 = 0.0
    for question, _expected in graded:
        raw = app.INDEX.search(question, app.TOP_K)
        new = app.rerank(question, raw)
        docs1 += len({h["chunk"]["doc"] for h in raw[:3]})
        docs2 += len({h["chunk"]["doc"] for h in new[:3]})
    n = max(1, len(graded))
    print("  distinct docs in top-3  BM25   : %.2f" % (docs1 / n))
    print("  distinct docs in top-3  +rerank: %.2f" % (docs2 / n))
    if flips:
        print("  ordering changed :")
        for question, before, after, expected in flips:
            mark = "gain" if first_new_ok(after, expected) and not first_new_ok(before, expected) else "swap"
            print("    [%s] %-48s %s -> %s  (expected %s)"
                  % (mark, question[:48], before, after, expected))
    return stage1, stage2, len(graded)


def first_new_ok(doc, expected):
    return doc == expected


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", help="base URL of a running server, e.g. http://127.0.0.1:8000")
    args = parser.parse_args()

    print("Brightpath Goods support bot - self check")
    print("retriever: BM25 (k1=%.2f, b=%.2f, heading boost %.1fx) over an inverted index"
          % (app.BM25Index.K1, app.BM25Index.B, app.BM25Index.HEADING_WEIGHT))
    print("index    : %d chunks / %d documents" % (
        len(app.INDEX.chunks), len(set(c["doc"] for c in app.INDEX.chunks))))
    print("target   : %s" % (args.url or "in-process (offline)"))

    compare_rerank()

    failures = []
    for question, expected in CASES:
        result = via_http(args.url, question) if args.url else app.answer_question(question)
        report(question, result, expected, failures)

    print(RULE)
    passed = len(CASES) - len(failures)
    print("RESULT: %d/%d checks passed" % (passed, len(CASES)))
    if failures:
        print("failed: %s" % failures)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
