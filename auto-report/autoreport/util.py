"""Small shared helpers: progress logging with per-stage timing, and text/number formatting."""

from __future__ import annotations

import io
import os
import re
import sys
import time
from datetime import datetime

_WS_RE = re.compile(r"\s+")
_NON_PRINTABLE_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


# --------------------------------------------------------------------------------------
# formatting
# --------------------------------------------------------------------------------------
def collapse_ws(value):
    """Collapse every run of whitespace (incl. newlines/nbsp) into one space, and trim."""
    if value is None:
        return ""
    text = str(value).replace("\u00a0", " ").replace("\u2009", " ").replace("\u202f", " ")
    text = _NON_PRINTABLE_RE.sub("", text)
    return _WS_RE.sub(" ", text).strip()


def slugify(value):
    text = re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")
    return text or "item"


def money(value, symbol="$", decimals=2):
    if value is None:
        return "n/a"
    return "{}{:,.{d}f}".format(symbol, float(value), d=decimals)


def num(value, decimals=2):
    if value is None:
        return "n/a"
    return "{:,.{d}f}".format(float(value), d=decimals)


def integer(value):
    if value is None:
        return "n/a"
    return "{:,}".format(int(value))


def pct(part, whole, decimals=1):
    if not whole:
        return "n/a"
    return "{:.{d}f}%".format(100.0 * part / whole, d=decimals)


def truncate(text, limit=70):
    text = collapse_ws(text)
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "\u2026"


# --------------------------------------------------------------------------------------
# timing
# --------------------------------------------------------------------------------------
class Stopwatch(object):
    """Measures elapsed wall-clock time for a named step."""

    def __init__(self):
        self._start = time.perf_counter()
        self.elapsed = 0.0

    def stop(self):
        self.elapsed = time.perf_counter() - self._start
        return self.elapsed


# --------------------------------------------------------------------------------------
# logging
# --------------------------------------------------------------------------------------
LEVELS = {"DEBUG": 10, "INFO": 20, "OK": 25, "WARN": 30, "ERROR": 40}
_LEVEL_TAG = {"DEBUG": "DBG ", "INFO": "INFO", "OK": "OK  ", "WARN": "WARN", "ERROR": "FAIL"}


class Logger(object):
    """Console + file logger that can time stages and print a summary table."""

    def __init__(self, level="INFO", log_path=None):
        self.level = LEVELS.get(str(level).upper(), 20)
        self._start = time.perf_counter()
        self.timings = []           # list of (label, seconds, note)
        self.counts = {"INFO": 0, "WARN": 0, "ERROR": 0}
        self._file = None
        if log_path is not None:
            self.attach_file(log_path)

    def attach_file(self, log_path):
        """Start mirroring every log line into ``log_path`` (used for output/run.log)."""
        if self._file is not None:
            return
        directory = os.path.dirname(os.path.abspath(str(log_path)))
        if directory:
            os.makedirs(directory, exist_ok=True)
        self._file = io.open(str(log_path), "w", encoding="utf-8", newline="\n")

    # -- low level ---------------------------------------------------------------------
    def _stamp(self):
        return "{:7.3f}s".format(time.perf_counter() - self._start)

    def _emit(self, level, stage, message):
        self.counts[level] = self.counts.get(level, 0) + 1
        line = "{} | {} | {:11s} | {}".format(
            self._stamp(), _LEVEL_TAG.get(level, level), stage[:11], message
        )
        stream = sys.stderr if level == "ERROR" else sys.stdout
        try:
            stream.write(line + "\n")
            stream.flush()
        except Exception:                                    # pragma: no cover - encoding
            pass
        if self._file is not None:
            self._file.write(line + "\n")
            self._file.flush()

    def _log(self, level, stage, message):
        if LEVELS.get(level, 20) >= self.level:
            self._emit(level, stage, message)

    # -- public ------------------------------------------------------------------------
    def debug(self, stage, message):
        self._log("DEBUG", stage, message)

    def info(self, stage, message):
        self._log("INFO", stage, message)

    def ok(self, stage, message):
        self._log("OK", stage, message)

    def warn(self, stage, message):
        self._log("WARN", stage, message)

    def error(self, stage, message):
        self._log("ERROR", stage, message)

    def banner(self, text):
        line = "-" * max(0, 78 - len(text))
        self.info("run", "{} {}".format(text, line))

    def stage(self, label, index=None, total=None):
        """Context manager: logs the start, times the block and records the duration."""
        return _Stage(self, label, index, total)

    def note_stage(self, label, seconds, note=""):
        self.timings.append((label, float(seconds), note))

    def summary_table(self):
        if not self.timings:
            return ""
        width = max(len(label) for label, _, _ in self.timings)
        width = max(width, 5)
        rows = ["{:<{w}}  {:>9}  {}".format("STAGE", "TIME", "DETAIL", w=width)]
        rows.append("{:<{w}}  {:>9}  {}".format("-" * width, "-" * 9, "-" * 6, w=width))
        total = 0.0
        for label, seconds, note in self.timings:
            total += seconds
            rows.append("{:<{w}}  {:>8.3f}s  {}".format(label, seconds, note, w=width))
        rows.append("{:<{w}}  {:>8.3f}s  {}".format("TOTAL", total, "", w=width))
        return "\n".join(rows)

    def close(self):
        if self._file is not None:
            try:
                self._file.write("\n" + self.summary_table() + "\n")
                self._file.close()
            except Exception:                                # pragma: no cover
                pass
            self._file = None


class _Stage(object):
    def __init__(self, logger, label, index, total):
        self.logger = logger
        self.label = label
        self.index = index
        self.total = total
        self.watch = None
        self.note = ""

    def __enter__(self):
        self.watch = Stopwatch()
        prefix = "[{}/{}] ".format(self.index, self.total) if self.index else ""
        self.logger.info(self.label, "{}start".format(prefix))
        return self

    def __exit__(self, exc_type, exc, tb):
        seconds = self.watch.stop()
        note = self.note
        if exc_type is not None:
            self.logger.error(self.label, "failed after {:.3f}s: {}".format(seconds, exc))
        self.logger.note_stage(self.label, seconds, note)
        return False


def utc_now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
