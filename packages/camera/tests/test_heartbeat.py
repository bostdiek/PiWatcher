import requests

from piwatcher_camera.heartbeat import HeartbeatManager, collect_telemetry


def test_given_elapsed_interval_when_is_due_then_returns_true() -> None:
    # Arrange
    heartbeat = HeartbeatManager(900, "http://server", "secret", "camera")
    heartbeat.last_sent = 100.0

    # Act
    result = heartbeat.is_due(now=1000.0)

    # Assert
    assert result is True


def test_given_recent_heartbeat_when_is_due_then_returns_false() -> None:
    # Arrange
    heartbeat = HeartbeatManager(900, "http://server", "secret", "camera")
    heartbeat.last_sent = 100.0

    # Act
    result = heartbeat.is_due(now=500.0)

    # Assert
    assert result is False


def test_given_piggyback_when_called_then_resets_timer(monkeypatch) -> None:
    # Arrange
    heartbeat = HeartbeatManager(900, "http://server", "secret", "camera")
    monkeypatch.setattr("piwatcher_camera.heartbeat.time.time", lambda: 1234.0)

    # Act
    heartbeat.piggyback()

    # Assert
    assert heartbeat.last_sent == 1234.0


def test_given_send_failure_when_called_then_resets_timer(monkeypatch) -> None:
    # Arrange
    heartbeat = HeartbeatManager(900, "http://server", "secret", "camera")
    monkeypatch.setattr("piwatcher_camera.heartbeat.time.time", lambda: 1234.0)

    def raise_connection_error(*_args, **_kwargs):
        raise requests.ConnectionError("network unavailable")

    monkeypatch.setattr("piwatcher_camera.heartbeat.requests.post", raise_connection_error)

    # Act
    result = heartbeat.send()

    # Assert
    assert result is False
    assert heartbeat.last_sent == 1234.0


def test_given_standalone_without_wifi_management_when_send_then_does_not_toggle_wifi(
    monkeypatch,
) -> None:
    # Arrange
    heartbeat = HeartbeatManager(900, "http://server", "secret", "camera")
    wifi_calls: list[str] = []
    monkeypatch.setattr("piwatcher_camera.heartbeat.wifi_on", lambda: wifi_calls.append("on"))
    monkeypatch.setattr("piwatcher_camera.heartbeat.wifi_off", lambda: wifi_calls.append("off"))
    monkeypatch.setattr(heartbeat, "send", lambda battery_pct=None: True)

    # Act
    result = heartbeat.send_standalone(manage_wifi=False)

    # Assert
    assert result is True
    assert wifi_calls == []


def test_given_frame_queue_when_collect_telemetry_then_reports_queue_and_disk(
    tmp_path,
) -> None:
    # Arrange
    frame_queue = tmp_path / "frames"
    frame_queue.mkdir()
    (frame_queue / "one.jpg").write_bytes(b"frame")
    (frame_queue / "ignore.txt").write_text("not a frame", encoding="utf-8")

    # Act
    telemetry = collect_telemetry(frame_queue, wifi_power_save=False)

    # Assert
    assert telemetry["queue_depth"] == 1
    assert telemetry["queued_event_count"] == 0
    disk_free_mb = telemetry["disk_free_mb"]
    assert isinstance(disk_free_mb, int)
    assert disk_free_mb > 0
    assert telemetry["wifi_power_save"] is False
    assert telemetry["software_version"] == "0.1.0"


def test_given_durable_bundle_when_collect_telemetry_then_reports_queued_event_count(
    tmp_path,
) -> None:
    # Arrange
    frame_queue = tmp_path / "frames"
    bundle_root = frame_queue / "events" / "2026" / "06" / "28" / "feeder-cam" / "event-1"
    bundle_root.mkdir(parents=True)
    (bundle_root / "frame_0000.jpg").write_bytes(b"frame")
    (bundle_root / "event.json").write_text(
        """
{
  "schema_version": 1,
  "event_id": "event-1",
  "camera_id": "feeder-cam",
  "event_start": "2026-06-28T16:00:00+00:00",
  "event_end": null,
  "status": "pending",
  "attempt_count": 0,
  "last_attempt_at": null,
  "next_attempt_at": null,
  "last_error": null,
  "upload_started_at": null,
  "frames": [
    {
      "sequence_num": 0,
      "file_name": "frame_0000.jpg",
      "captured_at": "2026-06-28T16:00:00+00:00"
    }
  ],
  "created_at": "2026-06-28T16:00:00+00:00",
  "updated_at": "2026-06-28T16:00:00+00:00"
}
""".strip(),
        encoding="utf-8",
    )

    # Act
    telemetry = collect_telemetry(frame_queue, wifi_power_save=None)

    # Assert
    assert telemetry["queue_depth"] == 1
    assert telemetry["queued_event_count"] == 1


def test_given_missing_queue_dir_when_collect_telemetry_then_omits_queued_event_count(
    tmp_path,
) -> None:
    # Arrange
    missing_queue = tmp_path / "missing"

    # Act
    telemetry = collect_telemetry(missing_queue, wifi_power_save=None)

    # Assert
    assert "queue_depth" not in telemetry
    assert "queued_event_count" not in telemetry
