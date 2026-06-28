from piwatcher_camera.config import CameraConfig
from piwatcher_camera.watcher import _should_manage_wifi


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
