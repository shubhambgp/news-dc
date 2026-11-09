"""Every Phase 4 endpoint against real Postgres + pgvector (TEST_DATABASE_URL, THROWAWAY database):
filters, sorts, deterministic pagination, detail provenance, related, topics, hybrid search."""

import math
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from conftest import TEST_DATABASE_URL
from fakes import FakeEmbedder
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.api import common
from app.main import app
from app.models import EMBEDDING_DIM, AIAnnotation, Item, ItemSource, Source
from app.security import reset_rate_limits

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL not set")

T0 = datetime(2026, 10, 5, 12, tzinfo=UTC)
client = TestClient(app)


def vec(cos_with_e0: float, other_axis: int = 1) -> list[float]:
    """Unit vector with the given cosine similarity to e0."""
    v = [0.0] * EMBEDDING_DIM
    v[0] = cos_with_e0
    v[other_axis] = math.sqrt(1 - cos_with_e0**2)
    return v


E0 = vec(1.0)


class QueryEmbedder:
    """Maps chosen query strings to fixed vectors; anything else gets an unrelated vector."""

    def __init__(self, mapping: dict[str, list[float]]) -> None:
        self.mapping = mapping

    def embed(self, text: str) -> list[float]:
        return self.mapping.get(text, vec(0.0, other_axis=200))


@pytest.fixture(scope="module")
def data(engine) -> dict[str, int]:
    """Six public items plus a rejected one and a near-duplicate."""
    S = sessionmaker(engine)
    with S.begin() as s:
        src = {x.key: x for x in s.query(Source).filter(Source.key.in_(["hn", "dcd", "arxiv"]))}
        ids: dict[str, int] = {}

        def add(
            name: str,
            title: str,
            *,
            days: float,
            source: str,
            cats: list[str],
            ctype: str = "news",
            rel: int = 80,
            qual: int = 60,
            emb: list[float] | None = None,
            status: str = "processed",
            summary: str = "",
            extra_sources: tuple[str, ...] = (),
            **item_kw: Any,
        ) -> None:
            it = Item(
                primary_source_id=src[source].id,
                original_url=f"https://example.com/{name}",
                canonical_url=f"https://example.com/{name}",
                url_hash=(name * 64)[:64],
                title=title,
                description=f"Description of {name}.",
                content_text="full text that must never be returned by the API",
                publisher="Example",
                published_at=T0 - timedelta(days=days),
                status=status,
                embedding=emb,
                points=10,
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
                        source_title=title,
                        source_engagement={"points": 10 * (i + 1)},
                        is_primary=i == 0,
                    )
                )
            s.add(
                AIAnnotation(
                    item_id=it.id,
                    is_relevant=status != "rejected_ai",
                    relevance_score=rel,
                    quality_score=qual,
                    primary_category=cats[0],
                    categories=cats,
                    content_type=ctype,
                    summary=summary or f"Summary of {title}.",
                    key_insights=[{"type": "technical", "text": f"Insight on {name}."}],
                    entities={"companies": ["Equinix"], "technologies": [], "locations": []},
                    tags=["tag-" + name],
                )
            )
            ids[name] = it.id

        add(
            "cool",
            "Liquid cooling retrofit at a colocation campus",
            days=0,
            source="hn",
            extra_sources=("dcd",),
            cats=["cooling", "sustainability"],
            rel=90,
            qual=80,
            emb=E0,
        )
        add(
            "immersion",
            "Immersion startup raises a funding round",
            days=1,
            source="dcd",
            cats=["cooling", "economics-finance"],
            ctype="investment",
            rel=70,
            qual=60,
            emb=vec(0.85),
            summary="Investors back immersion tanks for dense racks.",
        )
        add(
            "smr",
            "Nuclear SMR deal powers new campus",
            days=2,
            source="hn",
            cats=["power-energy"],
            rel=95,
            qual=90,
            emb=vec(0.0, other_axis=2),
        )
        add(
            "gpu",
            "GPU scheduling for training clusters",
            days=3,
            source="arxiv",
            cats=["ai-compute-gpus", "optimization"],
            ctype="research",
            rel=60,
            qual=70,
            emb=vec(0.9, other_axis=3),
        )
        # Same published_at as "immersion": the id tie-breaker decides their order.
        add("fiber", "Subsea fiber landing", days=1, source="dcd", cats=["networking"], qual=30)
        add(
            "old", "Old colocation pricing study", days=40, source="dcd", cats=["economics-finance"]
        )
        add(
            "gossip",
            "Celebrity cooling gossip",
            days=0,
            source="hn",
            cats=["cooling"],
            status="rejected_ai",
            emb=E0,
        )
        add(
            "dup",
            "Colocation campus gets liquid cooling",
            days=0.5,
            source="dcd",
            cats=["cooling"],
            status="duplicate",
            emb=vec(0.99),
            duplicate_of=ids["cool"],
            duplicate_similarity=0.95,
            duplicate_reason="test",
        )
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
    app.dependency_overrides[common.get_embedder] = lambda: QueryEmbedder({})
    reset_rate_limits()
    yield
    app.dependency_overrides.clear()


def ids_of(body: dict[str, Any], data: dict[str, int]) -> list[str]:
    names = {v: k for k, v in data.items()}
    return [names[i["id"]] for i in body["items"]]


def get(path: str, **params: Any) -> dict[str, Any]:
    r = client.get(path, params=params)
    assert r.status_code == 200, r.text
    return r.json()


# --- /items ---------------------------------------------------------------------------------


def test_items_lists_only_processed_newest_first_with_id_tiebreak(data):
    body = get("/api/v1/items")
    names = ids_of(body, data)
    assert set(names) == {"cool", "immersion", "fiber", "smr", "gpu", "old"}
    later, earlier = sorted(["immersion", "fiber"], key=data.get, reverse=True)
    assert names == ["cool", later, earlier, "smr", "gpu", "old"]
    assert body["total"] == 6 and body["has_more"] is False
    first = body["items"][0]
    assert first["published_at"] == "2026-10-05T12:00:00Z"  # UTC, Z suffix
    assert first["source"] == {"key": "hn", "name": first["source"]["name"]}
    assert "content_text" not in first


def test_items_pagination_never_skips_or_repeats(data):
    seen: list[int] = []
    for page in (1, 2, 3):
        body = get("/api/v1/items", page=page, page_size=2)
        assert body["page"] == page and body["total"] == 6
        assert body["has_more"] is (page < 3)
        seen += [i["id"] for i in body["items"]]
    assert len(seen) == len(set(seen)) == 6
    assert get("/api/v1/items", page=4, page_size=2)["items"] == []


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"category": "cooling"}, {"cool", "immersion"}),
        ({"category": "sustainability"}, {"cool"}),  # non-primary category matches too
        ({"category": "no-such-topic"}, set()),
        ({"content_type": "research"}, {"gpu"}),
        ({"source": "dcd"}, {"cool", "immersion", "fiber", "old"}),  # any source, not only primary
        ({"source": "arxiv"}, {"gpu"}),
        ({"min_quality": 70}, {"cool", "smr", "gpu"}),
        ({"from": "2026-10-03T12:00:00Z"}, {"cool", "immersion", "fiber", "smr"}),
        ({"to": "2026-10-03T12:00:00Z"}, {"gpu", "old"}),  # `to` is exclusive
        ({"from": "2026-10-01", "to": "2026-10-04T00:00:00+05:30"}, {"smr", "gpu"}),
        ({"category": "cooling", "content_type": "investment"}, {"immersion"}),
    ],
)
def test_items_filters(data, params, expected):
    assert set(ids_of(get("/api/v1/items", **params), data)) == expected


def test_items_sorts(data):
    assert ids_of(get("/api/v1/items", sort="relevance"), data)[:2] == ["smr", "cool"]
    assert ids_of(get("/api/v1/items", sort="quality"), data)[:3] == ["smr", "cool", "gpu"]


# --- /items/{id} ----------------------------------------------------------------------------


def test_item_detail_has_annotation_coverage_and_duplicates(data):
    d = get(f"/api/v1/items/{data['cool']}")
    assert d["title"].startswith("Liquid cooling")
    assert d["description"] == "Description of cool."
    assert d["key_insights"] == [{"type": "technical", "text": "Insight on cool."}]
    assert d["entities"]["companies"] == ["Equinix"]
    assert [(c["source"]["key"], c["is_primary"]) for c in d["coverage"]] == [
        ("hn", True),
        ("dcd", False),
    ]
    assert d["coverage"][1]["engagement"] == {"points": 20}
    assert [(x["id"], x["similarity"]) for x in d["also_covered_by"]] == [(data["dup"], 0.95)]
    assert "content_text" not in d and "embedding" not in d


@pytest.mark.parametrize("name", ["gossip", "dup"])
def test_item_detail_hides_non_processed(data, name):
    r = client.get(f"/api/v1/items/{data[name]}")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_item_detail_missing_is_404():
    assert client.get("/api/v1/items/987654321").json()["error"]["code"] == "not_found"


# --- /items/{id}/related ----------------------------------------------------------------------


def test_related_ranks_by_similarity_plus_shared_categories(data):
    rel = get(f"/api/v1/items/{data['cool']}/related")
    names = ids_of({"items": rel}, data)
    # gpu is more similar (0.90 vs 0.85) but immersion shares "cooling": 0.85 + 0.1 > 0.90.
    assert names[:2] == ["immersion", "gpu"]
    assert rel[0]["similarity"] == pytest.approx(0.85, abs=1e-3)
    assert rel[0]["score"] == pytest.approx(0.95, abs=1e-3)
    # Never itself, a rejected item, a duplicate, or an item without an embedding.
    assert not {"cool", "gossip", "dup", "fiber", "old"} & set(names)
    assert len(rel) <= 6


def test_related_without_embedding_is_empty_and_missing_is_404(data):
    assert get(f"/api/v1/items/{data['fiber']}/related") == []
    assert client.get("/api/v1/items/987654321/related").status_code == 404


# /feeds/relevant, /feeds/trending and /feeds/foryou: tests/test_recommend_db.py (Phase 5).


# --- /topics --------------------------------------------------------------------------------


def test_topics_have_counts_and_latest_three(data):
    topics = {t["slug"]: t for t in get("/api/v1/topics")}
    assert len(topics) == 14
    assert topics["cooling"]["item_count"] == 2
    assert [i["id"] for i in topics["cooling"]["latest"]] == [data["cool"], data["immersion"]]
    assert topics["economics-finance"]["item_count"] == 2  # immersion (secondary) + old
    assert topics["security"] == {**topics["security"], "item_count": 0, "latest": []}
    assert list(topics)[0] == "dc-infrastructure"  # sort_order from categories.yaml


def test_topic_page_filters_and_404(engine, data):
    body = get("/api/v1/topics/cooling", sort="quality")
    assert body["name"] and body["description"]
    assert ids_of(body["items"], data) == ["cool", "immersion"]
    assert ids_of(get("/api/v1/topics/cooling", min_quality=70)["items"], data) == ["cool"]
    assert client.get("/api/v1/topics/no-such-topic").status_code == 404
    with engine.begin() as c:
        c.execute(text("UPDATE categories SET enabled = false WHERE slug = 'networking'"))
    try:
        assert client.get("/api/v1/topics/networking").status_code == 404
        assert "networking" not in {t["slug"] for t in get("/api/v1/topics")}
    finally:
        with engine.begin() as c:
            c.execute(text("UPDATE categories SET enabled = true WHERE slug = 'networking'"))


# --- /search --------------------------------------------------------------------------------


def test_search_keyword_matches_title_and_ai_summary_with_highlights(data):
    body = get("/api/v1/search", q="liquid cooling")
    assert body["mode"] == "hybrid"
    names = ids_of(body, data)
    assert names[0] == "cool"
    assert "gossip" not in names and "dup" not in names
    assert "<mark>" in body["items"][0]["snippet"]
    # "tanks" is only in the AI summary of "immersion" (items.tsv has no summary, D-029).
    assert ids_of(get("/api/v1/search", q="tanks"), data) == ["immersion"]


def test_search_semantic_hits_fuse_with_keyword_hits(data):
    app.dependency_overrides[common.get_embedder] = lambda: QueryEmbedder({"campus": E0})
    body = get("/api/v1/search", q="campus")
    names = ids_of(body, data)
    # "cool" matches both retrievers, so it ranks first; "smr" (keyword only) and
    # "immersion"/"gpu" (semantic only, similarity ≥ 0.6) are also found.
    assert names[0] == "cool"
    assert {"smr", "immersion", "gpu"} <= set(names)
    assert body["total"] == len(names)
    scores = [i["score"] for i in body["items"]]
    assert scores == sorted(scores, reverse=True)


def test_search_drops_semantic_hits_below_similarity_floor(data):
    app.dependency_overrides[common.get_embedder] = lambda: QueryEmbedder(
        {"zzqx": vec(0.5, other_axis=200)}
    )
    assert get("/api/v1/search", q="zzqx")["items"] == []


def test_search_filters_and_pagination(data):
    app.dependency_overrides[common.get_embedder] = lambda: QueryEmbedder({"campus": E0})
    assert ids_of(get("/api/v1/search", q="campus", source="arxiv"), data) == ["gpu"]
    p1 = get("/api/v1/search", q="campus", page_size=2)
    p2 = get("/api/v1/search", q="campus", page=2, page_size=2)
    assert p1["has_more"] is True
    assert not {i["id"] for i in p1["items"]} & {i["id"] for i in p2["items"]}


def test_search_degrades_to_keyword_when_embedder_fails(data):
    app.dependency_overrides[common.get_embedder] = lambda: FakeEmbedder(fail=True)
    body = get("/api/v1/search", q="nuclear")
    assert body["mode"] == "keyword"
    assert ids_of(body, data) == ["smr"]


def test_search_no_results_and_odd_syntax(data):
    assert get("/api/v1/search", q="the")["items"] == []  # stopwords only: empty tsquery
    assert get("/api/v1/search", q='"liquid cooling" -immersion OR')["total"] >= 1


def test_utc_sessions(engine):
    from app.db import SessionLocal

    with SessionLocal() as s:  # the app's real engine settings, not the test engine
        assert isinstance(s, Session)
        assert s.execute(text("SHOW timezone")).scalar_one() == "UTC"


def test_search_sort_latest_keeps_hits_newest_first(data):
    app.dependency_overrides[common.get_embedder] = lambda: QueryEmbedder({"campus": E0})
    best = get("/api/v1/search", q="campus")
    latest = get("/api/v1/search", q="campus", sort="latest")
    assert set(ids_of(latest, data)) == set(ids_of(best, data))
    dates = [i["published_at"] for i in latest["items"]]
    assert dates == sorted(dates, reverse=True)
    assert client.get("/api/v1/search", params={"q": "campus", "sort": "x"}).status_code == 422
