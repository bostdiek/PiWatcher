"""WiFi management and frame batch upload to the base station."""

import logging
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import requests

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UploadErrorClassification:
    """Normalized classification for upload failures."""

    retryable: bool
    terminal: bool
    reason: str


@dataclass(frozen=True)
class UploadAttemptResult:
    """Outcome of a frame upload request."""

    success: bool
    classification: UploadErrorClassification | None = None


def classify_upload_error(error: Exception) -> UploadErrorClassification:
    """Classify upload failures into retryable vs terminal behavior."""
    if isinstance(error, requests.HTTPError):
        response = error.response
        status_code = response.status_code if response is not None else None
        if status_code in {401, 403}:
            return UploadErrorClassification(
                retryable=False,
                terminal=True,
                reason=f"HTTP {status_code}: authorization failed",
            )
        if status_code in {408, 429} or (status_code is not None and 500 <= status_code <= 599):
            return UploadErrorClassification(
                retryable=True,
                terminal=False,
                reason=f"HTTP {status_code}: transient server/network backpressure",
            )
        if status_code is not None and 400 <= status_code <= 499:
            return UploadErrorClassification(
                retryable=False,
                terminal=True,
                reason=f"HTTP {status_code}: invalid upload payload",
            )
        return UploadErrorClassification(
            retryable=True,
            terminal=False,
            reason=f"HTTP {status_code}: upload failed",
        )

    if isinstance(
        error,
        (
            requests.ConnectionError,
            requests.Timeout,
            requests.RequestException,
            OSError,
        ),
    ):
        return UploadErrorClassification(
            retryable=True,
            terminal=False,
            reason=str(error),
        )

    return UploadErrorClassification(
        retryable=False,
        terminal=True,
        reason=str(error),
    )


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
    event_end: datetime | None = None,
    camera_event_id: str | None = None,
    timeout: float = 60.0,
) -> bool:
    """Upload captured frames as a multipart POST to the base station.

    Returns True on success and False on failure so frame files can be retried.
    """
    result = upload_event_result(
        frames=frames,
        camera_id=camera_id,
        server_url=server_url,
        api_key=api_key,
        battery_pct=battery_pct,
        event_start=event_start,
        event_end=event_end,
        camera_event_id=camera_event_id,
        timeout=timeout,
    )
    return result.success


def upload_event_result(
    frames: list[Path],
    camera_id: str,
    server_url: str,
    api_key: str,
    battery_pct: int | None = None,
    event_start: datetime | None = None,
    event_end: datetime | None = None,
    camera_event_id: str | None = None,
    timeout: float = 60.0,
) -> UploadAttemptResult:
    """Upload captured frames and return a classified outcome."""
    if not frames:
        return UploadAttemptResult(
            success=False,
            classification=UploadErrorClassification(
                retryable=False,
                terminal=True,
                reason="no frames provided",
            ),
        )

    started_at = event_start or datetime.now(UTC)
    data: dict[str, str] = {
        "camera_id": camera_id,
        "event_start": started_at.isoformat(),
    }
    if event_end is not None:
        data["event_end"] = event_end.astimezone(UTC).isoformat()
    if camera_event_id:
        data["camera_event_id"] = camera_event_id
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
        classification = classify_upload_error(exc)
        logger.warning("event upload failed (%s): %s", classification.reason, exc)
        return UploadAttemptResult(success=False, classification=classification)
    finally:
        for handle in opened_files:
            handle.close()

    return UploadAttemptResult(success=True, classification=None)
