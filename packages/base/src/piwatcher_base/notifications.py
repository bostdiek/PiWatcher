"""Push notifications via ntfy.sh."""

import logging
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)


async def notify_detection(
    label: str,
    confidence: float,
    camera_id: str,
    thumbnail_path: Path | None = None,
    ntfy_url: str = "https://ntfy.sh",
    ntfy_topic: str = "piwatcher",
) -> None:
    """Send a best-effort push notification for a detection."""

    headers = {"Title": f"{label} detected ({confidence:.0%})", "Tags": "camera"}
    message = f"{label} spotted on {camera_id}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            if thumbnail_path and thumbnail_path.exists():
                headers["Filename"] = thumbnail_path.name
                await client.post(
                    f"{ntfy_url.rstrip('/')}/{ntfy_topic}",
                    content=thumbnail_path.read_bytes(),
                    headers=headers,
                )
            else:
                await client.post(
                    f"{ntfy_url.rstrip('/')}/{ntfy_topic}",
                    content=message,
                    headers=headers,
                )
    except httpx.HTTPError:
        logger.exception("Failed to send ntfy notification")
