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


def test_given_frame_queue_when_collect_telemetry_then_reports_queue_and_disk(tmp_path) -> None:
    # Arrange
    frame_queue = tmp_path / "frames"
    frame_queue.mkdir()
    (frame_queue / "one.jpg").write_bytes(b"frame")
    (frame_queue / "ignore.txt").write_text("not a frame", encoding="utf-8")

    # Act
    telemetry = collect_telemetry(frame_queue, wifi_power_save=False)

    # Assert
    assert telemetry["queue_depth"] == 1
    disk_free_mb = telemetry["disk_free_mb"]
    assert isinstance(disk_free_mb, int)
    assert disk_free_mb > 0
    assert telemetry["wifi_power_save"] is False
    assert telemetry["software_version"] == "0.1.0"
