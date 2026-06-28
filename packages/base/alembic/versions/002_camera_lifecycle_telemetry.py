"""camera lifecycle telemetry

Revision ID: 002_camera_lifecycle_telemetry
Revises: 001_initial_schema
Create Date: 2026-06-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "002_camera_lifecycle_telemetry"
down_revision: str | None = "001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add camera metadata and heartbeat telemetry."""

    op.create_table(
        "cameras",
        sa.Column("camera_id", sa.String(length=50), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("camera_id"),
    )
    op.create_index("ix_cameras_archived_at", "cameras", ["archived_at"], unique=False)

    op.add_column("heartbeats", sa.Column("ip_address", sa.String(length=45), nullable=True))
    op.add_column("heartbeats", sa.Column("wifi_rssi_dbm", sa.Integer(), nullable=True))
    op.add_column("heartbeats", sa.Column("disk_free_mb", sa.Integer(), nullable=True))
    op.add_column("heartbeats", sa.Column("queue_depth", sa.Integer(), nullable=True))
    op.add_column("heartbeats", sa.Column("cpu_temp_c", sa.Float(), nullable=True))
    op.add_column("heartbeats", sa.Column("wifi_power_save", sa.Boolean(), nullable=True))
    op.add_column("heartbeats", sa.Column("software_version", sa.String(length=50), nullable=True))

    op.execute("""
        INSERT INTO cameras (camera_id, display_name)
        SELECT DISTINCT camera_id, camera_id FROM events
        UNION
        SELECT DISTINCT camera_id, camera_id FROM heartbeats
        """)


def downgrade() -> None:
    """Remove camera metadata and heartbeat telemetry."""

    op.drop_column("heartbeats", "software_version")
    op.drop_column("heartbeats", "wifi_power_save")
    op.drop_column("heartbeats", "cpu_temp_c")
    op.drop_column("heartbeats", "queue_depth")
    op.drop_column("heartbeats", "disk_free_mb")
    op.drop_column("heartbeats", "wifi_rssi_dbm")
    op.drop_column("heartbeats", "ip_address")
    op.drop_index("ix_cameras_archived_at", table_name="cameras")
    op.drop_table("cameras")
