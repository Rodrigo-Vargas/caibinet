"""Add elapsed_seconds to sessions and operations

Revision ID: 0002_add_elapsed_seconds
Revises: 0001_initial
Create Date: 2026-03-26 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_add_elapsed_seconds"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("elapsed_seconds", sa.Float(), nullable=True))
    op.add_column("operations", sa.Column("elapsed_seconds", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("operations", "elapsed_seconds")
    op.drop_column("sessions", "elapsed_seconds")
