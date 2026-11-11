"""Ingestion runner against real Postgres (TEST_DATABASE_URL, a THROWAWAY database) with HTTP
mocked by respx. Covers PLAN Phase 2 acceptance: no duplicates on re-run, engagement refresh,
cross-source provenance, redirect resolution, per-source isolation and resumable checkpoints."""

import json
import threading
import time
from typing import Any
from urllib.parse import unquote

import httpx
import pytest
import respx
from conftest import FIXTURES, TEST_DATABASE_URL
from sqlalchemy import text

from app.config import get_settings
from app.ingest import hackernews, runner
from app.ingest.runner import ingest_all, ingest_source
from app.seed import seed

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL not set")

DCD_FEED = "https://www.datacenterdynamics.com/en/rss/"
DCK_FEED = "https://www.datacenterknowledge.com/rss.xml"
HN_BY_DATE = "https://hn.algolia.com/api/v1/search_by_date"
HN_SEARCH = "https://hn.algolia.com/api/v1/search"
ARTICLE = """<html><head><link rel="canonical" href="https://blog.example.org/posts/1gw-ai-dc">
</head><body><article><h1>Inside a 1 GW AI data center</h1>
<p>The campus draws one gigawatt for GPU clusters cooled with direct-to-chip liquid loops.</p>
<p>Operators negotiated a power purchase agreement with the local utility for new supply.</p>
</article></body></html>"""


@pytest.fixture(autouse=True)
def clean(engine, monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)  # retries/throttle without waiting
    yield
    with engine.begin() as c:
        c.execute(text("TRUNCATE item_sources, ai_annotations, items, pipeline_runs CASCADE"))
        c.execute(
            text(
                "UPDATE sources SET checkpoint = '{}', last_success_at = NULL, "
                "last_fetched_at = NULL, last_status = NULL, last_error = NULL"
            )
        )
    seed(engine, get_settings().config_dir)  # restores enabled flags and settings from YAML


@pytest.fixture
def web():
    """respx router: HN lookups find nothing, robots.txt is absent, articles serve ARTICLE."""
    with respx.mock(assert_all_called=False) as mock:
        mock.get(HN_SEARCH).respond(200, json={"hits": []})
        mock.get(url__regex=r".*/robots\.txt$").respond(404)
        mock.get("https://blog.example.org/posts/1gw-ai-dc").respond(200, html=ARTICLE)
        yield mock


def _q(engine, sql: str, **params) -> Any:
    with engine.connect() as c:
        return c.execute(text(sql), params).all()


def _one(engine, sql: str, **params) -> Any:
    with engine.connect() as c:
        return c.scalar(text(sql), params)


def _patch_settings(engine, key: str, **settings) -> None:
    with engine.begin() as c:
        c.execute(
            text("UPDATE sources SET settings = settings || cast(:p AS jsonb) WHERE key = :k"),
            {"p": json.dumps(settings), "k": key},
        )


def _hn_hits(points: int = 312, url: str | None = None) -> dict:
    hits = json.loads((FIXTURES / "hn_search.json").read_text())["hits"]
    hits[0]["points"] = points
    if url:
        hits[0]["url"] = url
    return {"hits": hits}


def _rss(link: str) -> str:
    return (
        '<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>'
        f"<item><title>Gigawatt AI campus</title><link>{link}</link><guid>g-1</guid>"
        "<pubDate>Mon, 09 Nov 2026 12:00:00 +0000</pubDate></item></channel></rss>"
    )


def test_running_twice_creates_no_duplicate_rows(engine, web):
    web.get(DCD_FEED).respond(200, content=(FIXTURES / "rss.xml").read_bytes())
    first = ingest_source("dcd", since_days=30, engine=engine)
    second = ingest_source("dcd", since_days=30, engine=engine)

    assert (first.counts.fetched, first.counts.new, first.counts.failed) == (3, 2, 1)
    assert first.status == "partial"  # the javascript: link was rejected and counted
    assert (second.counts.new, second.counts.duplicates) == (0, 2)
    assert _one(engine, "SELECT count(*) FROM items") == 2
    assert _one(engine, "SELECT count(*) FROM item_sources") == 2
    runs = _q(engine, "SELECT source_key, new, duplicates, failed FROM pipeline_runs ORDER BY id")
    assert runs == [("dcd", 2, 0, 1), ("dcd", 0, 2, 1)]
    row = _q(engine, "SELECT canonical_url, description, publisher FROM items ORDER BY id")[0]
    assert row == (
        "https://news.example.com/en/news/liquid-cooled-campus",
        "A 100 MW campus.",
        "DatacenterDynamics",
    )


def test_engagement_is_refreshed_and_other_sources_attach(engine, web):
    _patch_settings(engine, "hn", queries=["data center"])
    by_date = web.get(HN_BY_DATE)
    by_date.respond(200, json=_hn_hits(points=312))
    ingest_source("hn", since_days=30, engine=engine)
    by_date.respond(200, json=_hn_hits(points=400))
    again = ingest_source("hn", since_days=30, engine=engine)
    assert (again.counts.new, again.counts.duplicates) == (0, 2)

    story = "SELECT id, points, comments_count, content_text FROM items WHERE title LIKE 'Inside%'"
    item_id, points, comments, content = _q(engine, story)[0]
    assert (points, comments) == (400, 140)
    assert content and "gigawatt" in content  # full text extracted for HN links
    engagement = _one(
        engine, "SELECT source_engagement FROM item_sources WHERE external_id = '45000001'"
    )
    assert engagement["points"] == 400

    # The same article from an RSS feed attaches a second provenance row, not a second item.
    web.get(DCD_FEED).respond(200, text=_rss("https://blog.example.org/posts/1gw-ai-dc/?ref=rss"))
    ingest_source("dcd", since_days=30, engine=engine)
    assert _one(engine, "SELECT count(*) FROM items") == 2
    links = _q(
        engine,
        "SELECT s.key, l.is_primary FROM item_sources l JOIN sources s ON s.id = l.source_id "
        "WHERE l.item_id = :i ORDER BY l.id",
        i=item_id,
    )
    assert links == [("hn", True), ("dcd", False)]
    assert _one(engine, "SELECT points FROM items WHERE id = :i", i=item_id) == 400  # kept


def test_redirects_are_resolved_before_dedupe(engine, web):
    _patch_settings(engine, "hn", queries=["data center"])
    web.get(HN_BY_DATE).respond(200, json=_hn_hits(url="http://short.example/x"))
    web.get("http://short.example/x").respond(
        301, headers={"Location": "https://blog.example.org/posts/1gw-ai-dc?utm_source=hn"}
    )
    web.get("https://blog.example.org/posts/1gw-ai-dc?utm_source=hn").respond(200, html=ARTICLE)
    ingest_source("hn", since_days=30, engine=engine)

    original, resolved, canonical = _q(
        engine,
        "SELECT original_url, resolved_url, canonical_url FROM items WHERE title LIKE 'Inside%'",
    )[0]
    assert original == "http://short.example/x"
    assert resolved == "https://blog.example.org/posts/1gw-ai-dc?utm_source=hn"
    assert canonical == "https://blog.example.org/posts/1gw-ai-dc"

    web.get(DCD_FEED).respond(200, text=_rss("https://blog.example.org/posts/1gw-ai-dc"))
    result = ingest_source("dcd", since_days=30, engine=engine)
    assert (result.counts.new, result.counts.duplicates) == (0, 1)


def test_one_broken_source_does_not_stop_the_others(engine, web):
    with engine.begin() as c:
        c.execute(text("UPDATE sources SET enabled = (key IN ('dcd', 'dck'))"))
    web.get(DCD_FEED).respond(500)
    web.get(DCK_FEED).respond(200, content=(FIXTURES / "rss.xml").read_bytes())

    results = {r.source_key: r for r in ingest_all(since_days=30, engine=engine)}
    assert results["dcd"].status == "failed" and "HTTP 500" in (results["dcd"].error or "")
    assert results["dck"].counts.new == 2

    status = dict(_q(engine, "SELECT key, last_status FROM sources WHERE key IN ('dcd', 'dck')"))
    assert status == {"dcd": "error", "dck": "ok"}
    assert "HTTP 500" in _one(engine, "SELECT last_error FROM sources WHERE key = 'dcd'")
    assert _one(engine, "SELECT status FROM pipeline_runs WHERE source_key = 'dcd'") == "failed"


def test_capped_run_saves_checkpoint_and_resumes(engine, web, monkeypatch):
    monkeypatch.setattr(hackernews, "PAGE_SIZE", 2)
    _patch_settings(engine, "hn", queries=["gpu"], max_items_per_run=2)
    by_date = web.get(HN_BY_DATE)
    by_date.side_effect = [httpx.Response(200, json=_hn_hits())]
    first = ingest_source("hn", since_days=30, engine=engine)
    assert first.counts.fetched == 2
    checkpoint = _one(engine, "SELECT checkpoint FROM sources WHERE key = 'hn'")
    assert checkpoint["gpu"]["until"] == 1762500000

    by_date.side_effect = [httpx.Response(200, json={"hits": []})]
    ingest_source("hn", since_days=30, engine=engine)
    assert "created_at_i<=1762500000" in unquote(str(by_date.calls[-1].request.url))
    assert _one(engine, "SELECT checkpoint FROM sources WHERE key = 'hn'") == {}


def test_failure_mid_run_keeps_committed_pages_and_cursor(engine, web, monkeypatch):
    monkeypatch.setattr(hackernews, "PAGE_SIZE", 2)
    _patch_settings(engine, "hn", queries=["gpu"])
    web.get(HN_BY_DATE).side_effect = [httpx.Response(200, json=_hn_hits())] + [
        httpx.Response(503)
    ] * 4
    result = ingest_source("hn", since_days=30, engine=engine)

    assert result.status == "failed" and "HTTP 503" in (result.error or "")
    run = _q(
        engine, "SELECT fetched, new, status FROM pipeline_runs WHERE id = :i", i=result.run_id
    )
    assert run == [(2, 2, "failed")]  # only the committed page is reported
    assert _one(engine, "SELECT count(*) FROM items") == 2
    checkpoint = _one(engine, "SELECT checkpoint FROM sources WHERE key = 'hn'")
    assert checkpoint["gpu"]["until"] == 1762500000  # the next run resumes here


def test_no_transaction_is_held_open_during_enrichment(engine, web, monkeypatch):
    # Regression: a slow enrichment inside the page transaction hit the server's
    # idle_in_transaction_session_timeout during the real arXiv backfill.
    seen: list[int] = []
    original = runner.Enricher.many

    def checking_many(self, items):
        seen.append(
            _one(
                engine,
                "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
                "AND state LIKE 'idle in transaction%' AND pid <> pg_backend_pid()",
            )
        )
        return original(self, items)

    monkeypatch.setattr(runner.Enricher, "many", checking_many)
    web.get(DCD_FEED).respond(200, content=(FIXTURES / "rss.xml").read_bytes())
    ingest_source("dcd", since_days=30, engine=engine)
    assert seen == [0]


def test_concurrent_runs_do_not_duplicate(engine, web):
    web.get(DCD_FEED).respond(200, content=(FIXTURES / "rss.xml").read_bytes())
    threads = [
        threading.Thread(
            target=ingest_source, args=("dcd",), kwargs={"since_days": 30, "engine": engine}
        )
        for _ in range(8)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert _one(engine, "SELECT count(*) FROM items") == 2
    assert _one(engine, "SELECT count(*) FROM item_sources") == 2
    assert _one(engine, "SELECT count(*) FROM pipeline_runs WHERE status = 'failed'") == 0


def test_disabled_or_unknown_sources_are_refused(engine):
    with pytest.raises(ValueError, match="disabled"):
        ingest_source("register_dc", engine=engine)
    with pytest.raises(ValueError, match="unknown"):
        ingest_source("nope", engine=engine)


def test_ingest_all_stops_between_sources_on_shutdown(engine):
    assert ingest_all(engine=engine, should_stop=lambda: True) == []
    assert _q(engine, "SELECT count(*) FROM pipeline_runs")[0][0] == 0
