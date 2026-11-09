import pytest

from app.ingest.common import canonicalize_url, url_hash


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # tracking params removed, meaningful ones kept
        (
            "https://example.com/a?utm_source=x&utm_MEDIUM=y&id=7&fbclid=z&gclid=1&ref=hn",
            "https://example.com/a?id=7",
        ),
        ("https://example.com/a?UTM_Campaign=x", "https://example.com/a"),
        # query parameter order doesn't matter
        ("https://example.com/a?b=2&a=1", "https://example.com/a?a=1&b=2"),
        # meaningful params and their exact encoding are preserved
        (
            "https://example.com/s?q=liquid%20cooling&page=2",
            "https://example.com/s?page=2&q=liquid%20cooling",
        ),
        ("https://example.com/p?id=", "https://example.com/p?id="),
        # www. and host case
        ("https://WWW.Example.COM/a", "https://example.com/a"),
        ("https://News.Example.com/a", "https://news.example.com/a"),
        # trailing slash, and root path normalization
        ("https://example.com/a/b/", "https://example.com/a/b"),
        ("https://example.com", "https://example.com/"),
        ("https://example.com/", "https://example.com/"),
        ("https://example.com//", "https://example.com/"),
        # fragment removed
        ("https://example.com/a#section-2", "https://example.com/a"),
        # default ports removed, non-default kept
        ("https://example.com:443/a", "https://example.com/a"),
        ("http://example.com:80/a", "http://example.com/a"),
        ("https://example.com:8443/a", "https://example.com:8443/a"),
        ("http://example.com:443/a", "http://example.com:443/a"),
        # path case is preserved (paths can be case-sensitive)
        ("https://example.com/Papers/ABC.pdf", "https://example.com/Papers/ABC.pdf"),
        # scheme case normalized, but http is NOT rewritten to https (PLAN §11.3)
        ("HTTP://example.com/a", "http://example.com/a"),
        # credentials are never stored
        ("https://user:pass@example.com/a", "https://example.com/a"),
        # surrounding whitespace, trailing dot in host
        ("  https://example.com./a  ", "https://example.com/a"),
        # IPv6 literal
        ("http://[2001:db8::1]:8080/a", "http://[2001:db8::1]:8080/a"),
    ],
)
def test_canonicalize_url(raw, expected):
    assert canonicalize_url(raw) == expected


def test_http_and_https_stay_distinct():
    assert canonicalize_url("http://example.com/a") != canonicalize_url("https://example.com/a")


def test_case_sensitive_paths_stay_distinct():
    assert canonicalize_url("https://example.com/A") != canonicalize_url("https://example.com/a")


def test_canonicalize_is_idempotent():
    once = canonicalize_url("https://www.Example.com/a/?z=1&utm_source=x&a=2#f")
    assert canonicalize_url(once) == once


@pytest.mark.parametrize(
    "bad",
    [
        "ftp://example.com/a",
        "javascript:alert(1)",
        "example.com/a",
        "https:///a",
        "",
        "https://example.com:99999/",
    ],
)
def test_canonicalize_rejects_invalid(bad):
    with pytest.raises(ValueError):
        canonicalize_url(bad)


def test_url_hash_is_sha256_hex_and_dedupes_variants():
    a = url_hash(canonicalize_url("https://www.example.com/a/?utm_source=x#top"))
    b = url_hash(canonicalize_url("https://example.com/a"))
    assert a == b
    assert len(a) == 64 and int(a, 16) >= 0
    assert a != url_hash(canonicalize_url("https://example.com/b"))
