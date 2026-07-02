"""Heartbeat reception and camera health endpoints."""

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Annotated, cast

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import verify_api_key
from ..config import get_settings
from ..db import get_db
from ..models import Camera, Heartbeat

if TYPE_CHECKING:
    from sqlalchemy.engine import CursorResult

router = APIRouter(tags=["heartbeat"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
CameraIdForm = Annotated[str, Form(...)]
BatteryPctForm = Annotated[int | None, Form()]
UptimeSecondsForm = Annotated[int | None, Form()]
WifiRssiDbmForm = Annotated[int | None, Form()]
DiskFreeMbForm = Annotated[int | None, Form()]
QueueDepthForm = Annotated[int | None, Form()]
QueuedEventCountForm = Annotated[int | None, Form()]
CpuTempCForm = Annotated[float | None, Form()]
WifiPowerSaveForm = Annotated[bool | None, Form()]
SoftwareVersionForm = Annotated[str | None, Form()]


@router.post("/heartbeat", dependencies=[Depends(verify_api_key)])
async def receive_heartbeat(
    request: Request,
    session: DbSession,
    camera_id: CameraIdForm,
    battery_pct: BatteryPctForm = None,
    uptime_seconds: UptimeSecondsForm = None,
    wifi_rssi_dbm: WifiRssiDbmForm = None,
    disk_free_mb: DiskFreeMbForm = None,
    queue_depth: QueueDepthForm = None,
    queued_event_count: QueuedEventCountForm = None,
    cpu_temp_c: CpuTempCForm = None,
    wifi_power_save: WifiPowerSaveForm = None,
    software_version: SoftwareVersionForm = None,
) -> dict[str, str]:
    """Record a camera heartbeat."""

    camera = await session.get(Camera, camera_id)
    if camera is None:
        session.add(Camera(camera_id=camera_id, display_name=camera_id))

    session.add(
        Heartbeat(
            camera_id=camera_id,
            battery_pct=battery_pct,
            uptime_seconds=uptime_seconds,
            ip_address=request.client.host if request.client else None,
            wifi_rssi_dbm=wifi_rssi_dbm,
            disk_free_mb=disk_free_mb,
            queue_depth=queue_depth,
            queued_event_count=queued_event_count,
            cpu_temp_c=cpu_temp_c,
            wifi_power_save=wifi_power_save,
            software_version=software_version,
        )
    )
    await session.commit()
    return {"status": "ok"}


@router.get("/health/cameras")
async def camera_health(session: DbSession) -> list[dict[str, object]]:
    """Return the latest heartbeat for each camera."""

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
    heartbeats = (await session.scalars(statement)).all()
    return [
        {
            "camera_id": heartbeat.camera_id,
            "last_seen": (heartbeat.created_at.isoformat() if heartbeat.created_at else None),
            "battery_pct": heartbeat.battery_pct,
            "uptime_seconds": heartbeat.uptime_seconds,
            "ip_address": heartbeat.ip_address,
            "wifi_rssi_dbm": heartbeat.wifi_rssi_dbm,
            "disk_free_mb": heartbeat.disk_free_mb,
            "queue_depth": heartbeat.queue_depth,
            "queued_event_count": heartbeat.queued_event_count,
            "cpu_temp_c": heartbeat.cpu_temp_c,
            "wifi_power_save": heartbeat.wifi_power_save,
            "software_version": heartbeat.software_version,
        }
        for heartbeat in heartbeats
    ]


async def cleanup_old_heartbeats(session: AsyncSession) -> int:
    """Delete heartbeats older than the configured TTL."""

    cutoff = datetime.now(UTC) - timedelta(days=get_settings().heartbeat_ttl_days)
    result = cast(
        "CursorResult[object]",
        await session.execute(delete(Heartbeat).where(Heartbeat.created_at < cutoff)),
    )
    await session.commit()
    return result.rowcount or 0
