"""Durable job lifecycle (PLAN §11.4) and the worker's job handling against real Postgres."""

import threading
from datetime import UTC, datetime, timedelta

import pytest
from conftest import TEST_DATABASE_URL
from sqlalchemy import text

from app import db, jobs, worker
from app.ai.llm import LLMError
from app.pipeline.graph import PipelineResult

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL not set")


@pytest.fixture(autouse=True)
def clean(engine, monkeypatch):
    monkeypatch.setattr(db, "engine", engine)  # the worker uses the module-level engine
    yield
    with engine.begin() as c:
        c.execute(text("TRUNCATE jobs"))


def row(engine, job_id: int):
    with engine.connect() as c:
        return c.execute(text("SELECT * FROM jobs WHERE id = :i"), {"i": job_id}).one()


def age(engine, job_id: int, column: str, seconds: int) -> None:
    with engine.begin() as c:
        c.execute(
            text(f"UPDATE jobs SET {column} = now() - make_interval(secs => :s) WHERE id = :i"),
            {"s": seconds, "i": job_id},
        )


def test_one_active_job_per_kind(engine):
    first = jobs.enqueue(engine, "pipeline")
    assert first and jobs.enqueue(engine, "pipeline") is None  # replicas can't double-queue
    assert jobs.enqueue(engine, "ingest_all")  # other kinds are independent
    job = jobs.claim(engine, "w1")
    jobs.complete(engine, job, "w1")
    assert jobs.enqueue(engine, "pipeline")  # finished jobs don't block
    assert jobs.enqueue(engine, "pipeline", not_within=timedelta(hours=1)) is None


def test_unknown_kind_is_rejected(engine):
    with pytest.raises(ValueError):
        jobs.enqueue(engine, "mine_bitcoin")


def test_concurrent_claims_never_share_a_job(engine):
    jobs.enqueue(engine, "pipeline")
    jobs.enqueue(engine, "ingest_all")
    got: list = []
    start = threading.Barrier(4)

    def take(name: str) -> None:
        start.wait()
        got.append(jobs.claim(engine, name))

    threads = [threading.Thread(target=take, args=(f"w{i}",)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    claimed = [j.id for j in got if j is not None]
    assert len(claimed) == 2 and len(set(claimed)) == 2


def test_transient_failures_back_off_then_dead_letter(engine):
    job_id = jobs.enqueue(engine, "pipeline", max_attempts=2)
    job = jobs.claim(engine, "w1")
    assert (job.id, job.attempt_count, job.status) == (job_id, 1, "running")
    assert jobs.fail(engine, job, "w1", "timeout") == "retry_wait"
    r = row(engine, job_id)
    assert r.status == "retry_wait" and r.next_retry_at > datetime.now(UTC)
    assert r.locked_by is None and r.last_error == "timeout"
    assert jobs.claim(engine, "w1") is None  # not due yet

    age(engine, job_id, "next_retry_at", 1)
    job = jobs.claim(engine, "w2")
    assert job.attempt_count == 2
    assert jobs.fail(engine, job, "w2", "timeout again") == "dead_letter"  # no infinite retry
    assert row(engine, job_id).finished_at is not None

    assert jobs.retry_dead(engine, job_id)  # manual retry
    r = row(engine, job_id)
    assert (r.status, r.attempt_count) == ("pending", 0)


def test_permanent_failure_skips_retries(engine):
    job_id = jobs.enqueue(engine, "pipeline")
    job = jobs.claim(engine, "w1")
    assert jobs.fail(engine, job, "w1", "bad API key", permanent=True) == "dead_letter"
    assert row(engine, job_id).attempt_count == 1


def test_expired_lease_is_reclaimed_and_stale_worker_cannot_finish(engine):
    job_id = jobs.enqueue(engine, "pipeline")
    stale = jobs.claim(engine, "dead-worker", lease_s=60)
    assert jobs.claim(engine, "w2", lease_s=60) is None  # lease still valid
    age(engine, job_id, "locked_at", 120)
    fresh = jobs.claim(engine, "w2", lease_s=60)
    assert (fresh.id, fresh.attempt_count, fresh.locked_by) == (job_id, 2, "w2")
    jobs.complete(engine, stale, "dead-worker")  # ignored: no longer its job
    assert jobs.heartbeat(engine, job_id, "dead-worker") is False
    assert row(engine, job_id).status == "running"
    assert jobs.heartbeat(engine, job_id, "w2") is True


def test_expired_lease_on_last_attempt_goes_to_dead_letter(engine):
    job_id = jobs.enqueue(engine, "pipeline", max_attempts=1)
    jobs.claim(engine, "dead-worker", lease_s=60)
    age(engine, job_id, "locked_at", 120)
    assert jobs.claim(engine, "w2", lease_s=60) is None
    r = row(engine, job_id)
    assert r.status == "dead_letter" and "lease expired" in r.last_error


def test_release_and_cancel(engine):
    job_id = jobs.enqueue(engine, "pipeline")
    job = jobs.claim(engine, "w1")
    jobs.release(engine, job, "w1")  # graceful shutdown: no attempt spent
    r = row(engine, job_id)
    assert (r.status, r.attempt_count, r.locked_by) == ("pending", 0, None)
    assert jobs.cancel(engine, job_id)
    assert row(engine, job_id).status == "cancelled"
    assert not jobs.retry_dead(engine, job_id)  # only dead letters can be retried


# --- worker --------------------------------------------------------------------------------------


def _run_one(engine, kind: str, stop: threading.Event | None = None) -> tuple[str, int]:
    job_id = jobs.enqueue(engine, kind, {"trigger": "admin"})
    job = jobs.claim(engine, worker.WORKER_ID)
    return worker.run_job(job, stop or threading.Event()), job_id


def test_ingest_job_queues_the_pipeline(engine, monkeypatch):
    calls = []
    monkeypatch.setattr(worker, "ingest_all", lambda **kw: calls.append(kw) or [])
    outcome, job_id = _run_one(engine, "ingest_all")
    assert outcome == "succeeded" and row(engine, job_id).status == "succeeded"
    assert calls[0]["trigger"] == "admin"
    with engine.connect() as c:
        queued = c.execute(text("SELECT kind, payload FROM jobs WHERE status = 'pending'")).one()
    assert queued == ("pipeline", {"trigger": "admin"})


@pytest.mark.parametrize(
    ("result", "outcome"),
    [
        (PipelineResult(1, "succeeded", {}), "succeeded"),
        (PipelineResult(1, "partial", {"failed": 1}), "succeeded"),
        (PipelineResult(1, "failed", {}, error="provider down", retryable=True), "retry_wait"),
        (PipelineResult(1, "failed", {}, error="bad key", retryable=False), "dead_letter"),
        (PipelineResult(1, "succeeded", {}, stop_reason="shutdown requested"), "released"),
    ],
)
def test_pipeline_job_outcomes(engine, monkeypatch, result, outcome):
    monkeypatch.setattr(worker, "run_pipeline", lambda **kw: result)
    got, job_id = _run_one(engine, "pipeline")
    assert got == outcome
    expected_status = {"released": "pending"}.get(outcome, outcome)
    assert row(engine, job_id).status == expected_status


def test_missing_llm_config_is_permanent(engine, monkeypatch):
    def boom(**kw):
        raise LLMError(
            "ANTHROPIC_API_KEY and CLASSIFIER_MODEL must be set", retryable=False, fatal=True
        )

    monkeypatch.setattr(worker, "run_pipeline", boom)
    outcome, job_id = _run_one(engine, "pipeline")
    assert outcome == "dead_letter" and "CLASSIFIER_MODEL" in row(engine, job_id).last_error


def test_unexpected_crash_is_retried(engine, monkeypatch):
    def boom(**kw):
        raise ConnectionError("db went away")

    monkeypatch.setattr(worker, "run_pipeline", boom)
    outcome, job_id = _run_one(engine, "pipeline")
    assert outcome == "retry_wait" and "db went away" in row(engine, job_id).last_error


def test_shutdown_during_ingest_releases_the_job(engine, monkeypatch):
    stop = threading.Event()
    monkeypatch.setattr(worker, "ingest_all", lambda **kw: stop.set() or [])
    outcome, job_id = _run_one(engine, "ingest_all", stop)
    assert outcome == "released" and row(engine, job_id).status == "pending"


def test_schedule_tick_does_not_double_queue(engine):
    worker.schedule_ingest(60)
    worker.schedule_ingest(60)  # a second replica's tick
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM jobs")).scalar() == 1
