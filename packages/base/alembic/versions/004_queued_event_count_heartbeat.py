"""add queued event count to heartbeats

Revision ID: 004_queued_event_count_heartbeat
Revises: 003_camera_event_id
Create Date: 2026-06-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "004_queued_event_count_heartbeat"
down_revision: str | None = "003_camera_event_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add nullable queued_event_count heartbeat telemetry."""

    op.add_column("heartbeats", sa.Column("queued_event_count", sa.Integer(), nullable=True))


def downgrade() -> None:
    """Remove queued_event_count heartbeat telemetry."""

    op.drop_column("heartbeats", "queued_event_count")
