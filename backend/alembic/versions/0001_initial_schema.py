"""initial schema: all PLAN §5 tables plus item_sources (§11.2)

Revision ID: 0001
Revises:
Create Date: 2026-11-09 17:45:40.970712

"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Kept on downgrade: other objects may depend on it and it is harmless when unused.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "categories",
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "keywords", postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False
        ),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("slug", name=op.f("pk_categories")),
    )
    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trigger", sa.String(length=16), nullable=False),
        sa.Column("source_key", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="running", nullable=False),
        sa.Column("fetched", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("new", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("duplicates", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("rejected_prefilter", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("rejected_ai", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("processed", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("failed", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "cost_usd_estimate",
            sa.Numeric(precision=10, scale=4),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('running', 'succeeded', 'partial', 'failed')",
            name=op.f("ck_pipeline_runs_status_valid"),
        ),
        sa.CheckConstraint(
            "trigger IN ('schedule', 'admin', 'cli')", name=op.f("ck_pipeline_runs_trigger_valid")
        ),
        sa.CheckConstraint(
            "fetched >= 0 AND new >= 0 AND duplicates >= 0 AND rejected_prefilter >= 0 AND rejected_ai >= 0 AND processed >= 0 AND failed >= 0",
            name=op.f("ck_pipeline_runs_counts_nonneg"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pipeline_runs")),
    )
    op.create_index(
        "ix_pipeline_runs_started_at",
        "pipeline_runs",
        [sa.literal_column("started_at DESC")],
        unique=False,
    )
    op.create_table(
        "sources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "settings",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("last_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.Text(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "checkpoint",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "type IN ('hackernews', 'rss', 'arxiv', 'github')", name=op.f("ck_sources_type_valid")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sources")),
        sa.UniqueConstraint("key", name=op.f("uq_sources_key")),
    )
    op.create_table(
        "trend_briefs",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_md", sa.Text(), nullable=False),
        sa.Column(
            "sources",
            postgresql.ARRAY(sa.BigInteger()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("period_end > period_start", name=op.f("ck_trend_briefs_period_valid")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trend_briefs")),
    )
    op.create_table(
        "items",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("primary_source_id", sa.Integer(), nullable=True),
        sa.Column("original_url", sa.Text(), nullable=False),
        sa.Column("resolved_url", sa.Text(), nullable=True),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("url_hash", sa.String(length=64), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("content_text", sa.Text(), nullable=True),
        sa.Column("publisher", sa.Text(), nullable=True),
        sa.Column("author", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "source_tags",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("points", sa.Integer(), nullable=True),
        sa.Column("comments_count", sa.Integer(), nullable=True),
        sa.Column("discussion_url", sa.Text(), nullable=True),
        sa.Column(
            "related_links",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=32), server_default="new", nullable=False),
        sa.Column("duplicate_of", sa.BigInteger(), nullable=True),
        sa.Column("duplicate_similarity", sa.Float(), nullable=True),
        sa.Column("duplicate_reason", sa.Text(), nullable=True),
        sa.Column(
            "tsv",
            postgresql.TSVECTOR(),
            sa.Computed(
                "setweight(to_tsvector('english', coalesce(title, '')), 'A') || setweight(to_tsvector('english', coalesce(description, '')), 'B') || setweight(to_tsvector('english', coalesce(content_text, '')), 'C')",
                persisted=True,
            ),
            nullable=False,
        ),
        sa.Column("embedding", pgvector.sqlalchemy.vector.VECTOR(dim=384), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('new', 'rejected_prefilter', 'rejected_ai', 'duplicate', 'processed', 'failed')",
            name=op.f("ck_items_status_valid"),
        ),
        sa.CheckConstraint(
            "comments_count IS NULL OR comments_count >= 0",
            name=op.f("ck_items_comments_count_nonneg"),
        ),
        sa.CheckConstraint("duplicate_of <> id", name=op.f("ck_items_not_self_duplicate")),
        sa.CheckConstraint(
            "duplicate_similarity IS NULL OR duplicate_similarity BETWEEN 0 AND 1",
            name=op.f("ck_items_duplicate_similarity_range"),
        ),
        sa.CheckConstraint("points IS NULL OR points >= 0", name=op.f("ck_items_points_nonneg")),
        sa.ForeignKeyConstraint(
            ["duplicate_of"],
            ["items.id"],
            name=op.f("fk_items_duplicate_of_items"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["primary_source_id"],
            ["sources.id"],
            name=op.f("fk_items_primary_source_id_sources"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_items")),
        sa.UniqueConstraint("url_hash", name=op.f("uq_items_url_hash")),
    )
    op.create_index("ix_items_content_hash", "items", ["content_hash"], unique=False)
    op.create_index("ix_items_duplicate_of", "items", ["duplicate_of"], unique=False)
    op.create_index(
        "ix_items_embedding_hnsw",
        "items",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_index(
        op.f("ix_items_primary_source_id"), "items", ["primary_source_id"], unique=False
    )
    op.create_index(
        "ix_items_published_at_id",
        "items",
        [sa.literal_column("published_at DESC"), sa.literal_column("id DESC")],
        unique=False,
    )
    op.create_index("ix_items_status", "items", ["status"], unique=False)
    op.create_index("ix_items_tsv", "items", ["tsv"], unique=False, postgresql_using="gin")
    op.create_table(
        "ai_annotations",
        sa.Column("item_id", sa.BigInteger(), nullable=False),
        sa.Column("is_relevant", sa.Boolean(), nullable=False),
        sa.Column("is_spam", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("relevance_score", sa.SmallInteger(), nullable=True),
        sa.Column("quality_score", sa.SmallInteger(), nullable=True),
        sa.Column("primary_category", sa.String(length=64), nullable=True),
        sa.Column(
            "categories",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("content_type", sa.String(length=32), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column(
            "key_insights",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "entities",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "tags", postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False
        ),
        sa.Column("reject_reason", sa.Text(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("prompt_version", sa.Text(), nullable=True),
        sa.Column("prompt_hash", sa.String(length=64), nullable=True),
        sa.Column("tokens_in", sa.Integer(), nullable=True),
        sa.Column("tokens_out", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("cost_usd_estimate", sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "content_type IS NULL OR content_type IN ('news', 'research', 'investment', 'engineering')",
            name=op.f("ck_ai_annotations_content_type_valid"),
        ),
        sa.CheckConstraint(
            "quality_score BETWEEN 0 AND 100", name=op.f("ck_ai_annotations_quality_score_range")
        ),
        sa.CheckConstraint(
            "relevance_score BETWEEN 0 AND 100",
            name=op.f("ck_ai_annotations_relevance_score_range"),
        ),
        sa.CheckConstraint(
            "tokens_in IS NULL OR tokens_in >= 0", name=op.f("ck_ai_annotations_tokens_in_nonneg")
        ),
        sa.CheckConstraint(
            "tokens_out IS NULL OR tokens_out >= 0",
            name=op.f("ck_ai_annotations_tokens_out_nonneg"),
        ),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["items.id"],
            name=op.f("fk_ai_annotations_item_id_items"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["primary_category"],
            ["categories.slug"],
            name=op.f("fk_ai_annotations_primary_category_categories"),
            onupdate="CASCADE",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("item_id", name=op.f("pk_ai_annotations")),
    )
    op.create_index(
        "ix_ai_annotations_primary_category", "ai_annotations", ["primary_category"], unique=False
    )
    op.create_table(
        "item_sources",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("item_id", sa.BigInteger(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("source_title", sa.Text(), nullable=True),
        sa.Column(
            "source_engagement",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["items.id"],
            name=op.f("fk_item_sources_item_id_items"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name=op.f("fk_item_sources_source_id_sources"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_item_sources")),
        sa.UniqueConstraint(
            "source_id", "external_id", name=op.f("uq_item_sources_source_id_external_id")
        ),
        sa.UniqueConstraint("source_id", "item_id", name=op.f("uq_item_sources_source_id_item_id")),
    )
    op.create_index(op.f("ix_item_sources_item_id"), "item_sources", ["item_id"], unique=False)
    op.create_index(
        "uq_item_sources_one_primary",
        "item_sources",
        ["item_id"],
        unique=True,
        postgresql_where=sa.text("is_primary"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_item_sources_one_primary",
        table_name="item_sources",
        postgresql_where=sa.text("is_primary"),
    )
    op.drop_index(op.f("ix_item_sources_item_id"), table_name="item_sources")
    op.drop_table("item_sources")
    op.drop_index("ix_ai_annotations_primary_category", table_name="ai_annotations")
    op.drop_table("ai_annotations")
    op.drop_index("ix_items_tsv", table_name="items", postgresql_using="gin")
    op.drop_index("ix_items_status", table_name="items")
    op.drop_index("ix_items_published_at_id", table_name="items")
    op.drop_index(op.f("ix_items_primary_source_id"), table_name="items")
    op.drop_index(
        "ix_items_embedding_hnsw",
        table_name="items",
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.drop_index("ix_items_duplicate_of", table_name="items")
    op.drop_index("ix_items_content_hash", table_name="items")
    op.drop_table("items")
    op.drop_table("trend_briefs")
    op.drop_table("sources")
    op.drop_index("ix_pipeline_runs_started_at", table_name="pipeline_runs")
    op.drop_table("pipeline_runs")
    op.drop_table("categories")
