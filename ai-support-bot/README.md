# Brightpath Goods: AI Support Bot (RAG-lite)

A customer-support chatbot that answers questions only from a local
knowledge base, shows the documents it used, and runs with zero third-party
dependencies: Python standard library only, no build step, no API key
required.

It is a complete, self-contained work sample: a real BM25 retriever, a real
OpenAI-compatible LLM client, and a polished single-page chat UI served by the
same process.

```bash
python app.py          # open http://127.0.0.1:8000
```

## What it does

1. Serves a single-page chat UI and a JSON API from one `http.server`
   process (`ThreadingHTTPServer` + a custom `BaseHTTPRequestHandler`).
2. Retrieves the most relevant passages from `knowledge/*.md` using Okapi
   BM25 over an inverted index, with heading field-boosting, synonym expansion
   and light stemming.
3. Answers by sending only those passages to an OpenAI-compatible
   chat-completions endpoint, with a system prompt that forbids outside
   knowledge and requires a citation line.
4. Falls back to a deterministic extractive answer labelled `[MOCK MODE]`
   when no API key is configured, so the demo is always runnable.
5. Cites the source documents under every answer in a collapsible
   "Sources used" panel, with the file name, section and BM25 score.

## Architecture

```
                       ┌──────────────────────────────────────────┐
   browser  ──────────▶│  ThreadingHTTPServer (http.server)       │
   index.html          │                                          │
   (single file,       │   GET  /            → index.html         │
    inline CSS + JS)   │   GET  /api/health  → mode, model, stats │
                       │   POST /api/chat    → {answer, sources}  │
                       └───────────────┬──────────────────────────┘
                                       │
                          ┌────────────▼─────────────┐
                          │  answer_question()       │
                          └────┬──────────────┬──────┘
                               │              │
              ┌────────────────▼───┐   ┌──────▼─────────────────────────┐
              │  BM25Index.search  │   │  call_llm()  (urllib.request)  │
              │  · inverted index  │   │  POST {LLM_BASE_URL}           │
              │  · idf / tf / k1,b │   │       /chat/completions        │
              │  · heading boost   │   │  → live answer + citations     │
              │  · synonym expand  │   └──────┬─────────────────────────┘
              └────────┬───────────┘          │ no LLM_API_KEY / request
                       │ top-k chunks         │ failed
              ┌────────▼───────────┐   ┌──────▼─────────────────────────┐
              │  knowledge/*.md    │   │  extractive_answer()           │
              │  6 help-centre     │   │  sentence scoring over the top  │
              │  documents → 31    │   │  passages, labelled [MOCK MODE] │
              │  indexed chunks    │   └────────────────────────────────┘
              └────────────────────┘
```

Everything above runs in a single `python app.py` process. There is no
database, no cache server, and no network access at startup.

## How the retrieval works

* Chunking: each `##` section of each markdown document becomes one chunk;
  sections longer than 900 characters are split on paragraph, then sentence,
  boundaries so no chunk is diluted.
* Tokenisation: lowercased `[a-z0-9]+`, stop-word removal, then a small
  suffix stemmer (`-ing`, `-ies`, `-al`, `-ed`, `-s`, trailing `e`) so
  *arrival*/*arrive* and *policies*/*policy* collapse together.
* Inverted index: `term → [chunk ids]`, plus per-chunk term frequencies.
  Only chunks that contain at least one query term are ever scored.
* BM25: Okapi BM25 with `k1 = 1.5`, `b = 0.75`, Robertson/Sparck-Jones
  IDF smoothed as `log(1 + (N − df + 0.5) / (df + 0.5))`.
* Heading field boost: section and document titles are folded into each
  chunk's term frequencies at 4× weight (the classic field-boost trick), and
  body length alone drives the length normalisation.
* Synonym expansion: a small hand-written map adds related terms
  (`refund ↔ return`, `courier ↔ parcel ↔ shipping`) at 0.45 weight, so a
  question phrased differently from the documentation still lands.
* Sentence selection (mock mode): retrieved passages are split into
  sentences; each sentence is scored by the IDF mass of the question terms it
  contains, normalised by length, with its section heading in view. Sentences
  far below the best one are dropped rather than padding the reply.

## Running it

```bash
# 1. no dependencies, no build step
python app.py

# 2. open the UI
#    http://127.0.0.1:8000
```

Requires Python 3.7+ (f-strings are avoided, `ThreadingHTTPServer` is used).
Change the port with `--port 9000` or the `PORT` environment variable;
bind a different interface with `--host 0.0.0.0`.

### Self-check

```bash
python selftest.py                                  # in-process, offline
python selftest.py --url http://127.0.0.1:8000      # end-to-end over HTTP
```

The self-check asks nine questions (eight answerable, one out of scope) and
verifies each answer is grounded in the expected document and that the
out-of-scope question is refused. `sample_output.txt` is the real transcript
produced by running it against the live server.

## Mock mode vs live mode

| | MOCK MODE | LIVE |
|---|---|---|
| Trigger | `LLM_API_KEY` unset | `LLM_API_KEY` set |
| Answer | deterministic extractive summary of the retrieved passages | LLM answer grounded in the retrieved passages |
| Label | `[MOCK MODE]` badge in the reply and an amber pill in the header | green LIVE pill + model name |
| Needs internet | no | yes |

If a live call fails (bad key, quota, network down) the app degrades to the
mock answer and says so in the message footer instead of erroring out.

## Pointing it at a real LLM

Configured entirely through environment variables:

| Variable | Default | Meaning |
|---|---|---|
| `LLM_BASE_URL` | `https://api.deepseek.com/v1` | OpenAI-compatible base URL |
| `LLM_API_KEY` | *(unset: MOCK MODE)* | Bearer token |
| `LLM_MODEL` | `deepseek-chat` | Model name |

PowerShell

```powershell
$env:LLM_API_KEY = "sk-..."
$env:LLM_MODEL   = "deepseek-chat"
python app.py
```

bash / zsh

```bash
export LLM_API_KEY=sk-...
export LLM_MODEL=deepseek-chat
python app.py
```

Other OpenAI-compatible endpoints work by changing the base URL:

```bash
# OpenAI
LLM_BASE_URL=https://api.openai.com/v1 LLM_MODEL=gpt-4o-mini LLM_API_KEY=sk-... python app.py
# a local model server (no key needed -> set a dummy value to force LIVE mode)
LLM_BASE_URL=http://127.0.0.1:11434/v1 LLM_MODEL=llama3.1 LLM_API_KEY=local python app.py
```

## HTTP API

| Method | Path | Body | Response |
|---|---|---|---|
| `GET` | `/` | - | the chat UI (`index.html`) |
| `GET` | `/api/health` | - | `{status, mode, model, base_url, documents, chunks, retriever}` |
| `GET` | `/api/kb` | - | every indexed chunk (handy for demos and debugging) |
| `POST` | `/api/chat` | `{"message": "...", "history": [...]}` | `{answer, mode, model, note, latency_ms, sources[]}` |

```bash
curl -s http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Can I return an item after 30 days?"}'
```

## Project layout

```
ai-support-bot/
├── app.py               # server + retrieval + LLM client + mock answers
├── index.html           # single-file chat UI (inline CSS + JS, no CDN)
├── selftest.py          # grounded-answer self-check / transcript generator
├── requirements.txt     # empty: standard library only
├── sample_output.txt    # real transcript from a live run
├── README.md
└── knowledge/           # the fictional client's help centre
    ├── shipping.md      # delivery options, tracking, international, delays
    ├── returns.md       # 30-day window, refund timing, exclusions
    ├── payments.md      # payment methods, instalments, declines, VAT
    ├── warranty.md      # 2-year cover, exclusions, claims, repairs
    ├── contact.md       # hours, channels, escalation
    └── account.md       # order changes, password reset, loyalty points
```

Swapping in a real client's documentation means replacing the files in
`knowledge/`. The index, the chunking and the citations are all derived from
the folder, so nothing else needs to change.

## What a client gets

* A working, dependency-free support assistant that can be dropped on any box
  with Python 3 installed and started with one command.
* Genuine retrieval over their own documentation: not a prompt wrapper. The
  BM25 index, chunking, stemming and scoring are all visible and tunable.
* Answers that are grounded and cited, with a system prompt that refuses to
  invent policy, price or delivery details.
* A no-credential demo mode so stakeholders can click through the product
  before any API key or budget is approved.
* A single-file front end that is trivial to re-skin to a client's brand
  (colours live in one `:root` CSS block) and works on mobile.

## Limitations

* Retrieval is lexical, not semantic. BM25 matches words, not meaning; a
  question using none of the documentation's vocabulary can miss. A production
  build would add embeddings, deliberately out of scope here because it would
  require a third-party dependency.
* Mock mode is extractive. It quotes the best-matching sentences and can
  occasionally surface a true-but-tangential sentence when two passages score
  closely. Live mode does not have this limitation.
* No conversation memory in the retriever. Follow-up questions such as
  "and for Norway?" are not rewritten into standalone queries; the last three
  turns are passed to the LLM, but retrieval only sees the current message.
* Single-process, in-memory index. Rebuilt on start-up; fine for a help
  centre of this size, not for millions of documents.
* No auth, rate limiting or TLS. It is a demo: put it behind a reverse
  proxy before exposing it.
* Conversation history lives in browser memory only; nothing is logged or
  persisted server-side.

## Standard library only

`requirements.txt` is intentionally empty. The whole project imports nothing
outside the Python standard library: `http.server`, `urllib.request`, `json`,
`pathlib`, `math`, `re`, `collections`, `os`, `sys`, `time`, `argparse` and
`textwrap`. No pip install, no virtualenv, no build step, no CDN assets.
