"""API contract tests that need no database: validation errors, the error envelope, request IDs,
security headers, rate limits, OpenAPI, and the pure search helpers."""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.api import common
from app.api.search import render_snippet, rrf
from app.main import MAX_BODY_BYTES, app
from app.security import reset_rate_limits

client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def fresh_limits():
    reset_rate_limits()
    yield
    app.dependency_overrides.clear()


def assert_error(r, status: int, code: str) -> dict:
    assert r.status_code == status, r.text
    err = r.json()["error"]
    assert set(err) == {"code", "message", "request_id"}
    assert err["code"] == code
    assert err["request_id"] == r.headers["x-request-id"]
    return err


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/items?page_size=51",
        "/api/v1/items?page_size=0",
        "/api/v1/items?page=0",
        "/api/v1/items?page=1001",
        "/api/v1/items?sort=hot",
        "/api/v1/feeds/trending?page_size=51",
        "/api/v1/topics/cooling?sort=trendy",
        "/api/v1/items?content_type=blog",
        "/api/v1/items?min_quality=101",
        "/api/v1/items?category=Not%20A%20Slug",
        "/api/v1/items?source=../etc",
        "/api/v1/items?from=yesterday",
        "/api/v1/items?from=2026-02-01&to=2026-01-01",
        "/api/v1/items/0",
        "/api/v1/items/abc",
        "/api/v1/items/0/related",
        "/api/v1/feeds/relevant?page_size=100",
        "/api/v1/topics/BAD%20SLUG",
        "/api/v1/topics/cooling?sort=random",
        "/api/v1/search",
        "/api/v1/search?q=",
        "/api/v1/search?q=%20%20%20",
        "/api/v1/search?q=" + "x" * 201,
        "/api/v1/search?q=gpu&page_size=51",
    ],
)
def test_invalid_requests_get_422_envelope(path):
    """Validation runs before any DB access, so this needs no database."""
    err = assert_error(client.get(path), 422, "validation_error")
    assert err["message"]


def test_validation_message_names_the_field():
    err = assert_error(client.get("/api/v1/items?page_size=51"), 422, "validation_error")
    assert "page_size" in err["message"]


def test_unknown_route_and_method_use_envelope():
    assert_error(client.get("/api/v1/nope"), 404, "not_found")
    assert_error(client.post("/api/v1/items"), 405, "method_not_allowed")


def test_request_id_is_echoed_or_generated():
    r = client.get("/api/v1/health", headers={"X-Request-ID": "abc-123"})
    assert r.headers["x-request-id"] == "abc-123"
    r = client.get("/api/v1/health", headers={"X-Request-ID": "bad id\twith spaces"})
    assert r.headers["x-request-id"] != "bad id\twith spaces"
    assert len(r.headers["x-request-id"]) == 32


def test_security_headers_and_csp():
    r = client.get("/api/v1/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "no-referrer"
    assert r.headers["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'"
    # Swagger UI needs its CDN script, so the docs page has no CSP.
    docs = client.get("/api/v1/docs")
    assert docs.status_code == 200
    assert "content-security-policy" not in docs.headers


def test_cors_allows_only_configured_origins():
    ok = client.get("/api/v1/health", headers={"Origin": "http://localhost:5173"})
    assert ok.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert ok.headers["access-control-expose-headers"] == "X-Request-ID"
    bad = client.get("/api/v1/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in bad.headers


def test_rate_limit_returns_429_envelope_and_spares_health():
    for _ in range(60):
        assert client.get("/api/v1/items?page_size=999").status_code == 422
    r = client.get("/api/v1/items?page_size=999", headers={"Origin": "http://localhost:5173"})
    err = assert_error(r, 429, "rate_limited")
    assert "60 per 1 minute" in err["message"]
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"  # readable
    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/api/v1/ready").status_code in (200, 503)


def _broken_db(exc: Exception):
    def dep():
        raise exc
        yield  # pragma: no cover

    return dep


def test_database_down_is_503_envelope():
    app.dependency_overrides[common.get_db] = _broken_db(
        OperationalError("SELECT 1", {}, Exception("connection refused"))
    )
    assert_error(client.get("/api/v1/items"), 503, "db_unavailable")


def test_unexpected_error_is_500_envelope_without_details():
    app.dependency_overrides[common.get_db] = _broken_db(RuntimeError("secret internals"))
    err = assert_error(client.get("/api/v1/topics"), 500, "internal_error")
    assert "secret" not in err["message"]


@pytest.mark.parametrize(
    "body",
    [
        {"categoryWeights": {"Not A Slug": 1}},
        {"categoryWeights": {"cooling": float("inf")}},
        {"categoryWeights": {"cooling": 1e6}},
        {"readIds": list(range(1, 202))},  # over 200
        {"readIds": [0]},
        {"dismissedIds": ["abc"]},
        {"tagWeights": {"": 1}},
        {"tagWeights": {f"t{i}": 1 for i in range(201)}},
        {"explicitTopics": ["cooling"] * 65},
        {"unknownField": 1},
        [],
    ],
)
def test_foryou_profile_validation_is_422(body):
    """Pydantic rejects these before any DB access."""
    r = client.post(
        "/api/v1/feeds/foryou",
        content=json.dumps(body, allow_nan=True),
        headers={"Content-Type": "application/json"},
    )
    assert_error(r, 422, "validation_error")


def test_request_body_size_limits():
    big = b'{"tagWeights": {"' + b"x" * MAX_BODY_BYTES + b'": 1}}'
    r = client.post("/api/v1/feeds/foryou", content=big)
    assert_error(r, 413, "payload_too_large")

    def chunks():
        yield b"{}"

    r = client.post("/api/v1/feeds/foryou", content=chunks())  # chunked: no Content-Length
    assert_error(r, 411, "length_required")


def test_openapi_lists_every_phase4_endpoint_and_error_shape():
    spec = client.get("/api/v1/openapi.json").json()
    assert set(spec["paths"]) == {
        "/api/v1/health",
        "/api/v1/ready",
        "/api/v1/items",
        "/api/v1/items/{item_id}",
        "/api/v1/items/{item_id}/related",
        "/api/v1/feeds/relevant",
        "/api/v1/feeds/trending",
        "/api/v1/feeds/foryou",
        "/api/v1/topics",
        "/api/v1/topics/{slug}",
        "/api/v1/search",
    }
    assert "ErrorResponse" in spec["components"]["schemas"]
    item_responses = spec["paths"]["/api/v1/items/{item_id}"]["get"]["responses"]
    assert {"200", "404", "422", "429"} <= set(item_responses)


def test_rrf_fuses_rankings_deterministically():
    fused = rrf([1, 2, 3], [3, 4])
    ids = [i for i, _ in fused]
    assert ids[0] == 3  # found by both retrievers
    assert set(ids) == {1, 2, 3, 4}
    assert fused[0][1] == pytest.approx(1 / 63 + 1 / 61)
    # Equal scores (rank 1 in one list each) tie-break by id DESC.
    assert [i for i, _ in rrf([5], [7])] == [7, 5]
    assert rrf([], []) == []


def test_snippet_is_escaped_except_marks():
    raw = "<script>x</script> liquid & cooling"
    assert render_snippet(raw) == (
        "&lt;script&gt;x&lt;/script&gt; <mark>liquid</mark> &amp; <mark>cooling</mark>"
    )
