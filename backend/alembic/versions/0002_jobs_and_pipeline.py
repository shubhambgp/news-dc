"""durable jobs (§11.4) and AI pipeline bookkeeping (Phase 3, §11.5)

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-09

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACTIVE = "status IN ('pending', 'running', 'retry_wait')"


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default=sa.text("3"), nullable=False),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.Text(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("kind IN ('ingest_all', 'pipeline')", name=op.f("ck_jobs_kind_valid")),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'retry_wait', 'dead_letter', 'cancelled')",
            name=op.f("ck_jobs_status_valid"),
        ),
        sa.CheckConstraint(
            "attempt_count >= 0 AND max_attempts > 0", name=op.f("ck_jobs_attempts_valid")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jobs")),
    )
    op.create_index("ix_jobs_status_next_retry_at", "jobs", ["status", "next_retry_at"])
    op.create_index(
        "uq_jobs_one_active_per_kind",
        "jobs",
        ["kind"],
        unique=True,
        postgresql_where=sa.text(ACTIVE),
    )

    op.add_column(
        "items",
        sa.Column("ai_attempts", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column("items", sa.Column("status_reason", sa.Text(), nullable=True))
    op.create_check_constraint("ai_attempts_nonneg", "items", "ai_attempts >= 0")

    op.add_column("ai_annotations", sa.Column("attempts", sa.SmallInteger(), nullable=True))

    op.add_column(
        "pipeline_runs",
        sa.Column("kind", sa.String(length=16), server_default="ingest", nullable=False),
    )
    op.add_column("pipeline_runs", sa.Column("stop_reason", sa.Text(), nullable=True))
    op.create_check_constraint("kind_valid", "pipeline_runs", "kind IN ('ingest', 'pipeline')")


def downgrade() -> None:
    op.drop_constraint("kind_valid", "pipeline_runs", type_="check")
    op.drop_column("pipeline_runs", "stop_reason")
    op.drop_column("pipeline_runs", "kind")
    op.drop_column("ai_annotations", "attempts")
    op.drop_constraint("ai_attempts_nonneg", "items", type_="check")
    op.drop_column("items", "status_reason")
    op.drop_column("items", "ai_attempts")
    op.drop_index(
        "uq_jobs_one_active_per_kind", table_name="jobs", postgresql_where=sa.text(ACTIVE)
    )
    op.drop_index("ix_jobs_status_next_retry_at", table_name="jobs")
    op.drop_table("jobs")
