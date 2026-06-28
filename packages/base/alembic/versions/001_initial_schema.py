"""initial schema

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-06-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create initial PiWatcher tables."""

    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("camera_id", sa.String(length=50), nullable=False),
        sa.Column("event_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("frame_count", sa.Integer(), nullable=False),
        sa.Column("battery_pct", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("label", sa.String(length=50), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("raw_classification", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("classified_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_events_camera_id", "events", ["camera_id"], unique=False)
    op.create_index("ix_events_created_at", "events", ["created_at"], unique=False)

    op.create_table(
        "heartbeats",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("camera_id", sa.String(length=50), nullable=False),
        sa.Column("battery_pct", sa.Integer(), nullable=True),
        sa.Column("uptime_seconds", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_heartbeats_camera_id", "heartbeats", ["camera_id"], unique=False)
    op.create_index("ix_heartbeats_created_at", "heartbeats", ["created_at"], unique=False)

    op.create_table(
        "frames",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("sequence_num", sa.Integer(), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_frames_event_id", "frames", ["event_id"], unique=False)


def downgrade() -> None:
    """Remove initial PiWatcher tables."""

    op.drop_index("ix_frames_event_id", table_name="frames")
    op.drop_table("frames")
    op.drop_index("ix_heartbeats_created_at", table_name="heartbeats")
    op.drop_index("ix_heartbeats_camera_id", table_name="heartbeats")
    op.drop_table("heartbeats")
    op.drop_index("ix_events_created_at", table_name="events")
    op.drop_index("ix_events_camera_id", table_name="events")
    op.drop_table("events")
