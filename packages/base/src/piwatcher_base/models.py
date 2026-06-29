"""SQLAlchemy models for PiWatcher database."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for PiWatcher ORM models."""


class Event(Base):
    """Motion event captured by a camera."""

    __tablename__ = "events"
    __table_args__ = (
        Index("ix_events_created_at", "created_at"),
        Index(
            "ux_events_camera_id_camera_event_id",
            "camera_id",
            "camera_event_id",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    camera_id: Mapped[str] = mapped_column(String(50), index=True)
    camera_event_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    event_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    event_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    frame_count: Mapped[int] = mapped_column(Integer)
    battery_pct: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    label: Mapped[str | None] = mapped_column(String(50))
    confidence: Mapped[float | None] = mapped_column(Float)
    raw_classification: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite")
    )
    classified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    frames: Mapped[list["Frame"]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class Camera(Base):
    """Known camera node with dashboard lifecycle metadata."""

    __tablename__ = "cameras"

    camera_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    display_name: Mapped[str | None] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(Text)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class Frame(Base):
    """Stored frame belonging to an event."""

    __tablename__ = "frames"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    sequence_num: Mapped[int] = mapped_column(Integer)
    file_path: Mapped[str] = mapped_column(Text)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    event: Mapped[Event] = relationship(back_populates="frames")


class Heartbeat(Base):
    """Periodic camera health signal."""

    __tablename__ = "heartbeats"
    __table_args__ = (Index("ix_heartbeats_created_at", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    camera_id: Mapped[str] = mapped_column(String(50), index=True)
    battery_pct: Mapped[int | None] = mapped_column(Integer)
    uptime_seconds: Mapped[int | None] = mapped_column(Integer)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    wifi_rssi_dbm: Mapped[int | None] = mapped_column(Integer)
    disk_free_mb: Mapped[int | None] = mapped_column(Integer)
    queue_depth: Mapped[int | None] = mapped_column(Integer)
    queued_event_count: Mapped[int | None] = mapped_column(Integer)
    cpu_temp_c: Mapped[float | None] = mapped_column(Float)
    wifi_power_save: Mapped[bool | None] = mapped_column(Boolean)
    software_version: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
