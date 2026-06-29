from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta

import pytest

from piwatcher_camera.queue import (
    LegacyBacklogAction,
    QueueCounts,
    create_event_bundle,
    delete_legacy_backlog,
    get_active_queue_counts,
    inventory_legacy_backlog,
    load_due_event_bundles,
    load_ready_event_bundles,
    quarantine_legacy_backlog,
)


def test_given_new_bundle_when_create_event_bundle_then_writes_initial_manifest(
    tmp_path,
) -> None:
    # Arrange
    frame_queue_dir = tmp_path / "frames"
    started = datetime(2026, 6, 28, 15, 34, 31, 123456, tzinfo=UTC)

    # Act
    bundle = create_event_bundle(frame_queue_dir, "feeder-cam", started)

    # Assert
    manifest = json.loads(bundle.manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    assert manifest["event_id"].startswith("20260628T153431123456Z-feeder-cam")
    assert manifest["camera_id"] == "feeder-cam"
    assert manifest["event_start"] == started.isoformat()
    assert manifest["event_end"] is None
    assert manifest["status"] == "capturing"
    assert manifest["frames"] == []
    assert "created_at" in manifest
    assert "updated_at" in manifest


def test_given_bundle_when_record_frames_then_uses_ordered_normalized_names(
    tmp_path,
) -> None:
    # Arrange
    bundle = create_event_bundle(tmp_path / "frames", "yard-cam")
    first_frame = bundle.allocate_frame_path()
    first_frame.write_bytes(b"a")
    second_frame = bundle.allocate_frame_path()
    second_frame.write_bytes(b"b")

    # Act
    bundle.record_frame(first_frame, captured_at=datetime(2026, 6, 28, 16, 0, 1, tzinfo=UTC))
    bundle.record_frame(second_frame, captured_at=datetime(2026, 6, 28, 16, 0, 2, tzinfo=UTC))

    # Assert
    manifest = json.loads(bundle.manifest_path.read_text(encoding="utf-8"))
    assert [frame["file_name"] for frame in manifest["frames"]] == [
        "frame_0000.jpg",
        "frame_0001.jpg",
    ]
    assert [frame["sequence_num"] for frame in manifest["frames"]] == [0, 1]
    assert bundle.frame_paths() == [first_frame, second_frame]


def test_given_bundle_when_mark_ready_then_available_for_ready_load(tmp_path) -> None:
    # Arrange
    frame_queue_dir = tmp_path / "frames"
    old_bundle = create_event_bundle(
        frame_queue_dir,
        "camera-a",
        datetime(2026, 6, 28, 10, 0, 0, tzinfo=UTC),
    )
    new_bundle = create_event_bundle(
        frame_queue_dir,
        "camera-a",
        datetime(2026, 6, 28, 11, 0, 0, tzinfo=UTC),
    )
    old_frame = old_bundle.allocate_frame_path()
    old_frame.write_bytes(b"old")
    old_bundle.record_frame(old_frame)
    new_frame = new_bundle.allocate_frame_path()
    new_frame.write_bytes(b"new")
    new_bundle.record_frame(new_frame)
    old_bundle.mark_ready(event_end=datetime(2026, 6, 28, 10, 1, 0, tzinfo=UTC))
    new_bundle.mark_ready(event_end=datetime(2026, 6, 28, 11, 1, 0, tzinfo=UTC))

    # Act
    loaded = load_ready_event_bundles(frame_queue_dir)

    # Assert
    assert [bundle.event_id for bundle in loaded] == [
        old_bundle.event_id,
        new_bundle.event_id,
    ]
    assert loaded[0].event_end == datetime(2026, 6, 28, 10, 1, 0, tzinfo=UTC)
    assert loaded[1].event_end == datetime(2026, 6, 28, 11, 1, 0, tzinfo=UTC)


def test_given_pending_bundle_when_load_due_event_bundles_then_returns_due_only(
    tmp_path,
) -> None:
    # Arrange
    frame_queue_dir = tmp_path / "frames"
    base_time = datetime.now(UTC)
    due_bundle = create_event_bundle(frame_queue_dir, "camera-a")
    due_frame = due_bundle.allocate_frame_path()
    due_frame.write_bytes(b"due")
    due_bundle.record_frame(due_frame)
    due_bundle.mark_ready()

    later_bundle = create_event_bundle(frame_queue_dir, "camera-a")
    later_frame = later_bundle.allocate_frame_path()
    later_frame.write_bytes(b"later")
    later_bundle.record_frame(later_frame)
    later_bundle.mark_ready()
    later_bundle.mark_retryable_failure(
        error_message="temporarily unavailable",
        retry_after_seconds=120,
        now=base_time,
    )

    # Act
    due = load_due_event_bundles(
        frame_queue_dir,
        lease_seconds=300,
        now=base_time + timedelta(seconds=1),
    )

    # Assert
    assert [bundle.event_id for bundle in due] == [due_bundle.event_id]


def test_given_stale_uploading_bundle_when_load_due_event_bundles_then_recovers_lease(
    tmp_path,
) -> None:
    # Arrange
    frame_queue_dir = tmp_path / "frames"
    bundle = create_event_bundle(frame_queue_dir, "camera-a")
    frame_path = bundle.allocate_frame_path()
    frame_path.write_bytes(b"frame")
    bundle.record_frame(frame_path)
    bundle.mark_ready()
    bundle.mark_uploading(now=datetime(2026, 6, 28, 16, 0, 0, tzinfo=UTC))

    # Act
    due = load_due_event_bundles(
        frame_queue_dir,
        lease_seconds=30,
        now=datetime(2026, 6, 28, 16, 1, 0, tzinfo=UTC),
    )

    # Assert
    assert [item.event_id for item in due] == [bundle.event_id]
    assert due[0].status == "pending"


def test_given_pending_bundle_when_mark_retryable_failure_then_persists_retry_state(
    tmp_path,
) -> None:
    # Arrange
    bundle = create_event_bundle(tmp_path / "frames", "camera-a")
    frame_path = bundle.allocate_frame_path()
    frame_path.write_bytes(b"frame")
    bundle.record_frame(frame_path)
    bundle.mark_ready()
    bundle.mark_uploading(now=datetime(2026, 6, 28, 16, 0, 0, tzinfo=UTC))

    # Act
    bundle.mark_retryable_failure(
        error_message="HTTP 503",
        retry_after_seconds=45,
        now=datetime(2026, 6, 28, 16, 0, 5, tzinfo=UTC),
    )

    # Assert
    assert bundle.status == "pending"
    assert bundle.attempt_count == 1
    assert bundle.last_error == "HTTP 503"
    assert bundle.next_attempt_at == datetime(2026, 6, 28, 16, 0, 50, tzinfo=UTC)


def test_given_uploading_bundle_without_start_time_when_recover_stale_then_becomes_pending(
    tmp_path,
) -> None:
    # Arrange
    bundle = create_event_bundle(tmp_path / "frames", "camera-a")
    manifest = bundle.to_dict()
    manifest["status"] = "uploading"
    manifest["last_attempt_at"] = None
    manifest["upload_started_at"] = None
    bundle.manifest_path.write_text(f"{json.dumps(manifest)}\n", encoding="utf-8")
    loaded = load_due_event_bundles(
        tmp_path / "frames",
        lease_seconds=300,
        now=datetime(2026, 6, 28, 16, 10, 0, tzinfo=UTC),
    )

    # Assert
    assert len(loaded) == 1
    assert loaded[0].status == "pending"


def test_given_legacy_and_bundle_frames_when_get_active_queue_counts_then_excludes_quarantined(
    tmp_path,
) -> None:
    # Arrange
    frame_queue_dir = tmp_path / "frames"
    frame_queue_dir.mkdir(parents=True)
    (frame_queue_dir / "legacy-a.jpg").write_bytes(b"a")
    (frame_queue_dir / "legacy-b.jpg").write_bytes(b"b")

    bundle = create_event_bundle(frame_queue_dir, "camera-a")
    frame_path = bundle.allocate_frame_path()
    frame_path.write_bytes(b"frame")
    bundle.record_frame(frame_path)
    bundle.mark_ready()

    quarantine_root = frame_queue_dir / "legacy" / "20260628T170000Z"
    quarantine_root.mkdir(parents=True)
    (quarantine_root / "old.jpg").write_bytes(b"ignore")

    # Act
    counts = get_active_queue_counts(frame_queue_dir)

    # Assert
    assert counts == QueueCounts(queued_frames=3, queued_events=1)


def test_given_uploaded_bundle_when_get_active_queue_counts_then_excludes_uploaded(
    tmp_path,
) -> None:
    # Arrange
    frame_queue_dir = tmp_path / "frames"
    bundle = create_event_bundle(frame_queue_dir, "camera-a")
    frame_path = bundle.allocate_frame_path()
    frame_path.write_bytes(b"frame")
    bundle.record_frame(frame_path)
    bundle.mark_ready()

    manifest = bundle.to_dict()
    manifest["status"] = "uploaded"
    bundle.manifest_path.write_text(f"{json.dumps(manifest)}\n", encoding="utf-8")

    # Act
    counts = get_active_queue_counts(frame_queue_dir)

    # Assert
    assert counts == QueueCounts(queued_frames=0, queued_events=0)


def test_given_bundle_when_delete_then_removes_directory(tmp_path) -> None:
    # Arrange
    bundle = create_event_bundle(tmp_path / "frames", "camera-a")

    # Act
    bundle.delete()

    # Assert
    assert bundle.bundle_dir.exists() is False


def test_given_legacy_files_when_inventory_then_returns_summary(tmp_path) -> None:
    # Arrange
    frame_queue_dir = tmp_path / "frames"
    frame_queue_dir.mkdir(parents=True)
    first = frame_queue_dir / "oldest.jpg"
    second = frame_queue_dir / "newest.jpg"
    first.write_bytes(b"abc")
    second.write_bytes(b"defg")

    first_mtime = datetime(2026, 6, 28, 1, 0, 0, tzinfo=UTC).timestamp()
    second_mtime = datetime(2026, 6, 28, 2, 0, 0, tzinfo=UTC).timestamp()

    # Act
    os.utime(first, (first_mtime, first_mtime))
    os.utime(second, (second_mtime, second_mtime))
    summary = inventory_legacy_backlog(frame_queue_dir)

    # Assert
    assert summary.legacy_file_count == 2
    assert summary.total_bytes == 7
    assert summary.oldest_mtime == datetime.fromtimestamp(first_mtime, tz=UTC)
    assert summary.newest_mtime == datetime.fromtimestamp(second_mtime, tz=UTC)
    assert summary.candidate_action == "quarantine"


def test_given_no_legacy_files_when_inventory_then_returns_none_action(
    tmp_path,
) -> None:
    # Arrange
    frame_queue_dir = tmp_path / "frames"
    frame_queue_dir.mkdir(parents=True)

    # Act
    summary = inventory_legacy_backlog(frame_queue_dir)

    # Assert
    assert summary.legacy_file_count == 0
    assert summary.total_bytes == 0
    assert summary.oldest_mtime is None
    assert summary.newest_mtime is None
    assert summary.candidate_action == "none"


def test_given_legacy_files_when_quarantine_then_moves_to_timestamp_directory(
    tmp_path,
) -> None:
    # Arrange
    frame_queue_dir = tmp_path / "frames"
    frame_queue_dir.mkdir(parents=True)
    (frame_queue_dir / "frame_a.jpg").write_bytes(b"a")
    (frame_queue_dir / "frame_b.jpg").write_bytes(b"b")

    # Act
    action = quarantine_legacy_backlog(
        frame_queue_dir,
        now=datetime(2026, 6, 28, 17, 0, 0, tzinfo=UTC),
    )

    # Assert
    assert action == LegacyBacklogAction(
        action="quarantine",
        affected_file_count=2,
        destination=frame_queue_dir / "legacy" / "20260628T170000Z",
    )
    assert action.destination is not None
    assert sorted(path.name for path in action.destination.glob("*.jpg")) == [
        "frame_a.jpg",
        "frame_b.jpg",
    ]
    assert sorted(path.name for path in frame_queue_dir.glob("*.jpg")) == []


def test_given_missing_confirm_flag_when_delete_legacy_then_raises(tmp_path) -> None:
    # Arrange
    frame_queue_dir = tmp_path / "frames"
    frame_queue_dir.mkdir(parents=True)
    (frame_queue_dir / "frame_a.jpg").write_bytes(b"a")

    # Act & Assert
    with pytest.raises(ValueError, match="confirm_delete"):
        delete_legacy_backlog(frame_queue_dir)


def test_given_confirmed_delete_when_delete_legacy_then_removes_only_top_level_jpg(
    tmp_path,
) -> None:
    # Arrange
    frame_queue_dir = tmp_path / "frames"
    frame_queue_dir.mkdir(parents=True)
    (frame_queue_dir / "delete_me.jpg").write_bytes(b"a")
    (frame_queue_dir / "keep.txt").write_text("keep", encoding="utf-8")
    nested_dir = frame_queue_dir / "legacy" / "20260628T170000Z"
    nested_dir.mkdir(parents=True)
    (nested_dir / "nested.jpg").write_bytes(b"nested")

    # Act
    action = delete_legacy_backlog(frame_queue_dir, confirm_delete=True)

    # Assert
    assert action == LegacyBacklogAction(action="delete", affected_file_count=1, destination=None)
    assert (frame_queue_dir / "delete_me.jpg").exists() is False
    assert (frame_queue_dir / "keep.txt").exists() is True
    assert (nested_dir / "nested.jpg").exists() is True
