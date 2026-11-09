"""Durable, database-backed job lifecycle (PLAN §11.4). APScheduler only *enqueues*; workers
*claim* jobs here, so a crashed or restarted worker never loses scheduled work.

    pending -> running -> succeeded
                       -> retry_wait (transient, exponential backoff with jitter) -> running ...
                       -> dead_letter (permanent error, or max_attempts used)  -- retry_dead() -->
    pending / retry_wait -> cancelled

- Claims are atomic (`FOR UPDATE SKIP LOCKED`), so two workers never run the same job.
- A running job's lease is renewed by a heartbeat; a lease older than JOB_LEASE_SECONDS means
  the worker died, and the job can be claimed again.
- A partial unique index allows one active job per kind, so several schedulers (replicas)
  cannot queue duplicate runs.

CLI: `python -m app.jobs list | enqueue <kind> | retry <id> | cancel <id>`.
"""

import argparse
import json
import random
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Engine, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app import db
from app.config import get_settings
from app.models import JOB_ACTIVE, JOB_KINDS, Job

BACKOFF_BASE_S = 60.0
BACKOFF_CAP_S = 3600.0


class PermanentJobError(Exception):
    """Retrying cannot help (bad configuration, invalid input): go straight to dead_letter."""


def backoff_seconds(attempt: int, rng: random.Random | None = None) -> float:
    """Full jitter: uniform(0, min(cap, base * 2^(attempt-1))), at least 1 s."""
    ceiling = min(BACKOFF_CAP_S, BACKOFF_BASE_S * 2 ** max(attempt - 1, 0))
    return max(1.0, (rng or random).uniform(0, ceiling))


def enqueue(
    engine: Engine,
    kind: str,
    payload: dict[str, Any] | None = None,
    *,
    max_attempts: int = 3,
    not_within: timedelta | None = None,
) -> int | None:
    """Queue a job unless one of this kind is already active (or, with `not_within`, was created
    that recently). Returns the new job id, or None if nothing was queued."""
    if kind not in JOB_KINDS:
        raise ValueError(f"unknown job kind {kind!r}")
    with Session(engine) as s, s.begin():
        if not_within is not None:
            recent = s.scalar(
                select(Job.id)
                .where(Job.kind == kind, Job.created_at > datetime.now(UTC) - not_within)
                .limit(1)
            )
            if recent:
                return None
        stmt = (
            insert(Job)
            .values(kind=kind, payload=payload or {}, max_attempts=max_attempts)
            .on_conflict_do_nothing(
                index_elements=[Job.kind],
                index_where=Job.status.in_(JOB_ACTIVE),
            )
            .returning(Job.id)
        )
        return s.scalar(stmt)


def claim(engine: Engine, worker_id: str, lease_s: int | None = None) -> Job | None:
    """Atomically take the oldest runnable job: pending, due for retry, or with an expired lease.
    A job whose lease expired after its last allowed attempt goes to dead_letter instead."""
    lease = timedelta(seconds=lease_s or get_settings().job_lease_seconds)
    while True:
        with Session(engine, expire_on_commit=False) as s, s.begin():
            now = datetime.now(UTC)
            job = s.scalars(
                select(Job)
                .where(
                    (Job.status == "pending")
                    | ((Job.status == "retry_wait") & (Job.next_retry_at <= now))
                    | ((Job.status == "running") & (Job.locked_at < now - lease))
                )
                .order_by(Job.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            ).first()
            if job is None:
                return None
            if job.status == "running" and job.attempt_count >= job.max_attempts:
                job.status = "dead_letter"
                job.last_error = f"lease expired (worker {job.locked_by} lost) on last attempt"
                job.finished_at = now
                job.locked_at = job.locked_by = None
                continue
            job.status = "running"
            job.attempt_count += 1
            job.locked_at = now
            job.locked_by = worker_id
            job.next_retry_at = None
            return job


def heartbeat(engine: Engine, job_id: int, worker_id: str) -> bool:
    """Renew the lease. False means the job is no longer ours (reclaimed or cancelled)."""
    with Session(engine) as s, s.begin():
        return bool(
            s.execute(
                update(Job)
                .where(Job.id == job_id, Job.status == "running", Job.locked_by == worker_id)
                .values(locked_at=datetime.now(UTC))
            ).rowcount  # type: ignore[attr-defined]
        )


def _finish(engine: Engine, job: Job, worker_id: str, **values: Any) -> None:
    with Session(engine) as s, s.begin():
        s.execute(
            update(Job)
            .where(Job.id == job.id, Job.status == "running", Job.locked_by == worker_id)
            .values(locked_at=None, locked_by=None, updated_at=datetime.now(UTC), **values)
        )


def complete(engine: Engine, job: Job, worker_id: str) -> None:
    _finish(engine, job, worker_id, status="succeeded", finished_at=datetime.now(UTC))


def fail(engine: Engine, job: Job, worker_id: str, error: str, *, permanent: bool = False) -> str:
    """Record a failure. Returns the new status: retry_wait or dead_letter."""
    if permanent or job.attempt_count >= job.max_attempts:
        _finish(
            engine,
            job,
            worker_id,
            status="dead_letter",
            last_error=error[:2000],
            finished_at=datetime.now(UTC),
        )
        return "dead_letter"
    retry_at = datetime.now(UTC) + timedelta(seconds=backoff_seconds(job.attempt_count))
    _finish(
        engine, job, worker_id, status="retry_wait", last_error=error[:2000], next_retry_at=retry_at
    )
    return "retry_wait"


def release(engine: Engine, job: Job, worker_id: str) -> None:
    """Graceful shutdown: hand the job back without spending an attempt."""
    _finish(engine, job, worker_id, status="pending", attempt_count=job.attempt_count - 1)


def retry_dead(engine: Engine, job_id: int) -> bool:
    """Manual action: a dead-lettered job gets a fresh set of attempts."""
    with Session(engine) as s, s.begin():
        return bool(
            s.execute(
                update(Job)
                .where(Job.id == job_id, Job.status == "dead_letter")
                .values(
                    status="pending",
                    attempt_count=0,
                    next_retry_at=None,
                    finished_at=None,
                    updated_at=datetime.now(UTC),
                )
            ).rowcount  # type: ignore[attr-defined]
        )


def cancel(engine: Engine, job_id: int) -> bool:
    with Session(engine) as s, s.begin():
        return bool(
            s.execute(
                update(Job)
                .where(Job.id == job_id, Job.status.in_(("pending", "retry_wait")))
                .values(status="cancelled", finished_at=datetime.now(UTC))
            ).rowcount  # type: ignore[attr-defined]
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.jobs", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="the 30 most recent jobs")
    sub.add_parser("enqueue", help="queue a job now").add_argument("kind", choices=JOB_KINDS)
    sub.add_parser("retry", help="retry a dead-lettered job").add_argument("job_id", type=int)
    sub.add_parser("cancel", help="cancel a waiting job").add_argument("job_id", type=int)
    args = parser.parse_args(argv)

    if args.cmd == "list":
        with db.engine.connect() as c:
            rows = c.execute(
                text(
                    "SELECT id, kind, status, attempt_count, max_attempts, next_retry_at, "
                    "locked_by, left(last_error, 120) AS last_error, created_at, finished_at "
                    "FROM jobs ORDER BY id DESC LIMIT 30"
                )
            ).mappings()
            print(json.dumps([dict(r) for r in rows], indent=2, default=str))
        return 0
    if args.cmd == "enqueue":
        job_id = enqueue(db.engine, args.kind, {"trigger": "cli"})
        print(json.dumps({"queued": job_id}))
        return 0 if job_id else 1
    ok = (retry_dead if args.cmd == "retry" else cancel)(db.engine, args.job_id)
    print(json.dumps({args.cmd: args.job_id, "ok": ok}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
