"""Heartbeat endpoint tests."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from piwatcher_base.models import Camera, Heartbeat
from piwatcher_base.routes.heartbeat import cleanup_old_heartbeats


@pytest.mark.asyncio()
async def test_given_heartbeat_when_receive_then_records_camera_health(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    # Act
    response = await client.post(
        "/api/heartbeat",
        data={"camera_id": "feeder-cam", "battery_pct": 91, "uptime_seconds": 120},
        headers=auth_headers,
    )
    health_response = await client.get("/api/health/cameras")

    # Assert
    assert response.status_code == 200
    assert health_response.json()[0]["battery_pct"] == 91


@pytest.mark.asyncio()
async def test_given_heartbeat_telemetry_when_receive_then_records_camera_and_metrics(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    # Act
    response = await client.post(
        "/api/heartbeat",
        data={
            "camera_id": "feeder-cam",
            "battery_pct": 91,
            "uptime_seconds": 120,
            "wifi_rssi_dbm": -62,
            "disk_free_mb": 2048,
            "queue_depth": 3,
            "queued_event_count": 2,
            "cpu_temp_c": 54.2,
            "wifi_power_save": "false",
            "software_version": "0.1.0",
        },
        headers=auth_headers,
    )

    # Assert
    heartbeat = await db_session.scalar(
        select(Heartbeat).where(Heartbeat.camera_id == "feeder-cam")
    )
    camera = await db_session.get(Camera, "feeder-cam")
    assert response.status_code == 200
    assert camera is not None
    assert heartbeat is not None
    assert heartbeat.wifi_rssi_dbm == -62
    assert heartbeat.disk_free_mb == 2048
    assert heartbeat.queue_depth == 3
    assert heartbeat.queued_event_count == 2
    assert heartbeat.cpu_temp_c == 54.2
    assert heartbeat.wifi_power_save is False
    assert heartbeat.software_version == "0.1.0"


@pytest.mark.asyncio()
async def test_given_heartbeat_without_queued_event_count_when_health_requested_then_reports_null(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    # Act
    response = await client.post(
        "/api/heartbeat",
        data={
            "camera_id": "legacy-cam",
            "queue_depth": 7,
        },
        headers=auth_headers,
    )
    health_response = await client.get("/api/health/cameras")

    # Assert
    cameras = {item["camera_id"]: item for item in health_response.json()}
    assert response.status_code == 200
    assert cameras["legacy-cam"]["queue_depth"] == 7
    assert cameras["legacy-cam"]["queued_event_count"] is None


@pytest.mark.asyncio()
async def test_given_old_heartbeat_when_cleanup_then_deletes_expired_rows(
    db_session: AsyncSession,
) -> None:
    # Arrange
    db_session.add(
        Heartbeat(camera_id="old-cam", created_at=datetime.now(UTC) - timedelta(days=100))
    )
    db_session.add(Heartbeat(camera_id="new-cam", created_at=datetime.now(UTC)))
    await db_session.commit()

    # Act
    deleted = await cleanup_old_heartbeats(db_session)

    # Assert
    remaining = (await db_session.scalars(select(Heartbeat.camera_id))).all()
    assert deleted == 1
    assert remaining == ["new-cam"]
