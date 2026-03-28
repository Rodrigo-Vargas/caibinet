"""Add phase column to sessions table

Revision ID: 0004_add_session_phase
Revises: 0003_add_summary_cache
Create Date: 2026-03-27 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_add_session_phase"
down_revision = "0003_add_summary_cache"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from sqlalchemy import inspect
    bind = op.get_bind()
    inspector = inspect(bind)
    cols = [c["name"] for c in inspector.get_columns("sessions")]
    if "phase" not in cols:
        op.add_column("sessions", sa.Column("phase", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("sessions", "phase")
