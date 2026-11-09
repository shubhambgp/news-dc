"""SQLAlchemy models for every table in PLAN §5, with the §11.2 provenance and §11.10 rules.

All timestamps are timezone-aware UTC. Allowed values are enforced by CHECK constraints in the DB.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

EMBEDDING_DIM = 384  # BAAI/bge-small-en-v1.5. Changing it needs a re-embedding migration (§11.10).

SOURCE_TYPES = ("hackernews", "rss", "arxiv", "github")
ITEM_STATUSES = (
    "new",
    "rejected_prefilter",
    "rejected_ai",
    "duplicate",
    "processed",
    "failed",
)
CONTENT_TYPES = ("news", "research", "investment", "engineering")
RUN_TRIGGERS = ("schedule", "admin", "cli")
RUN_STATUSES = ("running", "succeeded", "partial", "failed")
RUN_KINDS = ("ingest", "pipeline")
JOB_KINDS = ("ingest_all", "pipeline", "trend_brief")
JOB_STATUSES = ("pending", "running", "succeeded", "retry_wait", "dead_letter", "cancelled")
JOB_ACTIVE = ("pending", "running", "retry_wait")


def _in(col: str, values: tuple[str, ...]) -> str:
    return f"{col} IN ({', '.join(repr(v) for v in values)})"


def _score(col: str) -> str:
    return f"{col} BETWEEN 0 AND 100"


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_N_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


def _created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


def _updated() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (CheckConstraint(_in("type", SOURCE_TYPES), name="type_valid"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(String(32))
    url: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))  # YAML-owned
    # Admin pause (Phase 8). A source is ingested only when `enabled` and not `admin_disabled`.
    admin_disabled: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    # The rest of the config/sources.yaml entry: terms_url, robots_policy, rate limit, ...
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status: Mapped[str | None] = mapped_column(Text)
    last_error: Mapped[str | None] = mapped_column(Text)
    # Per-source watermark/cursor so an interrupted backfill can resume (§11.6).
    checkpoint: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class Category(Base):
    __tablename__ = "categories"

    slug: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    keywords: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    # Set when Admin edits the category (Phase 8); seeding then leaves its text alone.
    admin_edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class Item(Base):
    """One row per unique piece of content (unique canonical URL)."""

    __tablename__ = "items"
    __table_args__ = (
        CheckConstraint(_in("status", ITEM_STATUSES), name="status_valid"),
        CheckConstraint("duplicate_of <> id", name="not_self_duplicate"),
        CheckConstraint(
            "duplicate_similarity IS NULL OR duplicate_similarity BETWEEN 0 AND 1",
            name="duplicate_similarity_range",
        ),
        CheckConstraint("points IS NULL OR points >= 0", name="points_nonneg"),
        CheckConstraint(
            "comments_count IS NULL OR comments_count >= 0", name="comments_count_nonneg"
        ),
        CheckConstraint("ai_attempts >= 0", name="ai_attempts_nonneg"),
        Index("ix_items_published_at_id", text("published_at DESC"), text("id DESC")),
        Index("ix_items_status", "status"),
        Index("ix_items_content_hash", "content_hash"),
        Index("ix_items_duplicate_of", "duplicate_of"),
        Index("ix_items_tsv", "tsv", postgresql_using="gin"),
        Index(
            "ix_items_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # Display convenience only; full provenance lives in item_sources (§11.2).
    primary_source_id: Mapped[int | None] = mapped_column(
        ForeignKey("sources.id", ondelete="RESTRICT"), index=True
    )
    original_url: Mapped[str] = mapped_column(Text)
    resolved_url: Mapped[str | None] = mapped_column(Text)
    canonical_url: Mapped[str] = mapped_column(Text)
    url_hash: Mapped[str] = mapped_column(String(64), unique=True)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    content_text: Mapped[str | None] = mapped_column(Text)
    publisher: Mapped[str | None] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    source_tags: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    points: Mapped[int | None] = mapped_column(Integer)
    comments_count: Mapped[int | None] = mapped_column(Integer)
    discussion_url: Mapped[str | None] = mapped_column(Text)
    related_links: Mapped[list[Any]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    status: Mapped[str] = mapped_column(String(32), server_default="new")
    # Near-duplicate link (§11.3): a reviewable heuristic, so keep the score and the reason.
    duplicate_of: Mapped[int | None] = mapped_column(ForeignKey("items.id", ondelete="SET NULL"))
    duplicate_similarity: Mapped[float | None] = mapped_column(Float)
    duplicate_reason: Mapped[str | None] = mapped_column(Text)
    tsv: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed(
            "setweight(to_tsvector('english', coalesce(title, '')), 'A') || "
            "setweight(to_tsvector('english', coalesce(description, '')), 'B') || "
            "setweight(to_tsvector('english', coalesce(content_text, '')), 'C')",
            persisted=True,
        ),
    )
    embedding: Mapped[Any | None] = mapped_column(Vector(EMBEDDING_DIM))  # NULL = not embedded yet
    # AI pipeline bookkeeping (§11.5): failed classification attempts, and why the item has its
    # current status (pre-filter/gate rejection reason, last LLM error, pending embedding).
    ai_attempts: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    status_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class ItemSource(Base):
    """One row per (source, item) observation: an item can be found by several sources (§11.2)."""

    __tablename__ = "item_sources"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id"),  # NULL external_ids never conflict
        UniqueConstraint("source_id", "item_id"),
        Index(
            "uq_item_sources_one_primary",
            "item_id",
            unique=True,
            postgresql_where=text("is_primary"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # RESTRICT on purpose: deleting an item or source must not silently erase provenance.
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="RESTRICT"), index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="RESTRICT"))
    external_id: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(Text)
    source_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    source_title: Mapped[str | None] = mapped_column(Text)
    # Each source's own discussion URL and engagement (points, comments, stars, ...).
    source_engagement: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb")
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    created_at: Mapped[datetime] = _created()


class AIAnnotation(Base):
    """Pipeline output, 1:1 with items. Derived data, so it is deleted with its item."""

    __tablename__ = "ai_annotations"
    __table_args__ = (
        CheckConstraint(_score("relevance_score"), name="relevance_score_range"),
        CheckConstraint(_score("quality_score"), name="quality_score_range"),
        CheckConstraint(
            f"content_type IS NULL OR {_in('content_type', CONTENT_TYPES)}",
            name="content_type_valid",
        ),
        CheckConstraint("tokens_in IS NULL OR tokens_in >= 0", name="tokens_in_nonneg"),
        CheckConstraint("tokens_out IS NULL OR tokens_out >= 0", name="tokens_out_nonneg"),
        Index("ix_ai_annotations_primary_category", "primary_category"),
        Index("ix_ai_annotations_summary_tsv", "summary_tsv", postgresql_using="gin"),
    )

    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), primary_key=True
    )
    is_relevant: Mapped[bool] = mapped_column(Boolean)
    is_spam: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    relevance_score: Mapped[int | None] = mapped_column(SmallInteger)
    quality_score: Mapped[int | None] = mapped_column(SmallInteger)
    primary_category: Mapped[str | None] = mapped_column(
        ForeignKey("categories.slug", ondelete="RESTRICT", onupdate="CASCADE")
    )
    categories: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    content_type: Mapped[str | None] = mapped_column(String(32))
    summary: Mapped[str | None] = mapped_column(Text)
    # Searched together with items.tsv (D-029): a generated column can only read its own row.
    summary_tsv: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed("setweight(to_tsvector('english', coalesce(summary, '')), 'B')", persisted=True),
    )
    key_insights: Mapped[list[Any]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    entities: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    reject_reason: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(Text)
    prompt_hash: Mapped[str | None] = mapped_column(String(64))
    tokens_in: Mapped[int | None] = mapped_column(Integer)
    tokens_out: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    attempts: Mapped[int | None] = mapped_column(SmallInteger)  # LLM calls, incl. a repair retry
    cost_usd_estimate: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class PipelineRun(Base):
    """Audit record of one ingestion/processing run. Never cascaded away."""

    __tablename__ = "pipeline_runs"
    __table_args__ = (
        CheckConstraint(_in("trigger", RUN_TRIGGERS), name="trigger_valid"),
        CheckConstraint(_in("status", RUN_STATUSES), name="status_valid"),
        CheckConstraint(_in("kind", RUN_KINDS), name="kind_valid"),
        CheckConstraint(
            "fetched >= 0 AND new >= 0 AND duplicates >= 0 AND rejected_prefilter >= 0 "
            "AND rejected_ai >= 0 AND processed >= 0 AND failed >= 0",
            name="counts_nonneg",
        ),
        Index("ix_pipeline_runs_started_at", text("started_at DESC")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    kind: Mapped[str] = mapped_column(String(16), server_default="ingest")
    trigger: Mapped[str] = mapped_column(String(16))
    source_key: Mapped[str | None] = mapped_column(String(64))  # NULL = all sources
    status: Mapped[str] = mapped_column(String(16), server_default="running")
    fetched: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    new: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    duplicates: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    rejected_prefilter: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    rejected_ai: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    processed: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    failed: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    cost_usd_estimate: Mapped[Decimal] = mapped_column(Numeric(10, 4), server_default=text("0"))
    error: Mapped[str | None] = mapped_column(Text)
    # Why a pipeline run stopped early (LLM item cap, daily spend limit, shutdown); shown in Admin.
    stop_reason: Mapped[str | None] = mapped_column(Text)


class Job(Base):
    """Durable job lifecycle (§11.4). APScheduler only enqueues; workers claim with SKIP LOCKED."""

    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(_in("kind", JOB_KINDS), name="kind_valid"),
        CheckConstraint(_in("status", JOB_STATUSES), name="status_valid"),
        CheckConstraint("attempt_count >= 0 AND max_attempts > 0", name="attempts_valid"),
        Index("ix_jobs_status_next_retry_at", "status", "next_retry_at"),
        # At most one active job per kind: duplicate schedules from several replicas no-op.
        Index(
            "uq_jobs_one_active_per_kind",
            "kind",
            unique=True,
            postgresql_where=text(_in("status", JOB_ACTIVE)),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    status: Mapped[str] = mapped_column(String(16), server_default="pending")
    attempt_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    max_attempts: Mapped[int] = mapped_column(Integer, server_default=text("3"))
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_by: Mapped[str | None] = mapped_column(Text)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TrendBrief(Base):
    __tablename__ = "trend_briefs"
    __table_args__ = (
        CheckConstraint("period_end > period_start", name="period_valid"),
        Index("ix_trend_briefs_created_at", text("created_at DESC")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    content_md: Mapped[str] = mapped_column(Text)
    # Evidence item ids in citation order: `[n]` in content_md refers to sources[n-1].
    sources: Mapped[list[int]] = mapped_column(ARRAY(BigInteger), server_default=text("'{}'"))
    model: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(Text)
    tokens_in: Mapped[int | None] = mapped_column(Integer)
    tokens_out: Mapped[int | None] = mapped_column(Integer)
    cost_usd_estimate: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    created_at: Mapped[datetime] = _created()
