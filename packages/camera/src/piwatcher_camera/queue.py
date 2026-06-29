"""Durable camera queue helpers for event bundles and legacy backlog files."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

EVENT_SCHEMA_VERSION = 1
_EVENT_MANIFEST_FILENAME = "event.json"
_EVENT_ROOT_DIRNAME = "events"
_LEGACY_ROOT_DIRNAME = "legacy"

STATUS_PENDING = "pending"
STATUS_UPLOADING = "uploading"
STATUS_UPLOADED = "uploaded"
STATUS_FAILED = "failed"


@dataclass(frozen=True)
class QueueCounts:
    """Active queue counts used for heartbeat telemetry."""

    queued_frames: int
    queued_events: int


@dataclass(frozen=True)
class LegacyBacklogInventory:
    """Summary statistics for loose legacy JPEG backlog files."""

    legacy_file_count: int
    total_bytes: int
    oldest_mtime: datetime | None
    newest_mtime: datetime | None
    candidate_action: str


@dataclass(frozen=True)
class LegacyBacklogAction:
    """Result of a legacy backlog file operation."""

    action: str
    affected_file_count: int
    destination: Path | None = None


class EventBundle:
    """Durable event bundle backed by an atomic manifest."""

    def __init__(self, frame_queue_dir: Path, bundle_dir: Path, manifest: dict[str, Any]) -> None:
        self.frame_queue_dir = frame_queue_dir
        self.bundle_dir = bundle_dir
        self._manifest = manifest

    @property
    def manifest_path(self) -> Path:
        """Path to the manifest JSON file."""
        return self.bundle_dir / _EVENT_MANIFEST_FILENAME

    @property
    def event_id(self) -> str:
        """Stable camera-local event identifier."""
        return str(self._manifest["event_id"])

    @property
    def camera_id(self) -> str:
        """Camera identifier stored in the manifest."""
        return str(self._manifest["camera_id"])

    @property
    def event_start(self) -> datetime:
        """Event start timestamp."""
        parsed = _parse_datetime(self._manifest.get("event_start"))
        if parsed is None:
            raise ValueError("event_start is missing")
        return parsed

    @property
    def event_end(self) -> datetime | None:
        """Optional event end timestamp."""
        return _parse_datetime(self._manifest.get("event_end"))

    @property
    def status(self) -> str:
        """Manifest status value."""
        return str(self._manifest.get("status", "unknown"))

    @property
    def attempt_count(self) -> int:
        """Number of upload attempts made for this bundle."""
        value = self._manifest.get("attempt_count", 0)
        return value if isinstance(value, int) and value >= 0 else 0

    @property
    def next_attempt_at(self) -> datetime | None:
        """Time at which this bundle becomes eligible for retry."""
        return _parse_datetime(self._manifest.get("next_attempt_at"))

    @property
    def last_attempt_at(self) -> datetime | None:
        """Time of the most recent upload attempt."""
        return _parse_datetime(self._manifest.get("last_attempt_at"))

    @property
    def upload_started_at(self) -> datetime | None:
        """Time at which uploading state was entered."""
        return _parse_datetime(self._manifest.get("upload_started_at"))

    @property
    def last_error(self) -> str | None:
        """Most recent upload error message, if any."""
        value = self._manifest.get("last_error")
        return value if isinstance(value, str) and value else None

    @property
    def frame_count(self) -> int:
        """Number of frames recorded in the manifest."""
        frames = self._manifest.get("frames", [])
        return len(frames) if isinstance(frames, list) else 0

    @property
    def created_at(self) -> datetime:
        """Manifest creation timestamp."""
        parsed = _parse_datetime(self._manifest.get("created_at"))
        if parsed is None:
            raise ValueError("created_at is missing")
        return parsed

    @property
    def updated_at(self) -> datetime:
        """Manifest last update timestamp."""
        parsed = _parse_datetime(self._manifest.get("updated_at"))
        if parsed is None:
            raise ValueError("updated_at is missing")
        return parsed

    def to_dict(self) -> dict[str, Any]:
        """Return a shallow copy of the manifest payload."""
        return dict(self._manifest)

    def allocate_frame_path(self) -> Path:
        """Return the next normalized frame path in this bundle."""
        sequence_num = self.frame_count
        while True:
            path = self.bundle_dir / f"frame_{sequence_num:04d}.jpg"
            if not path.exists():
                return path
            sequence_num += 1

    def record_frame(self, frame_path: Path, captured_at: datetime | None = None) -> None:
        """Append a frame entry and persist the manifest atomically."""
        frame_name = frame_path.name
        sequence_num = self.frame_count
        frames = self._manifest.setdefault("frames", [])
        if not isinstance(frames, list):
            raise ValueError("manifest frames must be a list")
        frames.append(
            {
                "sequence_num": sequence_num,
                "file_name": frame_name,
                "captured_at": _format_datetime(captured_at or _utc_now()),
            }
        )
        self._manifest["updated_at"] = _format_datetime(_utc_now())
        self._write_manifest()

    def mark_ready(self, event_end: datetime | None = None) -> None:
        """Mark this bundle as ready for upload."""
        self._manifest["status"] = STATUS_PENDING
        if event_end is not None:
            self._manifest["event_end"] = _format_datetime(event_end)
        self._manifest["next_attempt_at"] = _format_datetime(_utc_now())
        self._manifest["last_error"] = None
        self._manifest["upload_started_at"] = None
        self._manifest["updated_at"] = _format_datetime(_utc_now())
        self._write_manifest()

    def mark_uploading(self, *, now: datetime | None = None) -> None:
        """Mark this bundle as currently uploading and bump attempt metadata."""
        current = now or _utc_now()
        self._manifest["status"] = STATUS_UPLOADING
        self._manifest["attempt_count"] = self.attempt_count + 1
        now_text = _format_datetime(current)
        self._manifest["last_attempt_at"] = now_text
        self._manifest["upload_started_at"] = now_text
        self._manifest["updated_at"] = now_text
        self._write_manifest()

    def mark_uploaded(self, *, now: datetime | None = None) -> None:
        """Mark this bundle as uploaded successfully."""
        current = now or _utc_now()
        now_text = _format_datetime(current)
        self._manifest["status"] = STATUS_UPLOADED
        self._manifest["next_attempt_at"] = None
        self._manifest["last_error"] = None
        self._manifest["upload_started_at"] = None
        self._manifest["updated_at"] = now_text
        self._write_manifest()

    def mark_retryable_failure(
        self,
        *,
        error_message: str,
        retry_after_seconds: int,
        now: datetime | None = None,
    ) -> None:
        """Record a retryable failure and schedule the next attempt."""
        current = now or _utc_now()
        self._manifest["status"] = STATUS_PENDING
        self._manifest["last_error"] = error_message
        self._manifest["next_attempt_at"] = _format_datetime(
            current + timedelta(seconds=max(0, retry_after_seconds))
        )
        self._manifest["upload_started_at"] = None
        self._manifest["updated_at"] = _format_datetime(current)
        self._write_manifest()

    def mark_terminal_failure(
        self,
        *,
        error_message: str,
        now: datetime | None = None,
    ) -> None:
        """Record a terminal failure that requires operator intervention."""
        current = now or _utc_now()
        self._manifest["status"] = STATUS_FAILED
        self._manifest["last_error"] = error_message
        self._manifest["next_attempt_at"] = None
        self._manifest["upload_started_at"] = None
        self._manifest["updated_at"] = _format_datetime(current)
        self._write_manifest()

    def maybe_recover_stale_upload(
        self,
        *,
        lease_seconds: int,
        now: datetime | None = None,
    ) -> bool:
        """Return stale uploading bundles to pending when lease timeout expires."""
        if self.status != STATUS_UPLOADING:
            return False

        upload_started_at = self.upload_started_at or self.last_attempt_at
        if upload_started_at is None:
            self._manifest["status"] = STATUS_PENDING
            self._manifest["next_attempt_at"] = _format_datetime(now or _utc_now())
            self._manifest["upload_started_at"] = None
            self._manifest["updated_at"] = _format_datetime(now or _utc_now())
            self._write_manifest()
            return True

        current = now or _utc_now()
        elapsed_seconds = (current - upload_started_at).total_seconds()
        if elapsed_seconds < max(0, lease_seconds):
            return False

        self._manifest["status"] = STATUS_PENDING
        self._manifest["next_attempt_at"] = _format_datetime(current)
        self._manifest["upload_started_at"] = None
        self._manifest["updated_at"] = _format_datetime(current)
        self._write_manifest()
        return True

    def is_due(self, *, now: datetime | None = None) -> bool:
        """Return whether this bundle is eligible to upload now."""
        if self.status != STATUS_PENDING:
            return False

        due_at = self.next_attempt_at
        if due_at is None:
            return True

        current = now or _utc_now()
        return due_at <= current

    def frame_paths(self) -> list[Path]:
        """Return ordered frame paths from the manifest."""
        frames = self._manifest.get("frames", [])
        if not isinstance(frames, list):
            return []
        ordered = sorted(
            (
                frame
                for frame in frames
                if isinstance(frame, dict)
                and isinstance(frame.get("sequence_num"), int)
                and isinstance(frame.get("file_name"), str)
            ),
            key=lambda item: int(item["sequence_num"]),
        )
        return [self.bundle_dir / str(frame["file_name"]) for frame in ordered]

    def delete(self) -> None:
        """Delete the entire bundle directory."""
        shutil.rmtree(self.bundle_dir, ignore_errors=True)

    def _write_manifest(self) -> None:
        _write_json_atomic(self.manifest_path, self._manifest)


def create_event_bundle(
    frame_queue_dir: Path,
    camera_id: str,
    event_start: datetime | None = None,
) -> EventBundle:
    """Create a new durable event bundle and initial manifest."""
    started_at = event_start or _utc_now()
    event_id = _build_event_id(camera_id, started_at)
    bundle_dir = _build_bundle_dir(frame_queue_dir, camera_id, started_at, event_id)
    bundle_dir.mkdir(parents=True, exist_ok=False)

    now_text = _format_datetime(_utc_now())
    manifest: dict[str, Any] = {
        "schema_version": EVENT_SCHEMA_VERSION,
        "event_id": event_id,
        "camera_id": camera_id,
        "event_start": _format_datetime(started_at),
        "event_end": None,
        "status": "capturing",
        "attempt_count": 0,
        "last_attempt_at": None,
        "next_attempt_at": None,
        "last_error": None,
        "upload_started_at": None,
        "frames": [],
        "created_at": now_text,
        "updated_at": now_text,
    }
    bundle = EventBundle(frame_queue_dir=frame_queue_dir, bundle_dir=bundle_dir, manifest=manifest)
    _write_json_atomic(bundle.manifest_path, manifest)
    return bundle


def load_ready_event_bundles(frame_queue_dir: Path) -> list[EventBundle]:
    """Load ready durable bundles sorted by creation time."""
    bundles = [
        bundle
        for bundle in _load_all_event_bundles(frame_queue_dir)
        if bundle.status in {"ready", STATUS_PENDING}
    ]
    bundles.sort(key=lambda bundle: (bundle.created_at, bundle.event_id))
    return bundles


def load_due_event_bundles(
    frame_queue_dir: Path,
    *,
    lease_seconds: int,
    now: datetime | None = None,
) -> list[EventBundle]:
    """Load pending bundles eligible for upload, recovering stale leases first."""
    current = now or _utc_now()
    bundles: list[EventBundle] = []
    for bundle in _load_all_event_bundles(frame_queue_dir):
        if bundle.status == STATUS_UPLOADING:
            bundle.maybe_recover_stale_upload(lease_seconds=lease_seconds, now=current)
        if bundle.is_due(now=current):
            bundles.append(bundle)

    bundles.sort(key=lambda bundle: (bundle.created_at, bundle.event_id))
    return bundles


def get_active_queue_counts(frame_queue_dir: Path | None) -> QueueCounts | None:
    """Count active queued frames and durable events."""
    if frame_queue_dir is None or not frame_queue_dir.exists():
        return None

    legacy_frames = len(_legacy_jpeg_files(frame_queue_dir))
    bundle_frames = 0
    bundle_events = 0
    for bundle in _load_all_event_bundles(frame_queue_dir):
        if bundle.status == "uploaded":
            continue
        bundle_events += 1
        bundle_frames += bundle.frame_count

    return QueueCounts(queued_frames=legacy_frames + bundle_frames, queued_events=bundle_events)


def inventory_legacy_backlog(frame_queue_dir: Path) -> LegacyBacklogInventory:
    """Inspect loose top-level legacy JPEG files without modifying them."""
    files = _legacy_jpeg_files(frame_queue_dir)
    if not files:
        return LegacyBacklogInventory(
            legacy_file_count=0,
            total_bytes=0,
            oldest_mtime=None,
            newest_mtime=None,
            candidate_action="none",
        )

    mtimes = [datetime.fromtimestamp(path.stat().st_mtime, tz=UTC) for path in files]
    total_bytes = sum(path.stat().st_size for path in files)
    return LegacyBacklogInventory(
        legacy_file_count=len(files),
        total_bytes=total_bytes,
        oldest_mtime=min(mtimes),
        newest_mtime=max(mtimes),
        candidate_action="quarantine",
    )


def quarantine_legacy_backlog(
    frame_queue_dir: Path,
    *,
    now: datetime | None = None,
) -> LegacyBacklogAction:
    """Move loose top-level legacy JPEG files into a timestamped quarantine directory."""
    files = _legacy_jpeg_files(frame_queue_dir)
    if not files:
        return LegacyBacklogAction(action="quarantine", affected_file_count=0, destination=None)

    timestamp = (now or _utc_now()).strftime("%Y%m%dT%H%M%SZ")
    destination = frame_queue_dir / _LEGACY_ROOT_DIRNAME / timestamp
    destination.mkdir(parents=True, exist_ok=False)

    moved = 0
    for path in files:
        target = _unique_destination(destination, path.name)
        path.rename(target)
        moved += 1

    return LegacyBacklogAction(
        action="quarantine", affected_file_count=moved, destination=destination
    )


def delete_legacy_backlog(
    frame_queue_dir: Path,
    *,
    confirm_delete: bool = False,
) -> LegacyBacklogAction:
    """Delete loose top-level legacy JPEG files when explicitly confirmed."""
    if not confirm_delete:
        raise ValueError("confirm_delete must be True to delete legacy backlog files")

    deleted = 0
    for path in _legacy_jpeg_files(frame_queue_dir):
        path.unlink(missing_ok=True)
        deleted += 1

    return LegacyBacklogAction(action="delete", affected_file_count=deleted, destination=None)


def _load_all_event_bundles(frame_queue_dir: Path) -> list[EventBundle]:
    event_root = frame_queue_dir / _EVENT_ROOT_DIRNAME
    if not event_root.exists():
        return []

    bundles: list[EventBundle] = []
    for manifest_path in event_root.rglob(_EVENT_MANIFEST_FILENAME):
        if not manifest_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        bundle_dir = manifest_path.parent
        bundles.append(
            EventBundle(frame_queue_dir=frame_queue_dir, bundle_dir=bundle_dir, manifest=manifest)
        )
    return bundles


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.stem}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            temp_path = Path(handle.name)
        os.replace(temp_path, path)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink(missing_ok=True)


def _build_bundle_dir(
    frame_queue_dir: Path,
    camera_id: str,
    event_start: datetime,
    event_id: str,
) -> Path:
    started = event_start.astimezone(UTC)
    camera_slug = _slugify(camera_id)
    candidate = (
        frame_queue_dir
        / _EVENT_ROOT_DIRNAME
        / started.strftime("%Y")
        / started.strftime("%m")
        / started.strftime("%d")
        / camera_slug
        / event_id
    )

    if not candidate.exists():
        return candidate

    suffix = 1
    while True:
        alternate = candidate.parent / f"{event_id}-{suffix:02d}"
        if not alternate.exists():
            return alternate
        suffix += 1


def _build_event_id(camera_id: str, event_start: datetime) -> str:
    started = event_start.astimezone(UTC)
    return f"{started.strftime('%Y%m%dT%H%M%S%fZ')}-{_slugify(camera_id)}"


def _legacy_jpeg_files(frame_queue_dir: Path) -> list[Path]:
    if not frame_queue_dir.exists():
        return []
    return sorted(path for path in frame_queue_dir.glob("*.jpg") if path.is_file())


def _unique_destination(directory: Path, file_name: str) -> Path:
    candidate = directory / file_name
    if not candidate.exists():
        return candidate

    stem = Path(file_name).stem
    suffix = Path(file_name).suffix
    index = 1
    while True:
        alternate = directory / f"{stem}_{index:02d}{suffix}"
        if not alternate.exists():
            return alternate
        index += 1


def _slugify(value: str) -> str:
    cleaned = "".join(char if char.isalnum() else "-" for char in value.strip().lower())
    return cleaned.strip("-") or "camera"


def _format_datetime(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        if value.endswith("Z"):
            return datetime.fromisoformat(f"{value[:-1]}+00:00")
        return None


def _utc_now() -> datetime:
    return datetime.now(UTC)
