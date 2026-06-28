"""Periodic heartbeat reporting to the base station."""

import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import requests

from .transfer import wifi_off, wifi_on


class HeartbeatManager:
    """Track and send camera health heartbeats."""

    def __init__(
        self,
        interval: int,
        server_url: str,
        api_key: str,
        camera_id: str,
        *,
        frame_queue_dir: Path | None = None,
        wifi_power_save: bool | None = None,
    ) -> None:
        self.interval = interval
        self.server_url = server_url
        self.api_key = api_key
        self.camera_id = camera_id
        self.frame_queue_dir = frame_queue_dir
        self.wifi_power_save = wifi_power_save
        self.last_sent: float = 0.0
        self.started_at: float = time.monotonic()

    def is_due(self, now: float | None = None) -> bool:
        """Check if the heartbeat interval has elapsed."""
        current_time = time.time() if now is None else now
        return current_time - self.last_sent >= self.interval

    def send(self, battery_pct: int | None = None, timeout: float = 15.0) -> bool:
        """Send a heartbeat while WiFi is active."""
        self.last_sent = time.time()
        payload: dict[str, Any] = {
            "camera_id": self.camera_id,
            "uptime_seconds": int(time.monotonic() - self.started_at),
        }
        if battery_pct is not None:
            payload["battery_pct"] = battery_pct
        payload.update(collect_telemetry(self.frame_queue_dir, self.wifi_power_save))

        try:
            response = requests.post(
                f"{self.server_url.rstrip('/')}/api/heartbeat",
                data=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=timeout,
            )
            response.raise_for_status()
        except requests.RequestException:
            return False

        self.piggyback(battery_pct)
        return True

    def send_standalone(
        self,
        battery_pct: int | None = None,
        *,
        manage_wifi: bool = True,
    ) -> bool:
        """Turn WiFi on for a standalone heartbeat and turn it back off."""
        if manage_wifi:
            wifi_on()
        try:
            return self.send(battery_pct)
        finally:
            if manage_wifi:
                wifi_off()

    def piggyback(self, battery_pct: int | None = None) -> None:
        """Record that a heartbeat was sent alongside another upload."""
        _ = battery_pct
        self.last_sent = time.time()


def collect_telemetry(
    frame_queue_dir: Path | None,
    wifi_power_save: bool | None,
) -> dict[str, int | float | str | bool]:
    """Collect lightweight camera telemetry for dashboard health trends."""

    telemetry: dict[str, int | float | str | bool] = {
        "software_version": "0.1.0",
    }
    if wifi_power_save is not None:
        telemetry["wifi_power_save"] = wifi_power_save

    queue_depth = _queue_depth(frame_queue_dir)
    if queue_depth is not None:
        telemetry["queue_depth"] = queue_depth

    disk_free_mb = _disk_free_mb(frame_queue_dir)
    if disk_free_mb is not None:
        telemetry["disk_free_mb"] = disk_free_mb

    cpu_temp_c = _cpu_temp_c()
    if cpu_temp_c is not None:
        telemetry["cpu_temp_c"] = cpu_temp_c

    wifi_rssi_dbm = _wifi_rssi_dbm()
    if wifi_rssi_dbm is not None:
        telemetry["wifi_rssi_dbm"] = wifi_rssi_dbm

    return telemetry


def _queue_depth(frame_queue_dir: Path | None) -> int | None:
    if frame_queue_dir is None or not frame_queue_dir.exists():
        return None
    return sum(1 for path in frame_queue_dir.glob("*.jpg") if path.is_file())


def _disk_free_mb(frame_queue_dir: Path | None) -> int | None:
    if frame_queue_dir is None:
        return None
    try:
        frame_queue_dir.mkdir(parents=True, exist_ok=True)
        usage = shutil.disk_usage(frame_queue_dir)
    except OSError:
        return None
    return usage.free // (1024 * 1024)


def _cpu_temp_c() -> float | None:
    temp_path = Path("/sys/class/thermal/thermal_zone0/temp")
    try:
        return int(temp_path.read_text(encoding="utf-8").strip()) / 1000.0
    except (FileNotFoundError, OSError, ValueError):
        return None


def _wifi_rssi_dbm() -> int | None:
    try:
        result = subprocess.run(
            ["iw", "dev", "wlan0", "link"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None

    for line in result.stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("signal:"):
            parts = stripped.split()
            if len(parts) >= 2:
                try:
                    return int(float(parts[1]))
                except ValueError:
                    return None
    return None
