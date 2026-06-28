"""Frame storage tests."""

from datetime import UTC, datetime
from io import BytesIO

import pytest
from fastapi import UploadFile

from piwatcher_base.storage import store_frames


@pytest.mark.asyncio()
async def test_given_uploaded_frames_when_store_frames_then_writes_date_hierarchy(tmp_path) -> None:
    # Arrange
    frame = UploadFile(filename="frame.jpg", file=BytesIO(b"jpeg"))
    event_start = datetime(2026, 6, 27, 14, 32, 1, tzinfo=UTC)

    # Act
    paths = await store_frames([frame], "feeder-cam", event_start, tmp_path)

    # Assert
    assert paths == [tmp_path / "2026/06/27/feeder-cam/143201/frame_0000.jpg"]
    assert paths[0].read_bytes() == b"jpeg"
