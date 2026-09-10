#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Brightpath Goods - AI customer support bot ("RAG-lite").

A self-contained retrieval-augmented support assistant. Standard library only:
no pip install, no build step.   python app.py   ->   http://127.0.0.1:8000

Environment variables
    LLM_BASE_URL   OpenAI-compatible base URL (default https://api.deepseek.com/v1)
    LLM_API_KEY    API key; if unset the app runs in MOCK MODE (offline answers)
    LLM_MODEL      Model name (default deepseek-chat)
    PORT           HTTP port (default 8000)
"""

import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
KB_DIR = ROOT / "knowledge"
INDEX_FILE = ROOT / "index.html"

TOP_K = 4
MAX_CHUNK_CHARS = 900
DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-chat"

TOKEN_RE = re.compile(r"[a-z0-9]+")
SENT_RE = re.compile(r"(?<=[.!?])\s+")

STOPWORDS = set(
    """a an and are as at be been being by can could do does for from had has have how
    i if in into is it its me my of on or our should so than that the their them then
    there these this to us was we were what when where which who whom why will with
    would you your""".split()
)

_RAW_SYNONYMS = {
    "refund": ["return", "money back", "reimburse"],
    "return": ["refund", "send back"],
    "shipping": ["delivery", "parcel", "courier", "dispatch"],
    "delivery": ["shipping", "parcel"],
    "parcel": ["package", "shipping"],
    "late": ["delay", "delayed", "not arrived"],
    "broken": ["damaged", "faulty", "defect"],
    "damaged": ["broken", "faulty"],
    "fail": ["declined", "error", "problem"],
    "guarantee": ["warranty"],
    "warranty": ["guarantee", "repair"],
    "cancel": ["cancellation", "stop order"],
    "payment": ["pay", "card", "checkout", "invoice"],
    "coupon": ["promo code", "discount", "voucher"],
    "track": ["tracking", "where is my order"],
    "contact": ["support", "email", "phone", "chat"],
    "support": ["contact", "help", "agent"],
    "password": ["reset", "sign in", "login"],
    "invoice": ["receipt", "vat", "bill"],
    "vat": ["invoice", "tax"],
    "address": ["delivery address", "shipping address"],
    "points": ["loyalty", "rewards", "credit"],
}


def stem(word):
    """Very small suffix stripper - enough to match plurals, -ing and -al forms."""
    for suffix in ("ingly", "edly", "ation", "ies", "ied", "ing", "al", "es", "ed", "s"):
        if word.endswith(suffix) and len(word) > len(suffix) + 2:
            base = word[: -len(suffix)]
            if suffix in ("ies", "ied"):
                base += "y"
            if len(base) > 2 and base[-1] == base[-2] and base[-1] not in "ls":
                base = base[:-1]
            word = base
            break
    if len(word) > 3 and word.endswith("e"):
        word = word[:-1]
    return word


def _build_synonyms(raw):
    out = defaultdict(set)
    for key, values in raw.items():
        for value in values:
            for word in TOKEN_RE.findall(value.lower()):
                out[stem(key)].add(stem(word))
    return {k: sorted(v) for k, v in out.items()}


SYNONYMS = _build_synonyms(_RAW_SYNONYMS)


def tokenize(text):
    return [stem(t) for t in TOKEN_RE.findall(text.lower()) if t not in STOPWORDS]



# --- Knowledge base loading + chunking ---
def _split_long(body, limit=MAX_CHUNK_CHARS):
    """Split an over-long section on paragraph, then sentence, boundaries."""
    if len(body) <= limit:
        return [body]
    parts, current = [], ""
    for para in re.split(r"\n\s*\n", body):
        para = para.strip()
        if not para:
            continue
        if current and len(current) + len(para) + 2 > limit:
            parts.append(current.strip())
            current = ""
        current += para + "\n\n"
    if current.strip():
        parts.append(current.strip())

    out = []
    for part in parts:
        if len(part) <= limit:
            out.append(part)
            continue
        current = ""
        for sentence in SENT_RE.split(part.replace("\n", " ")):
            if current and len(current) + len(sentence) + 1 > limit:
                out.append(current.strip())
                current = ""
            current += sentence + " "
        if current.strip():
            out.append(current.strip())
    return out


def load_chunks(kb_dir=KB_DIR):
    """One chunk per markdown '##' section, further split if it is long."""
    chunks = []
    for path in sorted(kb_dir.glob("*.md")):
        title, section, buf = path.stem.replace("-", " ").title(), "", []

        def flush():
            body = "\n".join(buf).strip()
            if not body:
                return
            for piece in _split_long(body):
                chunks.append(
                    {
                        "doc": path.name,
                        "title": title,
                        "section": section or title,
                        "text": piece,
                    }
                )

        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("## "):
                flush()
                buf.clear()
                section = line[3:].strip()
            elif line.startswith("# "):
                flush()
                buf.clear()
                title = line[2:].strip()
            else:
                buf.append(line)
        flush()
    return chunks



# --- Retrieval: Okapi BM25 over an inverted index ---
class BM25Index:
    """Okapi BM25 ranking over an inverted index (standard library only).

    Document headings are folded into each chunk's term frequencies with a
    weight, which is the classic "field boost" trick: a query word that appears
    in a section heading is a much stronger signal than one buried in a
    paragraph. Body length alone drives the BM25 length normalisation.
    """

    K1 = 1.5
    B = 0.75
    HEADING_WEIGHT = 4.0

    def __init__(self, chunks):
        self.chunks = chunks
        self.postings = defaultdict(list)  # term -> [chunk id]
        self.tf = []  # chunk id -> Counter(term -> weighted freq)
        self.length = []  # chunk id -> body token count
        self.heading = []  # chunk id -> set of heading tokens
        self.avgdl = 1.0
        for cid, chunk in enumerate(chunks):
            body = tokenize(chunk["text"])
            heading = tokenize(chunk["section"] + " " + chunk["title"])
            counts = Counter(body)
            for term in heading:
                counts[term] += self.HEADING_WEIGHT
            self.tf.append(counts)
            self.length.append(len(body) or 1)
            self.heading.append(set(heading))
            for term in counts:
                self.postings[term].append(cid)
        self.n = len(chunks)
        self.avgdl = (sum(self.length) / self.n) if self.n else 1.0

    def idf(self, term):
        df = len(self.postings.get(term, ()))
        return math.log(1.0 + (self.n - df + 0.5) / (df + 0.5))

    def search(self, query, k=TOP_K):
        weights = Counter()
        for term in tokenize(query):
            weights[term] += 1.0
            for synonym in SYNONYMS.get(term, ()):
                weights[synonym] += 0.45  # expanded terms count less

        scores = defaultdict(float)
        for term, query_weight in weights.items():
            ids = self.postings.get(term)
            if not ids:
                continue
            idf = self.idf(term)
            for cid in ids:
                tf = self.tf[cid][term]
                norm = 1 - self.B + self.B * self.length[cid] / self.avgdl
                score = idf * (tf * (self.K1 + 1)) / (tf + self.K1 * norm)
                scores[cid] += query_weight * score

        ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:k]
        return [
            {"cid": cid, "chunk": self.chunks[cid], "score": round(score, 4)}
            for cid, score in ranked
        ]


INDEX = BM25Index(load_chunks())



# --- Answer generation ---
NO_ANSWER = (
    "I could not find anything about that in the Brightpath Goods help center. "
    "Please contact support@brightpath-goods.example or use live chat "
    "(Mon-Fri 08:00-20:00 CET) and a human agent will help you."
)

SYSTEM_PROMPT = """You are the customer support assistant for Brightpath Goods, an online home and kitchen store.

Answer the customer's question using ONLY the numbered knowledge base excerpts provided below.
Rules:
1. If the excerpts do not contain the answer, reply with exactly this sentence: "%s"
2. Never invent prices, delivery times, policies or order details, and never use outside knowledge.
3. Be concise and friendly: 2-4 sentences of plain language. Use bullet points only for step-by-step instructions.
4. Always end your reply with a citation line listing the source files you actually used, for example: "Sources: shipping.md"
""" % NO_ANSWER


def build_context(hits):
    blocks = []
    for i, hit in enumerate(hits, 1):
        chunk = hit["chunk"]
        blocks.append(
            "[%d] file=%s | section=%s\n%s" % (i, chunk["doc"], chunk["section"], chunk["text"])
        )
    return "\n\n".join(blocks)


def extractive_answer(question, hits):
    """Deterministic MOCK MODE answer.

    Extractive summarisation over the retrieved passages. Each sentence is
    scored by the IDF mass of the question terms it contains, normalised by its
    own length. A sentence also "sees" its section heading, so a section titled
    "Support hours" can answer a question about opening hours even though the
    sentence itself repeats few of the question words. The best few sentences
    are returned in reading order; sentences that score far below the best one
    are dropped rather than padding the answer.
    """
    query_terms = set(tokenize(question))
    if not hits or not query_terms:
        return None

    scored, seen = [], set()
    for rank, hit in enumerate(hits[:3]):
        chunk = hit["chunk"]
        heading_hits = len(set(tokenize(chunk["section"])) & query_terms)
        heading = chunk["section"] + " "  # let each sentence see its heading
        for pos, sentence in enumerate(SENT_RE.split(heading + " ".join(chunk["text"].split()))):
            sentence = sentence.strip()
            if len(sentence) < 25 or sentence in seen:
                continue
            tokens = tokenize(sentence)
            overlap = sum(INDEX.idf(t) for t in set(tokens) & query_terms)
            if overlap <= 0:
                continue
            seen.add(sentence)
            text = sentence[len(heading):] if sentence.startswith(heading) else sentence
            scored.append(
                (
                    overlap / math.sqrt(len(tokens)) * (1 + 0.3 * heading_hits)
                    + (0.35 if rank == 0 else 0.0),
                    rank,
                    pos,
                    text,
                )
            )

    if not scored:
        return None
    scored.sort(key=lambda c: (-c[0], c[1], c[2]))
    cutoff = 0.45 * scored[0][0]
    picked = sorted((c for c in scored[:4] if c[0] >= cutoff), key=lambda c: (c[1], c[2]))
    return "[MOCK MODE] " + " ".join(c[3] for c in picked)


def llm_settings():
    return (
        os.environ.get("LLM_BASE_URL", DEFAULT_BASE_URL).rstrip("/"),
        os.environ.get("LLM_API_KEY", "").strip(),
        os.environ.get("LLM_MODEL", DEFAULT_MODEL),
    )


def call_llm(question, hits, history, base_url, api_key, model, timeout=60):
    """Minimal OpenAI-compatible /chat/completions client built on urllib."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for turn in (history or [])[-4:]:
        role = turn.get("role")
        content = (turn.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content[:2000]})
    messages.append(
        {
            "role": "user",
            "content": "Knowledge base excerpts:\n\n%s\n\nCustomer question: %s"
            % (build_context(hits), question),
        }
    )
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 600,
        "stream": False,
    }
    request = urllib.request.Request(
        base_url + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + api_key,
            "User-Agent": "brightpath-support-bot/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"].strip()


def snippet(text, limit=240):
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "\u2026"


def answer_question(question, history=None):
    question = (question or "").strip()
    started = time.time()
    hits = INDEX.search(question, TOP_K)
    base_url, api_key, model = llm_settings()

    note = ""
    if api_key:
        try:
            text = call_llm(question, hits, history, base_url, api_key, model)
            mode, model_used = "live", model
        except Exception as exc:  # network down, bad key, quota, ...
            mode, model_used = "mock", "extractive"
            note = "LLM call failed (%s: %s) - answered offline instead." % (
                type(exc).__name__,
                exc,
            )
            text = extractive_answer(question, hits) or ("[MOCK MODE] " + NO_ANSWER)
    else:
        mode, model_used = "mock", "extractive"
        text = extractive_answer(question, hits) or ("[MOCK MODE] " + NO_ANSWER)
        if not hits:
            note = "No knowledge base passage matched this question."

    return {
        "answer": text,
        "mode": mode,
        "model": model_used,
        "note": note,
        "question": question,
        "latency_ms": int((time.time() - started) * 1000),
        "sources": [
            {
                "n": i,
                "doc": h["chunk"]["doc"],
                "section": h["chunk"]["section"],
                "score": h["score"],
                "snippet": snippet(h["chunk"]["text"]),
            }
            for i, h in enumerate(hits, 1)
        ],
    }



# --- HTTP server ---
class Handler(BaseHTTPRequestHandler):
    server_version = "BrightpathBot/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (time.strftime("%H:%M:%S"), fmt % args))

    def handle_one_request(self):
        # browsers routinely abort requests; that is noise, not an error
        try:
            BaseHTTPRequestHandler.handle_one_request(self)
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            self.close_connection = True

    def _send(self, status, body, content_type):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status, obj):
        self._send(status, json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8")

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            try:
                self._send(200, INDEX_FILE.read_text(encoding="utf-8"), "text/html; charset=utf-8")
            except OSError:
                self._send(500, "index.html is missing", "text/plain; charset=utf-8")
        elif path == "/api/health":
            base_url, api_key, model = llm_settings()
            self._send_json(
                200,
                {
                    "status": "ok",
                    "mode": "live" if api_key else "mock",
                    "model": model if api_key else "extractive",
                    "base_url": base_url if api_key else None,
                    "documents": sorted(p.name for p in KB_DIR.glob("*.md")),
                    "chunks": len(INDEX.chunks),
                    "retriever": "BM25 (k1=1.5, b=0.75) over an inverted index",
                },
            )
        elif path == "/api/kb":
            self._send_json(200, {"chunks": INDEX.chunks})
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self):
        if self.path.split("?")[0] != "/api/chat":
            self._send_json(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            message = payload.get("message", "")
            if not isinstance(message, str) or not message.strip():
                raise ValueError("field 'message' is required")
        except Exception as exc:
            self._send_json(400, {"error": "bad request: %s" % exc})
            return
        try:
            self._send_json(200, answer_question(message, payload.get("history")))
        except Exception as exc:  # never take the demo down
            self._send_json(500, {"error": "%s: %s" % (type(exc).__name__, exc)})


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    for i, arg in enumerate(argv):
        if arg == "--port" and i + 1 < len(argv):
            port = int(argv[i + 1])
        elif arg == "--host" and i + 1 < len(argv):
            host = argv[i + 1]

    base_url, api_key, model = llm_settings()
    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True

    print("Brightpath Goods support bot")
    print("  knowledge base : %d chunks from %d docs" % (len(INDEX.chunks), len(set(
        c["doc"] for c in INDEX.chunks))))
    print("  retriever      : BM25 inverted index, top-%d" % TOP_K)
    if api_key:
        print("  mode           : LIVE  (%s @ %s)" % (model, base_url))
    else:
        print("  mode           : MOCK  (no LLM_API_KEY set - offline extractive answers)")
    print("  serving        : http://%s:%d" % (host, port))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
