"""add camera event id idempotency

Revision ID: 003_camera_event_id
Revises: 002_camera_lifecycle_telemetry
Create Date: 2026-06-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "003_camera_event_id"
down_revision: str | None = "002_camera_lifecycle_telemetry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add camera_event_id for upload idempotency."""

    op.add_column("events", sa.Column("camera_event_id", sa.String(length=80), nullable=True))
    op.create_index(
        "ux_events_camera_id_camera_event_id",
        "events",
        ["camera_id", "camera_event_id"],
        unique=True,
    )


def downgrade() -> None:
    """Remove camera_event_id idempotency support."""

    op.drop_index("ux_events_camera_id_camera_event_id", table_name="events")
    op.drop_column("events", "camera_event_id")
