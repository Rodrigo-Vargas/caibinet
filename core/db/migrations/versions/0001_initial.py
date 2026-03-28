"""Initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2025-01-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("directory", sa.String(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "running", "applied", "undone", "error", "cancelled", name="sessionstatus"),
            nullable=False,
        ),
        sa.Column("total_files", sa.String(), nullable=True),
        sa.Column("processed_files", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "operations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("source_path", sa.String(), nullable=False),
        sa.Column("dest_path", sa.String(), nullable=False),
        sa.Column("original_name", sa.String(), nullable=False),
        sa.Column("proposed_name", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("ai_reasoning", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("file_hash", sa.String(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "pending", "approved", "applied", "undone", "skipped", "error",
                name="operationstatus",
            ),
            nullable=False,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "settings",
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("settings")
    op.drop_table("operations")
    op.drop_table("sessions")
