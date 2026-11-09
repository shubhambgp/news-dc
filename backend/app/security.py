"""Rate limiting and security headers (PLAN Phase 4). Admin auth arrives in Phase 8.

Rate limits use `limits` (the library slowapi wraps) directly. slowapi's middleware finds the
route by scanning `app.routes` for an `endpoint`, and FastAPI ≥ 0.16x wraps included routers in
objects without one, so slowapi silently exempted every route (D-030).
"""

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
