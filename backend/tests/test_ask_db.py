"""Ask NewsDC retrieval against real Postgres + pgvector (TEST_DATABASE_URL, THROWAWAY database):
the right items come back for seeded data, recency matters for "latest" questions, rejected
items never become evidence, and source links come from the database."""

import math
from datetime import UTC, datetime, timedelta

import pytest
from conftest import TEST_DATABASE_URL
from fakes import FakeChat, FakeEmbedder
from fastapi.testclient import TestClient
from sqlalchemy import func
from sqlalchemy.orm import Session, sessionmaker

from app.api import ask, common, search
from app.api.common import Filters
from app.main import app
from app.models import EMBEDDING_DIM, AIAnnotation, Item, Source
from app.security import reset_rate_limits

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL not set")
client = TestClient(app)


def vec(cos_with_e0: float, other_axis: int = 1) -> list[float]:
    v = [0.0] * EMBEDDING_DIM
    v[0] = cos_with_e0
    v[other_axis] = math.sqrt(1 - cos_with_e0**2)
    return v


class QueryEmbedder:
    def embed(self, text: str) -> list[float]:
        return vec(1.0) if "cooling" in text else vec(0.0, other_axis=200)


@pytest.fixture(scope="module")
def data(engine) -> dict[str, int]:
    now = datetime.now(UTC)
    S = sessionmaker(engine)
    ids: dict[str, int] = {}
    with S.begin() as s:
        dcd = s.query(Source).filter_by(key="dcd").one()

        def add(name: str, title: str, summary: str, days: float, emb, status="processed"):
            it = Item(
                primary_source_id=dcd.id,
                original_url=f"https://news.example/{name}",
                canonical_url=f"https://news.example/{name}",
                url_hash=(name * 64)[:64],
                title=title,
                description=summary,
                publisher="DCD",
                published_at=now - timedelta(days=days),
                status=status,
                embedding=emb,
            )
            s.add(it)
            s.flush()
            s.add(
                AIAnnotation(
                    item_id=it.id,
                    is_relevant=status == "processed",
                    relevance_score=85,
                    quality_score=70,
                    primary_category="cooling",
                    categories=["cooling"],
                    content_type="news",
                    summary=summary,
                    key_insights=[{"type": "technical", "text": f"Insight about {name}."}],
                    entities={},
                    tags=[],
                )
            )
            ids[name] = it.id

        add(
            "old",
            "Immersion cooling pilot finishes",
            "An operator finished a liquid cooling pilot with immersion tanks.",
            120,
            vec(0.97),
        )
        add(
            "new",
            "Direct-to-chip cooling goes live",
            "A colocation provider switched racks to direct liquid cooling.",
            1,
            vec(0.8),
        )
        add("power", "Utility signs grid deal", "A utility will supply 300 MW.", 2, vec(0.0, 7))
        add(
            "rejected",
            "Liquid cooling for gaming PCs",
            "A liquid cooling kit for desktop gaming PCs.",
            1,
            vec(0.99),
            status="rejected_ai",
        )
    return ids


@pytest.fixture
def db(engine, data):
    with Session(engine) as s:
        yield s


def ids(rows) -> list[int]:
    return [r[0].id for r in rows]


def test_retrieves_matching_items_only(db, data):
    got = ids(ask.retrieve(db, QueryEmbedder(), "How is liquid cooling being deployed?", False))
    assert set(got) == {data["old"], data["new"]}  # not the grid deal, never the rejected item


def test_latest_questions_prefer_recent_evidence(db, data):
    q = "liquid cooling immersion pilot"
    fused, _ = search.hybrid(
        db, QueryEmbedder(), func.websearch_to_tsquery("english", q), q, Filters()
    )
    assert fused[0][0] == data["old"]  # the better match, but 120 days old
    assert ids(ask.retrieve(db, QueryEmbedder(), q, True))[0] == data["new"]  # fresher wins


def test_keyword_only_when_embeddings_fail(db, data):
    got = ids(ask.retrieve(db, FakeEmbedder(fail=True), "grid deal utility", False))
    assert got == [data["power"]]


def test_no_match_returns_nothing(db):
    assert ask.retrieve(db, QueryEmbedder(), "sourdough bread recipes", False) == []


def test_endpoint_cites_database_links(engine, data):
    S = sessionmaker(engine)

    def get_db():
        with S() as s:
            yield s

    llm = FakeChat(chunks=("Racks moved to direct liquid cooling [1].",))
    app.dependency_overrides[common.get_db] = get_db
    app.dependency_overrides[common.get_embedder] = QueryEmbedder
    app.dependency_overrides[ask.get_llm] = lambda: llm
    reset_rate_limits()
    try:
        r = client.post("/api/v1/ask", json={"question": "What is the latest in liquid cooling?"})
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200
    first = r.text.split("\n\n")[0]
    assert first.startswith("event: sources")
    assert f'"n":1,"id":{data["new"]},"title":"Direct-to-chip cooling goes live"' in first
    assert "https://news.example/new" in first and "rejected" not in first
    prompt = llm.calls[0]["messages"][-1]["content"]
    assert "switched racks to direct liquid cooling" in prompt
    assert r.text.rstrip().endswith('{"cited":[1],"removed_citations":0,"truncated":false}')
