"""Worker entrypoint: `python -m app.worker`.

APScheduler enqueues an `ingest_all` job every INGEST_INTERVAL_MINUTES (immediately on start)
and a `trend_brief` job every Monday at 06:00 UTC (when the assistant model is configured).
The main loop claims jobs from the `jobs` table (app/jobs.py) and runs them; a finished ingest
queues a `pipeline` job. Several worker replicas are safe: claims use SKIP LOCKED, one active job
per kind is enforced by the database, and the pipeline itself holds an advisory lock.

Shutdown (SIGTERM/SIGINT): stop claiming, let the running job stop at its next safe point (between
sources / between pages of items), and hand it back as `pending` without spending an attempt.
Compose gives the worker a 60 s grace period; if it is killed anyway, the job's lease expires and
another worker reclaims it.
"""

import logging
import os
import signal
import socket
import threading
from datetime import UTC, datetime, timedelta
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler

from app import db, jobs
from app.ai import trends
from app.ai.classify import Prices
from app.ai.llm import AnthropicLLM, LLMError
from app.config import get_settings
from app.ingest.runner import ingest_all, ingest_source
from app.logging import setup_logging
from app.models import Job
from app.pipeline.graph import run_pipeline

log = logging.getLogger("app.worker")

WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"
POLL_SECONDS = 5.0
HEARTBEAT_SECONDS = 60.0


class Interrupted(Exception):
    """The job stopped early because the worker is shutting down."""


def handle(job: Job, stop: threading.Event) -> None:
    trigger = job.payload.get("trigger", "schedule")
    if job.kind == "ingest_all":
        if key := job.payload.get("source"):  # Admin: one source
            try:
                ingest_source(key, trigger=trigger)
            except ValueError as exc:  # unknown, disabled or paused source
                raise jobs.PermanentJobError(str(exc)) from exc
        else:  # source errors are recorded per source
            ingest_all(trigger=trigger, should_stop=stop.is_set)
        if stop.is_set():
            raise Interrupted
        jobs.enqueue(db.engine, "pipeline", {"trigger": trigger})
    elif job.kind == "pipeline":
        result = run_pipeline(trigger=trigger, should_stop=stop.is_set)
        if result.status == "failed":
            error = result.error or "pipeline failed"
            raise RuntimeError(error) if result.retryable else jobs.PermanentJobError(error)
        if result.stop_reason == "shutdown requested":
            raise Interrupted
    elif job.kind == "trend_brief":
        s = get_settings()
        llm = AnthropicLLM(
            api_key=s.anthropic_api_key,
            model=s.assistant_model,
            effort=s.assistant_effort,
            timeout_s=s.llm_timeout_seconds,
        )
        prices = Prices(s.assistant_input_usd_per_mtok, s.assistant_output_usd_per_mtok)
        trends.generate_brief(db.engine, llm, prices, s.assistant_max_tokens)
    else:
        raise jobs.PermanentJobError(f"no handler for job kind {job.kind!r}")


def run_job(job: Job, stop: threading.Event) -> str:
    ctx: dict[str, Any] = {"job_id": job.id, "kind": job.kind, "attempt": job.attempt_count}
    beating = threading.Event()

    def beat() -> None:
        while not beating.wait(HEARTBEAT_SECONDS):
            if not jobs.heartbeat(db.engine, job.id, WORKER_ID):
                log.warning("lost the job lease", extra=ctx)

    threading.Thread(target=beat, daemon=True).start()
    log.info("job started", extra=ctx)
    try:
        handle(job, stop)
    except Interrupted:
        jobs.release(db.engine, job, WORKER_ID)
        outcome = "released"
    except (jobs.PermanentJobError, LLMError) as exc:
        permanent = isinstance(exc, jobs.PermanentJobError) or not exc.retryable
        outcome = jobs.fail(db.engine, job, WORKER_ID, str(exc), permanent=permanent)
        log.error("job failed", extra=ctx | {"error": str(exc)[:300], "outcome": outcome})
    except Exception as exc:
        outcome = jobs.fail(db.engine, job, WORKER_ID, f"{type(exc).__name__}: {exc}")
        log.exception("job failed", extra=ctx | {"outcome": outcome})
    else:
        jobs.complete(db.engine, job, WORKER_ID)
        outcome = "succeeded"
    finally:
        beating.set()
    log.info("job finished", extra=ctx | {"outcome": outcome})
    return outcome


def schedule_ingest(interval_minutes: int) -> None:
    try:
        job_id = jobs.enqueue(
            db.engine,
            "ingest_all",
            {"trigger": "schedule"},
            not_within=timedelta(minutes=interval_minutes * 0.9),  # other replicas' ticks
        )
        log.info("scheduled ingest", extra={"job_id": job_id, "queued": job_id is not None})
    except Exception:  # the DB may be down; the next tick tries again
        log.exception("could not enqueue ingest job")


def schedule_brief() -> None:
    try:
        job_id = jobs.enqueue(
            db.engine, "trend_brief", {"trigger": "schedule"}, not_within=timedelta(days=6)
        )
        log.info("scheduled trend brief", extra={"job_id": job_id, "queued": job_id is not None})
    except Exception:
        log.exception("could not enqueue trend brief job")


def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())

    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        schedule_ingest,
        "interval",
        minutes=settings.ingest_interval_minutes,
        args=[settings.ingest_interval_minutes],
        next_run_time=datetime.now(UTC),
        max_instances=1,
        coalesce=True,
    )
    if settings.anthropic_api_key and settings.assistant_model:  # weekly, Monday 06:00 UTC
        scheduler.add_job(schedule_brief, "cron", day_of_week="mon", hour=6, coalesce=True)
    else:
        log.warning("trend brief not scheduled: ANTHROPIC_API_KEY or ASSISTANT_MODEL not set")
    scheduler.start()
    log.info("worker started", extra={"worker_id": WORKER_ID})
    while not stop.is_set():
        try:
            job = jobs.claim(db.engine, WORKER_ID)
        except Exception:
            log.exception("claim failed")
            job = None
        if job is None:
            stop.wait(POLL_SECONDS)
            continue
        run_job(job, stop)
    scheduler.shutdown(wait=False)
    log.info("worker stopped")


if __name__ == "__main__":
    main()
