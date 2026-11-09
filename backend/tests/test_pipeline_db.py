"""AI pipeline against real Postgres (TEST_DATABASE_URL, a THROWAWAY database) with a fake LLM and
embedder: statuses, stored annotations, near-duplicates, retries, spend limits, run locking."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from conftest import TEST_DATABASE_URL
from fakes import FakeEmbedder, FakeLLM, answer
from sqlalchemy import text

from app.ai.classify import PROMPT_VERSION
from app.ai.llm import LLMError
from app.config import Settings
from app.pipeline import graph
from app.pipeline.graph import PIPELINE_LOCK_KEY, reprocess_outdated, run_pipeline

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL not set")

NOW = datetime(2026, 11, 1, tzinfo=UTC)


@pytest.fixture(autouse=True)
def clean(engine, monkeypatch):
    settings = Settings(_env_file=None, max_llm_items_per_run=100)  # ignore the developer's .env
    monkeypatch.setattr(graph, "get_settings", lambda: settings)
    yield settings
    with engine.begin() as c:
        c.execute(text("TRUNCATE item_sources, ai_annotations, items, pipeline_runs, jobs CASCADE"))


_n = 0


def add_item(
    engine, title: str, *, source: str = "hn", desc: str | None = None, days: int = 0
) -> int:
    global _n
    _n += 1
    with engine.begin() as c:
        return c.execute(
            text(
                "INSERT INTO items (primary_source_id, original_url, canonical_url, url_hash, "
                "title, description, published_at) VALUES "
                "((SELECT id FROM sources WHERE key = :src), :url, :url, md5(:url) || md5(:url), "
                ":title, :desc, :pub) RETURNING id"
            ),
            {
                "src": source,
                "url": f"https://example.com/{_n}",
                "title": title,
                "desc": desc,
                "pub": NOW + timedelta(days=days),
            },
        ).scalar_one()


def q(engine, sql: str, **params) -> Any:
    with engine.connect() as c:
        return c.execute(text(sql), params).all()


def status(engine, item_id: int) -> str:
    return q(engine, "SELECT status FROM items WHERE id = :i", i=item_id)[0][0]


def run(engine, llm=None, embedder=None, **kw):
    return run_pipeline(
        engine=engine, llm=llm or FakeLLM(), embedder=embedder or FakeEmbedder(), **kw
    )


def test_every_outcome_is_stored_with_its_reason(engine):
    good = add_item(engine, "Operator deploys liquid cooling at its data center", desc="details")
    noise = add_item(engine, "Show HN: my sourdough starter tracker")
    off_topic = add_item(engine, "Nvidia GeForce review for gamers")
    weak = add_item(engine, "Data center press release")
    dc_source = add_item(engine, "Weekly roundup", source="dcd")  # no keywords, DC-only source

    def replies(user: str, n: int):
        if "GeForce" in user:
            return answer(is_relevant=False, relevance_score=20, reject_reason="gaming GPU review")
        if "press release" in user:
            return answer(quality_score=30)
        return answer()

    llm = FakeLLM(replies)
    result = run(engine, llm)

    assert {i: status(engine, i) for i in (good, noise, off_topic, weak, dc_source)} == {
        good: "processed",
        noise: "rejected_prefilter",
        off_topic: "rejected_ai",
        weak: "rejected_ai",
        dc_source: "processed",
    }
    assert len(llm.calls) == 4  # the pre-filtered item cost nothing
    assert result.status == "succeeded"
    assert result.counts == {"processed": 2, "rejected_prefilter": 1, "rejected_ai": 2}

    ann = q(
        engine,
        "SELECT item_id, primary_category, categories, tags, model, prompt_version, prompt_hash, "
        "tokens_in, tokens_out, attempts, reject_reason FROM ai_annotations ORDER BY item_id",
    )
    assert [a.item_id for a in ann] == [good, off_topic, weak, dc_source]  # rejections kept
    a = ann[0]
    assert (a.primary_category, a.categories, a.tags) == (
        "cooling",
        ["cooling", "sustainability"],
        ["liquid-cooling", "pue"],
    )
    assert (a.model, a.prompt_version, len(a.prompt_hash)) == ("fake-model", PROMPT_VERSION, 64)
    assert (a.tokens_in, a.tokens_out, a.attempts, a.reject_reason) == (1000, 200, 1, None)
    assert ann[1].reject_reason == "gaming GPU review"
    assert ann[2].reject_reason == "quality 30 < 40"

    reasons = dict(q(engine, "SELECT id, status_reason FROM items"))
    assert reasons[noise] == "no data center keywords"  # every rejection is auditable
    assert reasons[weak] == "quality 30 < 40" and reasons[good] is None
    # Only published items are embedded.
    embedded = q(engine, "SELECT id FROM items WHERE embedding IS NOT NULL ORDER BY id")
    assert [r.id for r in embedded] == [good, dc_source]
    run_row = q(engine, "SELECT * FROM pipeline_runs")[0]
    assert (run_row.kind, run_row.status, run_row.fetched, run_row.processed) == (
        "pipeline",
        "succeeded",
        5,
        2,
    )
    assert (run_row.rejected_prefilter, run_row.rejected_ai, run_row.finished_at is not None) == (
        1,
        2,
        True,
    )


def test_rerun_does_not_reprocess_or_duplicate(engine):
    add_item(engine, "Data center opens")
    run(engine)
    llm = FakeLLM()
    second = run(engine, llm)
    assert llm.calls == [] and second.counts == {}
    assert q(engine, "SELECT count(*) FROM ai_annotations")[0][0] == 1


def test_near_duplicates_in_one_run_and_across_runs(engine):
    a = add_item(engine, "Hyperscaler buys data center campus", days=0)
    b = add_item(engine, "Hyperscaler buys data center campus", days=1)  # same story, parallel
    late = add_item(engine, "Hyperscaler buys data center campus", days=30)  # outside 14 days
    run(engine)
    assert [status(engine, i) for i in (a, b, late)] == ["processed", "duplicate", "processed"]
    dup = q(engine, "SELECT * FROM items WHERE id = :i", i=b)[0]
    assert dup.duplicate_of == a and dup.duplicate_similarity > 0.99
    assert "cosine similarity" in dup.duplicate_reason and str(a) in dup.duplicate_reason

    c = add_item(engine, "Hyperscaler buys data center campus", days=2)  # next run: from the DB
    run(engine)
    row = q(engine, "SELECT status, duplicate_of FROM items WHERE id = :i", i=c)[0]
    assert (row.status, row.duplicate_of) == ("duplicate", a)


def test_transient_llm_failure_keeps_item_then_gives_up(engine):
    item = add_item(engine, "Data center story")
    down = FakeLLM(lambda u, n: LLMError("RateLimitError 429", retryable=True))
    for expected_attempts in (1, 2):
        result = run(engine, down)
        row = q(engine, "SELECT status, ai_attempts, status_reason FROM items")[0]
        assert (row.status, row.ai_attempts) == ("new", expected_attempts)  # never discarded
        assert "429" in row.status_reason and result.counts == {"retry_later": 1}
    run(engine, down)
    assert status(engine, item) == "failed"
    assert run(engine).counts == {}  # failed items are not picked up again


def test_provider_outage_aborts_run_and_keeps_items(engine):
    for i in range(8):
        add_item(engine, f"Data center story {i}")
    down = FakeLLM(lambda u, n: LLMError("APIConnectionError", retryable=True))
    result = run(engine, down)
    assert result.status == "failed" and result.retryable
    assert "unavailable" in result.error
    assert q(engine, "SELECT DISTINCT status FROM items")[0][0] == "new"


def test_bad_credentials_abort_without_touching_items(engine):
    add_item(engine, "Data center story")
    bad = FakeLLM(lambda u, n: LLMError("AuthenticationError 401", retryable=False, fatal=True))
    result = run(engine, bad)
    assert (result.status, result.retryable) == ("failed", False)
    assert q(engine, "SELECT status, ai_attempts FROM items")[0] == ("new", 0)


def test_invalid_output_twice_marks_failed(engine):
    item = add_item(engine, "Data center story")
    result = run(engine, FakeLLM(lambda u, n: "garbage"))
    assert status(engine, item) == "failed" and result.status == "partial"
    assert "invalid classifier output" in q(engine, "SELECT status_reason FROM items")[0][0]


def test_llm_item_cap_stops_run_with_reason(engine):
    ids = [add_item(engine, f"Data center story {i}") for i in range(4)]
    llm = FakeLLM()
    result = run(engine, llm, max_llm_items=2)
    assert len(llm.calls) == 2
    assert result.stop_reason == "MAX_LLM_ITEMS_PER_RUN reached"
    assert sorted(status(engine, i) for i in ids) == ["new", "new", "processed", "processed"]
    assert q(engine, "SELECT stop_reason FROM pipeline_runs")[0][0] == result.stop_reason


def test_daily_spend_limit(engine, clean):
    clean.classifier_input_usd_per_mtok = 1.0
    clean.daily_llm_budget_usd = 0.5
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO pipeline_runs (kind, trigger, status, cost_usd_estimate) "
                "VALUES ('pipeline', 'cli', 'succeeded', 0.5)"
            )
        )
    add_item(engine, "Data center story")
    llm = FakeLLM()
    result = run(engine, llm)
    assert llm.calls == [] and result.stop_reason == "DAILY_LLM_BUDGET_USD reached"


def test_cost_is_recorded_per_item_and_run(engine, clean):
    clean.classifier_input_usd_per_mtok = 1.0
    clean.classifier_output_usd_per_mtok = 5.0
    add_item(engine, "Data center story")
    result = run(engine)
    assert result.cost_usd == pytest.approx(0.002)
    assert q(engine, "SELECT cost_usd_estimate FROM ai_annotations")[0][0] == Decimal("0.002")
    assert q(engine, "SELECT cost_usd_estimate FROM pipeline_runs")[0][0] == Decimal("0.0020")


def test_embedding_failure_keeps_item_and_is_retried(engine):
    item = add_item(engine, "Data center story")
    run(engine, embedder=FakeEmbedder(fail=True))
    row = q(engine, "SELECT status, embedding, status_reason FROM items")[0]
    assert (row.status, row.embedding) == ("processed", None)  # annotation kept, still published
    assert "embedding failed" in row.status_reason
    run(engine)  # next run embeds the backlog
    row = q(engine, "SELECT embedding, status_reason FROM items WHERE id = :i", i=item)[0]
    assert row.embedding is not None and row.status_reason is None


def test_overlapping_runs_are_skipped(engine):
    add_item(engine, "Data center story")
    with engine.connect() as other:
        other.execute(text("SELECT pg_advisory_lock(:k)"), {"k": PIPELINE_LOCK_KEY})
        result = run(engine)
        other.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": PIPELINE_LOCK_KEY})
        other.commit()
    assert result.status == "skipped" and result.run_id is None
    assert q(engine, "SELECT count(*) FROM pipeline_runs")[0][0] == 0
    assert run(engine).counts == {"processed": 1}  # the lock was released


def test_reprocess_items_with_an_old_prompt_version(engine):
    item = add_item(engine, "Data center story")
    run(engine)
    assert reprocess_outdated(engine) == 0
    with engine.begin() as c:
        c.execute(text("UPDATE ai_annotations SET prompt_version = 'classify-v0'"))
    assert reprocess_outdated(engine) == 1
    assert status(engine, item) == "new"
    run(engine)
    assert q(engine, "SELECT prompt_version FROM ai_annotations")[0][0] == PROMPT_VERSION
    assert status(engine, item) == "processed"


def test_shutdown_stops_between_pages(engine):
    add_item(engine, "Data center story")
    result = run(engine, should_stop=lambda: True)
    assert result.stop_reason == "shutdown requested" and result.counts == {}
