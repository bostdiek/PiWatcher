"""LAN dashboard HTML routes."""

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta, tzinfo
from pathlib import Path
from typing import Annotated, Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..config import get_settings
from ..db import get_db
from ..models import Camera, Event, Frame, Heartbeat
from . import ws

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = PACKAGE_ROOT / "templates"
logger = logging.getLogger(__name__)

router = APIRouter(tags=["dashboard"])
router.include_router(ws.router)
templates = Jinja2Templates(directory=TEMPLATE_DIR)

DbSession = Annotated[AsyncSession, Depends(get_db)]
CameraIdForm = Annotated[str, Form(...)]
LOG_LOOKBACK_MINUTES = 15
LOG_UNITS = ("piwatcher-base.service", "piwatcher-inference.service")


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, session: DbSession) -> HTMLResponse:
    """Render the default dashboard view."""

    return await events_page(request, session)


@router.get("/events", response_class=HTMLResponse)
async def events_page(
    request: Request,
    session: DbSession,
    camera_id: str | None = None,
) -> HTMLResponse:
    """Render recent motion events."""

    events = await fetch_events(session, camera_id=camera_id)
    return templates.TemplateResponse(
        request,
        "events.html",
        {
            "events": [format_event_summary(event) for event in events],
            "cameras": await fetch_camera_ids(session),
            "selected_camera_id": camera_id,
        },
    )


@router.get("/events/partials", response_class=HTMLResponse)
async def events_partial(
    request: Request,
    session: DbSession,
    camera_id: str | None = None,
) -> HTMLResponse:
    """Render event cards for htmx refreshes."""

    events = await fetch_events(session, camera_id=camera_id)
    cards = [
        templates.get_template("partials/event_card.html").render(
            request=request,
            event=format_event_summary(event),
        )
        for event in events
    ]
    if cards:
        return HTMLResponse("\n".join(cards))
    return HTMLResponse(
        '<div class="col-span-full rounded-lg border border-gray-800 bg-gray-900 p-8 '
        'text-center text-gray-400">No events yet.</div>'
    )


@router.get("/events/{event_id}", response_class=HTMLResponse)
async def event_detail(request: Request, event_id: int, session: DbSession) -> HTMLResponse:
    """Render a single event with frame gallery and classification details."""

    event = await session.scalar(
        select(Event).options(selectinload(Event.frames)).where(Event.id == event_id)
    )
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    return templates.TemplateResponse(
        request,
        "event_detail.html",
        {
            "event": format_event_detail(event),
            "cameras": await fetch_camera_ids(session),
            "selected_camera_id": event.camera_id,
        },
    )


@router.get("/health", response_class=HTMLResponse)
async def health_page(
    request: Request,
    session: DbSession,
    show_archived: bool = False,
) -> HTMLResponse:
    """Render camera heartbeat and battery status."""

    cameras = await fetch_camera_health(session, include_archived=show_archived)
    chart_data = await fetch_telemetry_history(session, include_archived=show_archived)
    return templates.TemplateResponse(
        request,
        "health.html",
        {
            "cameras": await fetch_camera_ids(session),
            "cameras_health": cameras,
            "chart_data_json": json.dumps(chart_data),
            "selected_camera_id": None,
            "show_archived": show_archived,
        },
    )


@router.get("/logs", response_class=HTMLResponse)
async def logs_page(request: Request, session: DbSession) -> HTMLResponse:
    """Render recent base-station runtime logs."""

    return templates.TemplateResponse(
        request,
        "logs.html",
        {
            "cameras": await fetch_camera_ids(session),
            "selected_camera_id": None,
            "log_view": await read_recent_service_logs(),
        },
    )


@router.post("/health/archive")
async def archive_camera(session: DbSession, camera_id: CameraIdForm) -> RedirectResponse:
    """Hide a camera from default dashboard views without deleting history."""

    camera = await ensure_camera(session, camera_id)
    camera.archived_at = datetime.now(UTC)
    await session.commit()
    return RedirectResponse("/health", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/health/unarchive")
async def unarchive_camera(session: DbSession, camera_id: CameraIdForm) -> RedirectResponse:
    """Return an archived camera to default dashboard views."""

    camera = await ensure_camera(session, camera_id)
    camera.archived_at = None
    await session.commit()
    return RedirectResponse("/health?show_archived=1", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/frames/{frame_path:path}")
async def frame_file(frame_path: str) -> FileResponse:
    """Serve stored frame files from the configured storage root."""

    storage_root = get_settings().frame_storage_path.resolve()
    file_path = (storage_root / frame_path).resolve()
    try:
        file_path.relative_to(storage_root)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Frame not found",
        ) from exc
    if not file_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Frame not found")
    return FileResponse(file_path)


async def fetch_events(
    session: AsyncSession,
    *,
    camera_id: str | None = None,
    limit: int = 50,
) -> list[Event]:
    """Fetch recent events with frames for thumbnails."""

    statement = (
        select(Event)
        .options(selectinload(Event.frames))
        .order_by(Event.created_at.desc())
        .limit(limit)
    )
    if camera_id:
        statement = statement.where(Event.camera_id == camera_id)
    return list((await session.scalars(statement)).all())


async def fetch_camera_ids(session: AsyncSession) -> list[str]:
    """Fetch all known camera IDs from events and heartbeats."""

    cameras = await fetch_camera_metadata(session, include_archived=False)
    return [camera.camera_id for camera in cameras]


async def ensure_camera(session: AsyncSession, camera_id: str) -> Camera:
    """Return camera metadata, creating a default record when needed."""

    camera = await session.get(Camera, camera_id)
    if camera is None:
        camera = Camera(camera_id=camera_id, display_name=camera_id)
        session.add(camera)
        await session.flush()
    return camera


async def fetch_camera_metadata(
    session: AsyncSession,
    *,
    include_archived: bool,
) -> list[Camera]:
    """Fetch camera metadata, backfilling records for legacy IDs."""

    event_cameras = (await session.scalars(select(Event.camera_id).distinct())).all()
    heartbeat_cameras = (await session.scalars(select(Heartbeat.camera_id).distinct())).all()
    known_ids = sorted(set(event_cameras) | set(heartbeat_cameras))
    for camera_id in known_ids:
        await ensure_camera(session, camera_id)
    await session.commit()

    statement = select(Camera).order_by(Camera.camera_id)
    if not include_archived:
        statement = statement.where(Camera.archived_at.is_(None))
    return list((await session.scalars(statement)).all())


async def fetch_camera_health(
    session: AsyncSession,
    *,
    include_archived: bool = False,
) -> list[dict[str, Any]]:
    """Fetch latest heartbeat per camera with dashboard status metadata."""

    camera_metadata = await fetch_camera_metadata(session, include_archived=include_archived)
    visible_camera_ids = {camera.camera_id for camera in camera_metadata}

    latest_by_camera = (
        select(Heartbeat.camera_id, func.max(Heartbeat.created_at).label("last_seen"))
        .group_by(Heartbeat.camera_id)
        .subquery()
    )
    statement = (
        select(Heartbeat)
        .join(
            latest_by_camera,
            (Heartbeat.camera_id == latest_by_camera.c.camera_id)
            & (Heartbeat.created_at == latest_by_camera.c.last_seen),
        )
        .order_by(Heartbeat.camera_id)
    )
    statement = statement.where(Heartbeat.camera_id.in_(visible_camera_ids))
    heartbeats = (await session.scalars(statement)).all()
    metadata_by_id = {camera.camera_id: camera for camera in camera_metadata}
    return [
        format_camera_health(heartbeat, metadata_by_id.get(heartbeat.camera_id))
        for heartbeat in heartbeats
    ]


async def fetch_telemetry_history(
    session: AsyncSession,
    *,
    include_archived: bool = False,
) -> list[dict[str, object]]:
    """Fetch telemetry history over the last 24 hours for dashboard charts."""

    since = datetime.now(UTC) - timedelta(hours=24)
    visible_camera_ids = {
        camera.camera_id
        for camera in await fetch_camera_metadata(session, include_archived=include_archived)
    }
    statement = (
        select(Heartbeat)
        .where(Heartbeat.created_at >= since, Heartbeat.camera_id.in_(visible_camera_ids))
        .order_by(Heartbeat.camera_id, Heartbeat.created_at)
    )
    heartbeats = (await session.scalars(statement)).all()
    history_by_camera: dict[str, list[Heartbeat]] = {}
    for heartbeat in heartbeats:
        history_by_camera.setdefault(heartbeat.camera_id, []).append(heartbeat)

    return [
        {
            "camera_id": camera_id,
            "metrics": {
                "battery": metric_series(values, "battery_pct"),
                "wifi": metric_series(values, "wifi_rssi_dbm"),
                "queue": metric_series(values, "queue_depth"),
                "temperature": metric_series(values, "cpu_temp_c"),
                "disk": metric_series(values, "disk_free_mb"),
            },
        }
        for camera_id, values in sorted(history_by_camera.items())
    ]


def metric_series(heartbeats: list[Heartbeat], attribute: str) -> dict[str, object]:
    """Return chart labels and values for one nullable heartbeat metric."""

    points = [
        (heartbeat.created_at, getattr(heartbeat, attribute))
        for heartbeat in heartbeats
        if getattr(heartbeat, attribute) is not None
    ]
    return {
        "labels": [format_time(created_at) for created_at, _value in points],
        "values": [value for _created_at, value in points],
    }


async def read_recent_service_logs(
    units: tuple[str, ...] = LOG_UNITS,
    lookback_minutes: int = LOG_LOOKBACK_MINUTES,
) -> dict[str, object]:
    """Return recent journal entries for dashboard troubleshooting."""

    command = ["journalctl"]
    for unit in units:
        command.extend(["-u", unit])
    command.extend(
        [
            "--since",
            f"{lookback_minutes} minutes ago",
            "--no-pager",
            "-o",
            "short-iso",
        ]
    )

    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        return format_log_view(
            lines=[],
            units=units,
            lookback_minutes=lookback_minutes,
            error_message="journalctl is not available on this host.",
        )

    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        error_message = stderr.decode("utf-8", errors="replace").strip()
        if not error_message:
            error_message = "Unable to read recent system logs from the dashboard process."
        logger.warning("Failed to read recent service logs: %s", error_message)
        return format_log_view(
            lines=[],
            units=units,
            lookback_minutes=lookback_minutes,
            error_message=error_message,
        )

    output = stdout.decode("utf-8", errors="replace").strip()
    return format_log_view(
        lines=output.splitlines() if output else [],
        units=units,
        lookback_minutes=lookback_minutes,
    )


def format_log_view(
    *,
    lines: list[str],
    units: tuple[str, ...],
    lookback_minutes: int,
    error_message: str | None = None,
) -> dict[str, object]:
    """Package log metadata for dashboard rendering."""

    return {
        "lines": lines,
        "error_message": error_message,
        "lookback_minutes": lookback_minutes,
        "units": list(units),
        "has_entries": bool(lines),
    }


def format_event_summary(event: Event) -> dict[str, Any]:
    """Format event data for event card rendering."""

    frames = sorted(event.frames, key=lambda frame: frame.sequence_num)
    thumbnail = frames[0] if frames else None
    classified_at = normalize_datetime(event.classified_at)
    return {
        "id": event.id,
        "camera_id": event.camera_id,
        "frame_count": event.frame_count,
        "battery_pct": event.battery_pct,
        "label": event.label,
        "confidence": event.confidence,
        "classified_at": classified_at,
        "classification_status": "Classified" if classified_at else "Pending inference",
        "classification_status_class": (
            "bg-emerald-400/10 text-emerald-300"
            if classified_at
            else "bg-amber-400/10 text-amber-300"
        ),
        "created_at_display": format_datetime(event.created_at),
        "thumbnail_url": frame_url(thumbnail) if thumbnail else None,
    }


def format_event_detail(event: Event) -> dict[str, Any]:
    """Format event data for detail rendering."""

    summary = format_event_summary(event)
    summary.update(
        {
            "event_start_display": format_datetime(event.event_start),
            "event_end_display": (format_datetime(event.event_end) if event.event_end else None),
            "raw_classification_json": json.dumps(event.raw_classification or {}, indent=2),
            "frames": [
                format_frame(frame)
                for frame in sorted(event.frames, key=lambda item: item.sequence_num)
            ],
        }
    )
    return summary


def format_frame(frame: Frame) -> dict[str, Any]:
    """Format frame data for dashboard rendering."""

    return {
        "id": frame.id,
        "sequence_num": frame.sequence_num,
        "url": frame_url(frame),
        "captured_at_display": format_datetime(frame.captured_at),
    }


def format_camera_health(heartbeat: Heartbeat, camera: Camera | None) -> dict[str, Any]:
    """Format latest heartbeat with health color metadata."""

    last_seen = normalize_datetime(heartbeat.created_at)
    age_minutes = (datetime.now(UTC) - last_seen).total_seconds() / 60 if last_seen else None
    if age_minutes is None or age_minutes > 120:
        status_label = "Offline"
        status_class = "text-red-300"
        badge_class = "bg-red-400/10 text-red-300"
    elif age_minutes > 30:
        status_label = "Delayed"
        status_class = "text-yellow-300"
        badge_class = "bg-yellow-400/10 text-yellow-300"
    else:
        status_label = "Online"
        status_class = "text-emerald-300"
        badge_class = "bg-emerald-400/10 text-emerald-300"

    return {
        "camera_id": heartbeat.camera_id,
        "display_name": (
            camera.display_name if camera and camera.display_name else heartbeat.camera_id
        ),
        "archived": camera.archived_at is not None if camera else False,
        "battery_pct": heartbeat.battery_pct,
        "ip_address": heartbeat.ip_address,
        "wifi_rssi_dbm": heartbeat.wifi_rssi_dbm,
        "disk_free_mb": heartbeat.disk_free_mb,
        "queue_depth": heartbeat.queue_depth,
        "cpu_temp_c": heartbeat.cpu_temp_c,
        "uptime_seconds": heartbeat.uptime_seconds,
        "wifi_power_save": heartbeat.wifi_power_save,
        "software_version": heartbeat.software_version,
        "last_seen_display": relative_time(last_seen),
        "status_label": status_label,
        "status_class": status_class,
        "badge_class": badge_class,
    }


def frame_url(frame: Frame) -> str:
    """Return static URL for a stored frame."""

    storage_root = get_settings().frame_storage_path.resolve()
    raw_path = Path(frame.file_path)
    if not raw_path.is_absolute():
        relative_path = legacy_relative_frame_path(frame, raw_path)
        if relative_path is not None:
            return f"/frames/{relative_path.as_posix()}"

    file_path = raw_path.resolve()
    try:
        relative_path = file_path.relative_to(storage_root)
    except ValueError:
        relative_path = infer_storage_relative_frame_path(raw_path) or Path(file_path.name)
    return f"/frames/{relative_path.as_posix()}"


def legacy_relative_frame_path(frame: Frame, raw_path: Path) -> Path | None:
    """Rebuild legacy single-file frame paths when event metadata is available."""

    if len(raw_path.parts) > 1:
        return infer_storage_relative_frame_path(raw_path) or raw_path

    event = frame.event
    if event is None:
        return None

    started_at = normalize_datetime(event.event_start)
    if started_at is None:
        return None

    return Path(
        started_at.strftime("%Y/%m/%d"),
        event.camera_id,
        started_at.strftime("%H%M%S"),
        raw_path.name,
    )


def infer_storage_relative_frame_path(raw_path: Path) -> Path | None:
    """Strip any leading path segments before the stored frames hierarchy."""

    parts = raw_path.parts
    if "frames" not in parts:
        return None

    frames_index = len(parts) - 1 - parts[::-1].index("frames")
    trailing_parts = parts[frames_index + 1 :]
    if not trailing_parts:
        return None
    return Path(*trailing_parts)


def normalize_datetime(value: datetime | None) -> datetime | None:
    """Ensure datetimes are timezone-aware for comparisons."""

    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def display_timezone() -> tzinfo:
    """Return the timezone used for dashboard display timestamps."""

    timezone_name = get_settings().display_timezone
    if timezone_name:
        try:
            return ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            logger.warning("Invalid display timezone %s; falling back to UTC", timezone_name)
    return datetime.now().astimezone().tzinfo or UTC


def format_datetime(value: datetime | None) -> str:
    """Return compact local dashboard timestamp text."""

    normalized = normalize_datetime(value)
    if normalized is None:
        return "--"
    return normalized.astimezone(display_timezone()).strftime("%Y-%m-%d %H:%M %Z")


def format_time(value: datetime | None) -> str:
    """Return compact time text for chart labels."""

    normalized = normalize_datetime(value)
    if normalized is None:
        return "--"
    return normalized.astimezone(display_timezone()).strftime("%H:%M")


def relative_time(value: datetime | None) -> str:
    """Return a human-readable relative timestamp."""

    normalized = normalize_datetime(value)
    if normalized is None:
        return "Never seen"
    age_seconds = int((datetime.now(UTC) - normalized).total_seconds())
    if age_seconds < 60:
        return "Seen just now"
    age_minutes = age_seconds // 60
    if age_minutes < 60:
        return f"Seen {age_minutes} minutes ago"
    age_hours = age_minutes // 60
    if age_hours < 48:
        return f"Seen {age_hours} hours ago"
    return f"Seen {age_hours // 24} days ago"
