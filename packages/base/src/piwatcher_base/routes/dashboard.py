"""LAN dashboard HTML routes."""

import asyncio
import json
import logging
import os
import re
import shutil
from collections import deque
from contextlib import suppress
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
BASE_CPU_WINDOW_MINUTES = 15
LOG_UNITS = ("piwatcher-base.service", "piwatcher-inference.service")
INFERENCE_LOG_KEYWORDS = (
    "starting inference",
    "finished inference",
    "failed to classify",
    "inference endpoint",
    "chat/completions",
    "mmproj",
    "llama-swap",
)

INFERENCE_ERROR_KEYWORDS = (
    "http 500",
    "failed to classify",
    "server_error",
    "traceback",
    "exception",
)

BASE_CPU_HISTORY: deque[tuple[datetime, float]] = deque()


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
    base_health = await read_base_host_health()
    inference_activity = await read_recent_inference_activity(
        session,
        lookback_minutes=BASE_CPU_WINDOW_MINUTES,
    )
    base_cpu_chart = base_health.get(
        "cpu_temp_history",
        {
            "labels": [],
            "values": [],
            "lookback_minutes": BASE_CPU_WINDOW_MINUTES,
            "latest_value": None,
        },
    )
    return templates.TemplateResponse(
        request,
        "health.html",
        {
            "cameras": await fetch_camera_ids(session),
            "cameras_health": cameras,
            "chart_data_json": json.dumps(chart_data),
            "base_health": base_health,
            "base_cpu_chart_json": json.dumps(base_cpu_chart),
            "inference_activity": inference_activity,
            "inference_log_view": await read_recent_inference_logs(),
            "selected_camera_id": None,
            "show_archived": show_archived,
        },
    )


async def read_recent_inference_activity(
    session: AsyncSession,
    *,
    lookback_minutes: int,
) -> dict[str, int]:
    """Summarize recent inference throughput for host thermal diagnostics."""

    since = datetime.now(UTC) - timedelta(minutes=lookback_minutes)
    recent_payloads = (
        await session.scalars(
            select(Event.raw_classification)
            .where(Event.classified_at.is_not(None), Event.classified_at >= since)
            .order_by(Event.classified_at.desc())
        )
    ).all()

    sample_count = 0
    for payload in recent_payloads:
        if isinstance(payload, dict):
            samples = payload.get("samples")
            if isinstance(samples, list) and samples:
                sample_count += len(samples)
                continue
        sample_count += 1

    return {
        "lookback_minutes": lookback_minutes,
        "event_count": len(recent_payloads),
        "sample_count": sample_count,
    }


@router.get("/logs", response_class=HTMLResponse)
async def logs_page(request: Request, session: DbSession) -> HTMLResponse:
    """Render recent base-station runtime logs."""

    log_view = await read_recent_service_logs()
    inference_log_view = build_inference_log_view(log_view)

    return templates.TemplateResponse(
        request,
        "logs.html",
        {
            "cameras": await fetch_camera_ids(session),
            "selected_camera_id": None,
            "log_view": log_view,
            "inference_log_view": inference_log_view,
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
                "queued_frames": metric_series(values, "queue_depth"),
                "queued_events": metric_series(values, "queued_event_count"),
                "temperature": metric_series(values, "cpu_temp_c"),
                "temperature_15m": metric_series(
                    values,
                    "cpu_temp_c",
                    window_minutes=BASE_CPU_WINDOW_MINUTES,
                ),
                "disk": metric_series(values, "disk_free_mb"),
            },
        }
        for camera_id, values in sorted(history_by_camera.items())
    ]


def metric_series(
    heartbeats: list[Heartbeat],
    attribute: str,
    *,
    window_minutes: int | None = None,
) -> dict[str, object]:
    """Return chart labels and values for one nullable heartbeat metric."""

    points = [
        (heartbeat.created_at, getattr(heartbeat, attribute))
        for heartbeat in heartbeats
        if getattr(heartbeat, attribute) is not None
    ]

    if window_minutes is not None:
        cutoff = datetime.now(UTC) - timedelta(minutes=window_minutes)
        points = [
            (created_at, value)
            for created_at, value in points
            if created_at is not None and created_at >= cutoff
        ]

    return {
        "labels": [format_time(created_at) for created_at, _value in points],
        "values": [value for _created_at, value in points],
        "latest_value": points[-1][1] if points else None,
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


async def read_recent_inference_logs(
    lookback_minutes: int = LOG_LOOKBACK_MINUTES,
) -> dict[str, object]:
    """Return recent inference-related journal lines across base + inference units."""

    log_view = await read_recent_service_logs(lookback_minutes=lookback_minutes)
    return build_inference_log_view(log_view)


def build_inference_log_view(log_view: dict[str, object]) -> dict[str, object]:
    """Filter and summarize inference-related lines from a full log view."""

    if log_view.get("error_message"):
        return {
            **log_view,
            "lines": [],
            "display_lines": [],
            "has_entries": False,
            "filtered_count": 0,
            "title": "Inference activity",
            "summary": summarize_inference_lines([]),
        }

    raw_lines = log_view.get("lines", [])
    candidate_lines = raw_lines if isinstance(raw_lines, list) else []
    lines = [
        line
        for line in candidate_lines
        if isinstance(line, str)
        and any(keyword in line.lower() for keyword in INFERENCE_LOG_KEYWORDS)
    ]
    return {
        **log_view,
        "lines": lines,
        "display_lines": list(reversed(lines)),
        "has_entries": bool(lines),
        "filtered_count": len(lines),
        "title": "Inference activity",
        "summary": summarize_inference_lines(lines),
    }


def summarize_inference_lines(lines: list[str]) -> dict[str, object]:
    """Build compact inference diagnostics from filtered log lines."""

    lowered = [line.lower() for line in lines]
    error_count = sum(
        1 for line in lowered if any(keyword in line for keyword in INFERENCE_ERROR_KEYWORDS)
    )
    http_500_count = sum(1 for line in lowered if "http 500" in line)
    mmproj_error_count = sum(
        1 for line in lowered if "mmproj" in line or "image input is not supported" in line
    )
    success_count = sum(
        1
        for line in lowered
        if "finished inference" in line
        or re.search(r"chat/completions.*\"\s*200(?:\s|$)", line) is not None
    )

    status = "Idle"
    if success_count > 0 and error_count == 0:
        status = "Healthy"
    elif success_count > 0 and error_count > 0:
        status = "Degraded"
    elif error_count > 0:
        status = "Failing"

    latest_error = next(
        (
            line
            for line in reversed(lines)
            if any(keyword in line.lower() for keyword in INFERENCE_ERROR_KEYWORDS)
        ),
        None,
    )

    return {
        "status": status,
        "line_count": len(lines),
        "success_count": success_count,
        "error_count": error_count,
        "http_500_count": http_500_count,
        "mmproj_error_count": mmproj_error_count,
        "latest_error": latest_error,
    }


async def read_base_host_health() -> dict[str, object]:
    """Return base host health and service status for dashboard diagnostics."""

    settings = get_settings()
    storage_path = settings.frame_storage_path
    usage_base = storage_path if storage_path.exists() else storage_path.parent
    disk_total_bytes = None
    disk_used_bytes = None
    disk_free_bytes = None
    disk_used_pct = None
    try:
        usage = shutil.disk_usage(usage_base)
        disk_total_bytes = usage.total
        disk_used_bytes = usage.used
        disk_free_bytes = usage.free
        if usage.total > 0:
            disk_used_pct = (usage.used / usage.total) * 100
    except OSError:
        logger.warning("Unable to read disk usage for %s", usage_base)

    load_1m = None
    load_5m = None
    load_15m = None
    with suppress(OSError):
        load_1m, load_5m, load_15m = os.getloadavg()

    uptime_seconds = None
    try:
        uptime_text = Path("/proc/uptime").read_text(encoding="utf-8").strip()
        uptime_seconds = int(float(uptime_text.split()[0]))
    except (OSError, ValueError, IndexError):
        pass

    generated_at = datetime.now(UTC)
    cpu_temp_c = read_host_cpu_temp_c()
    update_base_cpu_history(generated_at, cpu_temp_c)
    service_states = await read_service_states(LOG_UNITS)

    return {
        "generated_at": generated_at,
        "cpu_temp_c": cpu_temp_c,
        "cpu_temp_history": build_base_cpu_history_view(),
        "uptime_seconds": uptime_seconds,
        "load_1m": load_1m,
        "load_5m": load_5m,
        "load_15m": load_15m,
        "frame_storage_path": str(storage_path),
        "disk_total_bytes": disk_total_bytes,
        "disk_used_bytes": disk_used_bytes,
        "disk_free_bytes": disk_free_bytes,
        "disk_used_pct": disk_used_pct,
        "service_states": service_states,
    }


def update_base_cpu_history(sampled_at: datetime, cpu_temp_c: float | None) -> None:
    """Append one base CPU sample and prune points outside the short trend window."""

    if cpu_temp_c is None:
        return

    BASE_CPU_HISTORY.append((sampled_at, cpu_temp_c))
    cutoff = sampled_at - timedelta(minutes=BASE_CPU_WINDOW_MINUTES)
    while BASE_CPU_HISTORY and BASE_CPU_HISTORY[0][0] < cutoff:
        BASE_CPU_HISTORY.popleft()


def build_base_cpu_history_view() -> dict[str, object]:
    """Build display-ready base CPU trend data for the health page."""

    cutoff = datetime.now(UTC) - timedelta(minutes=BASE_CPU_WINDOW_MINUTES)
    while BASE_CPU_HISTORY and BASE_CPU_HISTORY[0][0] < cutoff:
        BASE_CPU_HISTORY.popleft()

    points = list(BASE_CPU_HISTORY)
    return {
        "labels": [format_time(sampled_at) for sampled_at, _temp_c in points],
        "values": [temp_c for _sampled_at, temp_c in points],
        "lookback_minutes": BASE_CPU_WINDOW_MINUTES,
        "latest_value": points[-1][1] if points else None,
    }


async def read_service_states(
    units: tuple[str, ...],
) -> dict[str, dict[str, str | bool]]:
    """Read active + enable states for systemd units."""

    states: dict[str, dict[str, str | bool]] = {}
    for unit in units:
        states[unit] = {
            "active": await systemctl_query(unit, "is-active"),
            "enabled": await systemctl_query(unit, "is-enabled"),
        }
    return states


async def systemctl_query(unit: str, command: str) -> str:
    """Run one non-interactive systemctl query and return a normalized response."""

    try:
        process = await asyncio.create_subprocess_exec(
            "systemctl",
            command,
            unit,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        return "unavailable"

    stdout, stderr = await process.communicate()
    output = stdout.decode("utf-8", errors="replace").strip()
    if output:
        return output
    error = stderr.decode("utf-8", errors="replace").strip()
    if error:
        return error.splitlines()[0]
    return "unknown"


def read_host_cpu_temp_c() -> float | None:
    """Read host CPU temperature in Celsius when thermal zone files exist."""

    temp_path = Path("/sys/class/thermal/thermal_zone0/temp")
    if not temp_path.exists():
        return None
    try:
        return float(temp_path.read_text(encoding="utf-8").strip()) / 1000.0
    except (OSError, ValueError):
        return None


def format_log_view(
    *,
    lines: list[str],
    units: tuple[str, ...],
    lookback_minutes: int,
    error_message: str | None = None,
) -> dict[str, object]:
    """Package log metadata for dashboard rendering."""

    converted_lines = [localize_log_timestamp(line) for line in lines]

    return {
        "lines": converted_lines,
        "display_lines": list(reversed(converted_lines)),
        "error_message": error_message,
        "lookback_minutes": lookback_minutes,
        "units": list(units),
        "has_entries": bool(converted_lines),
        "timezone_label": dashboard_timezone_label(),
        "order": "newest_first",
    }


def localize_log_timestamp(line: str) -> str:
    """Convert an ISO timestamp prefix to the dashboard display timezone."""

    if " " not in line:
        return line

    timestamp_text, remainder = line.split(" ", 1)
    try:
        parsed = datetime.fromisoformat(timestamp_text)
    except ValueError:
        return line

    localized = normalize_datetime(parsed)
    if localized is None:
        return line
    localized = localized.astimezone(display_timezone())
    return f"{localized.strftime('%Y-%m-%d %H:%M:%S %Z')} {remainder}"


def dashboard_timezone_label() -> str:
    """Return a stable display label for dashboard-localized timestamps."""

    timezone = display_timezone()
    zone_name = getattr(timezone, "key", str(timezone))
    abbreviation = datetime.now(timezone).strftime("%Z")
    if abbreviation and abbreviation != zone_name:
        return f"{zone_name} ({abbreviation})"
    return zone_name


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
        "queued_frame_count": heartbeat.queue_depth,
        "queued_event_count": heartbeat.queued_event_count,
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
