"""Fetch layer.

A genuine ``urllib.request`` HTTP client: browser-like User-Agent, timeouts, retries with
exponential backoff + jitter, ``Retry-After`` support and polite per-host rate limiting.

It also solves the practical problem every scraping demo hits: the demo has to run when the
target site is unreachable. Each source may declare a local ``fixture``; in ``auto`` mode the
fetcher attempts the real request first and *transparently* falls back to the fixture, logging
exactly which path it took. Nothing is faked: the HTTP code is real and is used whenever the
network is available.
"""

from __future__ import annotations

import os
import random
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

from .util import Stopwatch, integer


class FetchError(Exception):
    """Raised when a source could not be retrieved by any permitted route."""


class FetchOutcome(object):
    """Result of retrieving one configured source."""

    __slots__ = ("source_id", "label", "url", "mode", "status", "attempts",
                 "elapsed", "content", "error", "fixture_path", "encoding")

    def __init__(self, **kwargs):
        for slot in self.__slots__:
            setattr(self, slot, kwargs.get(slot))

    @property
    def bytes(self):
        return len(self.content.encode("utf-8")) if self.content else 0

    @property
    def used_network(self):
        return self.mode == "network"

    def describe(self):
        return "{} [{}, {} chars, {:.2f}s]".format(
            self.source_id, self.mode, integer(self.bytes), self.elapsed or 0.0)


# --------------------------------------------------------------------------------------
# rate limiting
# --------------------------------------------------------------------------------------
class RateLimiter(object):
    """Enforces a minimum interval between requests to the same host."""

    def __init__(self, min_interval_seconds):
        self.min_interval = max(0.0, float(min_interval_seconds or 0.0))
        self._last = {}

    def wait(self, url, logger=None):
        host = urllib.parse.urlsplit(url).hostname or "?"
        previous = self._last.get(host)
        now = time.monotonic()
        slept = 0.0
        if previous is not None:
            remaining = self.min_interval - (now - previous)
            if remaining > 0:
                slept = remaining
                if logger:
                    logger.debug("fetch", "rate limit: sleeping {:.2f}s before next {!s} request"
                                 .format(slept, host))
                time.sleep(remaining)
        self._last[host] = time.monotonic()
        return slept


class ReachabilityCache(object):
    """Caches a cheap TCP probe per host so an unreachable site is not retried per source."""

    def __init__(self, timeout_seconds):
        self.timeout = float(timeout_seconds or 1.5)
        self._results = {}

    def probe(self, url, logger=None):
        host = urllib.parse.urlsplit(url).hostname
        if not host:
            return False, "no host in URL"
        if host in self._results:
            return self._results[host]
        port = urllib.parse.urlsplit(url).port or (443 if url.startswith("https") else 80)
        watch = Stopwatch()
        try:
            with socket.create_connection((host, port), timeout=self.timeout):
                result = (True, "tcp connect ok in {:.2f}s".format(watch.stop()))
        except Exception as exc:                                   # noqa: BLE001 - any failure means "down"
            result = (False, "{}: {}".format(type(exc).__name__, exc))
        self._results[host] = result
        if logger:
            logger.info("fetch", "reachability probe {!s}:{} -> {}".format(
                host, port, "UP" if result[0] else "DOWN (" + result[1] + ")"))
        return result


# --------------------------------------------------------------------------------------
# HTTP fetcher
# --------------------------------------------------------------------------------------
class HttpFetcher(object):
    """Real HTTP GET with retries, backoff and polite rate limiting."""

    RETRY_STATUS = frozenset([408, 425, 429, 500, 502, 503, 504])

    def __init__(self, fetch_config, logger=None):
        self.cfg = fetch_config or {}
        self.log = logger
        self.rate_limiter = RateLimiter(self.cfg.get("rate_limit_min_interval_seconds", 1.0))
        self.reachability = ReachabilityCache(self.cfg.get("probe_timeout_seconds", 1.5))
        self.timeout = float(self.cfg.get("timeout_seconds", 8))
        self.max_retries = int(self.cfg.get("max_retries", 2))
        self.backoff_base = float(self.cfg.get("backoff_base_seconds", 0.6))
        self.backoff_max = float(self.cfg.get("backoff_max_seconds", 6.0))
        self.headers = {
            "User-Agent": self.cfg.get("user_agent", "AutoReportBot/1.0"),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": self.cfg.get("accept_language", "en-US,en;q=0.9"),
            "Accept-Encoding": "identity",
            "Connection": "close",
        }
        self._context = ssl.create_default_context()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=self._context)
        )

    # -- single attempt -----------------------------------------------------------------
    def _attempt(self, url):
        request = urllib.request.Request(url, headers=self.headers, method="GET")
        response = self._opener.open(request, timeout=self.timeout)
        try:
            status = getattr(response, "status", None) or response.getcode()
            charset = response.headers.get_content_charset() or "utf-8"
            payload = response.read()
        finally:
            response.close()
        try:
            text = payload.decode(charset, errors="replace")
        except LookupError:
            text = payload.decode("utf-8", errors="replace")
        return text, int(status or 200), dict(response.headers)

    def _backoff(self, attempt, retry_after=None):
        if retry_after is not None:
            delay = min(float(retry_after), self.backoff_max)
        else:
            delay = min(self.backoff_base * (2 ** attempt), self.backoff_max)
            delay = delay * (0.7 + 0.6 * random.random())          # jitter, avoids thundering herd
        return max(0.0, delay)

    def fetch(self, url):
        """GET ``url``. Returns (text, status, attempts). Raises :class:`FetchError`."""
        last_error = None
        for attempt in range(self.max_retries + 1):
            if attempt:
                delay = self._backoff(attempt - 1, retry_after=getattr(self, "_retry_after", None))
                if self.log:
                    self.log.warn("fetch", "retry {}/{} for {} in {:.2f}s (last error: {})".format(
                        attempt, self.max_retries, url, delay, last_error))
                time.sleep(delay)
            self.rate_limiter.wait(url, self.log)
            watch = Stopwatch()
            try:
                text, status, headers = self._attempt(url)
                if status in self.RETRY_STATUS:
                    self._retry_after = _parse_retry_after(headers.get("Retry-After"))
                    last_error = "HTTP {} {}".format(status, _reason(status))
                    continue
                if self.log:
                    self.log.info("fetch", "GET {} -> HTTP {} ({} chars in {:.2f}s)".format(
                        url, status, integer(len(text)), watch.stop()))
                return text, status, attempt + 1
            except urllib.error.HTTPError as exc:
                self._retry_after = _parse_retry_after(exc.headers.get("Retry-After")
                                                       if exc.headers else None)
                last_error = "HTTP {} {}".format(exc.code, exc.reason)
                if exc.code not in self.RETRY_STATUS:
                    break
            except urllib.error.URLError as exc:
                last_error = "URLError: {}".format(exc.reason)
                self._retry_after = None
            except (socket.timeout, TimeoutError) as exc:
                last_error = "timeout after {}s ({})".format(self.timeout, exc)
                self._retry_after = None
            except Exception as exc:                               # noqa: BLE001
                last_error = "{}: {}".format(type(exc).__name__, exc)
                self._retry_after = None
        raise FetchError("could not fetch {} after {} attempt(s): {}".format(
            url, self.max_retries + 1, last_error))


def _parse_retry_after(value):
    if not value:
        return None
    try:
        return max(0.0, float(str(value).strip()))
    except ValueError:
        return None


_REASONS = {408: "Request Timeout", 425: "Too Early", 429: "Too Many Requests",
            500: "Internal Server Error", 502: "Bad Gateway", 503: "Service Unavailable",
            504: "Gateway Timeout", 403: "Forbidden", 404: "Not Found"}


def _reason(status):
    return _REASONS.get(status, "")


# --------------------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------------------
def load_fixture(path, encoding="utf-8"):
    """Read a bundled fixture file. Falls back to latin-1 if the declared encoding lies."""
    if not os.path.isfile(path):
        raise FetchError("fixture not found: {}".format(path))
    try:
        with open(path, "r", encoding=encoding or "utf-8") as handle:
            return handle.read()
    except UnicodeDecodeError:
        with open(path, "r", encoding="latin-1") as handle:
            return handle.read()


# --------------------------------------------------------------------------------------
# orchestration
# --------------------------------------------------------------------------------------
def collect_sources(config, logger, mode_override=None):
    """Retrieve every configured source. Returns a list of :class:`FetchOutcome`."""
    fetch_cfg = config.section("fetch")
    mode = (mode_override or fetch_cfg.get("mode", "auto")).lower()
    fetcher = HttpFetcher(fetch_cfg, logger)
    outcomes = []

    logger.info("fetch", "mode={!r} sources={} user-agent={!r}".format(
        mode, len(fetch_cfg.get("sources", [])), fetch_cfg.get("user_agent", "")[:48]))

    for source in fetch_cfg.get("sources", []):
        source_id = source.get("id", "?")
        label = source.get("label", source_id)
        url = source.get("url")
        fixture_path = config.source_fixture_path(source)
        encoding = fetch_cfg.get("fixture_encoding", "utf-8")
        watch = Stopwatch()

        if mode == "offline":
            outcomes.append(_from_fixture(source_id, label, url, fixture_path, encoding,
                                          "fixture-local", watch.stop(),
                                          "mode=offline: network skipped by configuration", logger))
            continue

        if url:
            reachable, why = fetcher.reachability.probe(url, logger)
            if reachable:
                try:
                    text, status, attempts = fetcher.fetch(url)
                    outcomes.append(FetchOutcome(
                        source_id=source_id, label=label, url=url, mode="network", status=status,
                        attempts=attempts, elapsed=watch.stop(), content=text, error=None,
                        fixture_path=fixture_path, encoding=encoding))
                    continue
                except FetchError as exc:
                    if mode == "online":
                        raise
                    if not fixture_path:
                        raise
                    logger.warn("fetch", "{}: live fetch failed ({}); using local fixture".format(
                        source_id, exc))
                    outcomes.append(_from_fixture(source_id, label, url, fixture_path, encoding,
                                                  "fixture-fallback", watch.stop(),
                                                  "live fetch failed: {}".format(exc), logger))
                    continue
            else:
                if mode == "online":
                    raise FetchError("{} unreachable and fetch.mode='online' ({}).".format(url, why))
                logger.warn("fetch", "{}: host unavailable ({}); using local fixture".format(
                    source_id, why))
                outcomes.append(_from_fixture(source_id, label, url, fixture_path, encoding,
                                              "fixture-fallback", watch.stop(),
                                              "host unreachable: {}".format(why), logger))
                continue

        # No URL configured at all: fixture-only source.
        outcomes.append(_from_fixture(source_id, label, url, fixture_path, encoding,
                                      "fixture-local", watch.stop(),
                                      "no url configured: fixture-only source", logger))

    return outcomes


def _from_fixture(source_id, label, url, fixture_path, encoding, mode, elapsed, reason, logger):
    if not fixture_path:
        raise FetchError("source {!r} has no fixture to fall back to".format(source_id))
    text = load_fixture(fixture_path, encoding)
    logger.info("fetch", "{}: loaded fixture {} ({} chars) [{}, {:.2f}s]".format(
        source_id, os.path.basename(fixture_path), integer(len(text)), mode, elapsed))
    return FetchOutcome(source_id=source_id, label=label, url=url, mode=mode, status=None,
                        attempts=0, elapsed=elapsed, content=text, error=reason,
                        fixture_path=fixture_path, encoding=encoding)
