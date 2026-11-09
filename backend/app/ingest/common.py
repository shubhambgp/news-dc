"""Helpers shared by all source adapters."""

import hashlib
from urllib.parse import urlsplit, urlunsplit

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
