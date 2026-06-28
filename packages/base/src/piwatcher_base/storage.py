"""Frame file storage organized by capture date."""

from datetime import datetime
from pathlib import Path

from fastapi import UploadFile


async def store_frames(
    frames: list[UploadFile],
    camera_id: str,
    event_start: datetime,
    storage_path: Path,
) -> list[Path]:
    """Store uploaded frames in a date/camera/event hierarchy."""

    event_dir = (
        storage_path / event_start.strftime("%Y/%m/%d") / camera_id / event_start.strftime("%H%M%S")
    )
    event_dir.mkdir(parents=True, exist_ok=True)

    stored_paths: list[Path] = []
    for index, frame in enumerate(frames):
        destination = event_dir / f"frame_{index:04d}.jpg"
        destination.write_bytes(await frame.read())
        stored_paths.append(destination)

    return stored_paths
