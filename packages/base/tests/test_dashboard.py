"""Dashboard route tests."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from piwatcher_base.models import Camera, Event, Frame, Heartbeat
from piwatcher_base.routes import dashboard


@pytest.mark.asyncio()
async def test_given_events_when_dashboard_events_requested_then_renders_cards(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path,
) -> None:
    # Arrange
    frame_path = tmp_path / "frames" / "feeder-cam" / "frame.jpg"
    frame_path.parent.mkdir(parents=True)
    frame_path.write_bytes(b"jpeg")
    event = Event(
        camera_id="feeder-cam",
        event_start=datetime.now(UTC),
        frame_count=1,
        label="deer",
        confidence=0.91,
        battery_pct=84,
        classified_at=datetime.now(UTC),
    )
    event.frames = [Frame(sequence_num=0, file_path=str(frame_path), captured_at=datetime.now(UTC))]
    db_session.add(event)
    await db_session.commit()

    # Act
    response = await client.get("/events")

    # Assert
    assert response.status_code == 200
    assert "deer" in response.text
    assert "feeder-cam" in response.text
    assert "Classified" in response.text


@pytest.mark.asyncio()
async def test_given_camera_filter_when_event_partials_requested_then_filters_events(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    # Arrange
    db_session.add(Event(camera_id="feeder-cam", event_start=datetime.now(UTC), frame_count=1))
    db_session.add(Event(camera_id="porch-cam", event_start=datetime.now(UTC), frame_count=1))
    await db_session.commit()

    # Act
    response = await client.get("/events/partials", params={"camera_id": "porch-cam"})

    # Assert
    assert response.status_code == 200
    assert "porch-cam" in response.text
    assert "feeder-cam" not in response.text


@pytest.mark.asyncio()
async def test_given_unclassified_event_when_dashboard_events_requested_then_renders_pending_status(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    # Arrange
    db_session.add(Event(camera_id="feeder-cam", event_start=datetime.now(UTC), frame_count=1))
    await db_session.commit()

    # Act
    response = await client.get("/events")

    # Assert
    assert response.status_code == 200
    assert "Pending inference" in response.text


@pytest.mark.asyncio()
async def test_given_event_detail_when_requested_then_renders_classification_json(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    # Arrange
    event = Event(
        camera_id="feeder-cam",
        event_start=datetime.now(UTC),
        frame_count=1,
        label="fox",
        raw_classification={"description": "animal near feeder"},
    )
    db_session.add(event)
    await db_session.commit()
    await db_session.refresh(event)

    # Act
    response = await client.get(f"/events/{event.id}")

    # Assert
    assert response.status_code == 200
    assert "fox" in response.text
    assert "animal near feeder" in response.text


@pytest.mark.asyncio()
async def test_given_heartbeats_when_health_requested_then_renders_status_and_chart_data(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    # Arrange
    db_session.add(
        Heartbeat(
            camera_id="feeder-cam",
            battery_pct=72,
            queue_depth=3,
            queued_event_count=1,
            created_at=datetime.now(UTC) - timedelta(minutes=5),
        )
    )
    await db_session.commit()

    # Act
    response = await client.get("/health")

    # Assert
    assert response.status_code == 200
    assert "feeder-cam" in response.text
    assert "Online" in response.text
    assert "Battery (%)" in response.text
    assert "Wi-Fi RSSI (dBm)" in response.text
    assert "Queued frames" in response.text
    assert "Queued events" in response.text
    assert "CPU temperature (C)" in response.text


@pytest.mark.asyncio()
async def test_given_archived_camera_when_health_requested_then_hides_until_requested(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    # Arrange
    db_session.add(
        Camera(camera_id="old-cam", display_name="Old Cam", archived_at=datetime.now(UTC))
    )
    db_session.add(Heartbeat(camera_id="old-cam", battery_pct=72, created_at=datetime.now(UTC)))
    await db_session.commit()

    # Act
    hidden_response = await client.get("/health")
    archived_response = await client.get("/health", params={"show_archived": "true"})

    # Assert
    assert hidden_response.status_code == 200
    assert "old-cam" not in hidden_response.text
    assert archived_response.status_code == 200
    assert "old-cam" in archived_response.text
    assert "Restore camera" in archived_response.text


@pytest.mark.asyncio()
async def test_given_legacy_heartbeat_when_health_requested_then_renders_without_telemetry(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    # Arrange
    db_session.add(
        Heartbeat(
            camera_id="legacy-cam",
            battery_pct=64,
            created_at=datetime.now(UTC) - timedelta(minutes=5),
        )
    )
    await db_session.commit()

    # Act
    response = await client.get("/health")

    # Assert
    assert response.status_code == 200
    assert "legacy-cam" in response.text


@pytest.mark.asyncio()
async def test_given_missing_queued_event_count_when_health_requested_then_renders_placeholder(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    # Arrange
    db_session.add(
        Heartbeat(
            camera_id="placeholder-cam",
            queue_depth=4,
            created_at=datetime.now(UTC) - timedelta(minutes=2),
        )
    )
    await db_session.commit()

    # Act
    response = await client.get("/health")

    # Assert
    assert response.status_code == 200
    assert "placeholder-cam" in response.text
    assert "Queued events" in response.text
    assert "Queued frame history for placeholder-cam" in response.text
    assert "Queued event history for placeholder-cam" in response.text


def test_given_display_timezone_when_format_datetime_then_renders_local_time(
    test_settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    monkeypatch.setattr(test_settings, "display_timezone", "America/Chicago")
    timestamp = datetime(2026, 6, 28, 16, 10, tzinfo=UTC)

    # Act
    formatted = dashboard.format_datetime(timestamp)

    # Assert
    assert formatted == "2026-06-28 11:10 CDT"


def test_given_display_timezone_when_format_time_then_renders_local_chart_label(
    test_settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    monkeypatch.setattr(test_settings, "display_timezone", "America/Chicago")
    timestamp = datetime(2026, 6, 28, 16, 10, tzinfo=UTC)

    # Act
    formatted = dashboard.format_time(timestamp)

    # Assert
    assert formatted == "11:10"


def test_given_legacy_frame_name_when_frame_url_requested_then_rebuilds_event_path() -> None:
    # Arrange
    event = Event(
        camera_id="roomtest",
        event_start=datetime(2026, 6, 28, 19, 10, 22, tzinfo=UTC),
        frame_count=1,
    )
    frame = Frame(
        sequence_num=0,
        file_path="frame_0000.jpg",
        captured_at=datetime.now(UTC),
    )
    frame.event = event

    # Act
    url = dashboard.frame_url(frame)

    # Assert
    assert url == "/frames/2026/06/28/roomtest/191022/frame_0000.jpg"


def test_given_prefixed_legacy_frame_path_when_frame_url_requested_then_strips_frames_prefix() -> (
    None
):
    # Arrange
    frame = Frame(
        sequence_num=0,
        file_path="tmp/piwatcher/frames/2026/06/28/roomtest/161040/frame_0000.jpg",
        captured_at=datetime.now(UTC),
    )

    # Act
    url = dashboard.frame_url(frame)

    # Assert
    assert url == "/frames/2026/06/28/roomtest/161040/frame_0000.jpg"


@pytest.mark.asyncio()
async def test_given_recent_logs_when_logs_requested_then_renders_log_output(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    async def fake_read_recent_service_logs() -> dict[str, object]:
        return {
            "lines": [
                (
                    "2026-06-28T01:10:00+00:00 pi5 piwatcher-base.service: "
                    "Inference endpoint unavailable"
                ),
                (
                    "2026-06-28T01:10:05+00:00 pi5 piwatcher-inference.service: "
                    "llama-swap request failed"
                ),
            ],
            "error_message": None,
            "lookback_minutes": 15,
            "units": ["piwatcher-base.service", "piwatcher-inference.service"],
            "has_entries": True,
        }

    monkeypatch.setattr(dashboard, "read_recent_service_logs", fake_read_recent_service_logs)

    # Act
    response = await client.get("/logs")

    # Assert
    assert response.status_code == 200
    assert "Base Logs" in response.text
    assert "Inference endpoint unavailable" in response.text
    assert "piwatcher-inference.service" in response.text
