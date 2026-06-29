import pytest

from piwatcher_camera.config import ConfigError, load_config


def test_given_required_env_when_load_config_then_returns_values(monkeypatch, tmp_path) -> None:
    # Arrange
    frame_queue_dir = tmp_path / "frames"
    monkeypatch.setenv("CAMERA_ID", "feeder-cam")
    monkeypatch.setenv("SERVER_URL", "http://pi5.local:8000")
    monkeypatch.setenv("PIWATCHER_API_KEY", "secret")
    monkeypatch.setenv("FRAME_QUEUE_DIR", str(frame_queue_dir))

    # Act
    config = load_config()

    # Assert
    assert config.camera_id == "feeder-cam"
    assert config.frame_queue_dir == frame_queue_dir
    assert frame_queue_dir.exists()


def test_given_only_required_env_when_load_config_then_uses_defaults(monkeypatch, tmp_path) -> None:
    # Arrange
    monkeypatch.setenv("CAMERA_ID", "feeder-cam")
    monkeypatch.setenv("SERVER_URL", "http://pi5.local:8000")
    monkeypatch.setenv("PIWATCHER_API_KEY", "secret")
    monkeypatch.setenv("FRAME_QUEUE_DIR", str(tmp_path / "frames"))

    # Act
    config = load_config()

    # Assert
    assert config.motion_threshold == 7.0
    assert config.capture_min_duration == 10.0
    assert config.heartbeat_interval == 900
    assert config.wifi_power_save is True
    assert config.wifi_startup_grace_seconds == 600
    assert config.queue_drain_max_events == 2
    assert config.queue_drain_max_seconds == 15
    assert config.queue_retry_initial_seconds == 30
    assert config.queue_retry_max_seconds == 3600
    assert config.queue_upload_lease_seconds == 300


def test_given_wifi_power_save_env_when_load_config_then_parses_boolean(
    monkeypatch,
    tmp_path,
) -> None:
    # Arrange
    monkeypatch.setenv("CAMERA_ID", "feeder-cam")
    monkeypatch.setenv("SERVER_URL", "http://pi5.local:8000")
    monkeypatch.setenv("PIWATCHER_API_KEY", "secret")
    monkeypatch.setenv("FRAME_QUEUE_DIR", str(tmp_path / "frames"))
    monkeypatch.setenv("WIFI_POWER_SAVE", "false")

    # Act
    config = load_config()

    # Assert
    assert config.wifi_power_save is False


def test_given_missing_required_env_when_load_config_then_raises(monkeypatch) -> None:
    # Arrange
    monkeypatch.delenv("CAMERA_ID", raising=False)
    monkeypatch.delenv("SERVER_URL", raising=False)
    monkeypatch.delenv("PIWATCHER_API_KEY", raising=False)

    # Act & Assert
    with pytest.raises(ConfigError, match="CAMERA_ID"):
        load_config()


def test_given_queue_drain_env_when_load_config_then_parses_queue_drain_values(
    monkeypatch,
    tmp_path,
) -> None:
    # Arrange
    monkeypatch.setenv("CAMERA_ID", "feeder-cam")
    monkeypatch.setenv("SERVER_URL", "http://pi5.local:8000")
    monkeypatch.setenv("PIWATCHER_API_KEY", "secret")
    monkeypatch.setenv("FRAME_QUEUE_DIR", str(tmp_path / "frames"))
    monkeypatch.setenv("QUEUE_DRAIN_MAX_EVENTS", "5")
    monkeypatch.setenv("QUEUE_DRAIN_MAX_SECONDS", "45")
    monkeypatch.setenv("QUEUE_RETRY_INITIAL_SECONDS", "10")
    monkeypatch.setenv("QUEUE_RETRY_MAX_SECONDS", "900")
    monkeypatch.setenv("QUEUE_UPLOAD_LEASE_SECONDS", "120")

    # Act
    config = load_config()

    # Assert
    assert config.queue_drain_max_events == 5
    assert config.queue_drain_max_seconds == 45
    assert config.queue_retry_initial_seconds == 10
    assert config.queue_retry_max_seconds == 900
    assert config.queue_upload_lease_seconds == 120
