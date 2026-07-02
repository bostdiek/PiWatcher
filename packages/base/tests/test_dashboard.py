"""Dashboard route tests."""

from datetime import UTC, datetime, timedelta
from typing import cast

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
    assert "Inferences (15m)" in response.text
    assert "Base CPU temperature (15m)" in response.text
    assert "CPU temperature (24h)" in response.text
    assert "CPU temperature (15m)" in response.text


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


@pytest.mark.asyncio()
async def test_given_base_health_when_health_requested_then_renders_diagnostics_panels(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    db_session.add(Heartbeat(camera_id="feeder-cam", battery_pct=75, created_at=datetime.now(UTC)))
    await db_session.commit()

    async def fake_read_base_host_health() -> dict[str, object]:
        return {
            "generated_at": datetime.now(UTC),
            "cpu_temp_c": 68.4,
            "uptime_seconds": 7200,
            "load_1m": 0.45,
            "load_5m": 0.31,
            "load_15m": 0.22,
            "frame_storage_path": "/tmp/piwatcher/frames",
            "disk_total_bytes": 100,
            "disk_used_bytes": 25,
            "disk_free_bytes": 75,
            "disk_used_pct": 25.0,
            "service_states": {
                "piwatcher-base.service": {"active": "active", "enabled": "enabled"},
                "piwatcher-inference.service": {
                    "active": "active",
                    "enabled": "enabled",
                },
            },
        }

    async def fake_read_recent_inference_logs() -> dict[str, object]:
        return {
            "lines": [
                "2026-07-01T09:27:43 pi5 uv: Starting inference for event 1",
                "2026-07-01T09:27:56 pi5 uv: Finished inference for event 1",
            ],
            "error_message": None,
            "lookback_minutes": 15,
            "units": ["piwatcher-base.service", "piwatcher-inference.service"],
            "has_entries": True,
            "filtered_count": 2,
            "title": "Inference activity",
        }

    monkeypatch.setattr(dashboard, "read_base_host_health", fake_read_base_host_health)
    monkeypatch.setattr(dashboard, "read_recent_inference_logs", fake_read_recent_inference_logs)

    # Act
    response = await client.get("/health")

    # Assert
    assert response.status_code == 200
    assert "Host health" in response.text
    assert "Inference activity" in response.text
    assert "Starting inference for event 1" in response.text
    assert "68.4 C" in response.text


@pytest.mark.asyncio()
async def test_given_service_logs_when_inference_logs_requested_then_filters_only_inference_lines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    async def fake_read_recent_service_logs(*_args, **_kwargs) -> dict[str, object]:
        return {
            "lines": [
                "GET /events/partials 200",
                "Starting inference for event 9",
                "Finished inference for event 9",
                "POST /api/heartbeat 200",
            ],
            "error_message": None,
            "lookback_minutes": 15,
            "units": ["piwatcher-base.service", "piwatcher-inference.service"],
            "has_entries": True,
        }

    monkeypatch.setattr(dashboard, "read_recent_service_logs", fake_read_recent_service_logs)

    # Act
    filtered = await dashboard.read_recent_inference_logs()

    # Assert
    assert filtered["has_entries"] is True
    assert filtered["filtered_count"] == 2
    filtered_lines = cast("list[str]", filtered["lines"])
    assert all("inference" in line.lower() for line in filtered_lines)


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


def test_given_utc_log_line_when_formatted_then_converts_to_dashboard_timezone(
    test_settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    monkeypatch.setattr(test_settings, "display_timezone", "America/Chicago")
    log_line = "2026-07-01T14:15:00+00:00 pi5 uv: GET /events/partials 200"

    # Act
    view = dashboard.format_log_view(
        lines=[log_line],
        units=("piwatcher-base.service",),
        lookback_minutes=15,
    )

    # Assert
    assert view["lines"] == ["2026-07-01 09:15:00 CDT pi5 uv: GET /events/partials 200"]
    assert view["timezone_label"] == "America/Chicago (CDT)"


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
    assert "Inference diagnostics" in response.text
    assert "Quick status" in response.text


def test_given_mixed_inference_lines_when_summarized_then_counts_500_and_mmproj_errors() -> None:
    # Arrange
    lines = [
        "2026-07-01 10:00:00 EDT pi5 uv: Starting inference for event 101",
        (
            "2026-07-01 10:00:05 EDT pi5 llama-swap: Request 127.0.0.1 "
            '"POST /v1/chat/completions HTTP/1.1" 200'
        ),
        (
            "2026-07-01 10:00:06 EDT pi5 uv: Inference endpoint returned HTTP 500: "
            "image input is not supported - hint: you may need to provide the mmproj"
        ),
        (
            "2026-07-01 10:00:06 EDT pi5 uv: Failed to classify frame "
            "/tmp/frame_0000.jpg for event 101"
        ),
    ]

    # Act
    summary = dashboard.summarize_inference_lines(lines)

    # Assert
    assert summary["line_count"] == 4
    assert summary["success_count"] == 1
    assert summary["error_count"] == 2
    assert summary["http_500_count"] == 1
    assert summary["mmproj_error_count"] == 1
    assert summary["status"] == "Degraded"
    assert "Failed to classify frame" in str(summary["latest_error"])


def test_given_chronological_log_lines_when_formatted_then_display_lines_are_newest_first(
    test_settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    monkeypatch.setattr(test_settings, "display_timezone", "UTC")
    lines = [
        "2026-07-01T10:00:00+00:00 pi5 uv: first",
        "2026-07-01T10:00:05+00:00 pi5 uv: second",
        "2026-07-01T10:00:10+00:00 pi5 uv: third",
    ]

    # Act
    view = dashboard.format_log_view(
        lines=lines,
        units=("piwatcher-base.service", "piwatcher-inference.service"),
        lookback_minutes=15,
    )

    # Assert
    view_lines = cast("list[str]", view["lines"])
    display_lines = cast("list[str]", view["display_lines"])
    assert view_lines[0].endswith("first")
    assert display_lines[0].endswith("third")
    assert display_lines[-1].endswith("first")
    assert view["order"] == "newest_first"


@pytest.mark.asyncio()
async def test_given_inference_lines_when_filtered_then_display_lines_are_newest_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    async def fake_read_recent_service_logs(*_args, **_kwargs) -> dict[str, object]:
        return {
            "lines": [
                "2026-07-01T10:00:00+00:00 pi5 uv: Starting inference for event 9",
                "2026-07-01T10:00:05+00:00 pi5 uv: Finished inference for event 9",
                "2026-07-01T10:00:10+00:00 pi5 uv: GET /events/partials 200",
            ],
            "error_message": None,
            "lookback_minutes": 15,
            "units": ["piwatcher-base.service", "piwatcher-inference.service"],
            "has_entries": True,
        }

    monkeypatch.setattr(dashboard, "read_recent_service_logs", fake_read_recent_service_logs)

    # Act
    view = await dashboard.read_recent_inference_logs()

    # Assert
    view_lines = cast("list[str]", view["lines"])
    display_lines = cast("list[str]", view["display_lines"])
    assert view_lines[0].endswith("Starting inference for event 9")
    assert display_lines[0].endswith("Finished inference for event 9")
    assert display_lines[-1].endswith("Starting inference for event 9")


@pytest.mark.asyncio()
async def test_given_recent_classified_events_when_requested_then_counts_samples(
    db_session: AsyncSession,
) -> None:
    # Arrange
    now = datetime.now(UTC)
    db_session.add_all(
        [
            Event(
                camera_id="feeder-cam",
                event_start=now,
                frame_count=3,
                classified_at=now - timedelta(minutes=2),
                raw_classification={
                    "samples": [
                        {"label": "deer", "confidence": 0.8, "description": "a deer"},
                        {
                            "label": "deer",
                            "confidence": 0.9,
                            "description": "same deer",
                        },
                        {
                            "label": "deer",
                            "confidence": 0.7,
                            "description": "deer moving",
                        },
                    ]
                },
            ),
            Event(
                camera_id="porch-cam",
                event_start=now,
                frame_count=2,
                classified_at=now - timedelta(minutes=5),
                raw_classification={
                    "samples": [
                        {"label": "human", "confidence": 0.9, "description": "person"},
                        {
                            "label": "human",
                            "confidence": 0.8,
                            "description": "person walking",
                        },
                    ]
                },
            ),
            Event(
                camera_id="old-cam",
                event_start=now,
                frame_count=1,
                classified_at=now - timedelta(minutes=45),
                raw_classification={
                    "samples": [
                        {"label": "fox", "confidence": 0.8, "description": "fox"},
                    ]
                },
            ),
            Event(
                camera_id="fallback-cam",
                event_start=now,
                frame_count=1,
                classified_at=now - timedelta(minutes=1),
                raw_classification=None,
            ),
        ]
    )
    await db_session.commit()

    # Act
    summary = await dashboard.read_recent_inference_activity(
        db_session,
        lookback_minutes=15,
    )

    # Assert
    assert summary["lookback_minutes"] == 15
    assert summary["event_count"] == 3
    assert summary["sample_count"] == 6
