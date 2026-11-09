"""Source adapters against fixture responses (respx), no DB."""

import json
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import respx
from conftest import FIXTURES

from app.config import get_settings
from app.ingest import arxiv, github, hackernews, rss
from app.ingest.common import Http, PermanentFetchError, RawItem
from app.models import Source

SINCE = datetime(2026, 1, 1, tzinfo=UTC)


def _source(type_: str, url: str, **settings) -> Source:
    return Source(key=type_, name=type_, type=type_, url=url, settings=settings)


def _http() -> Http:
    return Http(sleep=lambda s: None)


def _params(call) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlsplit(str(call.request.url)).query).items()}


# --- Hacker News -------------------------------------------------------------------------------


@respx.mock
def test_hn_maps_hits_and_clears_checkpoint_when_done():
    route = respx.get("https://hn.algolia.com/api/v1/search_by_date").respond(
        200, content=(FIXTURES / "hn_search.json").read_bytes()
    )
    checkpoint: dict = {}
    src = _source(
        "hackernews", "https://hn.algolia.com/api/v1/search_by_date", queries=["data center"]
    )
    with _http() as http:
        pages = list(hackernews.fetch(http, src, SINCE, checkpoint))
    assert checkpoint == {}  # query finished
    params = _params(route.calls[0])
    assert params["query"] == '"data center"'
    assert params["restrictSearchableAttributes"] == "title"
    assert params["numericFilters"] == f"created_at_i>{int(SINCE.timestamp())}"

    story, ask = (RawItem.model_validate(r) for r in pages[0])
    assert story.external_id == "45000001" and story.points == 312 and story.comments_count == 140
    assert story.discussion_url == "https://news.ycombinator.com/item?id=45000001"
    assert story.publisher == "blog.example.org"
    assert ask.url == ask.discussion_url  # Ask HN posts link to their own thread
    assert ask.description == "We are sizing & planning."


@respx.mock
def test_hn_pages_backwards_and_resumes_from_checkpoint(monkeypatch):
    monkeypatch.setattr(hackernews, "PAGE_SIZE", 2)
    hits = json.loads((FIXTURES / "hn_search.json").read_text())["hits"]
    route = respx.get("https://hn.algolia.com/api/v1/search_by_date")
    route.side_effect = [
        httpx.Response(200, json={"hits": hits}),
        httpx.Response(200, json={"hits": []}),
    ]
    src = _source("hackernews", "https://hn.algolia.com/api/v1/search_by_date", queries=["gpu"])
    checkpoint: dict = {}
    with _http() as http:
        gen = hackernews.fetch(http, src, SINCE, checkpoint)
        next(gen)
        # Interrupted after the first page: the cursor is the oldest story seen.
        assert checkpoint == {"gpu": {"until": 1762500000, "since": int(SINCE.timestamp())}}

    # A later run with a shorter window still finishes the older backfill from the cursor.
    route.side_effect = [httpx.Response(200, json={"hits": []})]
    later = datetime(2026, 11, 1, tzinfo=UTC)
    with _http() as http:
        list(hackernews.fetch(http, src, later, checkpoint))
    assert _params(route.calls[-1])["numericFilters"] == (
        f"created_at_i>{int(SINCE.timestamp())},created_at_i<=1762500000"
    )
    assert checkpoint == {}


@respx.mock
def test_hn_discussions_match_canonical_url_only():
    respx.get("https://hn.algolia.com/api/v1/search").respond(
        200,
        json={
            "hits": [
                {"objectID": "1", "url": "https://www.example.com/a/?utm_source=x", "points": 5},
                {"objectID": "2", "url": "https://example.com/a", "points": 50, "num_comments": 9},
                {"objectID": "3", "url": "https://example.com/a/other", "points": 99},
                {"objectID": "4", "url": None, "points": 1},
            ]
        },
    )
    with _http() as http:
        found = hackernews.discussions(http, "https://example.com/a")
    assert [d["url"] for d in found] == [
        "https://news.ycombinator.com/item?id=2",
        "https://news.ycombinator.com/item?id=1",
    ]
    assert found[0] == {
        "type": "hn_discussion",
        "url": "https://news.ycombinator.com/item?id=2",
        "title": None,
        "points": 50,
        "comments": 9,
    }


# --- RSS -----------------------------------------------------------------------------------------


@respx.mock
def test_rss_maps_entries_and_stores_validators():
    respx.get("https://news.example.com/rss").respond(
        200,
        content=(FIXTURES / "rss.xml").read_bytes(),
        headers={"ETag": '"v1"', "Content-Type": "application/rss+xml"},
    )
    src = _source("rss", "https://news.example.com/rss", attribution_label="Example News")
    checkpoint: dict = {}
    with _http() as http:
        (rows,) = list(rss.fetch(http, src, SINCE, checkpoint))
    assert checkpoint == {"etag": '"v1"'}
    assert len(rows) == 3  # the 2018 entry is older than `since`
    first = RawItem.model_validate(rows[0])
    assert first.external_id == "dc-1001"
    assert first.description == "A 100 MW campus."  # markup and script stripped
    assert first.publisher == "Example News" and first.author == "Jane Writer"
    assert first.source_tags == ["Cooling"]
    assert first.published_at == datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
    with pytest.raises(ValueError):
        RawItem.model_validate(rows[2])  # javascript: link


@respx.mock
def test_rss_conditional_get_and_304():
    route = respx.get("https://news.example.com/rss").respond(304)
    src = _source("rss", "https://news.example.com/rss")
    checkpoint = {"etag": '"v1"', "last_modified": "Mon, 09 Nov 2026 10:00:00 GMT"}
    with _http() as http:
        assert list(rss.fetch(http, src, SINCE, checkpoint)) == []
    headers = route.calls[0].request.headers
    assert headers["If-None-Match"] == '"v1"'
    assert headers["If-Modified-Since"] == "Mon, 09 Nov 2026 10:00:00 GMT"
    assert checkpoint["etag"] == '"v1"'  # unchanged


@respx.mock
def test_rss_garbage_is_a_permanent_error():
    respx.get("https://news.example.com/rss").respond(200, text="<html>not a feed")
    with _http() as http, pytest.raises(PermanentFetchError, match="unparseable"):
        list(rss.fetch(http, _source("rss", "https://news.example.com/rss"), SINCE, {}))


# --- arXiv ---------------------------------------------------------------------------------------


@respx.mock
def test_arxiv_versionless_ids_and_stops_at_since():
    route = respx.get("https://export.arxiv.org/api/query").respond(
        200, content=(FIXTURES / "arxiv.xml").read_bytes()
    )
    src = _source("arxiv", "https://export.arxiv.org/api/query", queries=["abs:x"])
    checkpoint: dict = {}
    with _http() as http:
        pages = list(arxiv.fetch(http, src, SINCE, checkpoint))
    assert route.call_count == 1 and checkpoint == {}
    params = _params(route.calls[0])
    assert params["sortBy"] == "submittedDate" and params["start"] == "0"
    rows = pages[0]
    assert [r["external_id"] for r in rows] == ["2611.01234", "2610.09999"]  # 2020 paper dropped
    paper = RawItem.model_validate(rows[0])
    assert paper.url == "https://arxiv.org/abs/2611.01234"
    assert paper.title == "Carbon-Aware Scheduling for Hyperscale Data Centers"
    assert paper.author == "A. Researcher, B. Scientist"
    assert paper.related_links == [{"type": "pdf", "url": "http://arxiv.org/pdf/2611.01234v2"}]
    assert paper.source_tags == ["cs.DC", "eess.SY"]


@respx.mock
def test_arxiv_empty_page_is_retryable_and_resumable():
    respx.get("https://export.arxiv.org/api/query").respond(
        200,
        text='<feed xmlns="http://www.w3.org/2005/Atom" '
        'xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">'
        "<opensearch:totalResults>500</opensearch:totalResults></feed>",
    )
    src = _source("arxiv", "https://export.arxiv.org/api/query", queries=["q"])
    checkpoint: dict = {"q": {"start": 200, "since": int(SINCE.timestamp())}}
    with _http() as http, pytest.raises(Exception, match="empty page at start=200"):
        list(arxiv.fetch(http, src, SINCE, checkpoint))
    assert checkpoint["q"]["start"] == 200


# --- GitHub ---------------------------------------------------------------------------------------


@respx.mock
def test_github_maps_repos_and_sends_token(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    get_settings.cache_clear()
    route = respx.get("https://api.github.com/search/repositories").respond(
        200, content=(FIXTURES / "github.json").read_bytes()
    )
    src = _source("github", "https://api.github.com/search/repositories", queries=["topic:dcim"])
    try:
        with _http() as http:
            (rows,) = list(github.fetch(http, src, SINCE, {}))
    finally:
        get_settings.cache_clear()
    request = route.calls[0].request
    assert request.headers["Authorization"] == "Bearer test-token"
    assert _params(route.calls[0])["q"] == "topic:dcim pushed:>=2026-01-01"
    repo = RawItem.model_validate(rows[0])
    assert repo.title == "acme/dcim-toolkit" and repo.points == 420
    assert repo.external_id == "101" and repo.source_tags == ["dcim", "datacenter"]
    assert repo.published_at == datetime(2025, 3, 1, 12, tzinfo=UTC)
    assert RawItem.model_validate(rows[1]).description is None
