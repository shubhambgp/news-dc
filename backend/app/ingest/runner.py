"""Run ingestion for one source or all enabled sources (PLAN Phase 2 tasks 2-5).

Per page: validate rows as RawItem, look up what is already known (by this source's external id
or by URL hash), enrich only the new ones (full text, resolved URL, related HN threads), then
upsert. The database enforces uniqueness, so concurrent runs cannot create duplicates:
- items: INSERT ... ON CONFLICT (url_hash) refreshes engagement instead of duplicating;
- item_sources: one row per (source, item); a second source attaches its own provenance row.
Each page commits together with the source checkpoint, so an interrupted run resumes there.
"""

import logging
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from pydantic import ValidationError
from sqlalchemy import Boolean, Engine, case, func, literal_column, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import db
from app.ingest import arxiv, github, hackernews, rss
from app.ingest.common import (
    FetchError,
    Http,
    RawItem,
    Robots,
    canonicalize_url,
    content_hash,
    extract_article,
    url_hash,
)
from app.models import Item, ItemSource, PipelineRun, Source

log = logging.getLogger(__name__)

Fetch = Callable[[Http, Source, datetime, dict[str, Any]], Iterator[list[dict[str, Any]]]]
ADAPTERS: dict[str, Fetch] = {
    "hackernews": hackernews.fetch,
    "rss": rss.fetch,
    "arxiv": arxiv.fetch,
    "github": github.fetch,
}

REFRESH_OVERLAP = timedelta(days=2)  # re-read recent items to refresh engagement
DEFAULT_MAX_ITEMS = 1000
ENRICH_WORKERS = 8
HN_LOOKUP_RPM = 60  # related-discussion lookups against Algolia


@dataclass
class Counts:
    fetched: int = 0
    new: int = 0
    duplicates: int = 0
    failed: int = 0


@dataclass
class RunResult:
    source_key: str
    run_id: int
    status: str
    counts: Counts
    error: str | None = None


@dataclass
class Enrichment:
    resolved_url: str | None = None
    canonical_url: str | None = None
    content_text: str | None = None
    discussions: list[dict[str, Any]] = field(default_factory=list)


class Enricher:
    """Extra fetches for *new* items only, in a small thread pool."""

    def __init__(self, source: Source, web: Http, hn: Http) -> None:
        self.fulltext = "content_text" in source.settings.get("allowed_fields", [])
        self.lookup_hn = source.type != "hackernews"
        self.web = web
        self.hn = hn
        self.robots = Robots(web)

    def one(self, item: RawItem) -> Enrichment:
        result = Enrichment()
        if self.fulltext:
            ex = extract_article(self.web, self.robots, item.url)
            result.resolved_url, result.canonical_url = ex.resolved_url, ex.canonical_url
            result.content_text = ex.text
        if self.lookup_hn:
            try:
                result.discussions = hackernews.discussions(self.hn, item.url)
            except (FetchError, httpx.HTTPError) as exc:
                log.info("hn lookup failed", extra={"error": str(exc)[:200]})
        return result

    def many(self, items: list[RawItem]) -> list[Enrichment]:
        if not items or not (self.fulltext or self.lookup_hn):
            return [Enrichment() for _ in items]
        # ponytail: no per-host throttle; up to ENRICH_WORKERS requests can hit one site at once
        # (RISKS R-011). Add a per-host semaphore if a site rate-limits us.
        with ThreadPoolExecutor(ENRICH_WORKERS) as pool:
            return list(pool.map(self.one, items))


def _engagement(item: RawItem) -> dict[str, Any]:
    values = {
        "points": item.points,
        "comments": item.comments_count,
        "discussion_url": item.discussion_url,
    }
    return {k: v for k, v in values.items() if v is not None}


# Keep the busier observation when one source reports the same URL twice (e.g. HN reposts).
_KEEP_HIGHER_ENGAGEMENT = text(
    "CASE WHEN coalesce((excluded.source_engagement->>'points')::int, 0) >= "
    "coalesce((item_sources.source_engagement->>'points')::int, 0) "
    "THEN excluded.source_engagement ELSE item_sources.source_engagement END"
)


def _refresh_known(s: Session, source: Source, item: RawItem, item_id: int) -> None:
    s.execute(
        update(ItemSource)
        .where(ItemSource.source_id == source.id, ItemSource.external_id == item.external_id)
        .values(
            last_seen_at=func.now(),
            source_engagement=_engagement(item),
            source_title=item.title,
        )
    )
    s.execute(
        update(Item)
        .where(Item.id == item_id, Item.primary_source_id == source.id)
        .values(
            points=func.greatest(Item.points, item.points),
            comments_count=func.greatest(Item.comments_count, item.comments_count),
            updated_at=func.now(),
        )
    )


def _upsert(s: Session, source: Source, item: RawItem, extra: Enrichment) -> bool:
    """Insert or attach one item. Returns True if a new `items` row was created."""
    canonical = extra.canonical_url or canonicalize_url(extra.resolved_url or item.url)
    body = extra.content_text or item.description
    ins = insert(Item).values(
        primary_source_id=source.id,
        original_url=item.url,
        resolved_url=extra.resolved_url,
        canonical_url=canonical,
        url_hash=url_hash(canonical),
        content_hash=content_hash(item.title, body),
        title=item.title,
        description=item.description,
        content_text=extra.content_text,
        publisher=item.publisher,
        author=item.author,
        published_at=item.published_at,
        source_tags=item.source_tags,
        points=item.points,
        comments_count=item.comments_count,
        discussion_url=item.discussion_url,
        related_links=item.related_links + extra.discussions,
    )
    ex = ins.excluded
    primary = Item.primary_source_id == ex.primary_source_id  # only the primary source's numbers
    stmt = ins.on_conflict_do_update(
        index_elements=[Item.url_hash],
        set_={
            "points": case((primary, func.greatest(Item.points, ex.points)), else_=Item.points),
            "comments_count": case(
                (primary, func.greatest(Item.comments_count, ex.comments_count)),
                else_=Item.comments_count,
            ),
            "updated_at": func.now(),
        },
    ).returning(Item.id, literal_column("(xmax = 0)", Boolean))  # xmax = 0 <=> row was inserted
    item_id, inserted = s.execute(stmt).one()

    link = insert(ItemSource).values(
        item_id=item_id,
        source_id=source.id,
        external_id=item.external_id,
        source_url=item.url,
        source_published_at=item.published_at,
        source_title=item.title,
        source_engagement=_engagement(item),
        is_primary=inserted,
    )
    s.execute(
        link.on_conflict_do_update(
            index_elements=[ItemSource.source_id, ItemSource.item_id],
            set_={"last_seen_at": func.now(), "source_engagement": _KEEP_HIGHER_ENGAGEMENT},
        )
    )
    return bool(inserted)


def _store_page(
    s: Session, source: Source, rows: list[dict[str, Any]], enricher: Enricher, counts: Counts
) -> None:
    items: list[RawItem] = []
    for row in rows:
        counts.fetched += 1
        try:
            items.append(RawItem.model_validate(row))
        except ValidationError as exc:
            counts.failed += 1
            log.warning(
                "invalid item skipped",
                extra={"source_key": source.key, "error": exc.errors(include_url=False)[:1]},
            )
    if not items:
        return

    ext_ids = [i.external_id for i in items if i.external_id]
    known_ext = {
        ext: item_id
        for ext, item_id in s.execute(
            select(ItemSource.external_id, ItemSource.item_id).where(
                ItemSource.source_id == source.id, ItemSource.external_id.in_(ext_ids)
            )
        )
        if ext is not None
    }
    hashes = {url_hash(i.canonical_url) for i in items}
    known_hash = set(s.scalars(select(Item.url_hash).where(Item.url_hash.in_(hashes))))
    new = [
        i
        for i in items
        if i.external_id not in known_ext and url_hash(i.canonical_url) not in known_hash
    ]
    # Never hold a transaction open across network I/O: enrichment can take minutes (throttled
    # HN lookups) and the DB kills sessions idle in a transaction for 60 s. Nothing is pending
    # here; the upserts below are conflict-safe if another run inserted meanwhile.
    s.commit()
    extras = {id(i): e for i, e in zip(new, enricher.many(new), strict=True)}

    for item in items:
        try:
            with s.begin_nested():  # one bad item rolls back alone
                if item.external_id in known_ext:
                    _refresh_known(s, source, item, known_ext[item.external_id])
                    inserted = False
                else:
                    inserted = _upsert(s, source, item, extras.get(id(item), Enrichment()))
        except IntegrityError as exc:
            counts.failed += 1
            log.warning(
                "item rejected by constraint",
                extra={"source_key": source.key, "error": str(exc.orig)[:200]},
            )
            continue
        if inserted:
            counts.new += 1
        else:
            counts.duplicates += 1


def _since(source: Source, since_days: int | None, now: datetime) -> datetime:
    if since_days:
        return now - timedelta(days=since_days)
    if source.last_success_at:
        return source.last_success_at - REFRESH_OVERLAP
    return now - timedelta(days=source.settings.get("backfill_window_days", 30))


def ingest_source(
    key: str,
    *,
    since_days: int | None = None,
    trigger: str = "cli",
    engine: Engine | None = None,
) -> RunResult:
    """Fetch and store one enabled source. Source failures are recorded, not raised."""
    with Session(engine or db.engine, expire_on_commit=False) as s:
        source = s.scalars(select(Source).where(Source.key == key)).one_or_none()
        if source is None:
            raise ValueError(f"unknown source {key!r}")
        if not source.enabled:
            raise ValueError(f"source {key!r} is disabled in config/sources.yaml")
        run = PipelineRun(trigger=trigger, source_key=key)
        s.add(run)
        s.commit()

        now = datetime.now(UTC)
        since = _since(source, since_days, now)
        checkpoint: dict[str, Any] = dict(source.checkpoint or {})
        cap = int(source.settings.get("max_items_per_run", DEFAULT_MAX_ITEMS))
        counts = Counts()
        committed = Counts()  # what the run record reports if a later page fails
        error: str | None = None
        ctx = {"source_key": key, "run_id": run.id}
        log.info("ingest started", extra=ctx | {"since": since.isoformat()})
        rpm = float(source.settings.get("max_requests_per_minute", 30))
        try:
            with (
                Http(rpm=rpm) as http,
                Http(timeout=10.0, attempts=2) as web,
                Http(rpm=HN_LOOKUP_RPM) as hn,
            ):
                enricher = Enricher(source, web, hn)
                for rows in ADAPTERS[source.type](http, source, since, checkpoint):
                    _store_page(s, source, rows, enricher, counts)
                    source.checkpoint = dict(checkpoint)
                    s.commit()
                    committed = Counts(**vars(counts))
                    log.info("page stored", extra=ctx | vars(counts))
                    if counts.fetched >= cap:
                        log.info("per-run cap reached; will resume", extra=ctx | {"cap": cap})
                        break
                else:
                    source.checkpoint = dict(checkpoint)  # completed queries are cleared
        except Exception as exc:  # one broken source must not stop the others (§11.4)
            s.rollback()
            counts = committed  # the failed page was rolled back
            error = f"{type(exc).__name__}: {exc}"[:1000]
            log.exception("ingest failed", extra=ctx)

        finished = datetime.now(UTC)
        status = "failed" if error else ("partial" if counts.failed else "succeeded")
        source.last_fetched_at = finished
        source.last_status = "error" if error else "ok"
        source.last_error = error
        if not error:
            source.last_success_at = finished
        run.finished_at = finished
        run.status = status
        run.error = error
        run.fetched, run.new = counts.fetched, counts.new
        run.duplicates, run.failed = counts.duplicates, counts.failed
        s.commit()
        log.info("ingest finished", extra=ctx | vars(counts) | {"status": status})
        return RunResult(key, run.id, status, counts, error)


def ingest_all(
    *, since_days: int | None = None, trigger: str = "schedule", engine: Engine | None = None
) -> list[RunResult]:
    """Every enabled source in turn; each records its own success or failure."""
    with Session(engine or db.engine) as s:
        keys = s.scalars(select(Source.key).where(Source.enabled).order_by(Source.id)).all()
    return [ingest_source(k, since_days=since_days, trigger=trigger, engine=engine) for k in keys]
