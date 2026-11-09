"""Phase 5 feeds against real Postgres + pgvector (TEST_DATABASE_URL, THROWAWAY database):
trending and relevant ordering in SQL, sort modes, and the For You acceptance check."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from conftest import TEST_DATABASE_URL
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.api import common
from app.main import app
from app.models import EMBEDDING_DIM, AIAnnotation, Item, ItemSource, Source
from app.recommend import scoring
from app.security import reset_rate_limits

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL not set")

NOW = datetime.now(UTC)  # trending and relevant decay with age, so the data is relative to now
client = TestClient(app)


def axis(i: int) -> list[float]:
    v = [0.0] * EMBEDDING_DIM
    v[i] = 1.0
    return v


@pytest.fixture(scope="module")
def data(engine) -> dict[str, int]:
    S = sessionmaker(engine)
    ids: dict[str, int] = {}
    with S.begin() as s:
        src = {x.key: x for x in s.query(Source)}

        def add(
            name: str,
            cat: str,
            *,
            hours: float,
            source: str = "dcd",
            rel: int = 70,
            qual: int = 70,
            extra_sources: tuple[str, ...] = (),
            status: str = "processed",
            emb: list[float] | None = None,
            **item_kw: Any,
        ) -> None:
            it = Item(
                primary_source_id=src[source].id,
                original_url=f"https://example.com/{name}",
                canonical_url=f"https://example.com/{name}",
                url_hash=(name * 64)[:64],
                title=f"Title {name}",
                publisher="Example",
                published_at=NOW - timedelta(hours=hours),
                status=status,
                embedding=emb,
                **item_kw,
            )
            s.add(it)
            s.flush()
            for i, key in enumerate((source, *extra_sources)):
                s.add(
                    ItemSource(
                        item_id=it.id,
                        source_id=src[key].id,
                        external_id=f"{key}-{name}",
                        source_url=f"https://{key}.example/{name}",
                        is_primary=i == 0,
                    )
                )
            s.add(
                AIAnnotation(
                    item_id=it.id,
                    is_relevant=True,
                    relevance_score=rel,
                    quality_score=qual,
                    primary_category=cat,
                    categories=[cat],
                    content_type="news",
                    summary=f"Summary of {name}.",
                    tags=[f"tag-{cat}"],
                )
            )
            ids[name] = it.id

        # Trending: engagement, coverage and age.
        add("hn_hot", "cooling", hours=3, source="hn", qual=60, points=300, comments_count=100)
        add("covered", "power-energy", hours=2, qual=70, extra_sources=("dck",))
        add("fresh", "power-energy", hours=1, qual=70)
        add("hn_old", "power-energy", hours=240, source="hn", points=300, comments_count=100)
        for i in range(2):  # near-duplicates of "covered": two more outlets, so coverage = 3
            add(
                f"covered_dup{i}",
                "power-energy",
                hours=2,
                status="duplicate",
                duplicate_of=ids["covered"],
                duplicate_similarity=0.95,
                duplicate_reason="test",
            )
        # Relevant: a strong 3-day-old item vs a weak fresh one.
        add("rel_strong_old", "regulation", hours=72, rel=95, qual=85)
        add("rel_weak_new", "regulation", hours=0.5, rel=60, qual=50)
        # For You pool: cooling dominates; other categories are discovery material.
        for i in range(12):
            add(f"cool{i}", "cooling", hours=5 + i, qual=55 + i, emb=axis(0))
        for i in range(3):
            add(f"net{i}", "networking", hours=6 + i, qual=85 - i, emb=axis(1))
            add(f"sec{i}", "security", hours=6 + i, qual=80 - i, emb=axis(2))
    yield ids
    with engine.begin() as c:
        c.execute(text("TRUNCATE item_sources, ai_annotations, items CASCADE"))


@pytest.fixture(autouse=True)
def api(engine, data):
    S = sessionmaker(engine)

    def db():
        with S() as s:
            yield s

    app.dependency_overrides[common.get_db] = db
    reset_rate_limits()
    yield
    app.dependency_overrides.clear()


def names_of(items: list[dict[str, Any]], data: dict[str, int]) -> list[str]:
    by_id = {v: k for k, v in data.items()}
    return [by_id[i["id"]] for i in items]


def get(path: str, **params: Any) -> dict[str, Any]:
    r = client.get(path, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def foryou(profile: dict[str, Any], **params: Any) -> dict[str, Any]:
    r = client.post("/api/v1/feeds/foryou", json=profile, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def age_hours(item: dict[str, Any]) -> float:
    published = datetime.fromisoformat(item["published_at"].replace("Z", "+00:00"))
    return (datetime.now(UTC) - published).total_seconds() / 3600


# --- trending ----------------------------------------------------------------------------------


def test_trending_feed_ranks_engagement_then_coverage_then_freshness(data):
    names = names_of(get("/api/v1/feeds/trending", page_size=50)["items"], data)
    assert names[:3] == ["hn_hot", "covered", "fresh"]
    assert names.index("hn_old") > names.index("fresh")
    assert not {"covered_dup0", "covered_dup1"} & set(names)  # duplicates are never listed


def test_trending_sort_on_items_and_topics(data):
    assert names_of(get("/api/v1/items", sort="trending")["items"], data)[0] == "hn_hot"
    topic = get("/api/v1/topics/power-energy", sort="trending")["items"]["items"]
    assert names_of(topic, data)[:2] == ["covered", "fresh"]
    pages = [get("/api/v1/feeds/trending", page=p, page_size=7)["items"] for p in (1, 2, 3, 4)]
    seen = [i["id"] for page in pages for i in page]
    assert len(seen) == len(set(seen)) == get("/api/v1/feeds/trending")["total"]


# --- most relevant -----------------------------------------------------------------------------


def test_relevant_feed_matches_the_python_formula(data):
    items = get("/api/v1/feeds/relevant", page_size=50)["items"]
    names = names_of(items, data)
    assert names.index("rel_strong_old") < names.index("rel_weak_new")  # mild decay
    scores = [
        scoring.relevant(i["relevance_score"], i["quality_score"], age_hours(i)) for i in items
    ]
    assert scores == sorted(scores, reverse=True)  # the SQL ordering is the documented formula


def test_relevant_sort_on_topic_page(data):
    topic = get("/api/v1/topics/regulation", sort="relevant")["items"]["items"]
    assert names_of(topic, data) == ["rel_strong_old", "rel_weak_new"]


# --- For You (PLAN Phase 5 acceptance) ---------------------------------------------------------


def test_cooling_heavy_profile_returns_mostly_cooling_plus_discovery_and_excludes_read(data):
    read = [data["cool0"], data["cool1"], data["cool2"]]
    dismissed = [data["cool3"]]
    profile = {
        "categoryWeights": {"cooling": 14, "power-energy": 0.5},
        "tagWeights": {"tag-cooling": 3},
        "readIds": read,
        "bookmarkIds": [],
        "dismissedIds": dismissed,
        "explicitTopics": [],
    }
    body = foryou(profile, page_size=10)
    top = body["items"]
    assert body["cold_start"] is False and len(top) == 10
    cooling = [i for i in top if "cooling" in i["categories"]]
    discover = [i for i in top if i["kind"] == "discover"]
    assert len(cooling) == 8  # "mostly cooling"
    assert len(discover) == 2  # ~20% discovery
    assert [i["kind"] for i in top].index("discover") == 4
    # Best-quality items from categories with no signal, one category per slot.
    assert [i["primary_category"] for i in discover] == ["networking", "regulation"]
    assert all(i["reason"].startswith("Discover: ") for i in discover)
    assert top[0]["reason"] == "Because you read 3 Cooling articles"

    full = foryou(profile, page_size=50)
    assert full["total"] == len(full["items"]) and full["has_more"] is False
    shown = {i["id"] for i in full["items"]}
    assert not shown & set(read + dismissed)  # read and dismissed items are excluded


def test_foryou_pagination_never_repeats(data):
    profile = {"categoryWeights": {"cooling": 5}}
    total = foryou(profile)["total"]
    seen = [i["id"] for p in (1, 2, 3, 4) for i in foryou(profile, page=p, page_size=7)["items"]]
    assert len(seen) == len(set(seen)) == total


def test_foryou_reads_alone_use_embedding_similarity(data):
    """No weights yet, only reads: the taste embedding (avg of read vectors) ranks cooling first."""
    body = foryou({"readIds": [data["cool0"]]}, page_size=4)
    assert all("cooling" in i["categories"] for i in body["items"])
    assert body["items"][0]["kind"] == "personal"


def test_cold_start_falls_back_to_trending_and_relevant(data):
    body = foryou({"dismissedIds": [data["hn_hot"]]}, page_size=50)
    assert body["cold_start"] is True
    assert {i["kind"] for i in body["items"]} == {"trending", "relevant"}
    assert data["hn_hot"] not in {i["id"] for i in body["items"]}
    assert names_of(body["items"][:1], data) == ["covered"]  # the top trending item left
    assert foryou({})["cold_start"] is True


def test_foryou_rejects_unknown_category_slug(data):
    r = client.post("/api/v1/feeds/foryou", json={"categoryWeights": {"not-a-topic": 1}})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"
    assert "not-a-topic" in r.json()["error"]["message"]
    r = client.post("/api/v1/feeds/foryou", json={"explicitTopics": ["nope"]})
    assert r.status_code == 422
