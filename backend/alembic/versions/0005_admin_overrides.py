"""admin overrides: sources.admin_disabled, categories.admin_edited_at (Phase 8)

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-09

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sources",
        sa.Column("admin_disabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "categories", sa.Column("admin_edited_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("categories", "admin_edited_at")
    op.drop_column("sources", "admin_disabled")
