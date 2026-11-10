"""Shared pieces of the public API: DB session, query parameters, the processed-items query,
deterministic ordering, page/page_size pagination and row serialization (PLAN Phase 4, §11.7)."""

import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import Query
from sqlalchemy import ColumnElement, Select, any_, func, literal, select
from sqlalchemy.orm import Session, defer

from app.ai.embeddings import Embedder, FastEmbedder
from app.db import SessionLocal
from app.models import AIAnnotation, Item, ItemSource, Source
from app.recommend.scoring import relevant_sql, trending_sql
from app.schemas import ContentType, ItemSummary, Page, SourceRef

PAGE_SIZE_MAX = 50
PAGE_MAX = 1000  # bounds the OFFSET a client can request
SLUG = r"^[a-z0-9][a-z0-9_-]*$"
Sort = Literal["latest", "relevance", "quality", "trending", "relevant"]
CACHE_SECONDS = 60


class ApiError(Exception):
    """Raised by handlers; rendered as {"error": {code, message, request_id}}."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def get_db() -> Iterator[Session]:
    with SessionLocal() as s:
        yield s


_embedder = FastEmbedder()


def get_embedder() -> Embedder:
    return _embedder


# ponytail: per-process dict, fine for one API container; use a shared cache if it scales out.
_ttl_cache: dict[str, tuple[float, Any]] = {}


def cached[T](key: str, compute: Callable[[], T]) -> T:
    """Reuse a response that doesn't depend on the request for CACHE_SECONDS (Phase 10)."""
    now = time.monotonic()
    hit = _ttl_cache.get(key)
    if hit is None or now - hit[0] >= CACHE_SECONDS:
        hit = _ttl_cache[key] = (now, compute())
    value: T = hit[1]
    return value


@dataclass(frozen=True)
class Filters:
    category: str | None = None
    content_type: str | None = None
    source: str | None = None
    min_quality: int | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None


def _utc(dt: datetime | None) -> datetime | None:
    """A timestamp without an offset is taken as UTC."""
    if dt is None or dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=UTC)


def item_filters(
    category: Annotated[
        str | None,
        Query(max_length=64, pattern=SLUG, description="Matches any of an item's categories."),
    ] = None,
    content_type: Annotated[ContentType | None, Query()] = None,
    source: Annotated[
        str | None, Query(max_length=64, pattern=SLUG, description="Source key, e.g. `hn`.")
    ] = None,
    min_quality: Annotated[int | None, Query(ge=0, le=100)] = None,
    date_from: Annotated[
        datetime | None, Query(alias="from", description="Published at or after (UTC).")
    ] = None,
    date_to: Annotated[
        datetime | None, Query(alias="to", description="Published before (UTC).")
    ] = None,
) -> Filters:
    date_from, date_to = _utc(date_from), _utc(date_to)
    if date_from and date_to and date_from >= date_to:
        raise ApiError(422, "validation_error", "query.from must be earlier than query.to")
    return Filters(category, content_type, source, min_quality, date_from, date_to)


@dataclass(frozen=True)
class Pagination:
    page: int
    page_size: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def pagination(
    page: Annotated[int, Query(ge=1, le=PAGE_MAX)] = 1,
    page_size: Annotated[int, Query(ge=1, le=PAGE_SIZE_MAX)] = 20,
) -> Pagination:
    return Pagination(page, page_size)


def base(*cols: Any) -> Select[Any]:
    """Public items only: `processed`, with an annotation; rejected rows stay out (§11.13)."""
    return (
        select(*cols)
        .select_from(Item)
        .join(AIAnnotation, AIAnnotation.item_id == Item.id)
        .outerjoin(Source, Source.id == Item.primary_source_id)
        .where(Item.status == "processed")
    )


def public_items() -> Select[Any]:
    return base(Item, AIAnnotation, Source.key, Source.name).options(
        defer(Item.content_text),
        defer(Item.embedding),
        defer(Item.tsv),
        defer(AIAnnotation.summary_tsv),
    )


def apply_filters(stmt: Select[Any], f: Filters) -> Select[Any]:
    if f.category:
        stmt = stmt.where(literal(f.category) == any_(AIAnnotation.categories))
    if f.content_type:
        stmt = stmt.where(AIAnnotation.content_type == f.content_type)
    if f.source:  # any source that found the item, not only the primary one (§11.2)
        stmt = stmt.where(
            Item.id.in_(
                select(ItemSource.item_id)
                .join(Source, Source.id == ItemSource.source_id)
                .where(Source.key == f.source)
            )
        )
    if f.min_quality is not None:
        stmt = stmt.where(AIAnnotation.quality_score >= f.min_quality)
    if f.date_from:
        stmt = stmt.where(Item.published_at >= f.date_from)
    if f.date_to:
        stmt = stmt.where(Item.published_at < f.date_to)
    return stmt


# Every ordering ends with the unique id so pages never skip or repeat rows (§11.7).
_NEWEST = (Item.published_at.desc().nulls_last(), Item.id.desc())
ORDER: dict[str, tuple[ColumnElement[Any], ...]] = {
    "latest": _NEWEST,
    "relevance": (AIAnnotation.relevance_score.desc().nulls_last(), *_NEWEST),
    "quality": (AIAnnotation.quality_score.desc().nulls_last(), *_NEWEST),
    # Phase 5 scores (app/recommend/scoring.py), computed at query time.
    "trending": (trending_sql().desc(), *_NEWEST),
    "relevant": (relevant_sql().desc(), *_NEWEST),
}


def summary_fields(row: Sequence[Any]) -> dict[str, Any]:
    """Fields of ItemSummary from a public_items() row (Item, AIAnnotation, key, name, ...)."""
    item: Item = row[0]
    ann: AIAnnotation = row[1]
    return {
        "id": item.id,
        "title": item.title,
        "url": item.original_url,
        "publisher": item.publisher,
        "author": item.author,
        "published_at": item.published_at,
        "source": SourceRef(key=row[2], name=row[3]) if row[2] else None,
        "primary_category": ann.primary_category,
        "categories": ann.categories,
        "content_type": ann.content_type,
        "summary": ann.summary,
        "tags": ann.tags,
        "relevance_score": ann.relevance_score,
        "quality_score": ann.quality_score,
        "points": item.points,
        "comments_count": item.comments_count,
        "discussion_url": item.discussion_url,
    }


def paginate(db: Session, stmt: Select[Any], order: str, pg: Pagination) -> Page[ItemSummary]:
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = db.execute(stmt.order_by(*ORDER[order]).offset(pg.offset).limit(pg.page_size)).all()
    return Page[ItemSummary](
        items=[ItemSummary(**summary_fields(r)) for r in rows],
        page=pg.page,
        page_size=pg.page_size,
        total=total,
        has_more=pg.offset + len(rows) < total,
    )
