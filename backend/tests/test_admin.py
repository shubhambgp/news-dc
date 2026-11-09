"""Admin auth without a database (Phase 8): disabled mode, 401 without a session, login, rate
limits, CSRF and origin checks, logout, forged/expired cookies; export Markdown helpers."""

import time
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app import security
from app.api.export import md_link, md_text, to_markdown
from app.config import get_settings
from app.main import app
from app.schemas import ExportRecord
from app.security import SESSION_COOKIE, new_session, read_session, reset_rate_limits

TOKEN = "t" * 32
SECRET = "s" * 48
PROTECTED = [
    ("get", "/api/v1/admin/session"),
    ("get", "/api/v1/admin/runs"),
    ("get", "/api/v1/admin/jobs"),
    ("get", "/api/v1/admin/sources"),
    ("get", "/api/v1/admin/categories"),
    ("get", "/api/v1/admin/rejected"),
    ("post", "/api/v1/admin/logout"),
    ("post", "/api/v1/admin/ingest"),
    ("post", "/api/v1/admin/pipeline"),
    ("post", "/api/v1/admin/trend-brief"),
    ("post", "/api/v1/admin/reprocess-outdated"),
    ("post", "/api/v1/admin/items/1/reprocess"),
    ("post", "/api/v1/admin/jobs/1/retry"),
    ("patch", "/api/v1/admin/sources/hn"),
    ("patch", "/api/v1/admin/categories/cooling"),
]


def client() -> TestClient:
    # https: the session cookie is Secure, so the client only sends it over https.
    return TestClient(app, base_url="https://testserver", raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def admin_env(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "admin_token", TOKEN)
    monkeypatch.setattr(s, "session_secret", SECRET)
    reset_rate_limits()
    security._revoked.clear()
    yield


def login(c: TestClient) -> str:
    r = c.post("/api/v1/admin/login", json={"token": TOKEN})
    assert r.status_code == 200, r.text
    return r.json()["csrf_token"]


def test_protected_routes_need_the_cookie():
    c = client()
    for method, path in PROTECTED:
        r = getattr(c, method)(path, **({"json": {}} if method != "get" else {}))
        assert r.status_code == 401, (path, r.text)
        assert r.json()["error"]["code"] == "unauthorized"


def test_admin_disabled_without_config(monkeypatch):
    monkeypatch.setattr(get_settings(), "session_secret", "")
    c = client()
    assert c.post("/api/v1/admin/login", json={"token": TOKEN}).status_code == 503
    r = c.get("/api/v1/admin/runs")
    assert r.status_code == 503 and r.json()["error"]["code"] == "admin_disabled"


def test_short_token_disables_admin(monkeypatch):
    monkeypatch.setattr(get_settings(), "admin_token", "short")
    assert client().post("/api/v1/admin/login", json={"token": "short"}).status_code == 503


def test_login_sets_a_strict_session_cookie():
    c = client()
    r = c.post("/api/v1/admin/login", json={"token": TOKEN})
    assert r.status_code == 200
    cookie = r.headers["set-cookie"].lower()
    for attr in ("httponly", "secure", "samesite=strict", "path=/api/v1/admin", "max-age=1800"):
        assert attr in cookie
    assert TOKEN not in r.headers["set-cookie"] and SECRET not in r.headers["set-cookie"]
    body = r.json()
    assert set(body) == {"csrf_token", "expires_at"} and body["expires_at"].endswith("Z")
    assert c.get("/api/v1/admin/session").json()["csrf_token"] == body["csrf_token"]


def test_wrong_token_is_401_without_detail():
    r = client().post("/api/v1/admin/login", json={"token": TOKEN[:-1]})
    assert r.status_code == 401
    assert r.json()["error"]["message"] == "invalid admin token"
    assert "set-cookie" not in r.headers


def test_login_rate_limited_per_ip():
    c = client()
    codes = [c.post("/api/v1/admin/login", json={"token": "x"}).status_code for _ in range(6)]
    assert codes == [401] * 5 + [429]
    # The correct token is refused too while the limit holds.
    assert c.post("/api/v1/admin/login", json={"token": TOKEN}).status_code == 429


def test_login_rate_limited_globally(monkeypatch):
    # 30/minute across clients: simulate other IPs by filling the global window directly.
    for _ in range(30):
        security.allow("all", security.parse("30/minute"), "admin_login_global")
    assert client().post("/api/v1/admin/login", json={"token": TOKEN}).status_code == 429


def test_login_validation():
    c = client()
    assert c.post("/api/v1/admin/login", json={}).status_code == 422
    assert c.post("/api/v1/admin/login", json={"token": "x" * 513}).status_code == 422
    assert c.post("/api/v1/admin/login", json={"token": TOKEN, "x": 1}).status_code == 422


def test_state_change_needs_csrf_token():
    c = client()
    csrf = login(c)
    r = c.post("/api/v1/admin/logout")
    assert r.status_code == 403 and r.json()["error"]["code"] == "csrf_failed"
    r = c.post("/api/v1/admin/logout", headers={"X-CSRF-Token": "nope"})
    assert r.status_code == 403
    assert c.post("/api/v1/admin/logout", headers={"X-CSRF-Token": csrf}).status_code == 204


def test_foreign_origin_is_refused():
    c = client()
    csrf = login(c)
    for h in ({"Origin": "https://evil.example"}, {"Referer": "https://evil.example/x"}):
        r = c.post("/api/v1/admin/logout", headers={"X-CSRF-Token": csrf, **h})
        assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden_origin"
    r = c.post(
        "/api/v1/admin/login", json={"token": TOKEN}, headers={"Origin": "https://evil.example"}
    )
    assert r.status_code == 403
    ok = {"X-CSRF-Token": csrf, "Origin": "http://localhost:5173"}  # CORS_ORIGINS default
    assert c.post("/api/v1/admin/logout", headers=ok).status_code == 204


def test_logout_revokes_the_session():
    c = client()
    csrf = login(c)
    replay = client()
    replay.cookies.set(SESSION_COOKIE, c.cookies[SESSION_COOKIE])
    assert replay.get("/api/v1/admin/session").status_code == 200  # the copy works...
    assert c.post("/api/v1/admin/logout", headers={"X-CSRF-Token": csrf}).status_code == 204
    assert c.get("/api/v1/admin/session").status_code == 401
    assert replay.get("/api/v1/admin/session").status_code == 401  # ...until logout


def test_each_login_rotates_the_session():
    c = client()
    first = login(c)
    assert login(c) != first


def test_forged_tampered_and_expired_cookies():
    sess, cookie = new_session(SECRET, 30)
    assert read_session(cookie, SECRET) == sess
    assert read_session(cookie, "other-secret" * 4) is None  # wrong key
    body, sig = cookie.split(".")
    assert read_session(body + "x." + sig, SECRET) is None  # tampered payload
    assert read_session(body, SECRET) is None  # no signature
    assert read_session("", SECRET) is None
    _, old = new_session(SECRET, 0)  # expires immediately
    time.sleep(0.01)
    assert read_session(old, SECRET) is None


def test_session_cookie_signed_with_secret_not_token():
    _, cookie = new_session(SECRET, 30)
    assert read_session(cookie, TOKEN) is None


def test_md_escaping_and_links():
    assert md_text("a <script>x</script> *b* [c](d)\n# h") == (
        r"a \<script\>x\</script\> \*b\* \[c\](d) \# h"
    )
    assert md_link("T", "javascript:alert(1)") == "T"
    assert md_link("T", "https://x.example/a b>c") == "[T](<https://x.example/a%20b%3Ec>)"


def test_markdown_groups_by_category():
    def rec(i: int, cat: str | None) -> ExportRecord:
        return ExportRecord(
            id=i,
            title=f"Item {i}",
            url=f"https://x.example/{i}",
            publisher="Pub",
            author=None,
            published_at=datetime(2026, 11, 1, tzinfo=UTC),
            source=None,
            primary_category=cat,
            categories=[cat] if cat else [],
            content_type="news",
            summary=f"Summary {i}.",
            tags=[],
            relevance_score=80,
            quality_score=70,
            points=None,
            comments_count=None,
            discussion_url=None,
            sources=[],
            entities={},
            key_insights=[{"type": "technical", "text": "Insight."}],
        )

    md = to_markdown(
        [rec(1, "power"), rec(2, "cooling"), rec(3, None)],
        {"cooling": "Cooling", "power": "Power"},
        datetime(2026, 11, 9, tzinfo=UTC),
    )
    assert md.index("## Cooling") < md.index("Item 2") < md.index("## Power") < md.index("Item 1")
    assert md.index("## Uncategorized") < md.index("Item 3")
    assert "*Pub · 2026-11-01 · news*" in md and "- **Technical:** Insight." in md
