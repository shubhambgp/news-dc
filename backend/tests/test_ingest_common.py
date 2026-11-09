"""Guarded HTTP client, SSRF checks, robots.txt, extraction and RawItem validation (no DB)."""

from datetime import UTC, datetime

import httpx
import pytest
import respx
from pydantic import ValidationError

from app.ingest import common
from app.ingest.common import (
    Http,
    PermanentFetchError,
    RawItem,
    Robots,
    TransientFetchError,
    UnsafeURLError,
    check_public_url,
    extract_article,
    html_to_text,
)

ARTICLE = """<html><head><title>T</title>
<link rel="canonical" href="https://blog.example.org/posts/gw-dc"></head>
<body><article><h1>Inside a gigawatt data center</h1>
<p>The campus draws one gigawatt for GPU clusters cooled with direct-to-chip liquid loops.</p>
<p>Operators negotiated a power purchase agreement with the local utility for new supply.</p>
<p>Construction finished in eighteen months, with phased energisation of every hall.</p>
</article><script>steal()</script></body></html>"""


class Sleeps(list[float]):
    def __call__(self, seconds: float) -> None:
        self.append(seconds)


@pytest.fixture
def sleeps() -> Sleeps:
    return Sleeps()


# --- SSRF ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "addr"),
    [
        ("http://localhost/x", "127.0.0.1"),
        ("http://internal.example/x", "10.0.0.5"),
        ("http://meta.example/latest", "169.254.169.254"),
        ("http://v6.example/x", "::1"),
        ("http://mapped.example/x", "::ffff:127.0.0.1"),
        ("http://cgnat.example/x", "100.64.0.1"),
    ],
)
def test_private_addresses_are_rejected(monkeypatch, url, addr):
    monkeypatch.setattr(common, "_resolve", lambda host, port: [addr])
    with pytest.raises(UnsafeURLError):
        check_public_url(url)


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://example.com/x", "http:///nohost"])
def test_unsupported_urls_are_rejected(url):
    with pytest.raises(UnsafeURLError):
        check_public_url(url)


def test_public_address_is_allowed():
    check_public_url("https://example.com/feed")  # conftest resolves to a public IP


@respx.mock
def test_redirects_are_followed_and_recorded(sleeps):
    respx.get("http://short.example/a").respond(
        301, headers={"Location": "https://blog.example.org/b"}
    )
    respx.get("https://blog.example.org/b").respond(200, text="ok")
    with Http(sleep=sleeps) as http:
        got = http.get("http://short.example/a")
    assert got.url == "https://blog.example.org/b"
    assert got.content == b"ok"


@respx.mock
def test_redirect_to_private_address_is_blocked(monkeypatch, sleeps):
    monkeypatch.setattr(
        common,
        "_resolve",
        lambda host, port: ["10.1.2.3"] if host == "evil.internal" else ["93.184.216.34"],
    )
    respx.get("https://example.com/a").respond(302, headers={"Location": "http://evil.internal/"})
    inner = respx.get("http://evil.internal/").respond(200)
    with Http(sleep=sleeps) as http, pytest.raises(UnsafeURLError):
        http.get("https://example.com/a")
    assert not inner.called


@respx.mock
def test_redirect_loop_is_bounded(sleeps):
    respx.get("https://example.com/loop").respond(302, headers={"Location": "/loop"})
    with Http(sleep=sleeps) as http, pytest.raises(PermanentFetchError, match="redirects"):
        http.get("https://example.com/loop")


@respx.mock
def test_not_modified_is_returned_not_followed(sleeps):
    # Regression: httpx treats every 3xx as `is_redirect`; a 304 has no Location header.
    respx.get("https://example.com/feed").respond(304)
    with Http(sleep=sleeps) as http:
        assert http.get("https://example.com/feed").status == 304


# --- limits and retries ---------------------------------------------------------------------


@respx.mock
def test_response_size_is_capped(sleeps):
    respx.get("https://example.com/declared").respond(200, headers={"Content-Length": "999999"})
    respx.get("https://example.com/streamed").respond(200, content=b"x" * 2048)
    with Http(sleep=sleeps) as http:
        with pytest.raises(PermanentFetchError, match="larger"):
            http.get("https://example.com/declared", max_bytes=1000)
        with pytest.raises(PermanentFetchError, match="larger"):
            http.get("https://example.com/streamed", max_bytes=1000)


@respx.mock
def test_429_is_retried_honouring_retry_after(sleeps):
    route = respx.get("https://example.com/api")
    route.side_effect = [
        httpx.Response(429, headers={"Retry-After": "7"}),
        httpx.Response(503),
        httpx.Response(200, json={"ok": True}),
    ]
    with Http(sleep=sleeps) as http:
        assert http.get("https://example.com/api").json() == {"ok": True}
    assert route.call_count == 3
    assert sleeps[0] >= 7  # Retry-After wins over the shorter backoff


@respx.mock
def test_retries_are_bounded(sleeps):
    route = respx.get("https://example.com/down").respond(500)
    with Http(sleep=sleeps, attempts=3) as http, pytest.raises(TransientFetchError):
        http.get("https://example.com/down")
    assert route.call_count == 3


@respx.mock
def test_client_errors_are_not_retried(sleeps):
    route = respx.get("https://example.com/missing").respond(404)
    with Http(sleep=sleeps) as http, pytest.raises(PermanentFetchError, match="404"):
        http.get("https://example.com/missing")
    assert route.call_count == 1


@respx.mock
def test_github_rate_limit_403_is_transient(sleeps):
    route = respx.get("https://api.github.com/search/repositories")
    route.side_effect = [
        httpx.Response(403, headers={"x-ratelimit-remaining": "0", "retry-after": "2"}),
        httpx.Response(200, json={"items": []}),
    ]
    with Http(sleep=sleeps) as http:
        http.get("https://api.github.com/search/repositories")
    assert route.call_count == 2 and sleeps[0] >= 2


@respx.mock
def test_requests_are_throttled_per_minute(sleeps):
    respx.get("https://example.com/x").respond(200)
    with Http(rpm=20, sleep=sleeps) as http:  # one request every 3 s (arXiv terms)
        http.get("https://example.com/x")
        http.get("https://example.com/x")
    assert len(sleeps) == 1 and 2.5 < sleeps[0] <= 3.0


# --- robots.txt and extraction ----------------------------------------------------------------


@respx.mock
def test_robots_blocking_claudebot_means_metadata_only(sleeps):
    respx.get("https://blog.example.org/robots.txt").respond(
        200, text="User-agent: ClaudeBot\nDisallow: /\n"
    )
    page = respx.get("https://blog.example.org/posts/gw-dc").respond(200, html=ARTICLE)
    with Http(sleep=sleeps) as http:
        got = extract_article(http, Robots(http), "https://blog.example.org/posts/gw-dc")
    assert got.skipped == "robots" and got.text is None
    assert not page.called


@respx.mock
def test_missing_robots_allows_extraction(sleeps):
    respx.get("http://blog.example.org/robots.txt").respond(404)
    respx.get("http://blog.example.org/p?id=1").respond(
        301, headers={"Location": "https://blog.example.org/posts/gw-dc?utm_source=x"}
    )
    respx.get("https://blog.example.org/posts/gw-dc?utm_source=x").respond(200, html=ARTICLE)
    with Http(sleep=sleeps) as http:
        got = extract_article(http, Robots(http), "http://blog.example.org/p?id=1")
    assert got.resolved_url == "https://blog.example.org/posts/gw-dc?utm_source=x"
    assert got.canonical_url == "https://blog.example.org/posts/gw-dc"  # verified rel=canonical
    assert got.text and "gigawatt" in got.text and "steal" not in got.text


@respx.mock
def test_cross_host_canonical_is_ignored(sleeps):
    respx.get("https://mirror.example.net/robots.txt").respond(404)
    respx.get("https://mirror.example.net/copy").respond(200, html=ARTICLE)
    with Http(sleep=sleeps) as http:
        got = extract_article(http, Robots(http), "https://mirror.example.net/copy")
    assert got.text and got.canonical_url is None


@respx.mock
def test_robots_server_error_disallows(sleeps):
    respx.get("https://flaky.example/robots.txt").respond(503)
    with Http(sleep=sleeps, attempts=1) as http:
        assert not Robots(http).allowed("https://flaky.example/a")


def test_paywalled_hosts_are_never_fetched():
    with respx.mock(assert_all_called=False) as mock, Http() as http:
        got = extract_article(http, Robots(http), "https://www.nytimes.com/2026/11/09/tech/x.html")
        assert got.skipped == "host" and not mock.calls


# --- RawItem ------------------------------------------------------------------------------------


def test_html_to_text_drops_markup_and_scripts():
    assert (
        html_to_text("<p>A &amp; <b>B</b></p><script>evil()</script><style>x{}</style>") == "A & B"
    )


def test_raw_item_normalizes_and_validates():
    item = RawItem(
        title="  <b>Liquid</b>   cooling ",
        url="https://WWW.Example.com/a/?utm_source=x",
        description="<p>" + "x" * 3000 + "</p>",
        published_at=datetime(2026, 11, 9, 12, 0),  # naive -> UTC
        source_tags=["a", "a", " ", "b"],
    )
    assert item.title == "Liquid cooling"
    assert item.description is not None and len(item.description) == 2000
    assert item.published_at == datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
    assert item.source_tags == ["a", "b"]
    assert item.canonical_url == "https://example.com/a"


@pytest.mark.parametrize(
    "bad", [{"url": "javascript:alert(1)"}, {"url": "/relative"}, {"title": ""}, {"points": -1}]
)
def test_raw_item_rejects_bad_rows(bad):
    with pytest.raises(ValidationError):
        RawItem.model_validate({"title": "t", "url": "https://example.com/a"} | bad)
