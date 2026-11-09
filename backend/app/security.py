"""Rate limiting, security headers (PLAN Phase 4) and admin sessions (Phase 8, §11.9).

Rate limits use `limits` (the library slowapi wraps) directly. slowapi's middleware finds the
route by scanning `app.routes` for an `endpoint`, and FastAPI ≥ 0.16x wraps included routers in
objects without one, so slowapi silently exempted every route (D-030).
"""

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass

from limits import RateLimitItem, parse
from limits.storage import MemoryStorage
from limits.strategies import MovingWindowRateLimiter

from app.config import get_settings

# ponytail: in-memory storage, so each API process counts separately; move to a shared store
# (Postgres/Redis) if the API ever runs as several processes. Behind Caddy, uvicorn must run with
# --proxy-headers so the client IP (not the proxy's) is the key (Phase 10).
_storage = MemoryStorage()
_limiter = MovingWindowRateLimiter(_storage)
DEFAULT_LIMIT = parse(get_settings().rate_limit_default)
RATE_LIMIT_EXEMPT = frozenset({"/api/v1/health", "/api/v1/ready"})  # probes poll these


def allow(client: str, limit: RateLimitItem = DEFAULT_LIMIT, scope: str = "default") -> bool:
    """Count one request for `client`; False once it is over `limit` in the moving window."""
    return _limiter.hit(limit, scope, client)


def reset_rate_limits() -> None:
    _storage.reset()


SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
}
# JSON responses never need to load anything. Swagger UI does (CDN script + inline JS), so the
# docs page is left without this header rather than given a policy that breaks it.
API_CSP = "default-src 'none'; frame-ancestors 'none'"


# --- Admin sessions (Phase 8, §11.9) -----------------------------------------------------------
# A session is a signed cookie: base64url(JSON {sid, csrf, exp}) + "." + HMAC-SHA256 with
# SESSION_SECRET (never ADMIN_TOKEN). Stateless, so a logout is remembered in memory until expiry.
SESSION_COOKIE = "newsdc_admin"
CSRF_HEADER = "X-CSRF-Token"


@dataclass(frozen=True)
class AdminSession:
    sid: str
    csrf: str
    exp: int


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _sig(body: str, secret: str) -> str:
    return _b64(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())


def check_admin_token(supplied: str, expected: str) -> bool:
    """Constant-time; says nothing about partial matches."""
    return hmac.compare_digest(supplied.encode(), expected.encode())


def new_session(secret: str, minutes: int) -> tuple[AdminSession, str]:
    """A fresh session id and CSRF token on every login (session rotation)."""
    sess = AdminSession(
        secrets.token_urlsafe(16), secrets.token_urlsafe(32), int(time.time()) + minutes * 60
    )
    body = _b64(json.dumps(vars(sess), separators=(",", ":")).encode())
    return sess, f"{body}.{_sig(body, secret)}"


# ponytail: in-memory logout list, per API process; a shared table if the API runs several
# processes. Sessions are short (ADMIN_SESSION_MINUTES), so the list stays tiny.
_revoked: dict[str, int] = {}


def revoke(sess: AdminSession) -> None:
    now = time.time()
    for sid in [k for k, exp in _revoked.items() if exp < now]:
        del _revoked[sid]
    _revoked[sess.sid] = sess.exp


def read_session(cookie: str, secret: str) -> AdminSession | None:
    """The session in a cookie, or None if it is malformed, forged, expired or logged out."""
    body, _, sig = cookie.partition(".")
    if not sig or not hmac.compare_digest(sig.encode(), _sig(body, secret).encode()):
        return None
    try:
        data = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        sess = AdminSession(str(data["sid"]), str(data["csrf"]), int(data["exp"]))
    except (ValueError, KeyError, TypeError):
        return None
    if sess.exp <= time.time() or sess.sid in _revoked:
        return None
    return sess


def origin_allowed(origin: str | None, referer: str | None, own: str, allowed: list[str]) -> bool:
    """CSRF defence in depth (§11.9): a browser request must come from the site itself or a
    configured CORS origin. Non-browser clients send neither header; the CSRF token still
    applies."""
    if origin is None and referer:
        scheme, _, rest = referer.partition("://")
        origin = f"{scheme}://{rest.split('/', 1)[0]}" if rest else referer
    return origin is None or origin == own or origin in allowed
