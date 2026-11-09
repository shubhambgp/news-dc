"""Trend briefs, GET /trends and GET /stats against real Postgres (TEST_DATABASE_URL, THROWAWAY
database). The LLM is FakeChat."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from conftest import TEST_DATABASE_URL
from fakes import FakeChat
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from app import jobs
from app.ai import trends
from app.ai.classify import Prices
from app.ai.llm import LLMError
from app.api import common
from app.main import app
from app.models import AIAnnotation, Item, ItemSource, PipelineRun, Source, TrendBrief
from app.security import reset_rate_limits

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL not set")
client = TestClient(app)
PRICES = Prices(4.0, 20.0)


@pytest.fixture(scope="module")
def data(engine):
    """10 processed items this week (6 mention liquid cooling), 20 in the baseline (2 do), one
    rejected item this week, and two pipeline runs."""
    now = datetime.now(UTC)
    ids: dict[str, list[int]] = {"week": [], "base": []}
    with sessionmaker(engine).begin() as s:
        dcd = s.query(Source).filter_by(key="dcd").one()

        def add(name, days, status="processed", tags=(), companies=(), quality=60, cat="cooling"):
            it = Item(
                primary_source_id=dcd.id,
                original_url=f"https://news.example/{name}",
                canonical_url=f"https://news.example/{name}",
                url_hash=(name * 64)[:64],
                title=f"Story {name}",
                publisher="DCD",
                published_at=now - timedelta(days=days),
                status=status,
            )
            s.add(it)
            s.flush()
            s.add(ItemSource(item_id=it.id, source_id=dcd.id, source_url=it.original_url))
            s.add(
                AIAnnotation(
                    item_id=it.id,
                    is_relevant=status == "processed",
                    relevance_score=80,
                    quality_score=quality,
                    primary_category=cat,
                    categories=[cat],
                    content_type="news",
                    summary=f"Summary of {name}.",
                    key_insights=[],
                    entities={"companies": list(companies), "technologies": []},
                    tags=list(tags),
                )
            )
            return it.id

        for i in range(10):
            tags = ["liquid-cooling"] if i < 6 else ["grid"]
            ids["week"].append(add(f"w{i}", 1 + i * 0.5, tags=tags, companies=["Acme"], quality=70))
        for i in range(20):
            ids["base"].append(
                add(
                    f"b{i}",
                    10 + i,
                    tags=["liquid-cooling"] if i < 2 else ["grid"],
                    cat="power-energy",
                    quality=50,
                )
            )
        add("rej", 1, status="rejected_ai", tags=["liquid-cooling"])
        s.add_all(
            [
                PipelineRun(kind="ingest", trigger="cli", status="succeeded", fetched=31, new=31),
                PipelineRun(
                    kind="pipeline",
                    trigger="cli",
                    status="succeeded",
                    processed=30,
                    rejected_ai=1,
                    cost_usd_estimate=Decimal("0.0123"),
                ),
            ]
        )
    yield ids
    with engine.begin() as c:
        c.execute(
            text("TRUNCATE item_sources, ai_annotations, items, pipeline_runs, trend_briefs, jobs")
        )


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
    with engine.begin() as c:
        c.execute(text("TRUNCATE trend_briefs"))


def test_brief_stored_with_valid_citations_only(engine, data):
    llm = FakeChat(chunks=("Liquid cooling spreads [1, 2]. ", "Made up [31]. Grid [7]."))
    brief = trends.generate_brief(engine, llm, PRICES, 4000)
    assert brief is not None
    assert brief.content_md == "Liquid cooling spreads [1, 2]. Made up . Grid [7]."
    assert sorted(brief.sources) == sorted(data["week"])  # this week's processed items only
    assert brief.prompt_version == trends.PROMPT_VERSION and brief.model == "fake-chat"
    assert brief.cost_usd_estimate == Decimal("0.006")  # 900 in x $4 + 120 out x $20 per M
    msg = llm.calls[0]["messages"][0]["content"]
    assert msg.count("<source n=") == 10 and "Story rej" not in msg
    assert "liquid-cooling (+" in msg  # rising topics are given to the model
    assert llm.calls[0]["system"] == trends.system_prompt()


def test_brief_skipped_without_enough_items(engine):
    llm = FakeChat()
    old = datetime(2020, 1, 1, tzinfo=UTC)
    assert trends.generate_brief(engine, llm, PRICES, 4000, now=old) is None
    assert llm.calls == []


@pytest.mark.parametrize(
    "llm",
    [FakeChat(chunks=("No citations here.",)), FakeChat(stop_reason="max_tokens")],
)
def test_unusable_brief_is_not_stored(engine, llm):
    with pytest.raises(LLMError) as exc:
        trends.generate_brief(engine, llm, PRICES, 4000)
    assert not exc.value.retryable
    with Session(engine) as s:
        assert s.scalar(select(TrendBrief.id)) is None


def test_trend_brief_job_kind_accepted(engine):
    assert jobs.enqueue(engine, "trend_brief", {"trigger": "cli"}) is not None


def test_trends_endpoint(engine, data):
    trends.generate_brief(engine, FakeChat(chunks=("Cooling [1]. Grid [2].",)), PRICES, 4000)
    r = client.get("/api/v1/trends")
    assert r.status_code == 200
    body = r.json()
    lc = next(t for t in body["tags"] if t["term"] == "liquid-cooling")
    # 6/10 this week vs 2/20 before (the rejected item does not count): +500%
    assert lc == {
        "term": "liquid-cooling",
        "recent": 6,
        "baseline": 2,
        "change_pct": 500,
        "new": False,
    }
    assert all(t["term"] != "grid" for t in body["tags"])  # 4/10 vs 18/20 fell
    assert body["companies"][0]["term"] == "Acme" and body["companies"][0]["new"]
    brief = body["brief"]
    assert brief["content_md"] == "Cooling [1]. Grid [2]."
    assert [s["n"] for s in brief["sources"]] == list(range(1, 11))
    assert brief["sources"][0]["url"].startswith("https://news.example/w")
    assert body["now"].endswith("Z")


def test_trends_without_brief():
    r = client.get("/api/v1/trends")
    assert r.status_code == 200 and r.json()["brief"] is None


def test_stats_endpoint(data):
    r = client.get("/api/v1/stats")
    assert r.status_code == 200
    b = r.json()
    assert b["funnel"] == {
        "fetched": 31,
        "new": 0,
        "rejected_prefilter": 0,
        "rejected_ai": 1,
        "duplicate": 0,
        "failed": 0,
        "processed": 30,
    }
    cats = {c["slug"]: c for c in b["by_category"]}
    assert cats["cooling"]["items"] == 10 and cats["cooling"]["avg_quality"] == 70.0
    assert cats["power-energy"]["items"] == 20 and cats["power-energy"]["avg_quality"] == 50.0
    assert cats["networking"]["items"] == 0 and cats["networking"]["avg_quality"] is None
    assert b["by_content_type"] == [{"key": "news", "items": 30}]
    dcd = next(s for s in b["by_source"] if s["key"] == "dcd")
    assert (dcd["items"], dcd["processed"]) == (31, 30)
    assert len(b["per_day"]) == 60 and sum(d["items"] for d in b["per_day"]) == 30
    assert b["per_day"][-1]["date"] == datetime.now(UTC).date().isoformat()
    assert [run["kind"] for run in b["pipeline_runs"]] == ["pipeline", "ingest"]
    assert b["ai_cost"]["classifier_usd"] == 0.0123
    assert b["ai_cost"]["total_usd"] == 0.0123
