"""Helpers shared by all source adapters: URL canonicalization, the RawItem contract, a guarded
HTTP client (SSRF checks, size caps, throttling, retries), robots.txt checks and full-text
extraction (PLAN Phase 2, §11.3, §11.6)."""

import email.utils
import hashlib
import ipaddress
import json
import logging
import socket
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpcore
import httpx
import trafilatura
from pydantic import BaseModel, Field, field_validator
from tenacity import (
    RetryCallState,
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

log = logging.getLogger(__name__)

USER_AGENT = "NewsDC/1.0 (+https://github.com/shubhambgp/news-dc)"

# Query parameters that only track the click, never select content. Matched case-insensitively.
TRACKING_PARAMS = frozenset(
    {
        "fbclid",
        "gclid",
        "dclid",
        "gbraid",
        "wbraid",
        "msclkid",
        "yclid",
        "igshid",
        "mc_cid",
        "mc_eid",
        "_hsenc",
        "_hsmi",
        "mkt_tok",
        "ref",
        "ref_src",
        "ref_url",
    }
)
TRACKING_PREFIXES = ("utm_",)
DEFAULT_PORTS = {"http": 80, "https": 443}


def _is_tracking(key: str) -> bool:
    k = key.lower()
    return k in TRACKING_PARAMS or k.startswith(TRACKING_PREFIXES)


def canonicalize_url(url: str) -> str:
    """Normalize a URL for exact-duplicate detection (PLAN §11.3).

    Does: lowercase scheme and host, drop `www.`, drop userinfo, drop the default port,
    drop the fragment, drop tracking params, sort the remaining params, drop a trailing slash.
    Does not: change http to https, change path case, or drop meaningful params.
    Raises ValueError for non-http(s) or host-less URLs.
    """
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    if scheme not in DEFAULT_PORTS:
        raise ValueError(f"unsupported URL scheme: {scheme or '(none)'}")
    host = (parts.hostname or "").rstrip(".")  # .hostname is already lowercased
    if not host:
        raise ValueError("URL has no host")
    host = host.removeprefix("www.")
    if ":" in host:  # IPv6 literal
        host = f"[{host}]"
    port = parts.port  # raises ValueError on a malformed port
    netloc = host if port in (None, DEFAULT_PORTS[scheme]) else f"{host}:{port}"

    path = parts.path or "/"
    if len(path) > 1:
        path = path.rstrip("/") or "/"

    # Work on raw "k=v" segments so values keep their exact original encoding.
    params = [p for p in parts.query.split("&") if p and not _is_tracking(p.split("=", 1)[0])]
    return urlunsplit((scheme, netloc, path, "&".join(sorted(params)), ""))


def url_hash(canonical_url: str) -> str:
    """sha256 hex of an already-canonical URL; stored in the UNIQUE `items.url_hash` column."""
    return hashlib.sha256(canonical_url.encode()).hexdigest()


def content_hash(title: str, body: str | None) -> str:
    """Secondary duplicate signal (§11.3): sha256 of the case- and whitespace-normalized text."""
    text = " ".join(f"{title} {body or ''}".lower().split())
    return hashlib.sha256(text.encode()).hexdigest()


def host_of(url: str) -> str:
    return (urlsplit(url).hostname or "").removeprefix("www.")


# --- untrusted text --------------------------------------------------------------------------


class _TextOnly(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in ("script", "style"):
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    """Plain text from untrusted HTML: tags dropped, script/style content dropped (§11.6)."""
    p = _TextOnly()
    p.feed(html)
    p.close()
    return " ".join(" ".join(p.parts).split())


DESCRIPTION_MAX_CHARS = 2000
FULLTEXT_MAX_CHARS = 6000


class RawItem(BaseModel):
    """What a source adapter produces for one piece of content (PLAN Phase 2).

    Adapters yield plain dicts; the runner validates them here, so one bad row is counted as
    failed instead of aborting the page.
    """

    title: str = Field(min_length=1, max_length=1000)
    url: str
    description: str | None = None
    publisher: str | None = None
    author: str | None = None
    published_at: datetime | None = None
    source_tags: list[str] = Field(default_factory=list)
    points: int | None = Field(default=None, ge=0)
    comments_count: int | None = Field(default=None, ge=0)
    discussion_url: str | None = None
    related_links: list[dict[str, Any]] = Field(default_factory=list)
    external_id: str | None = Field(default=None, max_length=500)

    @field_validator("title", mode="before")
    @classmethod
    def _title(cls, v: Any) -> Any:
        return html_to_text(v) if isinstance(v, str) else v

    @field_validator("description", mode="before")
    @classmethod
    def _description(cls, v: Any) -> Any:
        if not isinstance(v, str):
            return v
        return html_to_text(v)[:DESCRIPTION_MAX_CHARS] or None

    @field_validator("url")
    @classmethod
    def _url(cls, v: str) -> str:
        v = v.strip()
        if any(ord(c) < 32 or ord(c) == 127 for c in v):  # urlsplit drops them; we'd store them
            raise ValueError("control character in URL")
        canonicalize_url(v)  # raises ValueError for unusable URLs
        return v

    @field_validator("published_at")
    @classmethod
    def _utc(cls, v: datetime | None) -> datetime | None:
        if v is None:
            return None
        return v.replace(tzinfo=UTC) if v.tzinfo is None else v.astimezone(UTC)

    @field_validator("source_tags")
    @classmethod
    def _tags(cls, v: list[str]) -> list[str]:
        return list(dict.fromkeys(t.strip()[:100] for t in v if t and t.strip()))[:30]

    @property
    def canonical_url(self) -> str:
        return canonicalize_url(self.url)


# --- guarded HTTP ----------------------------------------------------------------------------


class FetchError(Exception):
    pass


class PermanentFetchError(FetchError):
    """Not worth retrying: 4xx, unsafe URL, oversize body, unparseable response."""


class UnsafeURLError(PermanentFetchError):
    pass


class TransientFetchError(FetchError):
    """Worth retrying: 429, 5xx, or a rate-limit 403. `retry_after` is in seconds."""

    def __init__(self, message: str, retry_after: float = 0.0) -> None:
        super().__init__(message)
        self.retry_after = retry_after


MAX_REDIRECTS = 5
MAX_BYTES = 5_000_000
MAX_RETRY_AFTER = 120.0
FETCH_DEADLINE = 60.0  # seconds per request; the httpx timeout only bounds each read
TRANSIENT_STATUSES = frozenset({429, 500, 502, 503, 504})
# NAT64 prefixes embed an IPv4 address; Python counts 64:ff9b::/96 as global.
NAT64 = (ipaddress.ip_network("64:ff9b::/96"), ipaddress.ip_network("64:ff9b:1::/48"))


def _resolve(host: str, port: int) -> list[str]:
    return [str(ai[4][0]) for ai in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)]


def _public_addrs(host: str, port: int) -> list[str]:
    """Every address `host` resolves to; UnsafeURLError if any of them is not public."""
    try:
        addrs = _resolve(host, port)
    except (OSError, ValueError, UnicodeError) as exc:
        raise PermanentFetchError(f"cannot resolve {host}: {exc}") from exc
    for addr in addrs:
        ip = ipaddress.ip_address(addr.split("%", 1)[0])
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        if not ip.is_global or ip.is_multicast or any(ip in net for net in NAT64):
            raise UnsafeURLError(f"{host} resolves to non-public address {ip}")
    return addrs


def check_public_url(url: str) -> None:
    """SSRF guard (§11.6): http(s) only, and every address the host resolves to is public.
    The connection itself is pinned to checked addresses by `_PinnedBackend`."""
    parts = urlsplit(url)
    if parts.scheme not in DEFAULT_PORTS or not parts.hostname:
        raise UnsafeURLError(f"unsupported URL: {url[:200]}")
    try:
        port = parts.port or DEFAULT_PORTS[parts.scheme]
    except ValueError as exc:
        raise PermanentFetchError(f"bad port in {url[:200]}") from exc
    _public_addrs(parts.hostname, port)


class _PinnedBackend(httpcore.SyncBackend):
    """Resolves, checks and connects to the same address, so a DNS answer that changes after
    `check_public_url` (rebinding) can't point the connection at an internal host. TLS still
    uses the hostname for SNI and certificate checks (httpcore passes it to start_tls)."""

    def connect_tcp(
        self, host: str, port: int, *args: Any, **kwargs: Any
    ) -> httpcore.NetworkStream:
        error: Exception | None = None
        for addr in _public_addrs(host, port):  # in order, like socket.create_connection
            try:
                return super().connect_tcp(addr, port, *args, **kwargs)
            except (httpcore.ConnectError, httpcore.ConnectTimeout) as exc:
                error = exc
        raise error or httpcore.ConnectError(f"no address for {host}")


def _retry_after(headers: httpx.Headers) -> float:
    value = headers.get("retry-after")
    if value:
        if value.strip().isdigit():
            return float(value)
        try:
            return max(0.0, email.utils.parsedate_to_datetime(value).timestamp() - time.time())
        except (TypeError, ValueError):
            return 0.0
    reset = headers.get("x-ratelimit-reset")  # GitHub: epoch seconds
    if reset and reset.isdigit():
        return max(0.0, float(reset) - time.time())
    return 0.0


def _raise_for_status(r: httpx.Response) -> None:
    s = r.status_code
    if s < 300 or s == 304:
        return
    rate_limited_403 = s == 403 and (
        r.headers.get("x-ratelimit-remaining") == "0" or "retry-after" in r.headers
    )
    if s in TRANSIENT_STATUSES or rate_limited_403:
        raise TransientFetchError(f"HTTP {s}", _retry_after(r.headers))
    raise PermanentFetchError(f"HTTP {s}")


_backoff = wait_random_exponential(multiplier=1, max=30)


def _wait(state: RetryCallState) -> float:
    exc = state.outcome.exception() if state.outcome else None
    hinted = exc.retry_after if isinstance(exc, TransientFetchError) else 0.0
    return max(min(hinted, MAX_RETRY_AFTER), _backoff(state))


@dataclass(frozen=True)
class Fetched:
    url: str  # final URL after redirects
    status: int
    headers: httpx.Headers
    content: bytes

    def json(self) -> Any:
        try:
            return json.loads(self.content)
        except ValueError as exc:
            raise PermanentFetchError(f"invalid JSON from {self.url[:200]}") from exc

    @property
    def text(self) -> str:
        content_type = {"content-type": self.headers.get("content-type", "")}
        charset = httpx.Response(200, headers=content_type).charset_encoding or "utf-8"
        try:
            return self.content.decode(charset, errors="replace")
        except LookupError:  # unknown charset name from an untrusted server
            return self.content.decode("utf-8", errors="replace")


class Http:
    """httpx wrapper used for every outbound request.

    Redirects are followed by hand so each hop passes the SSRF check. Bodies are size-capped.
    Requests are spaced to `rpm` per minute (thread-safe). Transient failures are retried with
    jittered exponential backoff that honours Retry-After, up to `attempts` tries.
    """

    def __init__(
        self,
        *,
        rpm: float = 0,
        timeout: float = 20.0,
        attempts: int = 4,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        transport = httpx.HTTPTransport()
        # httpx has no public hook for this; test_connections_are_pinned_to_checked_addresses
        # fails if an upgrade moves the attribute.
        transport._pool._network_backend = _PinnedBackend()
        self._client = httpx.Client(
            transport=transport,
            timeout=httpx.Timeout(timeout, connect=5.0),
            headers={"User-Agent": USER_AGENT},
            follow_redirects=False,
            trust_env=False,  # an env proxy would resolve hosts itself and skip the pinning
        )
        self._interval = 60.0 / rpm if rpm else 0.0
        self._next_at = 0.0
        self._lock = threading.Lock()
        self._attempts = attempts
        self._sleep = time.sleep if sleep is None else sleep

    def __enter__(self) -> "Http":
        return self

    def __exit__(self, *exc: object) -> None:
        self._client.close()

    def _throttle(self) -> None:
        with self._lock:
            now = time.monotonic()
            wait = self._next_at - now
            self._next_at = max(now, self._next_at) + self._interval
        if wait > 0:
            self._sleep(wait)

    def get(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        max_bytes: int = MAX_BYTES,
    ) -> Fetched:
        retrying = Retrying(
            stop=stop_after_attempt(self._attempts),
            wait=_wait,
            retry=retry_if_exception_type((TransientFetchError, httpx.TransportError)),
            sleep=self._sleep,
            reraise=True,
        )
        for attempt in retrying:
            with attempt:
                return self._get_once(url, params, headers, max_bytes)
        raise AssertionError("unreachable")  # reraise=True always raises on the last attempt

    def _get_once(
        self,
        url: str,
        params: dict[str, Any] | None,
        headers: dict[str, str] | None,
        max_bytes: int,
    ) -> Fetched:
        for _ in range(MAX_REDIRECTS + 1):
            check_public_url(url)
            self._throttle()
            deadline = time.monotonic() + FETCH_DEADLINE  # after the throttle: queueing is fine
            with self._client.stream("GET", url, params=params, headers=headers) as r:
                if r.has_redirect_location:
                    url = urljoin(str(r.url), r.headers["location"])
                    params = None  # already part of the Location URL
                    nxt = httpx.URL(url)
                    # the token stays on its host and never goes over plain http
                    if headers and (nxt.host != r.url.host or nxt.scheme != r.url.scheme):
                        headers = {k: v for k, v in headers.items() if k.lower() != "authorization"}
                    continue
                _raise_for_status(r)
                declared = r.headers.get("content-length", "")
                if declared.isdigit() and int(declared) > max_bytes:
                    raise PermanentFetchError(f"response larger than {max_bytes} bytes")
                body = bytearray()
                for chunk in r.iter_bytes():
                    body += chunk
                    if len(body) > max_bytes:
                        raise PermanentFetchError(f"response larger than {max_bytes} bytes")
                    if time.monotonic() > deadline:  # a trickling server never hits a timeout
                        raise PermanentFetchError(f"response slower than {FETCH_DEADLINE}s")
                return Fetched(str(r.url), r.status_code, r.headers, bytes(body))
        raise PermanentFetchError(f"more than {MAX_REDIRECTS} redirects")


# --- robots.txt and full-text extraction -----------------------------------------------------

# We must be allowed under our own name and under Anthropic's crawler names, because extracted
# text is sent to Claude for classification (Phase 3). Sites that opt out of those get metadata.
ROBOTS_AGENTS = ("NewsDC", "ClaudeBot", "anthropic-ai")
# Hard paywalls: metadata only, never fetched (PLAN Phase 2 task 1).
PAYWALLED_HOSTS = frozenset(
    {
        "nytimes.com",
        "ft.com",
        "wsj.com",
        "bloomberg.com",
        "economist.com",
        "theinformation.com",
        "barrons.com",
        "washingtonpost.com",
    }
)
SKIP_EXTRACTION_HOSTS = frozenset({"news.ycombinator.com", "github.com", "arxiv.org"})


class Robots:
    """Per-origin robots.txt cache (RFC 9309: 4xx = no rules, 5xx/unreachable = disallow)."""

    def __init__(self, http: Http) -> None:
        self._http = http
        self._cache: dict[str, RobotFileParser] = {}
        self._lock = threading.Lock()

    def allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        with self._lock:
            parser = self._cache.get(origin)
        if parser is None:
            parser = self._load(origin)
            with self._lock:
                self._cache[origin] = parser
        return all(parser.can_fetch(agent, url) for agent in ROBOTS_AGENTS)

    def _load(self, origin: str) -> RobotFileParser:
        parser = RobotFileParser()
        try:
            fetched = self._http.get(f"{origin}/robots.txt", max_bytes=512_000)
        except PermanentFetchError:
            parser.parse([])  # no rules: everything allowed
        except (TransientFetchError, httpx.HTTPError):
            parser.parse(["User-agent: *", "Disallow: /"])
        else:
            parser.parse(fetched.text.splitlines())
        return parser


def _is_paywalled(host: str) -> bool:
    return any(host == p or host.endswith(f".{p}") for p in PAYWALLED_HOSTS)


@dataclass
class Extracted:
    resolved_url: str | None = None
    canonical_url: str | None = None  # already canonicalized
    text: str | None = None
    skipped: str | None = None  # why nothing was fetched, for logs


def extract_article(http: Http, robots: Robots, url: str) -> Extracted:
    """Fetch an article page and extract its main text with trafilatura. Never raises.

    Also returns the post-redirect URL and the page's rel=canonical URL when it points at the
    same host (a "verified" canonical, §11.3). Text is truncated to FULLTEXT_MAX_CHARS.
    """
    host = host_of(url)
    if host in SKIP_EXTRACTION_HOSTS or _is_paywalled(host):
        return Extracted(skipped="host")
    try:
        if not robots.allowed(url):
            return Extracted(skipped="robots")
        fetched = http.get(url, max_bytes=2_000_000)
    except (FetchError, httpx.HTTPError) as exc:
        log.info("extraction fetch failed", extra={"host": host, "error": str(exc)[:200]})
        return Extracted(skipped="fetch_error")
    result = Extracted(resolved_url=fetched.url)
    if "html" not in fetched.headers.get("content-type", ""):
        result.skipped = "not_html"
        return result
    html = fetched.text
    try:
        text = trafilatura.extract(
            html, url=fetched.url, include_comments=False, include_tables=False
        )
        meta = trafilatura.extract_metadata(html, default_url=fetched.url)
    except Exception as exc:  # trafilatura parses untrusted HTML; never let it kill a run
        log.info("extraction failed", extra={"host": host, "error": type(exc).__name__})
        return result
    result.text = text[:FULLTEXT_MAX_CHARS] if text else None
    hint = meta.url if meta else None
    if hint:
        try:
            if host_of(hint) == host_of(fetched.url):
                result.canonical_url = canonicalize_url(urljoin(fetched.url, hint))
        except ValueError:
            pass
    return result
