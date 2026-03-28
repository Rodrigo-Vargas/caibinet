"""Add summary_cache table

Revision ID: 0003_add_summary_cache
Revises: 0002_add_elapsed_seconds
Create Date: 2026-03-26 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_add_summary_cache"
down_revision = "0002_add_elapsed_seconds"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from sqlalchemy import inspect
    bind = op.get_bind()
    if "summary_cache" not in inspect(bind).get_table_names():
        op.create_table(
            "summary_cache",
            sa.Column("file_hash", sa.String(), nullable=False),
            sa.Column("summary", sa.Text(), nullable=False),
            sa.Column("cached_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("file_hash"),
        )


def downgrade() -> None:
    op.drop_table("summary_cache")
