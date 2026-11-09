"""full-text index over the AI summary for hybrid search (Phase 4, D-013 / D-029)

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-09

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ai_annotations",
        sa.Column(
            "summary_tsv",
            postgresql.TSVECTOR(),
            sa.Computed(
                "setweight(to_tsvector('english', coalesce(summary, '')), 'B')", persisted=True
            ),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_ai_annotations_summary_tsv",
        "ai_annotations",
        ["summary_tsv"],
        unique=False,
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_ai_annotations_summary_tsv", table_name="ai_annotations")
    op.drop_column("ai_annotations", "summary_tsv")
