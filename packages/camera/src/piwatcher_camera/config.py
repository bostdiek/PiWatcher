"""Camera configuration from environment variables."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


class ConfigError(ValueError):
    """Raised when required camera configuration is missing or invalid."""


@dataclass(frozen=True)
class CameraConfig:
    """Runtime settings for a PiWatcher camera."""

    camera_id: str
    server_url: str
    api_key: str
    motion_threshold: float = 7.0
    min_changed_pct: float = 2.0
    capture_fps: float = 2.0
    capture_min_duration: float = 10.0
    cooldown_seconds: float = 5.0
    heartbeat_interval: int = 900
    lores_width: int = 160
    lores_height: int = 120
    main_width: int = 1024
    main_height: int = 1024
    frame_queue_dir: Path = Path("/tmp/piwatcher/frames")
    wifi_power_save: bool = True
    wifi_startup_grace_seconds: int = 600


def load_config(env_file: Path | str | None = None) -> CameraConfig:
    """Load camera config from an optional .env file and environment."""
    load_dotenv(dotenv_path=env_file)
    config = CameraConfig(
        camera_id=_required_env("CAMERA_ID"),
        server_url=_required_env("SERVER_URL"),
        api_key=_required_env("PIWATCHER_API_KEY"),
        motion_threshold=_float_env("MOTION_THRESHOLD", 7.0),
        min_changed_pct=_float_env("MIN_CHANGED_PCT", 2.0),
        capture_fps=_float_env("CAPTURE_FPS", 2.0),
        capture_min_duration=_float_env("CAPTURE_MIN_DURATION", 10.0),
        cooldown_seconds=_float_env("COOLDOWN_SECONDS", 5.0),
        heartbeat_interval=_int_env("HEARTBEAT_INTERVAL", 900),
        lores_width=_int_env("LORES_WIDTH", 160),
        lores_height=_int_env("LORES_HEIGHT", 120),
        main_width=_int_env("MAIN_WIDTH", 1024),
        main_height=_int_env("MAIN_HEIGHT", 1024),
        frame_queue_dir=Path(os.getenv("FRAME_QUEUE_DIR", "/tmp/piwatcher/frames")),
        wifi_power_save=_bool_env("WIFI_POWER_SAVE", True),
        wifi_startup_grace_seconds=_int_env("WIFI_STARTUP_GRACE_SECONDS", 600),
    )
    config.frame_queue_dir.mkdir(parents=True, exist_ok=True)
    return config


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise ConfigError(f"Missing required environment variable: {name}")
    return value


def _float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise ConfigError(f"Environment variable {name} must be a float") from exc


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ConfigError(f"Environment variable {name} must be an integer") from exc


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"Environment variable {name} must be a boolean")
