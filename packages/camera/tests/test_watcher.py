from piwatcher_camera.config import CameraConfig
from piwatcher_camera.queue import create_event_bundle, load_due_event_bundles
from piwatcher_camera.watcher import (
    _drain_pending_bundles,
    _retry_delay_seconds,
    _should_manage_wifi,
)


def test_given_wifi_power_save_disabled_when_should_manage_wifi_then_returns_false() -> None:
    # Arrange
    config = CameraConfig(
        camera_id="camera",
        server_url="http://server",
        api_key="secret",
        wifi_power_save=False,
    )

    # Act
    result = _should_manage_wifi(config, startup_time=0.0, now=1000.0)

    # Assert
    assert result is False


def test_given_startup_grace_active_when_should_manage_wifi_then_returns_false() -> None:
    # Arrange
    config = CameraConfig(
        camera_id="camera",
        server_url="http://server",
        api_key="secret",
        wifi_startup_grace_seconds=600,
    )

    # Act
    result = _should_manage_wifi(config, startup_time=100.0, now=699.0)

    # Assert
    assert result is False


def test_given_startup_grace_elapsed_when_should_manage_wifi_then_returns_true() -> None:
    # Arrange
    config = CameraConfig(
        camera_id="camera",
        server_url="http://server",
        api_key="secret",
        wifi_startup_grace_seconds=600,
    )

    # Act
    result = _should_manage_wifi(config, startup_time=100.0, now=700.0)

    # Assert
    assert result is True


class _StubHeartbeat:
    def __init__(self) -> None:
        self.send_calls: list[int | None] = []

    def send(self, battery_pct: int | None = None) -> bool:
        self.send_calls.append(battery_pct)
        return True


def test_given_bundle_upload_success_when_transfer_frames_then_bundle_deleted(
    monkeypatch, tmp_path
) -> None:
    # Arrange
    from piwatcher_camera.watcher import _transfer_frames

    config = CameraConfig(
        camera_id="camera-a",
        server_url="http://pi5.local:8000",
        api_key="secret",
    )
    bundle = create_event_bundle(tmp_path / "frames", "camera-a")
    frame_path = bundle.allocate_frame_path()
    frame_path.parent.mkdir(parents=True, exist_ok=True)
    frame_path.write_bytes(b"frame")
    bundle.record_frame(frame_path)
    bundle.mark_ready()

    heartbeat = _StubHeartbeat()
    captured_upload: dict[str, object] = {}
    monkeypatch.setattr("piwatcher_camera.watcher.get_battery_level", lambda: 62)
    monkeypatch.setattr(
        "piwatcher_camera.watcher._should_manage_wifi", lambda *_args, **_kwargs: False
    )

    def fake_upload_event(**kwargs):
        captured_upload.update(kwargs)
        return True

    monkeypatch.setattr("piwatcher_camera.watcher.upload_event", fake_upload_event)

    # Act
    _transfer_frames([frame_path], config, heartbeat, bundle, startup_time=0.0)

    # Assert
    assert heartbeat.send_calls == [62]
    assert bundle.bundle_dir.exists() is False
    assert captured_upload["event_start"] == bundle.event_start
    assert captured_upload["event_end"] == bundle.event_end
    assert captured_upload["camera_event_id"] == bundle.event_id


def test_given_bundle_upload_failure_when_transfer_frames_then_bundle_retained(
    monkeypatch, tmp_path
) -> None:
    # Arrange
    from piwatcher_camera.watcher import _transfer_frames

    config = CameraConfig(
        camera_id="camera-a",
        server_url="http://pi5.local:8000",
        api_key="secret",
    )
    bundle = create_event_bundle(tmp_path / "frames", "camera-a")
    frame_path = bundle.allocate_frame_path()
    frame_path.parent.mkdir(parents=True, exist_ok=True)
    frame_path.write_bytes(b"frame")
    bundle.record_frame(frame_path)
    bundle.mark_ready()

    heartbeat = _StubHeartbeat()
    monkeypatch.setattr("piwatcher_camera.watcher.get_battery_level", lambda: 62)
    monkeypatch.setattr(
        "piwatcher_camera.watcher._should_manage_wifi", lambda *_args, **_kwargs: False
    )
    monkeypatch.setattr("piwatcher_camera.watcher.upload_event", lambda **_kwargs: False)

    # Act
    _transfer_frames([frame_path], config, heartbeat, bundle, startup_time=0.0)

    # Assert
    assert heartbeat.send_calls == []
    assert bundle.bundle_dir.exists() is True


def test_given_no_bundle_when_transfer_frames_success_then_legacy_frames_deleted(
    monkeypatch,
    tmp_path,
) -> None:
    # Arrange
    from piwatcher_camera.watcher import _transfer_frames

    config = CameraConfig(
        camera_id="camera-a",
        server_url="http://pi5.local:8000",
        api_key="secret",
    )
    frame_path = tmp_path / "frame_legacy.jpg"
    frame_path.write_bytes(b"frame")
    heartbeat = _StubHeartbeat()

    monkeypatch.setattr("piwatcher_camera.watcher.get_battery_level", lambda: 62)
    monkeypatch.setattr(
        "piwatcher_camera.watcher._should_manage_wifi", lambda *_args, **_kwargs: False
    )
    monkeypatch.setattr("piwatcher_camera.watcher.upload_event", lambda **_kwargs: True)

    # Act
    _transfer_frames([frame_path], config, heartbeat, bundle=None, startup_time=0.0)

    # Assert
    assert heartbeat.send_calls == [62]
    assert frame_path.exists() is False


def test_given_due_bundle_when_drain_pending_bundles_then_uploads_and_deletes(
    monkeypatch,
    tmp_path,
) -> None:
    # Arrange
    config = CameraConfig(
        camera_id="camera-a",
        server_url="http://pi5.local:8000",
        api_key="secret",
        frame_queue_dir=tmp_path / "frames",
    )
    bundle = create_event_bundle(config.frame_queue_dir, "camera-a")
    frame_path = bundle.allocate_frame_path()
    frame_path.parent.mkdir(parents=True, exist_ok=True)
    frame_path.write_bytes(b"frame")
    bundle.record_frame(frame_path)
    bundle.mark_ready()
    heartbeat = _StubHeartbeat()

    class _Attempt:
        success = True
        classification = None

    monkeypatch.setattr(
        "piwatcher_camera.watcher.upload_event_result", lambda **_kwargs: _Attempt()
    )
    monkeypatch.setattr("piwatcher_camera.watcher.get_battery_level", lambda: 51)
    monkeypatch.setattr(
        "piwatcher_camera.watcher._should_manage_wifi", lambda *_args, **_kwargs: False
    )

    # Act
    _drain_pending_bundles(config, heartbeat, startup_time=0.0)

    # Assert
    assert heartbeat.send_calls == [51]
    assert bundle.bundle_dir.exists() is False


def test_given_terminal_failure_when_drain_pending_bundles_then_marks_failed(
    monkeypatch,
    tmp_path,
) -> None:
    # Arrange
    config = CameraConfig(
        camera_id="camera-a",
        server_url="http://pi5.local:8000",
        api_key="secret",
        frame_queue_dir=tmp_path / "frames",
    )
    bundle = create_event_bundle(config.frame_queue_dir, "camera-a")
    frame_path = bundle.allocate_frame_path()
    frame_path.parent.mkdir(parents=True, exist_ok=True)
    frame_path.write_bytes(b"frame")
    bundle.record_frame(frame_path)
    bundle.mark_ready()
    heartbeat = _StubHeartbeat()

    class _Classification:
        retryable = False
        terminal = True
        reason = "HTTP 400: invalid upload payload"

    class _Attempt:
        success = False
        classification = _Classification()

    monkeypatch.setattr(
        "piwatcher_camera.watcher.upload_event_result", lambda **_kwargs: _Attempt()
    )
    monkeypatch.setattr("piwatcher_camera.watcher.get_battery_level", lambda: 60)
    monkeypatch.setattr(
        "piwatcher_camera.watcher._should_manage_wifi", lambda *_args, **_kwargs: False
    )

    # Act
    _drain_pending_bundles(config, heartbeat, startup_time=0.0)
    reloaded = load_due_event_bundles(config.frame_queue_dir, lease_seconds=300)

    # Assert
    assert heartbeat.send_calls == []
    assert bundle.bundle_dir.exists() is True
    assert reloaded == []
    manifest_status = bundle.to_dict().get("status")
    assert manifest_status in {"pending", "uploading", "capturing", "failed"}
    refreshed = bundle.manifest_path.read_text(encoding="utf-8")
    assert '"status": "failed"' in refreshed


def test_given_retryable_failure_when_drain_pending_bundles_then_marks_pending_with_backoff(
    monkeypatch,
    tmp_path,
) -> None:
    # Arrange
    config = CameraConfig(
        camera_id="camera-a",
        server_url="http://pi5.local:8000",
        api_key="secret",
        frame_queue_dir=tmp_path / "frames",
        queue_retry_initial_seconds=30,
        queue_retry_max_seconds=120,
    )
    bundle = create_event_bundle(config.frame_queue_dir, "camera-a")
    frame_path = bundle.allocate_frame_path()
    frame_path.parent.mkdir(parents=True, exist_ok=True)
    frame_path.write_bytes(b"frame")
    bundle.record_frame(frame_path)
    bundle.mark_ready()
    heartbeat = _StubHeartbeat()

    class _Classification:
        retryable = True
        terminal = False
        reason = "HTTP 503: transient server/network backpressure"

    class _Attempt:
        success = False
        classification = _Classification()

    monkeypatch.setattr(
        "piwatcher_camera.watcher.upload_event_result", lambda **_kwargs: _Attempt()
    )
    monkeypatch.setattr("piwatcher_camera.watcher.get_battery_level", lambda: 60)
    monkeypatch.setattr(
        "piwatcher_camera.watcher._should_manage_wifi", lambda *_args, **_kwargs: False
    )

    # Act
    _drain_pending_bundles(config, heartbeat, startup_time=0.0)
    refreshed_manifest = bundle.manifest_path.read_text(encoding="utf-8")

    # Assert
    assert heartbeat.send_calls == []
    assert '"status": "pending"' in refreshed_manifest
    assert "HTTP 503: transient server/network backpressure" in refreshed_manifest
    assert '"next_attempt_at": ' in refreshed_manifest


def test_given_zero_drain_limit_when_drain_pending_bundles_then_skips_upload(
    monkeypatch, tmp_path
) -> None:
    # Arrange
    config = CameraConfig(
        camera_id="camera-a",
        server_url="http://pi5.local:8000",
        api_key="secret",
        frame_queue_dir=tmp_path / "frames",
        queue_drain_max_events=0,
    )
    heartbeat = _StubHeartbeat()
    called = {"uploaded": False}

    def fake_upload(**_kwargs):
        called["uploaded"] = True
        return None

    monkeypatch.setattr("piwatcher_camera.watcher.upload_event_result", fake_upload)

    # Act
    _drain_pending_bundles(config, heartbeat, startup_time=0.0)

    # Assert
    assert called["uploaded"] is False


def test_given_retry_attempt_count_when_retry_delay_seconds_then_caps_exponential_backoff() -> None:
    # Arrange
    config = CameraConfig(
        camera_id="camera-a",
        server_url="http://pi5.local:8000",
        api_key="secret",
        queue_retry_initial_seconds=30,
        queue_retry_max_seconds=90,
    )

    # Act
    delay_first = _retry_delay_seconds(config, attempt_count=1)
    delay_second = _retry_delay_seconds(config, attempt_count=2)
    delay_third = _retry_delay_seconds(config, attempt_count=3)

    # Assert
    assert delay_first == 30
    assert delay_second == 60
    assert delay_third == 90
