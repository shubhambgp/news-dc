"""trend brief job kind and trend brief model/cost columns (Phase 7)

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-09

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _kinds(*kinds: str) -> None:
    op.drop_constraint(op.f("ck_jobs_kind_valid"), "jobs", type_="check")
    values = ", ".join(f"'{k}'" for k in kinds)
    op.create_check_constraint(op.f("ck_jobs_kind_valid"), "jobs", f"kind IN ({values})")


def upgrade() -> None:
    _kinds("ingest_all", "pipeline", "trend_brief")
    op.add_column("trend_briefs", sa.Column("model", sa.Text(), nullable=True))
    op.add_column("trend_briefs", sa.Column("prompt_version", sa.Text(), nullable=True))
    op.add_column("trend_briefs", sa.Column("tokens_in", sa.Integer(), nullable=True))
    op.add_column("trend_briefs", sa.Column("tokens_out", sa.Integer(), nullable=True))
    op.add_column(
        "trend_briefs",
        sa.Column("cost_usd_estimate", sa.Numeric(precision=10, scale=6), nullable=True),
    )
    op.create_index(
        "ix_trend_briefs_created_at", "trend_briefs", [sa.text("created_at DESC")], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_trend_briefs_created_at", table_name="trend_briefs")
    for col in ("cost_usd_estimate", "tokens_out", "tokens_in", "prompt_version", "model"):
        op.drop_column("trend_briefs", col)
    op.execute("DELETE FROM jobs WHERE kind = 'trend_brief'")
    _kinds("ingest_all", "pipeline")
