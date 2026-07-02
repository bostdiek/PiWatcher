"""Event upload and query endpoints."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..auth import verify_api_key
from ..config import get_settings
from ..db import get_db
from ..inference import classify_event_background
from ..models import Camera, Event, Frame
from ..storage import store_frames
from .ws import broadcast_event_created

router = APIRouter(tags=["events"])

CameraIdForm = Annotated[str, Form(...)]
EventStartForm = Annotated[str, Form(...)]
EventEndForm = Annotated[str | None, Form()]
BatteryPctForm = Annotated[int | None, Form()]
CameraEventIdForm = Annotated[str | None, Form()]
FramesFile = Annotated[list[UploadFile], File(...)]
DbSession = Annotated[AsyncSession, Depends(get_db)]


def parse_datetime(value: str) -> datetime:
    """Parse an ISO-8601 timestamp into an aware datetime."""

    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


async def rollback_if_needed(session: AsyncSession) -> None:
    """Rollback an open transaction before handing a session back to the pool."""

    if session.in_transaction():
        await session.rollback()


@router.post(
    "/events",
    dependencies=[Depends(verify_api_key)],
    status_code=status.HTTP_201_CREATED,
)
async def create_event(
    background_tasks: BackgroundTasks,
    camera_id: CameraIdForm,
    event_start: EventStartForm,
    frames: FramesFile,
    session: DbSession,
    event_end: EventEndForm = None,
    battery_pct: BatteryPctForm = None,
    camera_event_id: CameraEventIdForm = None,
) -> dict[str, int | str]:
    """Receive camera frames, persist metadata, and queue inference."""

    if not frames:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one frame is required",
        )

    started_at = parse_datetime(event_start)
    ended_at = parse_datetime(event_end) if event_end else None

    if camera_event_id:
        existing = await session.scalar(
            select(Event).where(
                Event.camera_id == camera_id,
                Event.camera_event_id == camera_event_id,
            )
        )
        if existing is not None:
            existing_event_id = existing.id
            await rollback_if_needed(session)
            await session.close()
            return {"event_id": existing_event_id, "status": "accepted"}

        await rollback_if_needed(session)

    stored_paths = await store_frames(
        frames,
        camera_id,
        started_at,
        get_settings().frame_storage_path,
    )
    camera = await session.get(Camera, camera_id)
    if camera is None:
        session.add(Camera(camera_id=camera_id, display_name=camera_id))

    event = Event(
        camera_id=camera_id,
        camera_event_id=camera_event_id,
        event_start=started_at,
        event_end=ended_at,
        frame_count=len(stored_paths),
        battery_pct=battery_pct,
    )
    event.frames = [
        Frame(sequence_num=index, file_path=str(path), captured_at=started_at)
        for index, path in enumerate(stored_paths)
    ]
    session.add(event)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        if camera_event_id:
            existing = await session.scalar(
                select(Event).where(
                    Event.camera_id == camera_id,
                    Event.camera_event_id == camera_event_id,
                )
            )
            if existing is not None:
                existing_event_id = existing.id
                await rollback_if_needed(session)
                await session.close()
                return {"event_id": existing_event_id, "status": "accepted"}
        raise
    await session.refresh(event)
    event_id = event.id
    event_camera_id = event.camera_id
    await session.close()

    background_tasks.add_task(classify_event_background, event_id, stored_paths)
    background_tasks.add_task(broadcast_event_created, event_id, event_camera_id)
    return {"event_id": event_id, "status": "accepted"}


@router.get("/events")
async def list_events(
    session: DbSession,
    camera_id: str | None = None,
    limit: int = 50,
) -> list[dict[str, object]]:
    """List recent events, optionally filtered by camera."""

    bounded_limit = min(max(limit, 1), 200)
    statement = select(Event).order_by(Event.created_at.desc()).limit(bounded_limit)
    if camera_id:
        statement = statement.where(Event.camera_id == camera_id)
    events = (await session.scalars(statement)).all()
    return [serialize_event(event) for event in events]


@router.get("/events/{event_id}")
async def get_event(event_id: int, session: DbSession) -> dict[str, object]:
    """Return event details with frame paths and classification data."""

    event = await session.scalar(
        select(Event).options(selectinload(Event.frames)).where(Event.id == event_id)
    )
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    payload = serialize_event(event)
    payload["frames"] = [
        serialize_frame(frame)
        for frame in sorted(event.frames, key=lambda frame: frame.sequence_num)
    ]
    return payload


def serialize_event(event: Event) -> dict[str, object]:
    """Serialize an event for API responses."""

    return {
        "id": event.id,
        "camera_id": event.camera_id,
        "event_start": event.event_start.isoformat(),
        "event_end": event.event_end.isoformat() if event.event_end else None,
        "frame_count": event.frame_count,
        "battery_pct": event.battery_pct,
        "label": event.label,
        "confidence": event.confidence,
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }


def serialize_frame(frame: Frame) -> dict[str, object]:
    """Serialize frame metadata for API responses."""

    return {
        "id": frame.id,
        "sequence_num": frame.sequence_num,
        "file_path": str(Path(frame.file_path)),
        "captured_at": frame.captured_at.isoformat(),
    }
