"""WiFi management and frame batch upload to the base station."""

import logging
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

import requests

logger = logging.getLogger(__name__)


def wifi_on() -> None:
    """Enable WiFi radio via rfkill and wait briefly for association."""
    subprocess.run(["sudo", "rfkill", "unblock", "wifi"], check=True)
    time.sleep(5)


def wifi_off() -> None:
    """Disable WiFi radio via rfkill."""
    subprocess.run(["sudo", "rfkill", "block", "wifi"], check=True)


def upload_event(
    frames: list[Path],
    camera_id: str,
    server_url: str,
    api_key: str,
    battery_pct: int | None = None,
    event_start: datetime | None = None,
    timeout: float = 60.0,
) -> bool:
    """Upload captured frames as a multipart POST to the base station.

    Returns True on success and False on failure so frame files can be retried.
    """
    if not frames:
        return False

    started_at = event_start or datetime.now(UTC)
    data: dict[str, str] = {
        "camera_id": camera_id,
        "event_start": started_at.isoformat(),
    }
    if battery_pct is not None:
        data["battery_pct"] = str(battery_pct)

    url = f"{server_url.rstrip('/')}/api/events"
    opened_files = []
    try:
        files = []
        for index, frame in enumerate(frames):
            handle = frame.open("rb")
            opened_files.append(handle)
            files.append(("frames", (f"frame_{index:04d}.jpg", handle, "image/jpeg")))

        response = requests.post(
            url,
            data=data,
            files=files,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )
        response.raise_for_status()
    except (OSError, requests.RequestException) as exc:
        logger.warning("event upload failed: %s", exc)
        return False
    finally:
        for handle in opened_files:
            handle.close()

    return True
